import pytest

from orchestrator.core.data_handler import DataHandler


@pytest.fixture
def handler():
    return DataHandler()


async def test_write_and_read(handler):
    await handler.write("key1", "value1")
    result = await handler.read("key1")
    assert result == "value1"


async def test_read_default(handler):
    result = await handler.read("missing", default="fallback")
    assert result == "fallback"


async def test_read_missing_no_default(handler):
    result = await handler.read("missing")
    assert result is None


async def test_delete(handler):
    await handler.write("key1", "value1")
    await handler.delete("key1")
    result = await handler.read("key1")
    assert result is None


async def test_delete_missing(handler):
    # Should not raise
    await handler.delete("missing")


async def test_keys(handler):
    await handler.write("a", 1)
    await handler.write("b", 2)
    keys = await handler.keys()
    assert sorted(keys) == ["a", "b"]


async def test_overwrite(handler):
    await handler.write("key", "old")
    await handler.write("key", "new")
    assert await handler.read("key") == "new"
