"""
Telegram Notifier for local terminal.
"""
from __future__ import annotations
import asyncio, os, ssl, time
from datetime import datetime
import certifi
try:
    import aiohttp
    _AIOHTTP_OK = True
except ImportError:
    _AIOHTTP_OK = False
from core.logger import get_logger
log = get_logger("TelegramNotifier")

class TelegramNotifier:
    def __init__(self) -> None:
        self._token   = os.getenv("TELEGRAM_TOKEN", "")
        self._chat_id = os.getenv("TELEGRAM_CHAT_ID", "")
        self._alerted: set[str] = set()
        self._enabled = bool(self._token and self._chat_id)
        if not self._enabled:
            log.warning("Telegram not configured (TELEGRAM_TOKEN / TELEGRAM_CHAT_ID)")

    def reconfigure(self, token: str, chat_id: str) -> None:
        self._token = token; self._chat_id = chat_id
        self._enabled = bool(token and chat_id)

    async def send(self, msg: str) -> bool:
        if not self._enabled or not _AIOHTTP_OK: return False
        try:
            ctx = ssl.create_default_context(cafile=certifi.where())
            conn = aiohttp.TCPConnector(ssl=ctx)
            url = f"https://api.telegram.org/bot{self._token}/sendMessage"
            async with aiohttp.ClientSession(connector=conn) as s:
                async with s.post(url, json={"chat_id": self._chat_id, "text": msg, "parse_mode": "HTML"}, timeout=aiohttp.ClientTimeout(total=10)) as r:
                    ok = r.status == 200
                    if ok: log.debug(f"TG sent: {msg[:60]}")
                    else: log.warning(f"TG error {r.status}")
                    return ok
        except Exception as e:
            log.error(f"TG exception: {e}"); return False

    async def alert(self, key: str, msg: str) -> None:
        if key not in self._alerted:
            self._alerted.add(key)
            ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            full = f"\U0001f6a8 <b>ALERT</b> \u2014 Crypto Terminal LOCAL\n{msg}\n\u23f0 {ts}"
            await self.send(full)

    async def resolve(self, key: str, msg: str) -> None:
        if key in self._alerted:
            self._alerted.discard(key)
            ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            full = f"\u2705 <b>RESOLVED</b> \u2014 Crypto Terminal LOCAL\n{msg}\n\u23f0 {ts}"
            await self.send(full)

    async def notify_ws_stage(self, name: str, label: str, stage: str) -> None:
        if stage in ("lost", "dead"):
            await self.alert(f"ws_{name}", f"\u274c WS lost: <b>{label}</b>\nstage: {stage}")
        elif stage == "normal":
            await self.resolve(f"ws_{name}", f"WS restored: <b>{label}</b>")

    async def test(self) -> bool:
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        msg = f"\U0001f916 <b>Crypto Terminal LOCAL</b>\n\u2705 Test notification\n\u23f0 {ts}"
        return await self.send(msg)

_notifier: TelegramNotifier | None = None

def get_notifier() -> TelegramNotifier:
    global _notifier
    if _notifier is None: _notifier = TelegramNotifier()
    return _notifier
