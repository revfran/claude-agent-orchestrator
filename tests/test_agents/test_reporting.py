import pytest
from unittest.mock import AsyncMock, MagicMock

from orchestrator.agents.reporting import ReportingAgent
from orchestrator.core.data_handler import DataHandler
from orchestrator.models.config import AgentConfig
from orchestrator.models.messages import Message


@pytest.fixture
def agent(mock_claude_client):
    a = ReportingAgent(
        AgentConfig(agent_id="rep", agent_type="reporting"),
        mock_claude_client,
    )
    a.data_handler = DataHandler()
    return a


async def test_generate_report(agent):
    msg = Message(
        source="qa",
        target="report_input",
        payload={
            "architecture": "Microservices design",
            "code": "def main(): pass",
            "test_cases": ["test_basic"],
            "query": "Build API",
            "risk_log": {"verdict": "approved"},
        },
    )
    result = await agent.process(msg)

    assert result is not None
    assert "report" in result
    assert result["query"] == "Build API"
    agent.claude.messages.create.assert_called_once()


async def test_report_stored_in_data_handler(agent):
    msg = Message(
        source="qa",
        target="report_input",
        payload={"architecture": "A", "code": "C", "test_cases": [], "query": "My Query", "risk_log": {}},
    )
    await agent.process(msg)

    stored = await agent.data_handler.read("report:My Query")
    assert stored is not None
