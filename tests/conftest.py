import pytest
from unittest.mock import AsyncMock, MagicMock

from orchestrator.core.communication import MessageBus
from orchestrator.core.data_handler import DataHandler
from orchestrator.core.logging_monitor import Monitor


@pytest.fixture
def mock_claude_client():
    client = AsyncMock()
    response = MagicMock()
    response.content = [MagicMock(text="Mock Claude response")]
    client.messages.create = AsyncMock(return_value=response)
    return client


@pytest.fixture
def message_bus():
    return MessageBus()


@pytest.fixture
def data_handler():
    return DataHandler()


@pytest.fixture
def monitor():
    return Monitor(log_level="DEBUG")
