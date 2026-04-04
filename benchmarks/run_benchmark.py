"""
Orchestration performance benchmark.

Measures pipeline latency, per-agent processing time, message throughput,
and QA feedback loop behavior using deterministic mock responses.
No API key required — all Claude calls are mocked.

Usage:
    python -m benchmarks.run_benchmark
    python -m benchmarks.run_benchmark --iterations 5 --output results.json
"""

import argparse
import asyncio
import json
import statistics
import sys
import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from orchestrator.agents.acquisition import DataAcquisitionAgent
from orchestrator.agents.architect import ArchitectAgent
from orchestrator.agents.developer import DeveloperAgent
from orchestrator.agents.qa import QAAgent
from orchestrator.agents.reporting import ReportingAgent
from orchestrator.models.config import AgentConfig, OrchestratorConfig
from orchestrator.models.messages import Message
from orchestrator.orchestrator import Orchestrator
from orchestrator.pipeline import Pipeline

# ---------------------------------------------------------------------------
# Fixed mock responses — deterministic across runs
# ---------------------------------------------------------------------------

MOCK_RESPONSES = {
    # Scenario 1: happy path (no revisions)
    "no_revisions": [
        # acquisition
        "Requirements: The system needs a user authentication module with JWT tokens, "
        "rate limiting, and role-based access control.",
        # architect
        "Architecture: Three-layer design with API gateway, auth service, and user store. "
        "JWT for stateless auth, Redis for rate limiting, PostgreSQL for user data.",
        # QA arch review — approved
        '{"risk_items": [{"description": "Redis single point of failure", '
        '"severity": "LOW", "recommendation": "Add Redis sentinel"}], '
        '"has_blocking_risks": false, "summary": "Architecture is sound."}',
        # developer
        "```python\nfrom fastapi import FastAPI, Depends\n"
        "from auth import verify_jwt, check_role\n\n"
        "app = FastAPI()\n\n"
        "@app.get('/users')\n"
        "async def list_users(user=Depends(verify_jwt)):\n"
        "    return await get_users()\n```",
        # QA code review — approved
        '{"risk_items": [{"description": "Missing input validation", '
        '"severity": "LOW", "recommendation": "Add pydantic models"}], '
        '"has_blocking_risks": false, '
        '"test_cases": ["test_auth_required", "test_role_check"], '
        '"summary": "Code is acceptable."}',
        # reporting
        "# Final Report\n## Architecture\nThree-layer design approved.\n"
        "## Implementation\nFastAPI with JWT auth.\n"
        "## Risks\nAll LOW severity, documented.\n"
        "## Tests\n2 test cases generated.",
    ],
    # Scenario 2: one architecture revision
    "arch_revision": [
        # acquisition
        "Requirements: Payment processing system with PCI compliance.",
        # architect initial
        "Architecture: Monolithic payment service storing card numbers in plaintext.",
        # QA arch review — BLOCKED
        '{"risk_items": [{"description": "Plaintext card storage violates PCI-DSS", '
        '"severity": "HIGH", "recommendation": "Use tokenization and encrypt at rest"}], '
        '"has_blocking_risks": true, "summary": "Critical security risk."}',
        # architect revision
        "Revised Architecture: Payment service with Stripe tokenization. "
        "No raw card data stored. PCI-DSS compliant vault for tokens.",
        # QA arch review — approved
        '{"risk_items": [{"description": "Stripe dependency", '
        '"severity": "LOW", "recommendation": "Add fallback provider"}], '
        '"has_blocking_risks": false, "summary": "Risks addressed."}',
        # developer
        "```python\nimport stripe\n\nasync def charge(token, amount):\n"
        "    return stripe.Charge.create(source=token, amount=amount)\n```",
        # QA code review — approved
        '{"risk_items": [], "has_blocking_risks": false, '
        '"test_cases": ["test_charge_success", "test_charge_failure"], '
        '"summary": "Secure implementation."}',
        # reporting
        "# Report\n## Revisions: 1 architecture revision (PCI compliance fix)\n"
        "## Final: Stripe tokenization approach approved.",
    ],
    # Scenario 3: code revision
    "code_revision": [
        # acquisition
        "Requirements: File upload service with virus scanning.",
        # architect
        "Architecture: S3 upload with Lambda virus scan trigger.",
        # QA arch review — approved
        '{"risk_items": [], "has_blocking_risks": false, "summary": "Good design."}',
        # developer initial
        "```python\ndef upload(file):\n    os.system(f'mv {file.name} /uploads/')\n```",
        # QA code review — BLOCKED (command injection)
        '{"risk_items": [{"description": "OS command injection via filename", '
        '"severity": "HIGH", "recommendation": "Use shutil.move with sanitized paths"}], '
        '"has_blocking_risks": true, '
        '"test_cases": ["test_malicious_filename", "test_path_traversal"], '
        '"summary": "Critical vulnerability."}',
        # developer revision
        "```python\nimport shutil\nfrom pathlib import Path\n\n"
        "def upload(file):\n    safe_name = Path(file.name).name\n"
        "    shutil.move(file, Path('/uploads') / safe_name)\n```",
        # QA code review — approved
        '{"risk_items": [], "has_blocking_risks": false, '
        '"test_cases": ["test_safe_upload", "test_malicious_filename"], '
        '"summary": "Vulnerability fixed."}',
        # reporting
        "# Report\n## Revisions: 1 code revision (command injection fix)\n"
        "## Tests: 2 security test cases.",
    ],
}

SEED_QUERIES = {
    "no_revisions": {
        "query": "Design a user authentication module with JWT and RBAC",
        "sources": ["OWASP guidelines", "JWT best practices"],
    },
    "arch_revision": {
        "query": "Build a PCI-compliant payment processing system",
        "sources": ["PCI-DSS standards", "payment industry docs"],
    },
    "code_revision": {
        "query": "Create a secure file upload service with virus scanning",
        "sources": ["security best practices", "cloud architecture patterns"],
    },
}


def make_mock_client(responses: list[str]):
    """Create a mock Claude client returning predefined responses in order."""
    client = AsyncMock()
    side_effects = []
    for text in responses:
        resp = MagicMock()
        resp.content = [MagicMock(text=text)]
        resp.usage = MagicMock(input_tokens=100, output_tokens=len(text) // 4)
        side_effects.append(resp)
    client.messages.create = AsyncMock(side_effect=side_effects)
    return client


def build_pipeline(scenario: str):
    """Build a full pipeline for a given scenario."""
    responses = MOCK_RESPONSES[scenario]
    client = make_mock_client(responses)

    config = OrchestratorConfig(anthropic_api_key="benchmark-mock")
    with patch("orchestrator.core.agent_manager.anthropic.AsyncAnthropic"):
        orch = Orchestrator(config)

    pipe = Pipeline(orch)
    pipe.set_acquisition(
        DataAcquisitionAgent(
            AgentConfig(agent_id="acq", agent_type="acquisition"), client
        )
    )
    pipe.set_architect(
        ArchitectAgent(
            AgentConfig(agent_id="arch", agent_type="architect"), client
        )
    )
    pipe.set_qa(
        QAAgent(
            AgentConfig(agent_id="qa", agent_type="qa", max_revisions=2), client
        )
    )
    pipe.set_developer(
        DeveloperAgent(
            AgentConfig(agent_id="dev", agent_type="developer"), client
        )
    )
    pipe.set_reporting(
        ReportingAgent(
            AgentConfig(agent_id="rep", agent_type="reporting"), client
        )
    )
    input_channel = pipe.build()
    return orch, input_channel


async def run_scenario(scenario: str) -> dict:
    """Run a single benchmark scenario, return metrics."""
    orch, input_channel = build_pipeline(scenario)

    output_queue: asyncio.Queue = asyncio.Queue()
    orch.agent_manager.message_bus.subscribe("pipeline_output", output_queue)

    start = time.monotonic()
    await orch.run()

    seed = Message(
        source="benchmark",
        target=input_channel,
        payload=SEED_QUERIES[scenario],
    )
    await orch.agent_manager.message_bus.publish(input_channel, seed)

    result = await asyncio.wait_for(output_queue.get(), timeout=10.0)
    elapsed_ms = (time.monotonic() - start) * 1000

    await orch.shutdown()

    agent_metrics = orch.monitor.summary()
    total_messages = sum(m["messages_processed"] for m in agent_metrics.values())
    total_revisions = sum(m["revisions_triggered"] for m in agent_metrics.values())

    return {
        "scenario": scenario,
        "total_time_ms": round(elapsed_ms, 2),
        "total_messages_processed": total_messages,
        "total_revisions": total_revisions,
        "has_report": "report" in result.payload,
        "agent_metrics": agent_metrics,
    }


async def run_benchmark(iterations: int = 3) -> dict:
    """Run all scenarios multiple times and compute stats."""
    all_results: dict[str, list[dict]] = {}

    for scenario in MOCK_RESPONSES:
        all_results[scenario] = []
        for _ in range(iterations):
            result = await run_scenario(scenario)
            all_results[scenario].append(result)

    # Aggregate
    summary = {}
    for scenario, runs in all_results.items():
        times = [r["total_time_ms"] for r in runs]
        summary[scenario] = {
            "iterations": iterations,
            "total_time_ms": {
                "mean": round(statistics.mean(times), 2),
                "median": round(statistics.median(times), 2),
                "stdev": round(statistics.stdev(times), 2) if len(times) > 1 else 0,
                "min": round(min(times), 2),
                "max": round(max(times), 2),
            },
            "total_messages_processed": runs[0]["total_messages_processed"],
            "total_revisions": runs[0]["total_revisions"],
            "all_passed": all(r["has_report"] for r in runs),
            "agent_metrics": runs[0]["agent_metrics"],
        }

    return summary


def compare_results(current: dict, baseline: dict) -> str:
    """Generate a markdown comparison table."""
    lines = [
        "## Benchmark Results",
        "",
        "| Scenario | Metric | Baseline | Current | Delta |",
        "|----------|--------|----------|---------|-------|",
    ]

    for scenario in current:
        if scenario not in baseline:
            lines.append(f"| **{scenario}** | | _new scenario_ | | |")
            continue

        cur = current[scenario]
        base = baseline[scenario]

        cur_mean = cur["total_time_ms"]["mean"]
        base_mean = base["total_time_ms"]["mean"]
        delta_ms = cur_mean - base_mean
        delta_pct = (delta_ms / base_mean * 100) if base_mean > 0 else 0
        indicator = "+" if delta_ms > 0 else ""

        lines.append(
            f"| **{scenario}** | Total time (mean) | "
            f"{base_mean:.1f}ms | {cur_mean:.1f}ms | "
            f"{indicator}{delta_pct:.1f}% |"
        )
        lines.append(
            f"| | Messages | "
            f"{base['total_messages_processed']} | {cur['total_messages_processed']} | "
            f"{'=' if base['total_messages_processed'] == cur['total_messages_processed'] else 'changed'} |"
        )
        lines.append(
            f"| | Revisions | "
            f"{base['total_revisions']} | {cur['total_revisions']} | "
            f"{'=' if base['total_revisions'] == cur['total_revisions'] else 'changed'} |"
        )
        lines.append(
            f"| | All passed | "
            f"{'yes' if base['all_passed'] else 'NO'} | "
            f"{'yes' if cur['all_passed'] else 'NO'} | |"
        )

    # Overall assessment
    regressions = []
    for scenario in current:
        if scenario in baseline:
            cur_mean = current[scenario]["total_time_ms"]["mean"]
            base_mean = baseline[scenario]["total_time_ms"]["mean"]
            # Flag if >50% slower (generous threshold for mock-based timing)
            if cur_mean > base_mean * 1.5 and (cur_mean - base_mean) > 5:
                regressions.append(scenario)
            if not current[scenario]["all_passed"]:
                regressions.append(f"{scenario} (failures)")

    lines.append("")
    if regressions:
        lines.append(f"**Regressions detected:** {', '.join(regressions)}")
    else:
        lines.append("**No regressions detected.**")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Run orchestration benchmarks")
    parser.add_argument(
        "--iterations", type=int, default=3, help="Number of iterations per scenario"
    )
    parser.add_argument(
        "--output", type=str, default=None, help="Output JSON file path"
    )
    parser.add_argument(
        "--compare", type=str, default=None, help="Baseline JSON to compare against"
    )
    args = parser.parse_args()

    results = asyncio.run(run_benchmark(args.iterations))

    # Print summary
    print("=" * 60)
    print("BENCHMARK RESULTS")
    print("=" * 60)
    for scenario, data in results.items():
        t = data["total_time_ms"]
        print(f"\n  {scenario}:")
        print(f"    Time: {t['mean']:.1f}ms mean ({t['min']:.1f}-{t['max']:.1f}ms)")
        print(f"    Messages: {data['total_messages_processed']}")
        print(f"    Revisions: {data['total_revisions']}")
        print(f"    Passed: {data['all_passed']}")

    # Save results
    if args.output:
        output_path = Path(args.output)
        output_path.write_text(json.dumps(results, indent=2))
        print(f"\nResults saved to {output_path}")

    # Compare against baseline
    if args.compare:
        baseline_path = Path(args.compare)
        if baseline_path.exists():
            baseline = json.loads(baseline_path.read_text())
            comparison = compare_results(results, baseline)
            print(f"\n{comparison}")

            # Write comparison markdown for CI
            comparison_path = Path(args.output or "benchmark_results.json").with_suffix(
                ".md"
            )
            comparison_path.write_text(comparison)
            print(f"Comparison saved to {comparison_path}")
        else:
            print(f"\nBaseline file not found: {baseline_path}")

    return results


if __name__ == "__main__":
    main()
