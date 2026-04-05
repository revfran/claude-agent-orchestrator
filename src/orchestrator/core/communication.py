from __future__ import annotations

import asyncio
from collections import defaultdict
from typing import TYPE_CHECKING

from orchestrator.models.messages import Message

if TYPE_CHECKING:
    from orchestrator.core.logging_monitor import Monitor


class MessageBus:
    """Async pub/sub message bus using asyncio queues."""

    def __init__(self):
        self._channels: dict[str, list[asyncio.Queue[Message]]] = defaultdict(list)
        self.monitor: Monitor | None = None

    def subscribe(self, channel: str, queue: asyncio.Queue[Message]):
        self._channels[channel].append(queue)

    async def publish(self, channel: str, message: Message):
        subscribers = self._channels[channel]
        if self.monitor:
            self.monitor.emit(
                "bus_route",
                channel=channel,
                source=message.source,
                msg_type=message.msg_type,
                message_id=message.id,
                subscriber_count=len(subscribers),
            )
        for queue in subscribers:
            await queue.put(message)
