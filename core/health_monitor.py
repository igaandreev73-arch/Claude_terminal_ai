import asyncio
from datetime import datetime, timedelta, timezone

from core.base_module import BaseModule, ModuleStatus
from core.event_bus import EventBus
from core.logger import get_logger

log = get_logger("HealthMonitor")

HEARTBEAT_TIMEOUT_SEC = 60  # модуль считается мёртвым если нет heartbeat дольше N секунд
CHECK_INTERVAL_SEC = 30


class HealthMonitor:
    def __init__(self, event_bus: EventBus) -> None:
        self._event_bus = event_bus
        self._modules: dict[str, BaseModule] = {}
        self._running = False
        self._task: asyncio.Task | None = None

    def register(self, module: BaseModule) -> None:
        self._modules[module.name] = module
        log.info(f"Модуль зарегистрирован: {module.name}")

    def get_system_status(self) -> dict:
        now = datetime.now(timezone.utc)
        statuses = {}
        for name, module in self._modules.items():
            info = module.health_check()
            if module.last_heartbeat and (now - module.last_heartbeat) > timedelta(seconds=HEARTBEAT_TIMEOUT_SEC):
                info["status"] = ModuleStatus.ERROR.value
                info["error"] = "Heartbeat timeout"
            statuses[name] = info

        all_ok = all(s["status"] == ModuleStatus.RUNNING.value for s in statuses.values())
        return {
            "ok": all_ok,
            "checked_at": now.isoformat(),
            "modules": statuses,
        }

    async def _check_loop(self) -> None:
        log.info("Health Monitor запущен, проверка каждые 30 сек")
        while self._running:
            await asyncio.sleep(CHECK_INTERVAL_SEC)
            status = self.get_system_status()
            await self._event_bus.publish("HEALTH_UPDATE", status)
            if status["ok"]:
                log.info("Все модули работают нормально")
            else:
                dead = [n for n, s in status["modules"].items() if s["status"] != ModuleStatus.RUNNING.value]
                log.warning(f"Проблемные модули: {dead}")

    async def start(self) -> None:
        self._running = True
        self._task = asyncio.create_task(self._check_loop())

    async def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        log.info("Health Monitor остановлен")
