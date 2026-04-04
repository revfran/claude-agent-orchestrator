import asyncio
import json

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


def make_mock_client(responses=None):
    """Create a mock Claude client that returns predefined responses."""
    client = AsyncMock()
    if responses:
        side_effects = []
        for text in responses:
            resp = MagicMock()
            resp.content = [MagicMock(text=text)]
            side_effects.append(resp)
        client.messages.create = AsyncMock(side_effect=side_effects)
    else:
        resp = MagicMock()
        resp.content = [MagicMock(text="Mock response")]
        client.messages.create = AsyncMock(return_value=resp)
    return client


def qa_approved_response():
    """QA response that approves without blocking risks."""
    return json.dumps({
        "risk_items": [{"description": "Minor style issue", "severity": "LOW", "recommendation": "Consider refactoring"}],
        "has_blocking_risks": False,
        "test_cases": ["test_basic_functionality"],
        "summary": "No blocking risks found.",
    })


@patch("orchestrator.core.agent_manager.anthropic.AsyncAnthropic")
async def test_pipeline_build(mock_anthropic):
    config = OrchestratorConfig(anthropic_api_key="test")
    orch = Orchestrator(config)
    client = AsyncMock()

    pipe = Pipeline(orch)
    pipe.set_acquisition(DataAcquisitionAgent(AgentConfig(agent_id="acq", agent_type="acquisition"), client))
    pipe.set_architect(ArchitectAgent(AgentConfig(agent_id="arch", agent_type="architect"), client))
    pipe.set_qa(QAAgent(AgentConfig(agent_id="qa", agent_type="qa"), client))
    pipe.set_developer(DeveloperAgent(AgentConfig(agent_id="dev", agent_type="developer"), client))
    pipe.set_reporting(ReportingAgent(AgentConfig(agent_id="rep", agent_type="reporting"), client))

    input_channel = pipe.build()

    assert input_channel == "pipeline_input"
    assert len(orch.agent_manager.agents) == 5


@patch("orchestrator.core.agent_manager.anthropic.AsyncAnthropic")
async def test_pipeline_missing_agents(mock_anthropic):
    config = OrchestratorConfig(anthropic_api_key="test")
    orch = Orchestrator(config)
    pipe = Pipeline(orch)

    with pytest.raises(ValueError, match="All 5 agents must be set"):
        pipe.build()


@patch("orchestrator.core.agent_manager.anthropic.AsyncAnthropic")
async def test_full_pipeline_no_revisions(mock_anthropic):
    """End-to-end test: all QA reviews pass, no revisions needed."""
    config = OrchestratorConfig(anthropic_api_key="test")
    orch = Orchestrator(config)

    # Mock client returns: acquisition, architect, QA arch review (approved),
    # developer, QA code review (approved), reporting
    responses = [
        "Requirements: build a REST API",       # acquisition
        "Architecture: microservices design",     # architect
        qa_approved_response(),                   # QA arch review
        "Code: def main(): pass",                 # developer
        qa_approved_response(),                   # QA code review
        "# Final Report\nEverything looks good.", # reporting
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

    seed = Message(
        source="user",
        target=input_channel,
        payload={"query": "Build a REST API", "sources": ["docs"]},
    )
    await orch.agent_manager.message_bus.publish(input_channel, seed)

    result = await asyncio.wait_for(output_queue.get(), timeout=5.0)
    assert "report" in result.payload
    assert "Final Report" in result.payload["report"]

    await orch.shutdown()


@patch("orchestrator.core.agent_manager.anthropic.AsyncAnthropic")
async def test_full_pipeline_with_arch_revision(mock_anthropic):
    """End-to-end test: QA finds architecture risks, architect revises once."""
    config = OrchestratorConfig(anthropic_api_key="test")
    orch = Orchestrator(config)

    qa_needs_revision = json.dumps({
        "risk_items": [{"description": "No auth layer", "severity": "HIGH", "recommendation": "Add JWT auth"}],
        "has_blocking_risks": True,
        "test_cases": [],
        "summary": "Blocking risks found.",
    })

    responses = [
        "Requirements gathered",                  # acquisition
        "Architecture v1",                         # architect initial
        qa_needs_revision,                         # QA arch review (needs revision)
        "Architecture v2 with auth",               # architect revision
        qa_approved_response(),                    # QA arch review (approved)
        "Code implementation",                     # developer
        qa_approved_response(),                    # QA code review (approved)
        "# Report with revision history",          # reporting
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

    # Verify architect was called twice (initial + revision)
    assert client.messages.create.call_count == 8

    await orch.shutdown()
