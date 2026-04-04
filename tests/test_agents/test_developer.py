import pytest
from unittest.mock import AsyncMock, MagicMock

from orchestrator.agents.developer import DeveloperAgent
from orchestrator.core.logging_monitor import Monitor
from orchestrator.models.config import AgentConfig
from orchestrator.models.messages import Message


@pytest.fixture
def agent(mock_claude_client):
    a = DeveloperAgent(
        AgentConfig(agent_id="dev", agent_type="developer"),
        mock_claude_client,
    )
    a.monitor = Monitor(log_level="DEBUG")
    return a


async def test_initial_implementation(agent):
    msg = Message(
        source="qa",
        target="dev_input",
        payload={"architecture": "Microservices", "query": "Build API", "requirements": "REST endpoints"},
    )
    result = await agent.process(msg)

    assert result is not None
    assert "code" in result
    assert result["query"] == "Build API"
    assert result["revision_count"] == 0
    assert result["review_type"] == "code"


async def test_revision(agent):
    msg = Message(
        source="qa",
        target="code_revision",
        payload={
            "code_risks": "SQL injection vulnerability",
            "test_cases": ["test_sql_injection"],
            "code": "original code",
            "query": "Build API",
            "architecture": "Design",
        },
        msg_type="revision_request",
    )
    result = await agent.process(msg)

    assert result is not None
    assert result["revision_count"] == 1
    assert "addressed_risks" in result


async def test_multiple_revisions(agent):
    for i in range(3):
        msg = Message(
            source="qa",
            target="code_revision",
            payload={
                "code_risks": f"Risk {i}",
                "test_cases": [],
                "code": "code",
                "query": "Q",
                "architecture": "A",
            },
            msg_type="revision_request",
        )
        result = await agent.process(msg)
        assert result["revision_count"] == i + 1
