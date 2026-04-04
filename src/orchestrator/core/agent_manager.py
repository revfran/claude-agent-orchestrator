import anthropic

from orchestrator.core.agent_base import BaseAgent
from orchestrator.core.communication import MessageBus
from orchestrator.core.data_handler import DataHandler
from orchestrator.core.logging_monitor import Monitor
from orchestrator.models.config import OrchestratorConfig
from orchestrator.models.state import AgentState


class AgentManager:
    """Manages agent lifecycle and wiring to the message bus."""

    def __init__(self, config: OrchestratorConfig):
        self.config = config
        self.message_bus = MessageBus()
        self.agents: dict[str, BaseAgent] = {}
        self.claude_client = anthropic.AsyncAnthropic(api_key=config.anthropic_api_key)
        self.monitor: Monitor | None = None
        self.data_handler: DataHandler | None = None

    def register(self, agent: BaseAgent):
        agent._message_bus = self.message_bus
        if self.monitor:
            agent.monitor = self.monitor
        if self.data_handler:
            agent.data_handler = self.data_handler
        for channel in agent.config.input_channels:
            self.message_bus.subscribe(channel, agent._inbox)
        self.agents[agent.agent_id] = agent

    async def start_all(self):
        for agent in self.agents.values():
            await agent.start()

    async def stop_all(self):
        for agent in self.agents.values():
            await agent.stop()

    async def restart(self, agent_id: str):
        agent = self.agents[agent_id]
        await agent.stop()
        agent.state = AgentState.IDLE
        await agent.start()

    def get_status(self) -> dict[str, AgentState]:
        return {aid: a.state for aid, a in self.agents.items()}
