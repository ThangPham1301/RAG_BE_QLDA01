import logging
from django.db import models
from rest_framework import viewsets, status, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
from django.utils import timezone
from .models import Document
from .serializers import DocumentSerializer, DocumentUploadSerializer
from apps.teams.permissions import accessible_documents_for_user, user_can_access_document
from apps.teams.serializers import CreateDocumentShareSerializer, DocumentShareSerializer
from apps.realtime.events import send_document_status, send_to_user

logger = logging.getLogger(__name__)


class DocumentViewSet(viewsets.ModelViewSet):
    serializer_class = DocumentSerializer
    permission_classes = [permissions.IsAuthenticated]
    parser_classes = (JSONParser, MultiPartParser, FormParser)
    filterset_fields = ['chat_session_id', 'file_type', 'index_status']

    def get_queryset(self):
        user = self.request.user
        queryset = accessible_documents_for_user(user).select_related(
            'chat_session', 'chat_session__project', 'uploaded_by'
        ).order_by('-uploaded_at')

        chat_session_id = self.request.query_params.get('chat_session_id')
        if chat_session_id:
            from apps.teams.models import ChatDocumentAttachment
            attached_ids = ChatDocumentAttachment.objects.filter(chat_session_id=chat_session_id).values_list('document_id', flat=True)
            queryset = queryset.filter(models.Q(chat_session_id=chat_session_id) | models.Q(id__in=attached_ids))

        return queryset

    def list(self, request, *args, **kwargs):
        if not request.query_params.get('chat_session_id'):
            return Response({'error': 'chat_session_id is required'}, status=status.HTTP_400_BAD_REQUEST)
        return super().list(request, *args, **kwargs)

    def create(self, request, *args, **kwargs):
        """Handle document upload (single or multiple)"""
        files = request.FILES.getlist('files')
        chat_session_id = request.data.get('chat_session_id')

        if not chat_session_id:
            return Response(
                {'error': 'chat_session_id is required'},
                status=status.HTTP_400_BAD_REQUEST
            )

        documents = []
        errors = []
        
        file_list = files if files else [request.FILES.get('file')]
        file_list = [f for f in file_list if f]

        for file_obj in file_list:
            try:
                data = {
                    'chat_session_id': chat_session_id,
                    'title': request.data.get('title', ''),
                    'file': file_obj,
                }
                serializer = DocumentUploadSerializer(data=data, context={'request': request})
                if serializer.is_valid():
                    doc = serializer.save()
                    self._schedule_indexing(doc)
                    documents.append(doc)
                else:
                    errors.append(f"{file_obj.name}: {serializer.errors}")
            except Exception as e:
                logger.error(f"Error uploading {file_obj.name}: {e}", exc_info=True)
                errors.append(f"{file_obj.name}: {str(e)}")

        if not documents and errors:
            return Response(
                {'errors': errors},
                status=status.HTTP_400_BAD_REQUEST
            )

        output = DocumentSerializer(documents, many=True, context={'request': request})
        response_data = {
            'documents': output.data,
            'uploaded_count': len(documents)
        }
        if errors:
            response_data['errors'] = errors

        return Response(response_data, status=status.HTTP_201_CREATED)

    def _schedule_indexing(self, document):
        """Index document after upload"""
        try:
            document.index_status = Document.IndexStatus.INDEXING
            document.save(update_fields=['index_status'])
            send_document_status(document, Document.IndexStatus.INDEXING)
            
            # Import here to avoid circular imports
            from .services import populate_document_extracted_text, index_document_to_chroma
            
            logger.info(f'[_schedule_indexing] Starting extraction for doc_id={document.id}')
            populate_document_extracted_text(document)
            
            logger.info(f'[_schedule_indexing] Starting Chroma indexing for doc_id={document.id}')
            indexed_chunks = index_document_to_chroma(document)
            
            document.index_status = Document.IndexStatus.INDEXED
            document.indexed_chunks = indexed_chunks
            document.indexed_at = timezone.now()
            document.save(update_fields=['index_status', 'indexed_chunks', 'indexed_at'])
            send_document_status(document, Document.IndexStatus.INDEXED)
            logger.info(f'[_schedule_indexing] Completed successfully for doc_id={document.id}, chunks={indexed_chunks}')
            
        except Exception as e:
            logger.error(f"[_schedule_indexing] Indexing failed for doc_id={document.id}: {e}", exc_info=True)
            document.index_status = Document.IndexStatus.FAILED
            document.index_error = str(e)[:500]  # Truncate to 500 chars
            document.save(update_fields=['index_status', 'index_error'])
            send_document_status(document, Document.IndexStatus.FAILED)
            logger.error(f"[_schedule_indexing] Document marked as FAILED with error: {document.index_error}")

    @action(detail=True, methods=['post'])
    def reindex(self, request, pk=None):
        """Re-index a document"""
        doc = self.get_object()
        self._schedule_indexing(doc)
        doc.refresh_from_db()
        serializer = self.get_serializer(doc)
        return Response(serializer.data)

    @action(detail=True, methods=['post'])
    def restore(self, request, pk=None):
        """Restore a soft-deleted document"""
        doc = self.get_object()
        if not doc.is_deleted:
            return Response(
                {'error': 'Document is not deleted'},
                status=status.HTTP_400_BAD_REQUEST
            )
        doc.is_deleted = False
        doc.deleted_at = None
        doc.save()
        serializer = self.get_serializer(doc)
        return Response(serializer.data)

    def destroy(self, request, *args, **kwargs):
        """Soft delete document"""
        doc = self.get_object()
        if doc.team_links.exists():
            return Response(
                {'error': 'Team documents cannot be deleted from the document endpoint. Remove them from a chat instead.'},
                status=status.HTTP_403_FORBIDDEN,
            )
        if doc.chat_session.user_id != request.user.id and doc.uploaded_by_id != request.user.id and not request.user.is_staff:
            return Response({'error': 'You do not have permission to delete this document.'}, status=status.HTTP_403_FORBIDDEN)
        doc.is_deleted = True
        doc.deleted_at = timezone.now()
        doc.save()
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=False, methods=['post'], url_path='bulk-delete')
    def bulk_delete(self, request):
        document_ids = request.data.get('document_ids') or []
        if not isinstance(document_ids, list) or not document_ids:
            return Response({'document_ids': 'At least one document id is required.'}, status=status.HTTP_400_BAD_REQUEST)

        deleted = []
        skipped = []
        for doc in Document.objects.filter(id__in=document_ids, is_deleted=False).select_related('chat_session'):
            can_delete = (
                request.user.is_staff
                or doc.uploaded_by_id == request.user.id
                or doc.chat_session.user_id == request.user.id
            )
            if doc.team_links.exists() or not can_delete:
                skipped.append(doc.id)
                continue
            doc.is_deleted = True
            doc.deleted_at = timezone.now()
            doc.save(update_fields=['is_deleted', 'deleted_at', 'updated_at'])
            deleted.append(doc.id)

        missing = [doc_id for doc_id in document_ids if doc_id not in deleted and doc_id not in skipped]
        return Response({'deleted': deleted, 'skipped': skipped, 'missing': missing})

    @action(detail=False, methods=['post'], url_path='bulk-share')
    def bulk_share(self, request):
        document_ids = request.data.get('document_ids') or []
        email = request.data.get('email', '')
        if not isinstance(document_ids, list) or not document_ids:
            return Response({'document_ids': 'At least one document id is required.'}, status=status.HTTP_400_BAD_REQUEST)
        if not email:
            return Response({'email': 'This field is required.'}, status=status.HTTP_400_BAD_REQUEST)

        shared = []
        skipped = []
        errors = {}
        for doc in Document.objects.filter(id__in=document_ids, is_deleted=False).select_related('chat_session'):
            serializer = CreateDocumentShareSerializer(
                data={'email': email},
                context={'request': request, 'document': doc},
            )
            if not serializer.is_valid():
                errors[str(doc.id)] = serializer.errors
                skipped.append(doc.id)
                continue
            share = serializer.save()
            send_to_user(share.shared_with_id, 'document.shared', {
                'document_id': doc.id,
                'title': doc.title,
                'share_id': share.id,
                'shared_by': request.user.email,
            })
            shared.append(doc.id)

        missing = [doc_id for doc_id in document_ids if doc_id not in shared and doc_id not in skipped]
        return Response({'shared': shared, 'skipped': skipped, 'missing': missing, 'errors': errors})

    @action(detail=True, methods=['get'], url_path='preview', permission_classes=[permissions.AllowAny])
    def preview(self, request, pk=None):
        """Serve the raw file for inline preview (PDF, DOCX, TXT).
        Supports JWT via ?token= query param so iframes can load the file."""
        import mimetypes
        from django.http import FileResponse, Http404
        from django.contrib.auth import get_user_model
        import os

        # --- Auth: try Authorization header first, then ?token= query param ---
        user = request.user
        if not user or not user.is_authenticated:
            token_str = request.query_params.get('token', '')
            if token_str:
                try:
                    jwt_auth = JWTAuthentication()
                    validated = jwt_auth.get_validated_token(token_str.encode())
                    user = jwt_auth.get_user(validated)
                except (InvalidToken, TokenError, Exception):
                    from django.http import HttpResponseForbidden
                    return HttpResponseForbidden('Invalid or expired token.')
            else:
                from django.http import HttpResponseForbidden
                return HttpResponseForbidden('Authentication required.')

        # --- Fetch document (scoped to user unless admin) ---
        try:
            doc = Document.objects.get(pk=pk, is_deleted=False)
            if not user_can_access_document(user, doc):
                from django.http import HttpResponseForbidden
                return HttpResponseForbidden('You do not have access to this document.')
        except Document.DoesNotExist:
            raise Http404('Document not found.')

        if not doc.file:
            raise Http404('No file attached to this document.')

        try:
            file_path = doc.file.path
        except Exception:
            raise Http404('File path unavailable.')

        if not os.path.exists(file_path):
            raise Http404('File not found on disk.')

        mime_type, _ = mimetypes.guess_type(file_path)
        if not mime_type:
            mime_type = 'application/octet-stream'

        file_handle = open(file_path, 'rb')
        response = FileResponse(file_handle, content_type=mime_type)
        response['Content-Disposition'] = f'inline; filename="{os.path.basename(file_path)}"'
        response['X-Frame-Options'] = 'ALLOWALL'
        response['Access-Control-Allow-Origin'] = request.headers.get('Origin', '*')
        response['Access-Control-Allow-Credentials'] = 'true'
        return response

    @action(detail=True, methods=['get'], url_path='text')
    def get_text(self, request, pk=None):
        """Return the full extracted text of a document for preview.
        Bypasses per-user queryset filter so system-wide Library can access any doc."""
        doc = Document.objects.filter(pk=pk, is_deleted=False).first()
        if not doc or not user_can_access_document(request.user, doc):
            return Response({'detail': 'Document not found.'}, status=status.HTTP_404_NOT_FOUND)
        return Response({
            'document_id': doc.id,
            'title': doc.title,
            'file_type': doc.file_type,
            'extracted_text': doc.extracted_text or '',
            'index_status': doc.index_status,
            'indexed_chunks': doc.indexed_chunks,
        })

    @action(detail=True, methods=['get'], url_path='fields')
    def fields(self, request, pk=None):
        """Return extracted administrative fields for debugging and UI display."""
        doc = self.get_object()
        return Response({
            'document_id': doc.id,
            'title': doc.title,
            'extracted_fields': doc.extracted_fields or {},
        })

    @action(detail=True, methods=['get'], url_path='ocr-layout')
    def ocr_layout(self, request, pk=None):
        """Return OCR layout lines with coordinates."""
        doc = self.get_object()
        return Response({
            'document_id': doc.id,
            'title': doc.title,
            'ocr_layout': doc.ocr_layout or {},
        })

    @action(detail=True, methods=['post'], url_path='reextract-fields')
    def reextract_fields(self, request, pk=None):
        """Re-run administrative field extraction from saved OCR layout/text."""
        doc = self.get_object()
        from .admin_doc_extractor import extract_administrative_fields

        doc.extracted_fields = extract_administrative_fields(
            doc.ocr_layout or {},
            plain_text=doc.extracted_text or '',
        )
        doc.save(update_fields=['extracted_fields'])
        return Response({
            'document_id': doc.id,
            'title': doc.title,
            'extracted_fields': doc.extracted_fields,
        })

    @action(detail=True, methods=['post'])
    def share(self, request, pk=None):
        doc = self.get_object()
        serializer = CreateDocumentShareSerializer(data=request.data, context={'request': request, 'document': doc})
        serializer.is_valid(raise_exception=True)
        share = serializer.save()
        send_to_user(share.shared_with_id, 'document.shared', {
            'document_id': doc.id,
            'title': doc.title,
            'share_id': share.id,
            'shared_by': request.user.email,
        })
        return Response(DocumentShareSerializer(share).data, status=status.HTTP_201_CREATED)
