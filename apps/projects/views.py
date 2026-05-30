import csv
from io import StringIO
from datetime import timedelta

from django.db.models import Count, Q, Sum, Prefetch
from django.db.models.functions import TruncDate, TruncMonth, TruncYear
from django.http import HttpResponse
from django.utils import timezone
from django.views.decorators.http import require_GET
from rest_framework import viewsets, status, permissions
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.parsers import JSONParser, MultiPartParser, FormParser
from apps.auth.jwt import TokenVersionJWTAuthentication

from .models import Project
from .serializers import ProjectSerializer


def _user_is_admin(user):
    return bool(user and user.is_authenticated and (user.is_staff or user.is_superuser))


def _admin_required_response():
    return Response({'detail': 'Admin role is required.'}, status=status.HTTP_403_FORBIDDEN)


class ProjectViewSet(viewsets.ModelViewSet):
    serializer_class = ProjectSerializer
    permission_classes = [permissions.IsAuthenticated]
    parser_classes = (JSONParser, MultiPartParser, FormParser)

    def get_queryset(self):
        return Project.objects.filter(owner=self.request.user).exclude(name__startswith='Team Workspace - ').order_by('-created_at')

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

    def _series_map(self, queryset, trunc_fn, date_field='created_at'):
        series = {}
        for row in (
            queryset
            .annotate(period=trunc_fn(date_field))
            .values('period')
            .annotate(total=Count('id'))
            .order_by('period')
        ):
            period_value = row['period']
            if hasattr(period_value, 'date'):
                period_value = period_value.date()
            series[period_value] = row['total']
        return series

    def _build_library_tree(self, projects_qs, request, use_system_scope=True):
        from apps.chatbot.models import ChatSession
        from apps.documents.models import Document

        chat_qs = ChatSession.objects.filter(is_deleted=False).order_by('-updated_at')
        if not use_system_scope:
            # In 'mine' scope, only show the requesting user's chat sessions
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
                    doc_file_url = ''
                    if doc.file:
                        try:
                            doc_file_url = request.build_absolute_uri(doc.file.url)
                        except Exception:
                            pass
                    documents.append({
                        'document_id': doc.id,
                        'title': doc.title,
                        'file_type': doc.file_type,
                        'index_status': doc.index_status,
                        'indexed_chunks': doc.indexed_chunks,
                        'uploaded_at': doc.uploaded_at.isoformat(),
                        'file_url': doc_file_url,
                        'extracted_text_preview': (doc.extracted_text or '')[:8000],
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

        # Dashboard statistics always uses system-wide scope.
        # (Authorization/role-based filtering can be added later when needed.)
        scope = request.query_params.get('scope', 'system').lower()
        use_system_scope = scope != 'mine'

        if use_system_scope:
            projects_qs = Project.objects.all()
            users_qs = User.objects.all()
            visits_qs = AuthSession.objects.all()
            chats_qs = ChatSession.objects.filter(is_deleted=False)
            documents_qs = Document.objects.filter(is_deleted=False).select_related('chat_session', 'chat_session__project')
        else:
            # 'mine' scope: only data belonging to the requesting user
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

        filtered_uploads_qs = documents_qs.filter(
            uploaded_at__gte=time_window['start_at'],
            uploaded_at__lte=time_window['end_at'],
        )

        users_series = self._series_map(filtered_users_qs, time_window['trunc_fn'])
        visits_series = self._series_map(filtered_visits_qs, time_window['trunc_fn'])
        queries_series = self._series_map(filtered_queries_qs, time_window['trunc_fn'])
        uploads_series = self._series_map(filtered_uploads_qs, time_window['trunc_fn'], date_field='uploaded_at')

        periods = self._period_keys(time_window['start_at'], time_window['end_at'], time_window['group_by'])
        chart_rows = []
        for period_key in periods:
            chart_rows.append({
                'period': period_key.strftime(time_window['label_format']),
                'users': users_series.get(period_key, 0),
                'visits': visits_series.get(period_key, 0),
                'queries': queries_series.get(period_key, 0),
                'uploads': uploads_series.get(period_key, 0),
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
                'columns': ['period', 'users', 'visits', 'queries', 'uploads'],
                'bar': chart_rows,
                'line': chart_rows,
            },
            'library': {
                'projects': self._build_library_tree(projects_qs, request, use_system_scope=use_system_scope),
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
        if not _user_is_admin(request.user):
            return _admin_required_response()
        payload, error_response = self._build_statistics_payload(request)
        if error_response:
            return error_response
        return Response(payload)

    @action(detail=False, methods=['get'], url_path='statistics/export')
    def statistics_export_stable(self, request):
        """Export statistics through the ProjectViewSet router."""
        if not _user_is_admin(request.user):
            return _admin_required_response()
        return build_statistics_export_response(request)

    @action(detail=False, methods=['get'], url_path='statistics-export')
    def statistics_export(self, request):
        """Export statistics report as CSV, Excel-compatible HTML, PDF, or JSON."""
        if not _user_is_admin(request.user):
            return _admin_required_response()
        export_format = request.query_params.get('format', 'csv').lower()
        if export_format not in {'csv', 'xls', 'excel', 'pdf'}:
            return Response(
                {'error': 'format must be csv, xls, excel, or pdf'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            payload, error_response = self._build_statistics_payload(request)
            if error_response:
                return error_response
        except Exception as exc:
            payload = self._empty_statistics_payload(error=str(exc))

        writer_buffer = StringIO()
        writer = csv.writer(writer_buffer)
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

        chart_columns = payload.get('charts', {}).get('columns') or ['period', 'users', 'visits', 'queries', 'uploads']
        writer.writerow(chart_columns)
        for row in payload.get('charts', {}).get('line', []):
            writer.writerow([
                row.get('period', ''),
                row.get('users', 0),
                row.get('visits', 0),
                row.get('queries', 0),
                row.get('uploads', 0),
            ])
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
        for project_item in payload.get('library', {}).get('projects', []):
            for chat_item in project_item.get('chat_sessions', []):
                for doc_item in chat_item.get('documents', []):
                    writer.writerow([
                        project_item.get('project_id', ''),
                        project_item.get('project_name', ''),
                        chat_item.get('chat_session_id', ''),
                        chat_item.get('chat_session_title', ''),
                        doc_item.get('document_id', ''),
                        doc_item.get('title', ''),
                        doc_item.get('file_type', ''),
                        doc_item.get('index_status', ''),
                        doc_item.get('indexed_chunks', 0),
                        doc_item.get('uploaded_at', ''),
                    ])

        csv_text = writer_buffer.getvalue()

        if export_format == 'csv':
            response = HttpResponse(csv_text, content_type='text/csv; charset=utf-8')
            response['Content-Disposition'] = 'attachment; filename="statistics_report.csv"'
            return response

        if export_format in {'xls', 'excel'}:
            html_rows = []
            for line in csv_text.splitlines():
                cells = ''.join(f'<td>{cell}</td>' for cell in next(csv.reader([line])))
                html_rows.append(f'<tr>{cells}</tr>')
            html = '<html><head><meta charset="utf-8"></head><body><table>' + ''.join(html_rows) + '</table></body></html>'
            response = HttpResponse(html, content_type='application/vnd.ms-excel; charset=utf-8')
            response['Content-Disposition'] = 'attachment; filename="statistics_report.xls"'
            return response

        pdf_bytes = self._build_simple_pdf(csv_text)
        response = HttpResponse(pdf_bytes, content_type='application/pdf')
        response['Content-Disposition'] = 'attachment; filename="statistics_report.pdf"'
        return response

    def _empty_statistics_payload(self, error=''):
        now = timezone.now()
        return {
            'scope': 'system',
            'time_filter': {
                'group_by': 'day',
                'window': 0,
                'start_at': now.isoformat(),
                'end_at': now.isoformat(),
            },
            'summary': {
                'users': 0,
                'visits': 0,
                'queries': 0,
                'projects': 0,
                'total_documents': 0,
                'indexed_documents': 0,
                'indexing_documents': 0,
                'failed_documents': 0,
                'total_indexed_chunks': 0,
                'active_chat_sessions': 0,
                'export_error': error[:300],
            },
            'charts': {
                'columns': ['period', 'users', 'visits', 'queries', 'uploads'],
                'line': [],
            },
            'library': {'projects': []},
        }

    def _build_simple_pdf(self, text):
        """Build a dependency-free, single-font PDF for export smoke reliability."""
        def esc(value):
            return value.replace('\\', '\\\\').replace('(', '\\(').replace(')', '\\)')

        lines = ['Statistics Report'] + text.splitlines()
        page_chunks = [lines[i:i + 42] for i in range(0, len(lines), 42)] or [['Statistics Report']]
        objects = []
        pages = []

        objects.append('<< /Type /Catalog /Pages 2 0 R >>')
        objects.append('')  # pages placeholder
        objects.append('<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>')

        for chunk in page_chunks:
            content_lines = ['BT', '/F1 9 Tf', '50 790 Td', '14 TL']
            for index, line in enumerate(chunk):
                if index:
                    content_lines.append('T*')
                content_lines.append(f'({esc(line[:110])}) Tj')
            content_lines.append('ET')
            content = '\n'.join(content_lines)
            content_obj_id = len(objects) + 2
            page_obj_id = len(objects) + 1
            objects.append(
                f'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] '
                f'/Resources << /Font << /F1 3 0 R >> >> /Contents {content_obj_id} 0 R >>'
            )
            objects.append(f'<< /Length {len(content.encode("latin-1", errors="replace"))} >>\nstream\n{content}\nendstream')
            pages.append(page_obj_id)

        objects[1] = f'<< /Type /Pages /Kids [{" ".join(f"{page} 0 R" for page in pages)}] /Count {len(pages)} >>'

        output = ['%PDF-1.4\n']
        offsets = [0]
        for index, obj in enumerate(objects, start=1):
            offsets.append(sum(len(part.encode('latin-1', errors='replace')) for part in output))
            output.append(f'{index} 0 obj\n{obj}\nendobj\n')
        xref_offset = sum(len(part.encode('latin-1', errors='replace')) for part in output)
        output.append(f'xref\n0 {len(objects) + 1}\n0000000000 65535 f \n')
        for offset in offsets[1:]:
            output.append(f'{offset:010d} 00000 n \n')
        output.append(f'trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref_offset}\n%%EOF')
        return ''.join(output).encode('latin-1', errors='replace')


@require_GET
def statistics_export_view(request):
    auth_result = TokenVersionJWTAuthentication().authenticate(Request(request))
    if auth_result is None:
        return HttpResponse('Authentication credentials were not provided.', status=401)
    request.user, request.auth = auth_result
    if not _user_is_admin(request.user):
        return HttpResponse('Admin role is required.', status=403)
    return build_statistics_export_response(request)


def _request_params(request):
    return getattr(request, 'query_params', request.GET)


def _export_parse_time_window(request):
    params = _request_params(request)
    group_by = params.get('group_by', 'day').lower()
    if group_by not in {'day', 'month', 'year'}:
        return None, Response(
            {'error': 'group_by must be one of: day, month, year'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    default_window = {'day': 30, 'month': 12, 'year': 5}[group_by]
    try:
        window = int(params.get('window', default_window))
    except ValueError:
        return None, Response({'error': 'window must be an integer'}, status=status.HTTP_400_BAD_REQUEST)

    if window < 1:
        return None, Response({'error': 'window must be greater than 0'}, status=status.HTTP_400_BAD_REQUEST)

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


def _export_period_keys(start_at, end_at, group_by):
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
            current = current.replace(year=current.year + 1, month=1) if current.month == 12 else current.replace(month=current.month + 1)
        return keys

    current = current.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
    end_cursor = end_local.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
    while current <= end_cursor:
        keys.append(current.date())
        current = current.replace(year=current.year + 1)
    return keys


def _export_series_map(queryset, trunc_fn, date_field='created_at'):
    series = {}
    for row in (
        queryset
        .annotate(period=trunc_fn(date_field))
        .values('period')
        .annotate(total=Count('id'))
        .order_by('period')
    ):
        period_value = row['period']
        if hasattr(period_value, 'date'):
            period_value = period_value.date()
        series[period_value] = row['total']
    return series


def _export_library_tree(projects_qs, request, use_system_scope=True):
    from apps.chatbot.models import ChatSession
    from apps.documents.models import Document

    chat_qs = ChatSession.objects.filter(is_deleted=False).order_by('-updated_at')
    if not use_system_scope:
        chat_qs = chat_qs.filter(user=request.user)

    doc_qs = Document.objects.filter(is_deleted=False).order_by('-uploaded_at')
    project_list = projects_qs.prefetch_related(
        Prefetch('chat_sessions', queryset=chat_qs.prefetch_related(Prefetch('documents', queryset=doc_qs)))
    )

    tree = []
    for project in project_list:
        chat_items = []
        project_documents_count = 0
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
            project_documents_count += len(documents)
            chat_items.append({
                'chat_session_id': chat.id,
                'chat_session_title': chat.title,
                'documents_count': len(documents),
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


def build_statistics_payload_for_export(request):
    from apps.auth.models import User, AuthSession
    from apps.chatbot.models import ChatSession, ChatMessage
    from apps.documents.models import Document

    time_window, error_response = _export_parse_time_window(request)
    if error_response:
        return None, error_response

    params = _request_params(request)
    scope = params.get('scope', 'system').lower()
    use_system_scope = scope != 'mine'

    if use_system_scope:
        projects_qs = Project.objects.all()
        users_qs = User.objects.all()
        visits_qs = AuthSession.objects.all()
        chats_qs = ChatSession.objects.filter(is_deleted=False)
        documents_qs = Document.objects.filter(is_deleted=False).select_related('chat_session', 'chat_session__project')
    else:
        projects_qs = Project.objects.filter(owner=request.user)
        users_qs = User.objects.filter(id=request.user.id)
        visits_qs = AuthSession.objects.filter(user=request.user)
        chats_qs = ChatSession.objects.filter(project__in=projects_qs, user=request.user, is_deleted=False)
        documents_qs = Document.objects.filter(chat_session__project__in=projects_qs, is_deleted=False).select_related('chat_session', 'chat_session__project')

    user_queries_qs = ChatMessage.objects.filter(chat_session__in=chats_qs, role=ChatMessage.Role.USER)
    filtered_users_qs = users_qs.filter(created_at__gte=time_window['start_at'], created_at__lte=time_window['end_at'])
    filtered_visits_qs = visits_qs.filter(created_at__gte=time_window['start_at'], created_at__lte=time_window['end_at'])
    filtered_queries_qs = user_queries_qs.filter(created_at__gte=time_window['start_at'], created_at__lte=time_window['end_at'])
    filtered_uploads_qs = documents_qs.filter(uploaded_at__gte=time_window['start_at'], uploaded_at__lte=time_window['end_at'])

    users_series = _export_series_map(filtered_users_qs, time_window['trunc_fn'])
    visits_series = _export_series_map(filtered_visits_qs, time_window['trunc_fn'])
    queries_series = _export_series_map(filtered_queries_qs, time_window['trunc_fn'])
    uploads_series = _export_series_map(filtered_uploads_qs, time_window['trunc_fn'], date_field='uploaded_at')

    chart_rows = []
    for period_key in _export_period_keys(time_window['start_at'], time_window['end_at'], time_window['group_by']):
        chart_rows.append({
            'period': period_key.strftime(time_window['label_format']),
            'users': users_series.get(period_key, 0),
            'visits': visits_series.get(period_key, 0),
            'queries': queries_series.get(period_key, 0),
            'uploads': uploads_series.get(period_key, 0),
        })

    counts = documents_qs.aggregate(
        total_documents=Count('id'),
        indexed_documents=Count('id', filter=Q(index_status=Document.IndexStatus.INDEXED)),
        indexing_documents=Count('id', filter=Q(index_status=Document.IndexStatus.INDEXING)),
        failed_documents=Count('id', filter=Q(index_status=Document.IndexStatus.FAILED)),
        total_indexed_chunks=Sum('indexed_chunks'),
    )

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
            'columns': ['period', 'users', 'visits', 'queries', 'uploads'],
            'line': chart_rows,
        },
        'library': {'projects': _export_library_tree(projects_qs, request, use_system_scope=use_system_scope)},
    }
    return payload, None


def _empty_statistics_payload(error=''):
    now = timezone.now()
    return {
        'scope': 'system',
        'time_filter': {
            'group_by': 'day',
            'window': 0,
            'start_at': now.isoformat(),
            'end_at': now.isoformat(),
        },
        'summary': {
            'users': 0,
            'visits': 0,
            'queries': 0,
            'projects': 0,
            'total_documents': 0,
            'indexed_documents': 0,
            'indexing_documents': 0,
            'failed_documents': 0,
            'total_indexed_chunks': 0,
            'active_chat_sessions': 0,
            'export_error': error[:300],
        },
        'charts': {'columns': ['period', 'users', 'visits', 'queries', 'uploads'], 'line': []},
        'library': {'projects': []},
    }


def _build_simple_pdf(text):
    def esc(value):
        return value.replace('\\', '\\\\').replace('(', '\\(').replace(')', '\\)')

    lines = ['Statistics Report'] + text.splitlines()
    page_chunks = [lines[i:i + 42] for i in range(0, len(lines), 42)] or [['Statistics Report']]
    objects = ['<< /Type /Catalog /Pages 2 0 R >>', '', '<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>']
    pages = []
    for chunk in page_chunks:
        content_lines = ['BT', '/F1 9 Tf', '50 790 Td', '14 TL']
        for index, line in enumerate(chunk):
            if index:
                content_lines.append('T*')
            content_lines.append(f'({esc(line[:110])}) Tj')
        content_lines.append('ET')
        content = '\n'.join(content_lines)
        content_obj_id = len(objects) + 2
        page_obj_id = len(objects) + 1
        objects.append(f'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 3 0 R >> >> /Contents {content_obj_id} 0 R >>')
        objects.append(f'<< /Length {len(content.encode("latin-1", errors="replace"))} >>\nstream\n{content}\nendstream')
        pages.append(page_obj_id)
    objects[1] = f'<< /Type /Pages /Kids [{" ".join(f"{page} 0 R" for page in pages)}] /Count {len(pages)} >>'

    output = ['%PDF-1.4\n']
    offsets = [0]
    for index, obj in enumerate(objects, start=1):
        offsets.append(sum(len(part.encode('latin-1', errors='replace')) for part in output))
        output.append(f'{index} 0 obj\n{obj}\nendobj\n')
    xref_offset = sum(len(part.encode('latin-1', errors='replace')) for part in output)
    output.append(f'xref\n0 {len(objects) + 1}\n0000000000 65535 f \n')
    for offset in offsets[1:]:
        output.append(f'{offset:010d} 00000 n \n')
    output.append(f'trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref_offset}\n%%EOF')
    return ''.join(output).encode('latin-1', errors='replace')


def build_statistics_export_response(request):
    params = _request_params(request)
    export_format = params.get('format', 'csv').lower()
    if export_format not in {'csv', 'xls', 'excel', 'pdf'}:
        return Response({'error': 'format must be csv, xls, excel, or pdf'}, status=status.HTTP_400_BAD_REQUEST)

    try:
        payload, error_response = build_statistics_payload_for_export(request)
        if error_response:
            return error_response
    except Exception as exc:
        payload = _empty_statistics_payload(error=str(exc))

    writer_buffer = StringIO()
    writer = csv.writer(writer_buffer)
    writer.writerow(['scope', payload.get('scope', '')])
    writer.writerow(['group_by', payload.get('time_filter', {}).get('group_by', '')])
    writer.writerow(['window', payload.get('time_filter', {}).get('window', '')])
    writer.writerow(['start_at', payload.get('time_filter', {}).get('start_at', '')])
    writer.writerow(['end_at', payload.get('time_filter', {}).get('end_at', '')])
    writer.writerow([])
    writer.writerow(['summary_metric', 'value'])
    for key, value in payload.get('summary', {}).items():
        writer.writerow([key, value])
    writer.writerow([])
    writer.writerow(payload.get('charts', {}).get('columns') or ['period', 'users', 'visits', 'queries', 'uploads'])
    for row in payload.get('charts', {}).get('line', []):
        writer.writerow([row.get('period', ''), row.get('users', 0), row.get('visits', 0), row.get('queries', 0), row.get('uploads', 0)])
    writer.writerow([])
    writer.writerow(['project_id', 'project_name', 'chat_session_id', 'chat_session_title', 'document_id', 'document_title', 'file_type', 'index_status', 'indexed_chunks', 'uploaded_at'])
    for project_item in payload.get('library', {}).get('projects', []):
        for chat_item in project_item.get('chat_sessions', []):
            for doc_item in chat_item.get('documents', []):
                writer.writerow([
                    project_item.get('project_id', ''),
                    project_item.get('project_name', ''),
                    chat_item.get('chat_session_id', ''),
                    chat_item.get('chat_session_title', ''),
                    doc_item.get('document_id', ''),
                    doc_item.get('title', ''),
                    doc_item.get('file_type', ''),
                    doc_item.get('index_status', ''),
                    doc_item.get('indexed_chunks', 0),
                    doc_item.get('uploaded_at', ''),
                ])

    csv_text = writer_buffer.getvalue()
    if export_format == 'csv':
        response = HttpResponse(csv_text, content_type='text/csv; charset=utf-8')
        response['Content-Disposition'] = 'attachment; filename="statistics_report.csv"'
        return response

    if export_format in {'xls', 'excel'}:
        html_rows = []
        for line in csv_text.splitlines():
            cells = ''.join(f'<td>{cell}</td>' for cell in next(csv.reader([line])))
            html_rows.append(f'<tr>{cells}</tr>')
        html = '<html><head><meta charset="utf-8"></head><body><table>' + ''.join(html_rows) + '</table></body></html>'
        response = HttpResponse(html, content_type='application/vnd.ms-excel; charset=utf-8')
        response['Content-Disposition'] = 'attachment; filename="statistics_report.xls"'
        return response

    response = HttpResponse(_build_simple_pdf(csv_text), content_type='application/pdf')
    response['Content-Disposition'] = 'attachment; filename="statistics_report.pdf"'
    return response
