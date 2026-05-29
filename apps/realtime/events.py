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


def send_document_status(document, status=None):
    payload = {
        'document_id': document.id,
        'title': document.title,
        'index_status': status or document.index_status,
        'indexed_chunks': document.indexed_chunks,
        'index_error': document.index_error,
        'chat_session_id': document.chat_session_id,
        'uploaded_by_id': str(document.uploaded_by_id) if document.uploaded_by_id else None,
    }
    send_to_user(document.chat_session.user_id, 'document.status', payload)
    if document.uploaded_by_id and document.uploaded_by_id != document.chat_session.user_id:
        send_to_user(document.uploaded_by_id, 'document.status', payload)

    for team_link in document.team_links.select_related('team').prefetch_related('team__memberships'):
        payload['team_id'] = team_link.team_id
        for membership in team_link.team.memberships.all():
            send_to_user(membership.user_id, 'team.document.status', payload)


def send_team_event(team, event_type, payload=None):
    payload = {'team_id': team.id, 'team_name': team.name, **(payload or {})}
    for membership in team.memberships.all():
        send_to_user(membership.user_id, event_type, payload)
