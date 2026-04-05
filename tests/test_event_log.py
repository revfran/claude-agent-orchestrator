"""Verify structured JSON event logging through a full pipeline run."""

import asyncio
import json
import logging

import pytest
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


def make_mock_client(responses):
    client = AsyncMock()
    side_effects = []
    for text in responses:
        resp = MagicMock()
        resp.content = [MagicMock(text=text)]
        resp.usage = MagicMock(input_tokens=100, output_tokens=50)
        side_effects.append(resp)
    client.messages.create = AsyncMock(side_effect=side_effects)
    return client


def qa_approved():
    return json.dumps({
        "risk_items": [],
        "has_blocking_risks": False,
        "test_cases": ["test_basic"],
        "summary": "Approved.",
    })


def qa_rejected():
    return json.dumps({
        "risk_items": [{"description": "Missing auth", "severity": "HIGH", "recommendation": "Add auth"}],
        "has_blocking_risks": True,
        "test_cases": [],
        "summary": "Blocking risks.",
    })


@patch("orchestrator.core.agent_manager.anthropic.AsyncAnthropic")
async def test_event_log_captures_full_pipeline(mock_anthropic, tmp_path):
    """Run a pipeline with one arch revision, capture events to a JSONL file,
    and verify the expected event sequence appears."""

    log_file = tmp_path / "events.jsonl"

    # Attach a FileHandler to orchestrator.events
    event_logger = logging.getLogger("orchestrator.events")
    fh = logging.FileHandler(str(log_file))
    fh.setLevel(logging.DEBUG)
    # Use the same JSON formatter the Monitor installs
    from orchestrator.core.logging_monitor import _JsonFormatter
    fh.setFormatter(_JsonFormatter())
    event_logger.addHandler(fh)

    try:
        config = OrchestratorConfig(anthropic_api_key="test")
        orch = Orchestrator(config)

        responses = [
            "Requirements gathered",           # acquisition
            "Architecture v1",                  # architect initial
            qa_rejected(),                      # QA arch review → reject
            "Architecture v2 with auth",        # architect revision
            qa_approved(),                      # QA arch review → approve
            "Code implementation",              # developer
            qa_approved(),                      # QA code review → approve
            "# Final Report",                   # reporting
        ]
        client = make_mock_client(responses)

        pipe = Pipeline(orch)
        pipe.set_acquisition(DataAcquisitionAgent(AgentConfig(agent_id="acq", agent_type="acquisition"), client))
        pipe.set_architect(ArchitectAgent(AgentConfig(agent_id="arch", agent_type="architect"), client))
        pipe.set_qa(QAAgent(AgentConfig(agent_id="qa", agent_type="qa", max_revisions=2), client))
        pipe.set_developer(DeveloperAgent(AgentConfig(agent_id="dev", agent_type="developer"), client))
        pipe.set_reporting(ReportingAgent(AgentConfig(agent_id="rep", agent_type="reporting"), client))
        input_channel = pipe.build()

        output_queue: asyncio.Queue = asyncio.Queue()
        orch.agent_manager.message_bus.subscribe("pipeline_output", output_queue)

        await orch.run()

        seed = Message(source="user", target=input_channel, payload={"query": "Build API", "sources": []})
        await orch.agent_manager.message_bus.publish(input_channel, seed)

        result = await asyncio.wait_for(output_queue.get(), timeout=5.0)
        assert "report" in result.payload

        await orch.shutdown()

        # Flush the handler so everything is written
        fh.flush()

        # Parse the JSONL file
        lines = log_file.read_text().strip().splitlines()
        events = [json.loads(line) for line in lines]
        event_names = [e["event"] for e in events]

        # --- Verify expected event sequence ---

        # Orchestrator lifecycle
        assert "orchestrator_starting" in event_names
        assert "orchestrator_ready" in event_names
        assert "orchestrator_shutdown" in event_names

        # All 5 agents started and stopped
        started = [e for e in events if e["event"] == "agent_started"]
        stopped = [e for e in events if e["event"] == "agent_stopped"]
        assert {e["agent"] for e in started} == {"acq", "arch", "qa", "dev", "rep"}
        assert {e["agent"] for e in stopped} == {"acq", "arch", "qa", "dev", "rep"}

        # Messages flowed through the bus
        assert "bus_route" in event_names
        assert "message_received" in event_names
        assert "message_published" in event_names
        assert "message_processed" in event_names

        # Claude API calls tracked with tokens
        api_calls = [e for e in events if e["event"] == "claude_api_call"]
        assert len(api_calls) == 8  # one per mock response
        assert all(e["input_tokens"] == 100 for e in api_calls)
        assert all(e["output_tokens"] == 50 for e in api_calls)

        # QA gate decisions: one rejection, then approval for arch; one approval for code
        rejected = [e for e in events if e["event"] == "qa_gate_rejected"]
        approved = [e for e in events if e["event"] == "qa_gate_approved"]
        assert len(rejected) == 1
        assert rejected[0]["review_type"] == "architecture"
        assert len(approved) == 2
        assert {e["review_type"] for e in approved} == {"architecture", "code"}

        # Revision loop
        revision_started = [e for e in events if e["event"] == "revision_started"]
        assert len(revision_started) >= 1
        assert revision_started[0]["agent"] == "arch"
        assert "revision_triggered" in event_names

        # Every event has a timestamp and level
        for e in events:
            assert "ts" in e
            assert "level" in e

        # Shutdown event has metrics summary
        shutdown = [e for e in events if e["event"] == "orchestrator_shutdown"][0]
        assert "metrics" in shutdown
        assert "acq" in shutdown["metrics"]

    finally:
        event_logger.removeHandler(fh)
        fh.close()


@patch("orchestrator.core.agent_manager.anthropic.AsyncAnthropic")
async def test_event_log_valid_jsonl(mock_anthropic, tmp_path):
    """Every line in the event log must be valid JSON (parseable by jq)."""

    log_file = tmp_path / "events.jsonl"
    event_logger = logging.getLogger("orchestrator.events")
    from orchestrator.core.logging_monitor import _JsonFormatter
    fh = logging.FileHandler(str(log_file))
    fh.setFormatter(_JsonFormatter())
    event_logger.addHandler(fh)

    try:
        config = OrchestratorConfig(anthropic_api_key="test")
        orch = Orchestrator(config)

        responses = [
            "Reqs", "Arch", qa_approved(), "Code", qa_approved(), "Report",
        ]
        client = make_mock_client(responses)

        pipe = Pipeline(orch)
        pipe.set_acquisition(DataAcquisitionAgent(AgentConfig(agent_id="acq", agent_type="acquisition"), client))
        pipe.set_architect(ArchitectAgent(AgentConfig(agent_id="arch", agent_type="architect"), client))
        pipe.set_qa(QAAgent(AgentConfig(agent_id="qa", agent_type="qa"), client))
        pipe.set_developer(DeveloperAgent(AgentConfig(agent_id="dev", agent_type="developer"), client))
        pipe.set_reporting(ReportingAgent(AgentConfig(agent_id="rep", agent_type="reporting"), client))
        input_channel = pipe.build()

        output_queue: asyncio.Queue = asyncio.Queue()
        orch.agent_manager.message_bus.subscribe("pipeline_output", output_queue)
        await orch.run()

        seed = Message(source="user", target=input_channel, payload={"query": "Test", "sources": []})
        await orch.agent_manager.message_bus.publish(input_channel, seed)
        await asyncio.wait_for(output_queue.get(), timeout=5.0)
        await orch.shutdown()

        fh.flush()
        lines = log_file.read_text().strip().splitlines()

        # Every line must be valid JSON
        assert len(lines) > 0, "No events were logged"
        for i, line in enumerate(lines):
            try:
                json.loads(line)
            except json.JSONDecodeError:
                pytest.fail(f"Line {i+1} is not valid JSON: {line[:200]}")

    finally:
        event_logger.removeHandler(fh)
        fh.close()
