import asyncio
from collections import defaultdict

from orchestrator.models.messages import Message


class MessageBus:
    """Async pub/sub message bus using asyncio queues."""

    def __init__(self):
        self._channels: dict[str, list[asyncio.Queue[Message]]] = defaultdict(list)

    def subscribe(self, channel: str, queue: asyncio.Queue[Message]):
        self._channels[channel].append(queue)

    async def publish(self, channel: str, message: Message):
        for queue in self._channels[channel]:
            await queue.put(message)
