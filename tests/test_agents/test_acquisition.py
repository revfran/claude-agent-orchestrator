import pytest
from unittest.mock import AsyncMock, MagicMock

from orchestrator.agents.acquisition import DataAcquisitionAgent
from orchestrator.models.config import AgentConfig
from orchestrator.models.messages import Message


@pytest.fixture
def agent(mock_claude_client):
    return DataAcquisitionAgent(
        AgentConfig(agent_id="acq", agent_type="acquisition", system_prompt="Gather data."),
        mock_claude_client,
    )


async def test_process(agent):
    msg = Message(
        source="user",
        target="pipeline_input",
        payload={"query": "Build a REST API", "sources": ["docs", "standards"]},
    )
    result = await agent.process(msg)

    assert result is not None
    assert result["query"] == "Build a REST API"
    assert "requirements" in result
    assert "context" in result
    agent.claude.messages.create.assert_called_once()


async def test_process_no_sources(agent):
    msg = Message(
        source="user",
        target="pipeline_input",
        payload={"query": "Simple task"},
    )
    result = await agent.process(msg)

    assert result is not None
    assert result["query"] == "Simple task"
