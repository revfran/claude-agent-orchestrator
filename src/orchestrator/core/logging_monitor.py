import logging
import time
from dataclasses import dataclass, field


@dataclass
class AgentMetrics:
    messages_processed: int = 0
    errors: int = 0
    total_processing_time_ms: float = 0.0
    revisions_triggered: int = 0
    last_active: float = field(default_factory=time.time)


class Monitor:
    """Logging and metrics tracking for agents."""

    def __init__(self, log_level: str = "INFO"):
        self.logger = logging.getLogger("orchestrator")
        self.logger.setLevel(getattr(logging, log_level))
        if not self.logger.handlers:
            handler = logging.StreamHandler()
            handler.setFormatter(
                logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
            )
            self.logger.addHandler(handler)
        self._metrics: dict[str, AgentMetrics] = {}

    def get_metrics(self, agent_id: str) -> AgentMetrics:
        if agent_id not in self._metrics:
            self._metrics[agent_id] = AgentMetrics()
        return self._metrics[agent_id]

    def record_processed(self, agent_id: str, duration_ms: float):
        m = self.get_metrics(agent_id)
        m.messages_processed += 1
        m.total_processing_time_ms += duration_ms
        m.last_active = time.time()
        self.logger.debug(f"Agent {agent_id}: processed message in {duration_ms:.1f}ms")

    def record_error(self, agent_id: str, error: Exception):
        m = self.get_metrics(agent_id)
        m.errors += 1
        self.logger.error(f"Agent {agent_id}: {error}")

    def record_revision(self, agent_id: str):
        m = self.get_metrics(agent_id)
        m.revisions_triggered += 1
        self.logger.info(f"Agent {agent_id}: revision triggered")

    def summary(self) -> dict[str, dict]:
        return {
            agent_id: {
                "messages_processed": m.messages_processed,
                "errors": m.errors,
                "total_processing_time_ms": round(m.total_processing_time_ms, 1),
                "revisions_triggered": m.revisions_triggered,
            }
            for agent_id, m in self._metrics.items()
        }
