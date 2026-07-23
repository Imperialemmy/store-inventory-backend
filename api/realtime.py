from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer


ACTIVITY_GROUP = "business_activity"


def publish_change(resources, source="backend"):
    """Broadcast a committed data change to every authenticated app client."""
    layer = get_channel_layer()
    if layer is None:
        return
    payload = {
        "resources": sorted(set(resources)),
        "source": source,
    }
    async_to_sync(layer.group_send)(
        ACTIVITY_GROUP,
        {"type": "data.changed", "payload": payload},
    )
