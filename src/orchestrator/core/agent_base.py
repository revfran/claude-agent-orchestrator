import asyncio
import time
from abc import ABC, abstractmethod

from orchestrator.core.communication import MessageBus
from orchestrator.core.data_handler import DataHandler
from orchestrator.core.logging_monitor import Monitor
from orchestrator.models.config import AgentConfig
from orchestrator.models.messages import Message
from orchestrator.models.state import AgentState


class BaseAgent(ABC):
    """Abstract base class for all agents."""

    def __init__(self, config: AgentConfig, claude_client):
        self.config = config
        self.agent_id = config.agent_id
        self.state = AgentState.IDLE
        self.claude = claude_client
        self._inbox: asyncio.Queue[Message] = asyncio.Queue()
        self._message_bus: MessageBus | None = None
        self.monitor: Monitor | None = None
        self.data_handler: DataHandler | None = None
        self._task: asyncio.Task | None = None

    async def start(self):
        self.state = AgentState.RUNNING
        self._task = asyncio.create_task(self._run_loop())

    async def stop(self):
        self.state = AgentState.STOPPED
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def _run_loop(self):
        try:
            while self.state == AgentState.RUNNING:
                try:
                    msg = await asyncio.wait_for(self._inbox.get(), timeout=1.0)
                except asyncio.TimeoutError:
                    continue

                start = time.monotonic()
                try:
                    result = await self.process(msg)
                    duration_ms = (time.monotonic() - start) * 1000
                    if self.monitor:
                        self.monitor.record_processed(self.agent_id, duration_ms)
                    if result is not None:
                        await self._publish(result)
                except Exception as e:
                    self.state = AgentState.ERROR
                    if self.monitor:
                        self.monitor.record_error(self.agent_id, e)
                    raise
        except asyncio.CancelledError:
            pass

    async def _publish(self, payload: dict):
        if not self._message_bus:
            return
        for channel in self.config.output_channels:
            msg = Message(source=self.agent_id, target=channel, payload=payload)
            await self._message_bus.publish(channel, msg)

    async def _publish_to(self, channel: str, payload: dict, msg_type: str = "data"):
        if not self._message_bus:
            return
        msg = Message(
            source=self.agent_id, target=channel, payload=payload, msg_type=msg_type
        )
        await self._message_bus.publish(channel, msg)

    @abstractmethod
    async def process(self, message: Message) -> dict | None:
        ...

    async def call_claude(self, prompt: str, system: str | None = None) -> str:
        response = await self.claude.messages.create(
            model=self.config.claude_model,
            max_tokens=2048,
            system=system or self.config.system_prompt,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.content[0].text
