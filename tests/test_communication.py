import asyncio

import pytest

from orchestrator.core.communication import MessageBus
from orchestrator.models.messages import Message


@pytest.fixture
def bus():
    return MessageBus()


@pytest.fixture
def make_message():
    def _make(source="test", target="ch1", payload=None):
        return Message(source=source, target=target, payload=payload or {"data": "hello"})
    return _make


async def test_publish_subscribe(bus, make_message):
    queue: asyncio.Queue = asyncio.Queue()
    bus.subscribe("ch1", queue)

    msg = make_message()
    await bus.publish("ch1", msg)

    received = await asyncio.wait_for(queue.get(), timeout=1.0)
    assert received.id == msg.id
    assert received.payload == {"data": "hello"}


async def test_fan_out(bus, make_message):
    q1: asyncio.Queue = asyncio.Queue()
    q2: asyncio.Queue = asyncio.Queue()
    bus.subscribe("ch1", q1)
    bus.subscribe("ch1", q2)

    msg = make_message()
    await bus.publish("ch1", msg)

    r1 = await asyncio.wait_for(q1.get(), timeout=1.0)
    r2 = await asyncio.wait_for(q2.get(), timeout=1.0)
    assert r1.id == msg.id
    assert r2.id == msg.id


async def test_no_subscribers(bus, make_message):
    # Publishing to a channel with no subscribers should not raise
    await bus.publish("empty_channel", make_message())


async def test_multiple_channels(bus, make_message):
    q1: asyncio.Queue = asyncio.Queue()
    q2: asyncio.Queue = asyncio.Queue()
    bus.subscribe("ch1", q1)
    bus.subscribe("ch2", q2)

    await bus.publish("ch1", make_message(target="ch1"))
    await bus.publish("ch2", make_message(target="ch2"))

    assert not q1.empty()
    assert not q2.empty()
    assert q1.qsize() == 1
    assert q2.qsize() == 1
