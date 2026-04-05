"""
CI review runner — runs the orchestrator pipeline on PR changed files
and produces a markdown report for posting as a GitHub comment.

Usage:
    # Review changed files (reads from git diff)
    python -m orchestrator.ci --project . --focus security

    # Review specific files
    python -m orchestrator.ci --project . --files src/auth.py src/api.py

    # With API key: run full AI pipeline
    ANTHROPIC_API_KEY=sk-... python -m orchestrator.ci --project . --focus security

    # Output to file (for GitHub Actions)
    python -m orchestrator.ci --project . --output review.md
"""

import argparse
import asyncio
import json
import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from orchestrator.review import scan_project, generate_review_prompt


def get_pr_changed_files(project_path: str, base_ref: str = "origin/main") -> list[str]:
    """Get list of files changed in the current PR vs base branch."""
    try:
        result = subprocess.run(
            ["git", "diff", "--name-only", "--diff-filter=ACMR", base_ref],
            capture_output=True, text=True, cwd=project_path,
        )
        if result.returncode == 0:
            return [f.strip() for f in result.stdout.strip().split("\n") if f.strip()]
    except Exception:
        pass
    return []


def build_structural_report(project_path: str, focus: str, changed_files: list[str]) -> str:
    """Build a report based on structural analysis (no API key needed)."""
    ctx = scan_project(project_path)
    prompts = generate_review_prompt(ctx, focus=focus, files=changed_files or None)

    # Filter to changed files if available
    if changed_files:
        reviewed_files = [f for f in ctx.files if f.path in changed_files]
    else:
        reviewed_files = [f for f in ctx.files if f.category in ("code", "test")]

    # Language stats
    lang_summary = ", ".join(
        f"**{ext}** ({count})" for ext, count in sorted(ctx.language_stats.items())
    )

    # Build structural findings
    lines = [
        "## Orchestrator Review Report",
        "",
        "### Project Overview",
        f"- **Languages:** {lang_summary}",
        f"- **Total lines:** {ctx.total_lines:,}",
        f"- **Has tests:** {'Yes' if ctx.has_tests else 'No'}",
        f"- **Has CI:** {'Yes' if ctx.has_ci else 'No'}",
        f"- **Has Docker:** {'Yes' if ctx.has_docker else 'No'}",
        f"- **Review focus:** {focus}",
        "",
    ]

    if changed_files:
        lines.extend([
            "### Files Reviewed",
            "",
            *[f"- `{f}`" for f in changed_files[:50]],
            "",
        ])

    # Structural risk indicators
    risks = []

    for f in reviewed_files:
        if f.category != "code":
            continue
        content = f.content
        line_count = content.count("\n") + 1

        # Large files
        if line_count > 300:
            risks.append(
                f"- **[MEDIUM]** `{f.path}` is {line_count} lines — consider splitting"
            )

        # Security patterns
        if focus in ("security", "general"):
            for i, line in enumerate(content.split("\n"), 1):
                stripped = line.strip()
                lower = stripped.lower()
                # Skip comments and lines that are just string comparisons
                if stripped.startswith("#"):
                    continue
                # Count quotes to detect if patterns appear inside strings
                # If the pattern is preceded by a quote, it's a string reference
                def _is_actual_call(pattern: str, text: str) -> bool:
                    idx = text.find(pattern)
                    if idx < 0:
                        return False
                    before = text[:idx]
                    # If more opening quotes than closing before pattern, it's in a string
                    return before.count('"') % 2 == 0 and before.count("'") % 2 == 0

                if _is_actual_call("os.system(", lower) or (
                    _is_actual_call("subprocess.call(", lower) and "shell=true" in lower
                ):
                    risks.append(
                        f"- **[HIGH]** `{f.path}:{i}` — potential command injection"
                    )
                if _is_actual_call("eval(", lower):
                    risks.append(
                        f"- **[HIGH]** `{f.path}:{i}` — `eval()` usage, potential code injection"
                    )
                if _is_actual_call("password", lower) and ("=" in lower or ":" in lower):
                    if "getenv" not in lower and "environ" not in lower and "config" not in lower:
                        risks.append(
                            f"- **[MEDIUM]** `{f.path}:{i}` — possible hardcoded password"
                        )
                # Flag TODO/FIXME/HACK comments — but only actual comments,
                # not code that string-matches against them
                comment_pos = stripped.find("#")
                if comment_pos >= 0:
                    comment_text = stripped[comment_pos:].lower()
                    # Ensure # is not inside a string (even number of quotes before it)
                    before_hash = stripped[:comment_pos]
                    if before_hash.count('"') % 2 == 0 and before_hash.count("'") % 2 == 0:
                        if "# todo" in comment_text or "# fixme" in comment_text or "# hack" in comment_text:
                            risks.append(
                                f"- **[LOW]** `{f.path}:{i}` — `{stripped[:80]}`"
                            )

        # Quality patterns
        if focus in ("quality", "general"):
            for i, line in enumerate(content.split("\n"), 1):
                stripped = line.strip()
                # Skip comments and string literals
                if stripped.startswith("#") or stripped.startswith(("'", '"', "f'")):
                    continue
                if stripped == "except:" or stripped.startswith("except:"):
                    risks.append(
                        f"- **[MEDIUM]** `{f.path}:{i}` — bare `except:` catches all exceptions"
                    )
                if stripped.startswith("from ") and "import *" in stripped:
                    risks.append(
                        f"- **[LOW]** `{f.path}:{i}` — wildcard import"
                    )

    # Test coverage check
    code_files = {f.path for f in reviewed_files if f.category == "code"}
    test_files = {f.path for f in ctx.files if f.category == "test"}
    if code_files and not test_files:
        risks.append("- **[MEDIUM]** No test files found in the project")
    elif changed_files:
        changed_code = [f for f in changed_files if any(f.endswith(ext) for ext in (".py", ".js", ".ts", ".go", ".rs", ".java"))]
        changed_tests = [f for f in changed_files if "test" in f.lower()]
        if changed_code and not changed_tests:
            risks.append(
                "- **[LOW]** Code changes without corresponding test changes"
            )

    if risks:
        # Deduplicate and sort by severity
        seen = set()
        unique_risks = []
        for r in risks:
            if r not in seen:
                seen.add(r)
                unique_risks.append(r)

        severity_order = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}
        unique_risks.sort(key=lambda r: severity_order.get(
            r.split("**")[1] if "**" in r else "LOW", 3
        ))

        high_count = sum(1 for r in unique_risks if "[HIGH]" in r)
        med_count = sum(1 for r in unique_risks if "[MEDIUM]" in r)
        low_count = sum(1 for r in unique_risks if "[LOW]" in r)

        lines.extend([
            "### Risk Assessment",
            "",
            f"> **{high_count}** HIGH | **{med_count}** MEDIUM | **{low_count}** LOW",
            "",
            *unique_risks,
            "",
        ])
    else:
        lines.extend([
            "### Risk Assessment",
            "",
            "> No structural risks detected.",
            "",
        ])

    lines.extend([
        "---",
        f"*Structural analysis by [Claude Agent Orchestrator]"
        f"(https://github.com/revfran/claude-agent-orchestrator) "
        f"| Focus: {focus}*",
    ])

    return "\n".join(lines)


async def build_ai_report(
    project_path: str, focus: str, changed_files: list[str]
) -> str:
    """Run the full AI pipeline and produce a report (requires API key)."""
    from orchestrator.agents.acquisition import DataAcquisitionAgent
    from orchestrator.agents.architect import ArchitectAgent
    from orchestrator.agents.developer import DeveloperAgent
    from orchestrator.agents.qa import QAAgent
    from orchestrator.agents.reporting import ReportingAgent
    from orchestrator.models.config import AgentConfig, OrchestratorConfig
    from orchestrator.models.messages import Message
    from orchestrator.orchestrator import Orchestrator
    from orchestrator.pipeline import Pipeline

    ctx = scan_project(project_path)

    # Build file content summary for the query
    if changed_files:
        target_files = [f for f in ctx.files if f.path in changed_files]
    else:
        target_files = [f for f in ctx.files if f.category in ("code", "test")]

    file_summaries = "\n".join(
        f"--- {f.path} ---\n{f.content[:3000]}" for f in target_files[:20]
    )

    config = OrchestratorConfig()
    orch = Orchestrator(config)
    client = orch.agent_manager.claude_client

    pipe = Pipeline(orch)
    pipe.set_acquisition(DataAcquisitionAgent(
        AgentConfig(agent_id="acq", agent_type="acquisition",
                    system_prompt="You are a code reviewer. Analyze the project context."),
        client,
    ))
    pipe.set_architect(ArchitectAgent(
        AgentConfig(agent_id="arch", agent_type="architect",
                    system_prompt="You are a software architect reviewing code for design issues."),
        client,
    ))
    pipe.set_qa(QAAgent(
        AgentConfig(agent_id="qa", agent_type="qa", max_revisions=2,
                    system_prompt="You are a QA engineer. Identify risks with severity levels."),
        client,
    ))
    pipe.set_developer(DeveloperAgent(
        AgentConfig(agent_id="dev", agent_type="developer",
                    system_prompt="You are a senior developer. Suggest concrete fixes."),
        client,
    ))
    pipe.set_reporting(ReportingAgent(
        AgentConfig(agent_id="rep", agent_type="reporting",
                    system_prompt="You are a technical writer. Produce a concise PR review report in markdown."),
        client,
    ))
    input_channel = pipe.build()

    output_queue: asyncio.Queue = asyncio.Queue()
    orch.agent_manager.message_bus.subscribe("pipeline_output", output_queue)
    await orch.run()

    seed = Message(
        source="ci",
        target=input_channel,
        payload={
            "query": (
                f"Review this code with focus on {focus}. "
                f"Project: {project_path}\n"
                f"Changed files: {', '.join(changed_files) if changed_files else 'all'}\n\n"
                f"{file_summaries}"
            ),
            "sources": [f"Focus: {focus}"],
        },
    )
    await orch.agent_manager.message_bus.publish(input_channel, seed)

    result = await asyncio.wait_for(output_queue.get(), timeout=300)
    await orch.shutdown()

    report = result.payload.get("report", "No report generated.")

    lines = [
        "## Orchestrator Review Report",
        "",
        report,
        "",
        "---",
        f"*AI-powered review by [Claude Agent Orchestrator]"
        f"(https://github.com/revfran/claude-agent-orchestrator) "
        f"| Focus: {focus}*",
    ]
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Run orchestrator review on a project")
    parser.add_argument("--project", type=str, default=".", help="Project directory to review")
    parser.add_argument("--focus", type=str, default="general",
                        choices=["general", "security", "performance", "quality"],
                        help="Review focus area")
    parser.add_argument("--files", nargs="*", default=None, help="Specific files to review")
    parser.add_argument("--base-ref", type=str, default="origin/main",
                        help="Base branch for diff (default: origin/main)")
    parser.add_argument("--output", type=str, default=None, help="Output file for report")
    parser.add_argument("--mode", type=str, default="auto", choices=["auto", "structural", "ai"],
                        help="Review mode: structural (no API), ai (requires API key), auto (detect)")
    args = parser.parse_args()

    project_path = str(Path(args.project).resolve())

    # Determine changed files
    changed_files = args.files or get_pr_changed_files(project_path, args.base_ref)

    # Determine mode
    mode = args.mode
    if mode == "auto":
        mode = "ai" if os.environ.get("ANTHROPIC_API_KEY") else "structural"

    print(f"Review mode: {mode}")
    print(f"Focus: {args.focus}")
    print(f"Changed files: {len(changed_files)} files")

    if mode == "ai":
        report = asyncio.run(build_ai_report(project_path, args.focus, changed_files))
    else:
        report = build_structural_report(project_path, args.focus, changed_files)

    # Output
    print(report)
    if args.output:
        Path(args.output).write_text(report)
        print(f"\nReport saved to {args.output}")


if __name__ == "__main__":
    main()
