# Claude Agent Orchestrator

## Project

Python async framework for coordinating Claude-powered AI subagents. Uses asyncio queues for in-process messaging, pydantic for models, and the Anthropic SDK for Claude API calls.

## Commands

- `pip install -e ".[dev]"` — install with dev dependencies
- `pytest tests/ -v` — run tests (all mocked, no API key needed)
- `python -m benchmarks.run_benchmark` — run performance benchmarks

## Self-Review on Code Changes

When making code changes to this project, always run your own changes through the Quick Review pipeline (below) before reporting completion. This means:

1. After writing code, act as each agent role in sequence (Architect → QA → Developer → QA → Reporter → Verifier)
2. If tests fail, diagnose through the QA stages — never dismiss failures without investigation
3. Ensure documentation is updated to reflect the changes (the Developer and QA roles check for this)
4. End with the Verifier stage: run `pytest tests/ -v` and confirm 0 failures

This applies to all code changes, not just explicit review requests.

## Reviewing External Projects

This orchestrator can be used as a horizontal tool to review and improve code in **any** project. When a user asks to review an external project (or the current project), follow this workflow:

### How to Run a Review

```python
from orchestrator.review import scan_project, format_review_for_claude_code

# Scan the target project
ctx = scan_project("/path/to/target/project")

# Generate the structured review document
review = format_review_for_claude_code(ctx, focus="security")
# focus options: "general", "security", "performance", "quality"

# To review specific files only:
review = format_review_for_claude_code(ctx, focus="quality", files=["src/auth.py", "src/api.py"])
```

Then follow the generated review document stage by stage:

1. **Stage 1 — Data Acquisition**: Read the project context, summarize what the project does
2. **Stage 2 — Architecture Review**: Analyze the codebase structure, design patterns, coupling
3. **Stage 3 — QA Architecture Risk Assessment**: Identify architectural risks with severity levels, including documentation gaps. If HIGH risks are found, revise the architecture findings
4. **Stage 4 — Code Review**: Review individual files for bugs, vulnerabilities, quality issues. Also flag outdated or missing documentation
5. **Stage 5 — QA Code Risk Assessment**: Assess code risks, flag documentation gaps, and generate test cases. If HIGH risks are found, revise the code review
6. **Stage 6 — Final Report**: Compile all findings into a structured report with file:line references, concrete fixes, and a documentation update plan
7. **Stage 7 — How to Know the Changes Will Work**: Concrete verification checklist with commands to run, expected output, and regression signals

### Quick Review (no Python needed)

If the orchestrator is not installed, you can still follow the pipeline protocol manually:

1. Read the project's file structure and key files
2. Act as **Architect**: review the overall design, note concerns
3. Act as **QA Agent**: assess risks in the architecture (HIGH/MEDIUM/LOW severity)
4. If HIGH risks found: revise architectural recommendations
5. Act as **Developer**: review code file by file, find specific bugs and issues; flag outdated docs
6. Act as **QA Agent**: assess code risks, flag documentation gaps, suggest test cases
7. If HIGH risks found: revise code recommendations
8. Act as **Reporter**: compile a final report with prioritized action items and documentation updates
9. Act as **Verifier**: produce a concrete checklist the user can follow to confirm the changes work

## Architecture

See `docs/ARCHITECTURE.md` for the full technical architecture.

Key files:
- `src/orchestrator/core/agent_base.py` — BaseAgent ABC
- `src/orchestrator/core/communication.py` — MessageBus
- `src/orchestrator/core/logging_monitor.py` — Monitor with structured JSON event log
- `src/orchestrator/pipeline.py` — Pipeline with QA feedback loops
- `src/orchestrator/review.py` — Project scanner for external reviews

## Observability

The orchestrator emits structured JSON events via the `orchestrator.events` Python logger. To capture events to a file:

```python
import logging
fh = logging.FileHandler("events.jsonl")
logging.getLogger("orchestrator.events").addHandler(fh)
```

Watch live: `tail -f events.jsonl | jq .`

See `docs/ARCHITECTURE.md` § Observability for the full event catalog.
