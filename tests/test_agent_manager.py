import asyncio

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from orchestrator.core.agent_base import BaseAgent
from orchestrator.core.agent_manager import AgentManager
from orchestrator.core.logging_monitor import Monitor
from orchestrator.models.config import AgentConfig, OrchestratorConfig
from orchestrator.models.messages import Message
from orchestrator.models.state import AgentState


class EchoAgent(BaseAgent):
    """Simple agent that echoes messages for testing."""

    async def process(self, message: Message) -> dict | None:
        return {"echo": message.payload}


@pytest.fixture
def config():
    return OrchestratorConfig(anthropic_api_key="test-key")


@pytest.fixture
def manager(config):
    with patch("orchestrator.core.agent_manager.anthropic.AsyncAnthropic"):
        mgr = AgentManager(config)
        mgr.monitor = Monitor(log_level="DEBUG")
        return mgr


@pytest.fixture
def mock_client():
    return AsyncMock()


def make_echo_agent(agent_id="echo1", input_channels=None, output_channels=None, client=None):
    return EchoAgent(
        AgentConfig(
            agent_id=agent_id,
            agent_type="echo",
            input_channels=input_channels or [],
            output_channels=output_channels or [],
        ),
        client or AsyncMock(),
    )


async def test_register(manager):
    agent = make_echo_agent()
    manager.register(agent)
    assert "echo1" in manager.agents
    assert agent._message_bus is manager.message_bus


async def test_start_and_stop(manager):
    agent = make_echo_agent()
    manager.register(agent)

    await manager.start_all()
    assert agent.state == AgentState.RUNNING

    await manager.stop_all()
    assert agent.state == AgentState.STOPPED


async def test_get_status(manager):
    a1 = make_echo_agent("a1")
    a2 = make_echo_agent("a2")
    manager.register(a1)
    manager.register(a2)

    status = manager.get_status()
    assert status == {"a1": AgentState.IDLE, "a2": AgentState.IDLE}

    await manager.start_all()
    status = manager.get_status()
    assert status == {"a1": AgentState.RUNNING, "a2": AgentState.RUNNING}

    await manager.stop_all()


async def test_restart(manager):
    agent = make_echo_agent()
    manager.register(agent)

    await manager.start_all()
    assert agent.state == AgentState.RUNNING

    await manager.restart("echo1")
    assert agent.state == AgentState.RUNNING

    await manager.stop_all()


async def test_message_routing(manager):
    agent = make_echo_agent(input_channels=["test_input"], output_channels=["test_output"])
    manager.register(agent)

    output_queue: asyncio.Queue = asyncio.Queue()
    manager.message_bus.subscribe("test_output", output_queue)

    await manager.start_all()

    msg = Message(source="tester", target="test_input", payload={"hello": "world"})
    await manager.message_bus.publish("test_input", msg)

    result = await asyncio.wait_for(output_queue.get(), timeout=2.0)
    assert result.payload == {"echo": {"hello": "world"}}

    await manager.stop_all()
