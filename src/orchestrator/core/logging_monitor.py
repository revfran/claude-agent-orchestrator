import json
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


class _JsonFormatter(logging.Formatter):
    """Formats log records as single-line JSON objects."""

    def format(self, record: logging.LogRecord) -> str:
        event: dict[str, Any] = record.__dict__.get("event_data", {})
        entry = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "event": event.get("event", record.getMessage()),
            **{k: v for k, v in event.items() if k != "event"},
        }
        return json.dumps(entry, default=str)


@dataclass
class AgentMetrics:
    messages_processed: int = 0
    errors: int = 0
    total_processing_time_ms: float = 0.0
    revisions_triggered: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    last_active: float = field(default_factory=time.time)


class Monitor:
    """Logging and metrics tracking for agents.

    Provides two loggers:
    - ``orchestrator`` — human-readable stream log (existing behaviour).
    - ``orchestrator.events`` — structured JSON event log for machine
      consumption.  Attach a ``FileHandler`` or any standard handler to
      ``logging.getLogger("orchestrator.events")`` to capture events.

    Quick start for watching events in a terminal::

        import logging
        fh = logging.FileHandler("events.jsonl")
        fh.setLevel(logging.DEBUG)
        logging.getLogger("orchestrator.events").addHandler(fh)

    Then: ``tail -f events.jsonl | python -m json.tool``
    """

    def __init__(self, log_level: str = "INFO"):
        # Human-readable logger (unchanged)
        self.logger = logging.getLogger("orchestrator")
        self.logger.setLevel(getattr(logging, log_level))
        if not self.logger.handlers:
            handler = logging.StreamHandler()
            handler.setFormatter(
                logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
            )
            self.logger.addHandler(handler)

        # Structured JSON event logger
        self._event_logger = logging.getLogger("orchestrator.events")
        self._event_logger.setLevel(logging.DEBUG)
        self._event_logger.propagate = False
        if not self._event_logger.handlers:
            eh = logging.StreamHandler()
            eh.setFormatter(_JsonFormatter())
            self._event_logger.addHandler(eh)

        self._metrics: dict[str, AgentMetrics] = {}

    # ------------------------------------------------------------------
    # Structured event emission
    # ------------------------------------------------------------------

    def emit(self, event: str, level: int = logging.INFO, **data: Any) -> None:
        """Emit a structured JSON event.

        Every event gets a ``ts``, ``level``, and ``event`` field
        automatically.  Additional keyword arguments become top-level
        fields in the JSON object.
        """
        record = self._event_logger.makeRecord(
            name="orchestrator.events",
            level=level,
            fn="",
            lno=0,
            msg=event,
            args=(),
            exc_info=None,
        )
        record.__dict__["event_data"] = {"event": event, **data}
        self._event_logger.handle(record)

    # ------------------------------------------------------------------
    # Metrics (unchanged public API)
    # ------------------------------------------------------------------

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
        self.emit(
            "message_processed",
            agent=agent_id,
            duration_ms=round(duration_ms, 1),
            total_processed=m.messages_processed,
        )

    def record_error(self, agent_id: str, error: Exception):
        m = self.get_metrics(agent_id)
        m.errors += 1
        self.logger.error(f"Agent {agent_id}: {error}")
        self.emit(
            "agent_error",
            level=logging.ERROR,
            agent=agent_id,
            error=str(error),
            error_type=type(error).__name__,
        )

    def record_revision(self, agent_id: str):
        m = self.get_metrics(agent_id)
        m.revisions_triggered += 1
        self.logger.info(f"Agent {agent_id}: revision triggered")
        self.emit(
            "revision_triggered",
            agent=agent_id,
            total_revisions=m.revisions_triggered,
        )

    def record_tokens(self, agent_id: str, input_tokens: int, output_tokens: int):
        m = self.get_metrics(agent_id)
        m.input_tokens += input_tokens
        m.output_tokens += output_tokens
        self.emit(
            "claude_api_call",
            agent=agent_id,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )

    def summary(self) -> dict[str, dict]:
        return {
            agent_id: {
                "messages_processed": m.messages_processed,
                "errors": m.errors,
                "total_processing_time_ms": round(m.total_processing_time_ms, 1),
                "revisions_triggered": m.revisions_triggered,
                "input_tokens": m.input_tokens,
                "output_tokens": m.output_tokens,
                "total_tokens": m.input_tokens + m.output_tokens,
            }
            for agent_id, m in self._metrics.items()
        }
