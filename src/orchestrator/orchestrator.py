from orchestrator.core.agent_base import BaseAgent
from orchestrator.core.agent_manager import AgentManager
from orchestrator.core.data_handler import DataHandler
from orchestrator.core.logging_monitor import Monitor
from orchestrator.models.config import OrchestratorConfig


class Orchestrator:
    """Top-level facade for the agent orchestration system."""

    def __init__(self, config: OrchestratorConfig):
        self.config = config
        self.monitor = Monitor(config.log_level)
        self.data_handler = DataHandler()
        self.agent_manager = AgentManager(config)
        self.agent_manager.monitor = self.monitor
        self.agent_manager.data_handler = self.data_handler

    def add_agent(self, agent: BaseAgent):
        agent.monitor = self.monitor
        agent.data_handler = self.data_handler
        self.agent_manager.register(agent)

    async def run(self):
        self.monitor.logger.info("Starting orchestrator...")
        await self.agent_manager.start_all()
        self.monitor.logger.info("All agents started.")

    async def shutdown(self):
        await self.agent_manager.stop_all()
        self.monitor.logger.info("Orchestrator shut down.")
        self.monitor.logger.info(f"Metrics: {self.monitor.summary()}")
