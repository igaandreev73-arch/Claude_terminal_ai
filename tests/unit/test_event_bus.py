import asyncio
import pytest
from core.event_bus import EventBus, Event


@pytest.fixture
async def bus():
    b = EventBus()
    await b.start()
    yield b
    await b.stop()


async def test_subscribe_and_publish(bus):
    received: list[Event] = []

    async def handler(event: Event):
        received.append(event)

    bus.subscribe("TEST_EVENT", handler)
    await bus.publish("TEST_EVENT", {"value": 42})
    await asyncio.sleep(0.05)

    assert len(received) == 1
    assert received[0].type == "TEST_EVENT"
    assert received[0].data == {"value": 42}


async def test_multiple_subscribers(bus):
    results: list[str] = []

    async def handler_a(event: Event):
        results.append("A")

    async def handler_b(event: Event):
        results.append("B")

    bus.subscribe("MULTI", handler_a)
    bus.subscribe("MULTI", handler_b)
    await bus.publish("MULTI")
    await asyncio.sleep(0.05)

    assert "A" in results
    assert "B" in results


async def test_unknown_event_type_does_not_raise(bus):
    # публикация события без подписчиков не должна падать
    await bus.publish("NO_SUBSCRIBERS", {"x": 1})
    await asyncio.sleep(0.05)


async def test_handler_exception_does_not_stop_bus(bus):
    ok_received: list[bool] = []

    async def bad_handler(event: Event):
        raise RuntimeError("сломанный обработчик")

    async def good_handler(event: Event):
        ok_received.append(True)

    bus.subscribe("ERR_EVENT", bad_handler)
    bus.subscribe("ERR_EVENT", good_handler)
    await bus.publish("ERR_EVENT")
    await asyncio.sleep(0.05)

    # хороший обработчик должен отработать несмотря на ошибку в плохом
    assert ok_received == [True]
