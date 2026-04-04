import pytest
from unittest.mock import AsyncMock, MagicMock

from orchestrator.agents.architect import ArchitectAgent
from orchestrator.core.logging_monitor import Monitor
from orchestrator.models.config import AgentConfig
from orchestrator.models.messages import Message


@pytest.fixture
def agent(mock_claude_client):
    a = ArchitectAgent(
        AgentConfig(agent_id="arch", agent_type="architect"),
        mock_claude_client,
    )
    a.monitor = Monitor(log_level="DEBUG")
    return a


async def test_initial_design(agent):
    msg = Message(
        source="acq",
        target="arch_input",
        payload={"query": "Build API", "requirements": "REST endpoints", "context": "web app"},
    )
    result = await agent.process(msg)

    assert result is not None
    assert "architecture" in result
    assert result["query"] == "Build API"
    assert result["revision_count"] == 0
    assert result["review_type"] == "architecture"


async def test_revision(agent):
    msg = Message(
        source="qa",
        target="arch_revision",
        payload={
            "risk_assessment": "Missing auth layer",
            "architecture": "Original design",
            "query": "Build API",
            "requirements": "REST endpoints",
        },
        msg_type="revision_request",
    )
    result = await agent.process(msg)

    assert result is not None
    assert result["revision_count"] == 1
    assert "addressed_risks" in result
    agent.claude.messages.create.assert_called_once()
