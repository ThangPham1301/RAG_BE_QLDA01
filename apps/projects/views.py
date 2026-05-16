import csv
from datetime import timedelta

from django.db.models import Count, Q, Sum, Prefetch
from django.db.models.functions import TruncDate, TruncMonth, TruncYear
from django.http import HttpResponse
from django.utils import timezone
from rest_framework import viewsets, status, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.parsers import JSONParser, MultiPartParser, FormParser

from .models import Project
from .serializers import ProjectSerializer


class ProjectViewSet(viewsets.ModelViewSet):
    serializer_class = ProjectSerializer
    permission_classes = [permissions.IsAuthenticated]
    parser_classes = (JSONParser, MultiPartParser, FormParser)

    def get_queryset(self):
        return Project.objects.filter(owner=self.request.user).order_by('-created_at')

    def perform_create(self, serializer):
        serializer.save(owner=self.request.user)

    def _parse_time_window(self, request):
        group_by = request.query_params.get('group_by', 'day').lower()
        if group_by not in {'day', 'month', 'year'}:
            return None, Response(
                {'error': 'group_by must be one of: day, month, year'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        default_window = {'day': 30, 'month': 12, 'year': 5}[group_by]
        try:
            window = int(request.query_params.get('window', default_window))
        except ValueError:
            return None, Response(
                {'error': 'window must be an integer'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if window < 1:
            return None, Response(
                {'error': 'window must be greater than 0'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        now = timezone.now()
        if group_by == 'day':
            start_at = now - timedelta(days=window - 1)
            trunc_fn = TruncDate
            label_format = '%Y-%m-%d'
        elif group_by == 'month':
            start_at = now - timedelta(days=(window * 31))
            trunc_fn = TruncMonth
            label_format = '%Y-%m'
        else:
            start_at = now - timedelta(days=(window * 366))
            trunc_fn = TruncYear
            label_format = '%Y'

        return {
            'group_by': group_by,
            'window': window,
            'start_at': start_at,
            'end_at': now,
            'trunc_fn': trunc_fn,
            'label_format': label_format,
        }, None

    def _period_keys(self, start_at, end_at, group_by):
        keys = []
        current = timezone.localtime(start_at)
        end_local = timezone.localtime(end_at)

        if group_by == 'day':
            current = current.replace(hour=0, minute=0, second=0, microsecond=0)
            end_cursor = end_local.replace(hour=0, minute=0, second=0, microsecond=0)
            while current <= end_cursor:
                keys.append(current.date())
                current = current + timedelta(days=1)
            return keys

        if group_by == 'month':
            current = current.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            end_cursor = end_local.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            while current <= end_cursor:
                keys.append(current.date())
                if current.month == 12:
                    current = current.replace(year=current.year + 1, month=1)
                else:
                    current = current.replace(month=current.month + 1)
            return keys

        current = current.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
        end_cursor = end_local.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
        while current <= end_cursor:
            keys.append(current.date())
            current = current.replace(year=current.year + 1)
        return keys

    def _series_map(self, queryset, trunc_fn):
        series = {}
        for row in (
            queryset
            .annotate(period=trunc_fn('created_at'))
            .values('period')
            .annotate(total=Count('id'))
            .order_by('period')
        ):
            period_value = row['period']
            if hasattr(period_value, 'date'):
                period_value = period_value.date()
            series[period_value] = row['total']
        return series

    def _build_library_tree(self, projects_qs, request):
        from apps.chatbot.models import ChatSession
        from apps.documents.models import Document

        chat_qs = ChatSession.objects.filter(is_deleted=False).order_by('-updated_at')
        if not request.user.is_staff:
            chat_qs = chat_qs.filter(user=request.user)

        doc_qs = Document.objects.filter(is_deleted=False).order_by('-uploaded_at')
        project_list = projects_qs.prefetch_related(
            Prefetch('chat_sessions', queryset=chat_qs.prefetch_related(Prefetch('documents', queryset=doc_qs)))
        )

        tree = []
        for project in project_list:
            project_documents_count = 0
            chat_items = []

            for chat in project.chat_sessions.all():
                documents = []
                for doc in chat.documents.all():
                    documents.append({
                        'document_id': doc.id,
                        'title': doc.title,
                        'file_type': doc.file_type,
                        'index_status': doc.index_status,
                        'indexed_chunks': doc.indexed_chunks,
                        'uploaded_at': doc.uploaded_at.isoformat(),
                    })

                documents_count = len(documents)
                project_documents_count += documents_count
                chat_items.append({
                    'chat_session_id': chat.id,
                    'chat_session_title': chat.title,
                    'documents_count': documents_count,
                    'documents': documents,
                })

            tree.append({
                'project_id': project.id,
                'project_name': project.name,
                'chat_sessions_count': len(chat_items),
                'documents_count': project_documents_count,
                'chat_sessions': chat_items,
            })

        return tree

    def _build_statistics_payload(self, request):
        from apps.auth.models import User, AuthSession
        from apps.chatbot.models import ChatSession, ChatMessage
        from apps.documents.models import Document

        time_window, error_response = self._parse_time_window(request)
        if error_response:
            return None, error_response

        scope = request.query_params.get('scope', 'mine').lower()
        allow_system_scope = request.user.is_staff
        use_system_scope = scope == 'system' and allow_system_scope

        if use_system_scope:
            projects_qs = Project.objects.all()
            users_qs = User.objects.all()
            visits_qs = AuthSession.objects.all()
            chats_qs = ChatSession.objects.filter(is_deleted=False)
            documents_qs = Document.objects.filter(is_deleted=False).select_related('chat_session', 'chat_session__project')
        else:
            projects_qs = self.get_queryset()
            users_qs = User.objects.filter(id=request.user.id)
            visits_qs = AuthSession.objects.filter(user=request.user)
            chats_qs = ChatSession.objects.filter(project__in=projects_qs, user=request.user, is_deleted=False)
            documents_qs = Document.objects.filter(
                chat_session__project__in=projects_qs,
                is_deleted=False,
            ).select_related('chat_session', 'chat_session__project')

        user_queries_qs = ChatMessage.objects.filter(
            chat_session__in=chats_qs,
            role=ChatMessage.Role.USER,
        )

        filtered_users_qs = users_qs.filter(
            created_at__gte=time_window['start_at'],
            created_at__lte=time_window['end_at'],
        )
        filtered_visits_qs = visits_qs.filter(
            created_at__gte=time_window['start_at'],
            created_at__lte=time_window['end_at'],
        )
        filtered_queries_qs = user_queries_qs.filter(
            created_at__gte=time_window['start_at'],
            created_at__lte=time_window['end_at'],
        )

        users_series = self._series_map(filtered_users_qs, time_window['trunc_fn'])
        visits_series = self._series_map(filtered_visits_qs, time_window['trunc_fn'])
        queries_series = self._series_map(filtered_queries_qs, time_window['trunc_fn'])

        periods = self._period_keys(time_window['start_at'], time_window['end_at'], time_window['group_by'])
        chart_rows = []
        for period_key in periods:
            chart_rows.append({
                'period': period_key.strftime(time_window['label_format']),
                'users': users_series.get(period_key, 0),
                'visits': visits_series.get(period_key, 0),
                'queries': queries_series.get(period_key, 0),
            })

        counts = documents_qs.aggregate(
            total_documents=Count('id'),
            indexed_documents=Count('id', filter=Q(index_status=Document.IndexStatus.INDEXED)),
            indexing_documents=Count('id', filter=Q(index_status=Document.IndexStatus.INDEXING)),
            failed_documents=Count('id', filter=Q(index_status=Document.IndexStatus.FAILED)),
            total_indexed_chunks=Sum('indexed_chunks'),
        )

        recent_uploads = []
        for doc in documents_qs.order_by('-uploaded_at')[:8]:
            recent_uploads.append({
                'document_id': doc.id,
                'title': doc.title,
                'project_id': doc.chat_session.project_id,
                'project_name': doc.chat_session.project.name,
                'chat_session_id': doc.chat_session_id,
                'chat_session_title': doc.chat_session.title if doc.chat_session else None,
                'index_status': doc.index_status,
                'uploaded_at': doc.uploaded_at.isoformat(),
            })

        payload = {
            'scope': 'system' if use_system_scope else 'mine',
            'time_filter': {
                'group_by': time_window['group_by'],
                'window': time_window['window'],
                'start_at': time_window['start_at'].isoformat(),
                'end_at': time_window['end_at'].isoformat(),
            },
            'summary': {
                'users': filtered_users_qs.count(),
                'visits': filtered_visits_qs.count(),
                'queries': filtered_queries_qs.count(),
                'projects': projects_qs.count(),
                'total_documents': counts['total_documents'] or 0,
                'indexed_documents': counts['indexed_documents'] or 0,
                'indexing_documents': counts['indexing_documents'] or 0,
                'failed_documents': counts['failed_documents'] or 0,
                'total_indexed_chunks': counts['total_indexed_chunks'] or 0,
                'active_chat_sessions': chats_qs.filter(is_archived=False).count(),
            },
            'charts': {
                'columns': ['period', 'users', 'visits', 'queries'],
                'bar': chart_rows,
                'line': chart_rows,
            },
            'library': {
                'projects': self._build_library_tree(projects_qs, request),
            },
            'recent_uploads': recent_uploads,
            # Legacy fields kept for backward compatibility with older clients.
            'total_projects': projects_qs.count(),
            'total_documents': counts['total_documents'] or 0,
            'indexed_documents': counts['indexed_documents'] or 0,
            'indexing_documents': counts['indexing_documents'] or 0,
            'failed_documents': counts['failed_documents'] or 0,
            'total_indexed_chunks': counts['total_indexed_chunks'] or 0,
            'active_chat_sessions': chats_qs.filter(is_archived=False).count(),
        }
        return payload, None

    @action(detail=True, methods=['get'])
    def documents(self, request, pk=None):
        """Get all documents in this project"""
        project = self.get_object()
        from apps.documents.models import Document
        docs = Document.objects.filter(chat_session__project=project, is_deleted=False).select_related('chat_session', 'chat_session__project')
        from apps.documents.serializers import DocumentSerializer
        serializer = DocumentSerializer(docs, many=True, context={'request': request})
        return Response(serializer.data)

    @action(detail=True, methods=['get'])
    def chats(self, request, pk=None):
        """Get all chat sessions in this project"""
        project = self.get_object()
        from apps.chatbot.models import ChatSession
        chats = ChatSession.objects.filter(project=project, user=request.user, is_deleted=False).order_by('-updated_at')
        from apps.chatbot.serializers import ChatSessionSerializer
        serializer = ChatSessionSerializer(chats, many=True, context={'request': request})
        return Response(serializer.data)

    @action(detail=False, methods=['get'])
    def statistics(self, request):
        """Dashboard + statistics data with real metrics and time-series."""
        payload, error_response = self._build_statistics_payload(request)
        if error_response:
            return error_response
        return Response(payload)

    @action(detail=False, methods=['get'], url_path='statistics-export')
    def statistics_export(self, request):
        """Export statistics report as CSV or JSON."""
        payload, error_response = self._build_statistics_payload(request)
        if error_response:
            return error_response

        export_format = request.query_params.get('format', 'csv').lower()
        if export_format == 'json':
            return Response(payload)

        if export_format != 'csv':
            return Response(
                {'error': 'format must be csv or json'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="statistics_report.csv"'

        writer = csv.writer(response)
        writer.writerow(['scope', payload['scope']])
        writer.writerow(['group_by', payload['time_filter']['group_by']])
        writer.writerow(['window', payload['time_filter']['window']])
        writer.writerow(['start_at', payload['time_filter']['start_at']])
        writer.writerow(['end_at', payload['time_filter']['end_at']])
        writer.writerow([])

        writer.writerow(['summary_metric', 'value'])
        for key, value in payload['summary'].items():
            writer.writerow([key, value])
        writer.writerow([])

        writer.writerow(payload['charts']['columns'])
        for row in payload['charts']['line']:
            writer.writerow([row['period'], row['users'], row['visits'], row['queries']])
        writer.writerow([])

        writer.writerow([
            'project_id',
            'project_name',
            'chat_session_id',
            'chat_session_title',
            'document_id',
            'document_title',
            'file_type',
            'index_status',
            'indexed_chunks',
            'uploaded_at',
        ])
        for project_item in payload['library']['projects']:
            for chat_item in project_item['chat_sessions']:
                for doc_item in chat_item['documents']:
                    writer.writerow([
                        project_item['project_id'],
                        project_item['project_name'],
                        chat_item['chat_session_id'],
                        chat_item['chat_session_title'],
                        doc_item['document_id'],
                        doc_item['title'],
                        doc_item['file_type'],
                        doc_item['index_status'],
                        doc_item['indexed_chunks'],
                        doc_item['uploaded_at'],
                    ])

        return response
