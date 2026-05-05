import logging
from django.db import models
from rest_framework import viewsets, status, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.parsers import FormParser, MultiPartParser
from django.utils import timezone
from .models import Document
from .serializers import DocumentSerializer, DocumentUploadSerializer

logger = logging.getLogger(__name__)


class DocumentViewSet(viewsets.ModelViewSet):
    serializer_class = DocumentSerializer
    permission_classes = [permissions.IsAuthenticated]
    parser_classes = (MultiPartParser, FormParser)
    filterset_fields = ['project', 'file_type', 'index_status']

    def get_queryset(self):
        user = self.request.user
        # Users can only see documents they uploaded, or in projects they own
        from apps.projects.models import Project
        user_projects = Project.objects.filter(owner=user).values_list('id', flat=True)
        queryset = Document.objects.filter(
            models.Q(uploaded_by=user) | models.Q(project_id__in=user_projects),
            is_deleted=False
        ).order_by('-uploaded_at')

        project_id = self.request.query_params.get('project')
        if project_id:
            queryset = queryset.filter(project_id=project_id)

        return queryset

    def create(self, request, *args, **kwargs):
        """Handle document upload (single or multiple)"""
        files = request.FILES.getlist('files')
        project_id = request.data.get('project')
        
        if not project_id:
            return Response(
                {'error': 'project is required'},
                status=status.HTTP_400_BAD_REQUEST
            )

        documents = []
        errors = []
        
        file_list = files if files else [request.FILES.get('file')]
        file_list = [f for f in file_list if f]

        for file_obj in file_list:
            try:
                data = {
                    'project': project_id,
                    'title': request.data.get('title', ''),
                    'file': file_obj
                }
                serializer = DocumentUploadSerializer(data=data, context={'request': request})
                if serializer.is_valid():
                    doc = serializer.save(uploaded_by=request.user)
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
            
            # Import here to avoid circular imports
            from .services import populate_document_extracted_text, index_document_to_chroma
            
            populate_document_extracted_text(document)
            indexed_chunks = index_document_to_chroma(document)
            
            document.index_status = Document.IndexStatus.INDEXED
            document.indexed_chunks = indexed_chunks
            document.indexed_at = timezone.now()
            document.save(update_fields=['index_status', 'indexed_chunks', 'indexed_at'])
            
        except Exception as e:
            logger.error(f"Indexing failed for {document.id}: {e}", exc_info=True)
            document.index_status = Document.IndexStatus.FAILED
            document.index_error = str(e)
            document.save(update_fields=['index_status', 'index_error'])

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
        doc.is_deleted = True
        doc.deleted_at = timezone.now()
        doc.save()
        return Response(status=status.HTTP_204_NO_CONTENT)
