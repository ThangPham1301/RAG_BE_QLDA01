import json
import logging

from channels.generic.websocket import AsyncWebsocketConsumer


logger = logging.getLogger(__name__)


class RealtimeConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        user = self.scope.get('user')
        if not user or not user.is_authenticated:
            logger.warning('Realtime WebSocket rejected: unauthenticated user')
            await self.close(code=4401)
            return

        self.user = user
        self.groups_to_join = [f'user_{user.id}']

        if user.is_staff or user.is_superuser:
            self.groups_to_join.append('admins')

        for group_name in self.groups_to_join:
            await self.channel_layer.group_add(group_name, self.channel_name)

        await self.accept()
        await self.send_json({
            'type': 'connection.ready',
            'payload': {'user_id': str(user.id), 'admin': bool(user.is_staff or user.is_superuser)},
        })

    async def disconnect(self, close_code):
        for group_name in getattr(self, 'groups_to_join', []):
            await self.channel_layer.group_discard(group_name, self.channel_name)

    async def receive(self, text_data=None, bytes_data=None):
        if not text_data:
            return
        try:
            data = json.loads(text_data)
        except json.JSONDecodeError:
            return
        if data.get('type') == 'ping':
            await self.send_json({'type': 'pong'})

    async def app_event(self, event):
        await self.send_json({
            'type': event.get('event_type', 'event'),
            'payload': event.get('payload', {}),
        })

    async def send_json(self, data):
        await self.send(text_data=json.dumps(data, ensure_ascii=False))
