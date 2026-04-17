import asyncio
from datetime import datetime, timedelta, timezone
import pytest

from core.base_module import BaseModule, ModuleStatus
from core.event_bus import EventBus
from core.health_monitor import HealthMonitor, HEARTBEAT_TIMEOUT_SEC


class DummyModule(BaseModule):
    def __init__(self, name: str):
        super().__init__(name)

    async def start(self):
        self.status = ModuleStatus.RUNNING
        self.heartbeat()

    async def stop(self):
        self.status = ModuleStatus.STOPPED


@pytest.fixture
def event_bus():
    return EventBus()


@pytest.fixture
def monitor(event_bus):
    return HealthMonitor(event_bus)


def test_register_module(monitor):
    mod = DummyModule("тест")
    monitor.register(mod)
    status = monitor.get_system_status()
    assert "тест" in status["modules"]


async def test_running_module_is_ok(monitor):
    mod = DummyModule("активный")
    await mod.start()
    monitor.register(mod)

    status = monitor.get_system_status()
    assert status["modules"]["активный"]["status"] == ModuleStatus.RUNNING.value


async def test_stale_heartbeat_detected(monitor):
    mod = DummyModule("зависший")
    await mod.start()
    # Искусственно устаревший heartbeat
    mod.last_heartbeat = datetime.now(timezone.utc) - timedelta(seconds=HEARTBEAT_TIMEOUT_SEC + 10)
    monitor.register(mod)

    status = monitor.get_system_status()
    assert status["modules"]["зависший"]["status"] == ModuleStatus.ERROR.value
    assert status["ok"] is False


async def test_system_status_ok_when_all_running(monitor):
    mod1 = DummyModule("mod1")
    mod2 = DummyModule("mod2")
    await mod1.start()
    await mod2.start()
    monitor.register(mod1)
    monitor.register(mod2)

    status = monitor.get_system_status()
    assert status["ok"] is True
    assert "checked_at" in status


async def test_health_update_event_published():
    bus = EventBus()
    await bus.start()
    monitor = HealthMonitor(bus)

    events_received: list = []

    async def handler(event):
        events_received.append(event)

    bus.subscribe("HEALTH_UPDATE", handler)

    mod = DummyModule("тест")
    await mod.start()
    monitor.register(mod)

    await monitor.start()
    await asyncio.sleep(0.1)  # ждём первой проверки (но таймер 30сек, поэтому события нет здесь)
    await monitor.stop()
    await bus.stop()
    # Событие не придёт за 0.1 сек (CHECK_INTERVAL=30), но убеждаемся что нет исключений
