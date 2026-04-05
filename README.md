# Claude Agent Orchestrator

A horizontal tool for reviewing and improving code in **any** project. It coordinates Claude-powered AI subagents in a pipeline with QA feedback loops — an Architect reviews design, a QA agent assesses risks, a Developer suggests fixes, and a Reporter compiles actionable findings.

Works with **Claude Code Pro/Max subscriptions** (no API key needed) or with a direct Anthropic API key.

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

All 44 tests use mocked Claude responses — no API key or subscription needed.

## Reviewing Any Project (Claude Code Pro/Max)

The primary use case: point the orchestrator at **any codebase** and get a structured review with risk assessments and concrete fixes. No API key needed — Claude Code is the AI.

### From Any Project Directory

Open Claude Code in the project you want to review, then:

```
> Use the orchestrator at ~/claude-agent-orchestrator to review this project for security issues
```

Claude Code will read the `CLAUDE.md` from the orchestrator repo, scan your project files, and follow the 6-stage pipeline:

1. **Data Acquisition** — scan project structure, languages, configs
2. **Architecture Review** — analyze design patterns, coupling, separation of concerns
3. **QA Risk Assessment** — classify risks as HIGH/MEDIUM/LOW, flag blockers
4. **Code Review** — find bugs, vulnerabilities, quality issues with file:line references
5. **QA Code Assessment** — assess code risks, generate test cases
6. **Final Report** — prioritized action items with concrete fixes

### Programmatic Usage

You can also use the scanner directly from Python:

```python
from orchestrator.review import scan_project, format_review_for_claude_code

# Scan any project
ctx = scan_project("/path/to/any/project")

# Generate the full review document
review = format_review_for_claude_code(ctx, focus="security")
# focus options: "general", "security", "performance", "quality"

# Or review specific files only
review = format_review_for_claude_code(ctx, focus="quality", files=["src/auth.py"])
```

### Focus Areas

| Focus | What it checks |
|-------|---------------|
| `general` | Overall code quality, maintainability, correctness |
| `security` | Injection, auth issues, data exposure, OWASP Top 10 |
| `performance` | N+1 queries, blocking calls, resource leaks, complexity |
| `quality` | DRY violations, naming, error handling, test coverage |

### With an Anthropic API Key

If you have a direct API key, you can also run the full async pipeline:

```bash
export ANTHROPIC_API_KEY=sk-ant-...
python -m examples.demo_pipeline
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
├── orchestrator.py        # Top-level Orchestrator facade
└── review.py              # Project scanner for reviewing external codebases
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
