# Architecture Overview

The Claude Agent Orchestrator coordinates multiple Claude-powered AI subagents in a pipeline with QA feedback loops. Each agent has a specialized role, and the QA agent ensures quality by reviewing outputs at critical checkpoints.

## System Components

### Core Layer

| Component | File | Purpose |
|-----------|------|---------|
| **BaseAgent** | `src/orchestrator/core/agent_base.py` | Abstract base class all agents extend. Provides async run loop, message inbox, Claude API helper |
| **MessageBus** | `src/orchestrator/core/communication.py` | Pub/sub messaging using asyncio queues. Agents publish to named channels; subscribers receive copies |
| **AgentManager** | `src/orchestrator/core/agent_manager.py` | Registers agents, wires them to message bus channels, manages lifecycle (start/stop/restart) |
| **DataHandler** | `src/orchestrator/core/data_handler.py` | Async key-value store for shared data between agents (e.g., risk logs, reports) |
| **Monitor** | `src/orchestrator/core/logging_monitor.py` | Human-readable logging + structured JSON event log (`orchestrator.events`) + per-agent metrics |

### Agent Roles

| Agent | File | Role |
|-------|------|------|
| **DataAcquisitionAgent** | `src/orchestrator/agents/acquisition.py` | Gathers requirements, context, and data from the input query |
| **ArchitectAgent** | `src/orchestrator/agents/architect.py` | Designs solution architecture; revises based on QA risk findings |
| **QAAgent** | `src/orchestrator/agents/qa.py` | Reviews architecture & code for risks; classifies severity; generates tests; flags documentation gaps |
| **DeveloperAgent** | `src/orchestrator/agents/developer.py` | Implements solution code; fixes issues based on QA findings; proposes documentation updates |
| **ReportingAgent** | `src/orchestrator/agents/reporting.py` | Generates final structured report with risk resolution log and documentation update plan |

## Pipeline Flow with QA Feedback Loops

```
  User Query
      │
      ▼
┌──────────────┐
│    Data       │  Gathers requirements, context,
│  Acquisition  │  and relevant data
└──────┬───────┘
       │ {query, requirements, context}
       ▼
┌──────────────┐
│  Architect    │  Designs solution architecture
└──────┬───────┘
       │ {architecture, design_decisions}
       ▼
┌──────────────┐
│  QA Agent     │  RISK ASSESSMENT #1: Architecture Review
│  (Arch Review)│  - Scalability, security, maintainability risks
│               │  - Edge cases and failure modes
└──────┬───────┘
       │
       │  blocking risks found?
       ├──── YES ──▶ ┌──────────────┐
       │              │  Architect    │  Revises architecture
       │              │  (Revision)   │  to address risks
       │              └──────┬───────┘
       │                     │ {revised_architecture}
       │◀────────────────────┘  (back to QA, max 2 iterations)
       │
       │  approved
       ▼
┌──────────────┐
│  Developer    │  Implements solution based on
│               │  approved architecture
└──────┬───────┘
       │ {code, implementation_notes}
       ▼
┌──────────────┐
│  QA Agent     │  RISK ASSESSMENT #2: Code Review + Tests
│  (Code Review)│  - Bugs, security vulnerabilities, edge cases
│               │  - Generates test cases
└──────┬───────┘
       │
       │  blocking risks found?
       ├──── YES ──▶ ┌──────────────┐
       │              │  Developer    │  Fixes code issues
       │              │  (Revision)   │  based on QA findings
       │              └──────┬───────┘
       │                     │ {revised_code}
       │◀────────────────────┘  (back to QA, max 2 iterations)
       │
       │  approved
       ▼
┌──────────────┐
│  Reporting    │  Generates final structured report:
│               │  architecture, code, tests, risk log
└──────┬───────┘
       │
       ▼
   Final Report
```

## Message Format

All inter-agent communication uses a single `Message` model:

```python
class Message(BaseModel):
    id: str          # Unique message ID (auto-generated)
    source: str      # Agent ID of sender
    target: str      # Channel name
    payload: dict    # Arbitrary data
    timestamp: datetime
    msg_type: str    # "data", "review_request", "risk_assessment", "revision_request", "control"
```

The `msg_type` field controls routing:
- `"data"` — normal pipeline data flowing forward
- `"revision_request"` — QA sending work back to architect/developer for fixes

## Channel Topology

```
pipeline_input ──▶ DataAcquisition ──▶ arch_input ──▶ Architect ──▶ arch_review ──▶ QA
                                                          ▲                         │
                                                          │    arch_revision        │
                                                          └────────────────────────┘
                                                                                    │
                                                                    dev_input       │
                                                                        ◀───────────┘
Developer ◀── dev_input
Developer ──▶ code_review ──▶ QA
                               │
              code_revision    │
Developer ◀───────────────────┘
                               │
               report_input    │
                    ◀──────────┘
Reporting ◀── report_input
Reporting ──▶ pipeline_output
```

## QA Risk Assessment

The QA Agent classifies risks by severity:

| Severity | Action |
|----------|--------|
| **HIGH** | Blocks progression — must be addressed before moving forward |
| **MEDIUM** | Should be addressed — triggers revision if combined with HIGH |
| **LOW** | Noted in report but does not block |

Risk assessment output:
```json
{
  "risk_items": [
    {"description": "...", "severity": "HIGH", "recommendation": "..."}
  ],
  "has_blocking_risks": true,
  "test_cases": ["test case 1", "test case 2"],
  "summary": "..."
}
```

Maximum 2 revision iterations per checkpoint to prevent infinite loops. If risks remain after 2 rounds, the pipeline proceeds with risks documented in the final report.

## Extending with Custom Agents

To create a custom agent:

1. Subclass `BaseAgent` from `orchestrator.core.agent_base`
2. Implement the `process(message: Message) -> dict | None` method
3. Use `self.call_claude(prompt)` to call the Claude API
4. Use `self.data_handler` to read/write shared data
5. Return a dict to publish to output channels, or `None` to skip

```python
from orchestrator.core.agent_base import BaseAgent
from orchestrator.models.messages import Message

class MyCustomAgent(BaseAgent):
    async def process(self, message: Message) -> dict | None:
        data = message.payload.get("input_data", "")
        result = await self.call_claude(f"Process this: {data}")
        return {"output": result}
```

Register the agent with the orchestrator:
```python
from orchestrator.models.config import AgentConfig

agent = MyCustomAgent(
    AgentConfig(
        agent_id="my_agent",
        agent_type="custom",
        input_channels=["my_input"],
        output_channels=["my_output"],
    ),
    orchestrator.agent_manager.claude_client,
)
orchestrator.add_agent(agent)
```

## Observability — Structured Event Log

The `Monitor` class exposes two loggers:

| Logger | Format | Purpose |
|--------|--------|---------|
| `orchestrator` | Human-readable (`asctime [LEVEL] name: message`) | Console output during development |
| `orchestrator.events` | Single-line JSON (JSONL) | Machine-consumable event stream for external tools |

### Event stream

Every orchestration milestone emits a structured JSON event via `monitor.emit()`. Events contain `ts`, `level`, `event`, and contextual fields.

| Event | Emitted by | Key fields |
|---|---|---|
| `orchestrator_starting` | `Orchestrator.run()` | `agent_count`, `agents` |
| `orchestrator_ready` | `Orchestrator.run()` | — |
| `orchestrator_shutdown` | `Orchestrator.shutdown()` | `metrics` |
| `agent_started` | `BaseAgent.start()` | `agent`, `input_channels`, `output_channels` |
| `agent_stopped` | `BaseAgent.stop()` | `agent` |
| `message_received` | `BaseAgent._run_loop()` | `agent`, `source`, `channel`, `msg_type`, `message_id` |
| `message_published` | `BaseAgent._publish*()` | `agent`, `channel`, `msg_type`, `message_id` |
| `message_processed` | `Monitor.record_processed()` | `agent`, `duration_ms`, `total_processed` |
| `bus_route` | `MessageBus.publish()` | `channel`, `source`, `subscriber_count` |
| `claude_api_call` | `Monitor.record_tokens()` | `agent`, `input_tokens`, `output_tokens` |
| `qa_gate_approved` | `QAAgent` | `review_type`, `revisions_made` |
| `qa_gate_rejected` | `QAAgent` | `review_type`, `revision_count`, `max_revisions` |
| `revision_started` | `ArchitectAgent` / `DeveloperAgent` | `agent`, `revision_number` |
| `revision_triggered` | `Monitor.record_revision()` | `agent`, `total_revisions` |
| `agent_error` | `Monitor.record_error()` | `agent`, `error`, `error_type` |

### Consuming the event log

**File output (for tail, jq, ELK, Datadog):**
```python
import logging
fh = logging.FileHandler("events.jsonl")
fh.setLevel(logging.DEBUG)
logging.getLogger("orchestrator.events").addHandler(fh)
```

**Watch live:**
```bash
tail -f events.jsonl | jq .
```

**Example event payload:**
```json
{"ts": "2026-04-05T14:23:01.123456+00:00", "level": "INFO", "event": "qa_gate_rejected", "agent": "qa", "review_type": "architecture", "revision_count": 1, "max_revisions": 2}
```

Any standard Python `logging.Handler` can be attached — Syslog, CloudWatch, HTTP, etc.

## Review Pipeline — Documentation & Verification

The review workflow (in `review.py`) includes seven stages:

1. **Data Acquisition** — gather project context
2. **Architecture Review** — analyse design patterns and structure
3. **QA Architecture Risk Assessment** — flag risks including documentation gaps
4. **Code Review** — find bugs, vulnerabilities, and documentation staleness
5. **QA Code Risk Assessment** — assess code risks and flag documentation gaps
6. **Final Report** — structured report including a **Documentation Updates** section
7. **How to Know the Changes Will Work** — concrete verification checklist with commands, expected output, and regression signals

The Developer agent proposes documentation updates alongside code changes. The QA agent flags any documentation that has fallen out of sync. The Reporting agent compiles the documentation update plan into the final report.
