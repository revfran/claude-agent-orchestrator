# Claude Agent Orchestrator

A Python async framework that coordinates multiple Claude-powered AI subagents in a pipeline with QA feedback loops. Each agent has a specialized role, and a QA agent reviews outputs at critical checkpoints, sending work back for revision when risks are found.

## Quick Start

### Prerequisites

- Python 3.11+
- A way to access Claude (see [Usage Options](#usage-options) below)

### Install

```bash
git clone https://github.com/revfran/claude-agent-orchestrator.git
cd claude-agent-orchestrator
pip install -e ".[dev]"
```

### Run Tests

```bash
pytest tests/ -v
```

All 34 tests use mocked Claude responses — no API key or subscription needed.

## Usage Options

### Option 1: Claude Code (Pro/Max Subscription)

If you have a **Claude Code Pro** or **Max** subscription, you can use Claude Code itself to run and interact with the orchestrator — no API key required.

**Using the CLI:**

```bash
# Open Claude Code in the project directory
claude

# Then ask Claude to run the pipeline:
> Run the demo pipeline from examples/demo_pipeline.py with a query about designing a REST API

# Or interact with individual components:
> Create a DataAcquisitionAgent and process the query "Design a caching layer for a web app"
```

**Using Claude Code in your IDE (VS Code / JetBrains):**

1. Open the project in your IDE with the Claude Code extension installed
2. Ask Claude to run or modify the orchestrator pipeline
3. Claude has full access to the codebase and can execute the agents

**Key points for Claude Code users:**
- Claude Code runs on your subscription — no separate API billing
- You can ask Claude to modify agent behavior, add new agents, or adjust the pipeline
- Claude can run the benchmarks (`python -m benchmarks.run_benchmark`) to test changes
- The test suite (`pytest tests/ -v`) always works without any API access

### Option 2: Anthropic API Key

If you have a direct Anthropic API key (from [console.anthropic.com](https://console.anthropic.com)):

```bash
export ANTHROPIC_API_KEY=sk-ant-...
python -m examples.demo_pipeline
```

### Option 3: Claude Agent SDK

You can integrate the orchestrator into applications built with the [Claude Agent SDK](https://docs.anthropic.com/en/docs/agents/agent-sdk):

```python
import asyncio
from orchestrator.orchestrator import Orchestrator
from orchestrator.models.config import OrchestratorConfig
from orchestrator.pipeline import Pipeline
from orchestrator.agents.acquisition import DataAcquisitionAgent
from orchestrator.agents.architect import ArchitectAgent
from orchestrator.agents.qa import QAAgent
from orchestrator.agents.developer import DeveloperAgent
from orchestrator.agents.reporting import ReportingAgent
from orchestrator.models.config import AgentConfig
from orchestrator.models.messages import Message

async def run():
    config = OrchestratorConfig()
    orch = Orchestrator(config)
    client = orch.agent_manager.claude_client

    pipe = Pipeline(orch)
    pipe.set_acquisition(DataAcquisitionAgent(AgentConfig(agent_id="acq", agent_type="acquisition"), client))
    pipe.set_architect(ArchitectAgent(AgentConfig(agent_id="arch", agent_type="architect"), client))
    pipe.set_qa(QAAgent(AgentConfig(agent_id="qa", agent_type="qa", max_revisions=2), client))
    pipe.set_developer(DeveloperAgent(AgentConfig(agent_id="dev", agent_type="developer"), client))
    pipe.set_reporting(ReportingAgent(AgentConfig(agent_id="rep", agent_type="reporting"), client))
    input_channel = pipe.build()

    output_queue = asyncio.Queue()
    orch.agent_manager.message_bus.subscribe("pipeline_output", output_queue)
    await orch.run()

    await orch.agent_manager.message_bus.publish(input_channel, Message(
        source="user", target=input_channel,
        payload={"query": "Design a REST API with authentication", "sources": []},
    ))

    result = await asyncio.wait_for(output_queue.get(), timeout=300)
    print(result.payload["report"])
    await orch.shutdown()

asyncio.run(run())
```

## Architecture

The orchestrator coordinates 5 agents in a pipeline with QA feedback loops:

```
User Query ──▶ Data Acquisition ──▶ Architect ──▶ QA Review ──▶ Developer ──▶ QA Review ──▶ Reporting ──▶ Final Report
                                        ▲            │               ▲            │
                                        └── revision ┘               └── revision ┘
```

| Agent | Role |
|-------|------|
| **Data Acquisition** | Gathers requirements, context, and data from the input query |
| **Architect** | Designs solution architecture; revises based on QA findings |
| **QA** | Reviews architecture and code for risks; generates test cases |
| **Developer** | Implements solution code; fixes issues from QA review |
| **Reporting** | Generates final report with architecture, code, tests, and risk log |

The QA agent sits at two checkpoints and classifies risks as HIGH/MEDIUM/LOW. HIGH severity risks block progression and require revision (max 2 iterations per checkpoint).

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the full technical architecture, message format, channel topology, and guide on creating custom agents.

## Project Structure

```
src/orchestrator/
├── core/                  # Framework infrastructure
│   ├── agent_base.py      # BaseAgent ABC — all agents extend this
│   ├── agent_manager.py   # Agent lifecycle management
│   ├── communication.py   # MessageBus (async pub/sub via queues)
│   ├── data_handler.py    # Shared async key-value store
│   └── logging_monitor.py # Logging and per-agent metrics
├── models/                # Pydantic data models
│   ├── messages.py        # Message schema
│   ├── config.py          # Agent and orchestrator configuration
│   └── state.py           # AgentState enum
├── agents/                # Subagent implementations
│   ├── acquisition.py     # Data Acquisition Agent
│   ├── architect.py       # Architect Agent
│   ├── qa.py              # QA Agent (risk assessment + tests)
│   ├── developer.py       # Developer Agent
│   └── reporting.py       # Reporting Agent
├── pipeline.py            # Pipeline builder with QA feedback loops
└── orchestrator.py        # Top-level Orchestrator facade
```

## Benchmarks

The project includes an orchestration benchmark suite that measures pipeline performance using deterministic mock responses (no API key needed):

```bash
# Run benchmarks
python -m benchmarks.run_benchmark --iterations 5

# Compare against baseline
python -m benchmarks.run_benchmark --iterations 5 --output current.json --compare benchmarks/baseline.json
```

Three scenarios are tested:
- **no_revisions** — happy path, all QA reviews pass
- **arch_revision** — QA blocks architecture, architect revises
- **code_revision** — QA blocks code (command injection), developer fixes

A GitHub Action runs benchmarks on every PR and posts comparison results as a comment.

## Development

```bash
# Install with dev dependencies
pip install -e ".[dev]"

# Run tests
pytest tests/ -v

# Run benchmarks
python -m benchmarks.run_benchmark
```

## License

MIT
