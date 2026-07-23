from channels.generic.websocket import AsyncJsonWebsocketConsumer

from .realtime import ACTIVITY_GROUP


class ActivityConsumer(AsyncJsonWebsocketConsumer):
    async def connect(self):
        user = self.scope.get("user")
        if not user or not user.is_authenticated:
            await self.close(code=4401)
            return
        await self.channel_layer.group_add(ACTIVITY_GROUP, self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(ACTIVITY_GROUP, self.channel_name)

    async def data_changed(self, event):
        await self.send_json(event["payload"])
