import logging

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer


logger = logging.getLogger(__name__)


def _send_group(group_name, event_type, payload):
    channel_layer = get_channel_layer()
    if not channel_layer:
        return
    try:
        async_to_sync(channel_layer.group_send)(
            group_name,
            {
                'type': 'app.event',
                'event_type': event_type,
                'payload': payload or {},
            },
        )
    except Exception:
        logger.exception('Realtime event failed: group=%s type=%s', group_name, event_type)


def send_to_user(user_id, event_type, payload=None):
    if user_id:
        _send_group(f'user_{user_id}', event_type, payload)


def send_to_admins(event_type, payload=None):
    _send_group('admins', event_type, payload)


def notification_payload(notification):
    return {
        'id': notification.id,
        'title': notification.title,
        'message': notification.message,
        'data': notification.data or {},
        'is_read': notification.is_read,
        'created_at': notification.created_at.isoformat(),
    }


def send_notification(notification):
    send_to_user(notification.user_id, 'notification.created', notification_payload(notification))


def send_document_ready_notifications(document, payload):
    from apps.teams.models import InAppNotification

    recipient_ids = set()
    if document.uploaded_by_id:
        recipient_ids.add(document.uploaded_by_id)
    if document.chat_session_id and document.chat_session.user_id:
        recipient_ids.add(document.chat_session.user_id)

    for team_link in document.team_links.select_related('team').prefetch_related('team__memberships'):
        for membership in team_link.team.memberships.all():
            recipient_ids.add(membership.user_id)

    for user_id in recipient_ids:
        notification = InAppNotification.objects.create(
            user_id=user_id,
            title='Document is ready',
            message=f'"{document.title}" has been indexed and is ready to use.',
            data={
                'type': 'document_ready',
                'document_id': document.id,
                'chat_session_id': document.chat_session_id,
                'index_status': payload.get('index_status'),
            },
        )
        send_notification(notification)


def send_document_status(document, status=None):
    current_status = status or document.index_status
    payload = {
        'document_id': document.id,
        'title': document.title,
        'index_status': current_status,
        'indexed_chunks': document.indexed_chunks,
        'index_error': document.index_error,
        'chat_session_id': document.chat_session_id,
        'uploaded_by_id': str(document.uploaded_by_id) if document.uploaded_by_id else None,
    }
    send_to_admins('dashboard.document.status', payload)
    send_to_user(document.chat_session.user_id, 'document.status', payload)
    if document.uploaded_by_id and document.uploaded_by_id != document.chat_session.user_id:
        send_to_user(document.uploaded_by_id, 'document.status', payload)

    for team_link in document.team_links.select_related('team').prefetch_related('team__memberships'):
        payload['team_id'] = team_link.team_id
        for membership in team_link.team.memberships.all():
            send_to_user(membership.user_id, 'team.document.status', payload)

    if current_status == 'indexed':
        send_document_ready_notifications(document, payload)


def send_team_event(team, event_type, payload=None):
    payload = {'team_id': team.id, 'team_name': team.name, **(payload or {})}
    for membership in team.memberships.all():
        send_to_user(membership.user_id, event_type, payload)
