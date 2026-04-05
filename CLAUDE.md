# Claude Agent Orchestrator

## Project

Python async framework for coordinating Claude-powered AI subagents. Uses asyncio queues for in-process messaging, pydantic for models, and the Anthropic SDK for Claude API calls.

## Commands

- `pip install -e ".[dev]"` — install with dev dependencies
- `pytest tests/ -v` — run tests (all mocked, no API key needed)
- `python -m benchmarks.run_benchmark` — run performance benchmarks

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
3. **Stage 3 — QA Architecture Risk Assessment**: Identify architectural risks with severity levels. If HIGH risks are found, revise the architecture findings
4. **Stage 4 — Code Review**: Review individual files for bugs, vulnerabilities, quality issues
5. **Stage 5 — QA Code Risk Assessment**: Assess code risks and generate test cases. If HIGH risks are found, revise the code review
6. **Stage 6 — Final Report**: Compile all findings into a structured report with file:line references and concrete fixes

### Quick Review (no Python needed)

If the orchestrator is not installed, you can still follow the pipeline protocol manually:

1. Read the project's file structure and key files
2. Act as **Architect**: review the overall design, note concerns
3. Act as **QA Agent**: assess risks in the architecture (HIGH/MEDIUM/LOW severity)
4. If HIGH risks found: revise architectural recommendations
5. Act as **Developer**: review code file by file, find specific bugs and issues
6. Act as **QA Agent**: assess code risks, suggest test cases
7. If HIGH risks found: revise code recommendations
8. Act as **Reporter**: compile a final report with prioritized action items

## Architecture

See `docs/ARCHITECTURE.md` for the full technical architecture.

Key files:
- `src/orchestrator/core/agent_base.py` — BaseAgent ABC
- `src/orchestrator/core/communication.py` — MessageBus
- `src/orchestrator/pipeline.py` — Pipeline with QA feedback loops
- `src/orchestrator/review.py` — Project scanner for external reviews
