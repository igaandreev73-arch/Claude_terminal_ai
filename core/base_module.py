from abc import ABC, abstractmethod
from datetime import datetime, timezone
from enum import Enum
from typing import TYPE_CHECKING

from core.logger import get_logger

if TYPE_CHECKING:
    from core.health_monitor import HealthMonitor


class ModuleStatus(Enum):
    STOPPED = "stopped"
    STARTING = "starting"
    RUNNING = "running"
    ERROR = "error"


class BaseModule(ABC):
    def __init__(self, name: str) -> None:
        self.name = name
        self.status = ModuleStatus.STOPPED
        self.last_heartbeat: datetime | None = None
        self.error_message: str | None = None
        self._log = get_logger(name)

    @abstractmethod
    async def start(self) -> None: ...

    @abstractmethod
    async def stop(self) -> None: ...

    def heartbeat(self) -> None:
        self.last_heartbeat = datetime.now(timezone.utc)

    def health_check(self) -> dict:
        return {
            "module": self.name,
            "status": self.status.value,
            "last_heartbeat": self.last_heartbeat.isoformat() if self.last_heartbeat else None,
            "error": self.error_message,
        }
