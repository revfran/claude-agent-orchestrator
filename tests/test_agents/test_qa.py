import asyncio
import json

import pytest
from unittest.mock import AsyncMock, MagicMock

from orchestrator.agents.qa import QAAgent
from orchestrator.core.communication import MessageBus
from orchestrator.core.data_handler import DataHandler
from orchestrator.models.config import AgentConfig
from orchestrator.models.messages import Message


def make_qa_agent(mock_claude_client, max_revisions=2):
    agent = QAAgent(
        AgentConfig(agent_id="qa", agent_type="qa", max_revisions=max_revisions),
        mock_claude_client,
    )
    agent._message_bus = MessageBus()
    agent.data_handler = DataHandler()
    return agent


def set_claude_response(client, text):
    resp = MagicMock()
    resp.content = [MagicMock(text=text)]
    client.messages.create = AsyncMock(return_value=resp)


async def test_arch_review_approved(mock_claude_client):
    agent = make_qa_agent(mock_claude_client)

    approved = json.dumps({
        "risk_items": [],
        "has_blocking_risks": False,
        "summary": "Looks good",
    })
    set_claude_response(mock_claude_client, approved)

    # Subscribe to dev_input to catch forwarded message
    dev_queue: asyncio.Queue = asyncio.Queue()
    agent._message_bus.subscribe("dev_input", dev_queue)

    msg = Message(
        source="arch",
        target="arch_review",
        payload={"architecture": "Design A", "query": "Build API", "requirements": "REST", "review_type": "architecture", "revision_count": 0},
    )
    result = await agent.process(msg)
    assert result is None  # QA routes manually

    forwarded = await asyncio.wait_for(dev_queue.get(), timeout=1.0)
    assert forwarded.payload["architecture"] == "Design A"


async def test_arch_review_needs_revision(mock_claude_client):
    agent = make_qa_agent(mock_claude_client)

    needs_revision = json.dumps({
        "risk_items": [{"description": "No auth", "severity": "HIGH", "recommendation": "Add auth"}],
        "has_blocking_risks": True,
        "summary": "Blocking risks",
    })
    set_claude_response(mock_claude_client, needs_revision)

    revision_queue: asyncio.Queue = asyncio.Queue()
    agent._message_bus.subscribe("arch_revision", revision_queue)

    msg = Message(
        source="arch",
        target="arch_review",
        payload={"architecture": "Design A", "query": "Build API", "requirements": "REST", "review_type": "architecture", "revision_count": 0},
    )
    await agent.process(msg)

    forwarded = await asyncio.wait_for(revision_queue.get(), timeout=1.0)
    assert forwarded.msg_type == "revision_request"
    assert "risk_assessment" in forwarded.payload


async def test_arch_review_max_revisions_reached(mock_claude_client):
    agent = make_qa_agent(mock_claude_client, max_revisions=1)

    needs_revision = json.dumps({
        "risk_items": [{"description": "Still risky", "severity": "HIGH", "recommendation": "Fix it"}],
        "has_blocking_risks": True,
        "summary": "Still blocking",
    })
    set_claude_response(mock_claude_client, needs_revision)

    dev_queue: asyncio.Queue = asyncio.Queue()
    agent._message_bus.subscribe("dev_input", dev_queue)

    msg = Message(
        source="arch",
        target="arch_review",
        payload={"architecture": "Design B", "query": "Build API", "requirements": "REST", "review_type": "architecture", "revision_count": 1},
    )
    await agent.process(msg)

    # Should forward to dev despite risks since max revisions reached
    forwarded = await asyncio.wait_for(dev_queue.get(), timeout=1.0)
    assert forwarded.payload["architecture"] == "Design B"


async def test_code_review_approved(mock_claude_client):
    agent = make_qa_agent(mock_claude_client)

    approved = json.dumps({
        "risk_items": [],
        "has_blocking_risks": False,
        "test_cases": ["test_login", "test_signup"],
        "summary": "Code looks good",
    })
    set_claude_response(mock_claude_client, approved)

    report_queue: asyncio.Queue = asyncio.Queue()
    agent._message_bus.subscribe("report_input", report_queue)

    msg = Message(
        source="dev",
        target="code_review",
        payload={"code": "def main(): pass", "query": "Build API", "architecture": "Design A", "review_type": "code", "revision_count": 0},
    )
    await agent.process(msg)

    forwarded = await asyncio.wait_for(report_queue.get(), timeout=1.0)
    assert "test_cases" in forwarded.payload


async def test_parse_invalid_json(mock_claude_client):
    agent = make_qa_agent(mock_claude_client)

    set_claude_response(mock_claude_client, "This is not valid JSON at all")

    dev_queue: asyncio.Queue = asyncio.Queue()
    agent._message_bus.subscribe("dev_input", dev_queue)

    msg = Message(
        source="arch",
        target="arch_review",
        payload={"architecture": "Design", "query": "Q", "requirements": "R", "review_type": "architecture", "revision_count": 0},
    )
    await agent.process(msg)

    # Should approve since parsing fails and defaults to no blocking risks
    forwarded = await asyncio.wait_for(dev_queue.get(), timeout=1.0)
    assert forwarded is not None
