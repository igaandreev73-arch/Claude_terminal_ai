"""
Telegram Bot — long polling для команд.

Работает как фоновая asyncio-задача в collector mode (VPS).
Использует существующие функции из telemetry/server.py для получения данных.

Команды:
  /summary  — сводка по БД (размер, свечи, стаканы, ликвидации)
  /status   — статус сервисов (collector, WS, watchdog)
  /health   — здоровье системы (CPU, RAM, диск, uptime)
  /symbols  — список пар с trust_score
  /help     — список команд
"""
from __future__ import annotations

import asyncio
import os
import ssl
import time
from datetime import datetime, timezone

import certifi

try:
    import aiohttp
    _AIOHTTP_OK = True
except ImportError:
    _AIOHTTP_OK = False

from core.logger import get_logger

log = get_logger("TGBot")

# Импортируем функции из server.py для получения данных
# (они используют ту же БД и те же утилиты)
from telemetry.server import _datastats, _dbstats, _svc, _sys, _syms


class TelegramBot:
    """Long-polling Telegram бот для команд о состоянии VPS."""

    def __init__(self) -> None:
        self._token = os.getenv("TELEGRAM_TOKEN", "")
        self._chat_id = os.getenv("TELEGRAM_CHAT_ID", "")
        self._enabled = bool(self._token and self._chat_id) and _AIOHTTP_OK
        self._running = False
        self._last_update_id: int = 0
        self._poll_task: asyncio.Task | None = None
        # Кэш команд для дедупликации (чтобы не обрабатывать одно и то же update дважды)
        self._processed: set[int] = set()

        if not self._enabled:
            log.warning("TG Bot не настроен (TELEGRAM_TOKEN / TELEGRAM_CHAT_ID)")

    async def start(self) -> None:
        """Запускает polling цикл в фоновой задаче."""
        if not self._enabled:
            log.info("TG Bot пропущен — нет конфигурации")
            return
        self._running = True
        self._poll_task = asyncio.create_task(self._poll_loop())
        log.info("TG Bot запущен (long polling, интервал 5с)")

    async def stop(self) -> None:
        """Останавливает polling."""
        self._running = False
        if self._poll_task:
            self._poll_task.cancel()
            try:
                await self._poll_task
            except asyncio.CancelledError:
                pass
        log.info("TG Bot остановлен")

    async def _poll_loop(self) -> None:
        """Основной цикл: каждые 5 сек проверяет новые сообщения."""
        while self._running:
            try:
                await self._check_updates()
            except asyncio.CancelledError:
                break
            except Exception as e:
                log.warning(f"TG Bot polling error: {e}")
            await asyncio.sleep(5)

    async def _check_updates(self) -> None:
        """GET /getUpdates?offset=... с Telegram API."""
        ctx = ssl.create_default_context(cafile=certifi.where())
        connector = aiohttp.TCPConnector(ssl=ctx)
        url = f"https://api.telegram.org/bot{self._token}/getUpdates"
        params = {
            "offset": self._last_update_id + 1,
            "timeout": 10,
            "allowed_updates": '["message"]',
        }
        async with aiohttp.ClientSession(connector=connector) as session:
            async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                if resp.status != 200:
                    return
                data = await resp.json()
                if not data.get("ok"):
                    return
                for update in data.get("result", []):
                    uid = update.get("update_id", 0)
                    if uid in self._processed:
                        continue
                    self._processed.add(uid)
                    self._last_update_id = max(self._last_update_id, uid)
                    await self._handle_update(update)

    async def _handle_update(self, update: dict) -> None:
        """Обрабатывает одно входящее сообщение."""
        msg = update.get("message", {})
        chat_id = msg.get("chat", {}).get("id")
        text = (msg.get("text") or "").strip()

        # Проверяем, что сообщение от нашего chat_id
        if str(chat_id) != str(self._chat_id):
            return

        if not text.startswith("/"):
            return

        command = text.split()[0].lower()
        log.info(f"TG Bot команда: {command} от {chat_id}")

        if command == "/summary":
            reply = self._build_summary()
        elif command == "/status":
            reply = self._build_status()
        elif command == "/health":
            reply = self._build_health()
        elif command == "/symbols":
            reply = self._build_symbols()
        elif command == "/help":
            reply = self._build_help()
        else:
            reply = (
                f"❌ Неизвестная команда: {command}\n"
                f"Используй /help для списка команд."
            )

        await self._send(reply)

    async def _send(self, text: str) -> None:
        """Отправляет сообщение в Telegram."""
        if not self._enabled:
            return
        ctx = ssl.create_default_context(cafile=certifi.where())
        connector = aiohttp.TCPConnector(ssl=ctx)
        url = f"https://api.telegram.org/bot{self._token}/sendMessage"
        payload = {
            "chat_id": self._chat_id,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        }
        try:
            async with aiohttp.ClientSession(connector=connector) as session:
                async with session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    if resp.status != 200:
                        log.warning(f"TG Bot send error: {resp.status}")
        except Exception as e:
            log.warning(f"TG Bot send exception: {e}")

    # ── Построение ответов ─────────────────────────────────────────────────

    def _build_summary(self) -> str:
        """Сводка по БД: /summary"""
        try:
            db = _dbstats()
            data = _datastats()
            now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

            total_candles = sum(d.get("candles", 0) for d in data)
            total_ob = sum(d.get("ob_snapshots", 0) for d in data)
            total_liq = sum(d.get("liquidations", 0) for d in data)
            db_size = db.get("size_mb", 0)

            lines = [
                f"📊 <b>Сводка VPS</b>",
                f"━━━━━━━━━━━━━━━━",
                f"💾 БД: <b>{db_size:.1f} MB</b>",
                f"🕯 Свечей: <b>{total_candles:,}</b>",
                f"📖 Стаканов: <b>{total_ob:,}</b>",
                f"💥 Ликвидаций: <b>{total_liq:,}</b>",
                f"━━━━━━━━━━━━━━━━",
                f"⏰ {now}",
            ]

            # Добавляем информацию по символам
            lines.append("")
            lines.append("📈 <b>По парам:</b>")
            for d in data:
                sym = d.get("symbol", "?").replace("/USDT", "")
                trust = d.get("trust_score", 0)
                emoji = "🟢" if trust > 90 else "🟡" if trust > 70 else "🔴"
                lines.append(
                    f"{emoji} {sym}: свечей {d.get('candles', 0):,} | "
                    f"стаканов {d.get('ob_snapshots', 0):,} | "
                    f"ликв {d.get('liquidations', 0):,} | "
                    f"trust {trust}%"
                )

            return "\n".join(lines)
        except Exception as e:
            return f"❌ Ошибка получения сводки: {e}"

    def _build_status(self) -> str:
        """Статус сервисов: /status"""
        try:
            svc = _svc()
            now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

            svc_emoji = "✅" if svc.get("active") else "❌"
            since = svc.get("since", "—")

            lines = [
                f"🔍 <b>Статус VPS</b>",
                f"━━━━━━━━━━━━━━━━",
                f"{svc_emoji} Collector: <b>{svc.get('status', '?')}</b>",
                f"🕐 Запущен: {since}",
                f"━━━━━━━━━━━━━━━━",
                f"⏰ {now}",
            ]
            return "\n".join(lines)
        except Exception as e:
            return f"❌ Ошибка получения статуса: {e}"

    def _build_health(self) -> str:
        """Здоровье системы: /health"""
        try:
            sys_info = _sys()
            svc = _svc()
            now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

            cpu = sys_info.get("cpu_percent", 0)
            ram_pct = sys_info.get("ram_percent", 0)
            ram_used = sys_info.get("ram_used_mb", 0)
            ram_total = sys_info.get("ram_total_mb", 0)
            disk_pct = sys_info.get("disk_percent", 0)
            disk_free = sys_info.get("disk_free_gb", 0)

            cpu_emoji = "🟢" if cpu < 60 else "🟡" if cpu < 85 else "🔴"
            ram_emoji = "🟢" if ram_pct < 75 else "🟡" if ram_pct < 90 else "🔴"
            disk_emoji = "🟢" if disk_pct < 70 else "🟡" if disk_pct < 85 else "🔴"

            lines = [
                f"❤️ <b>Здоровье VPS</b>",
                f"━━━━━━━━━━━━━━━━",
                f"{cpu_emoji} CPU: <b>{cpu}%</b>",
                f"{ram_emoji} RAM: <b>{ram_used}/{ram_total} MB ({ram_pct}%)</b>",
                f"{disk_emoji} Диск: <b>{disk_pct}%</b> (свободно {disk_free} GB)",
                f"{'✅' if svc.get('active') else '❌'} Сервис: <b>{svc.get('status', '?')}</b>",
                f"━━━━━━━━━━━━━━━━",
                f"⏰ {now}",
            ]
            return "\n".join(lines)
        except Exception as e:
            return f"❌ Ошибка получения health: {e}"

    def _build_symbols(self) -> str:
        """Список пар с trust_score: /symbols"""
        try:
            data = _datastats()
            now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

            lines = [
                f"📈 <b>Пары VPS</b>",
                f"━━━━━━━━━━━━━━━━",
            ]
            for d in data:
                sym = d.get("symbol", "?")
                trust = d.get("trust_score", 0)
                emoji = "🟢" if trust > 90 else "🟡" if trust > 70 else "🔴"
                last = d.get("last_candle", "—")
                if last and last != "—":
                    # Показываем только дату
                    last = last[:10]
                lines.append(f"{emoji} <b>{sym}</b>: trust {trust}% | последняя: {last}")

            lines.append(f"━━━━━━━━━━━━━━━━")
            lines.append(f"⏰ {now}")
            return "\n".join(lines)
        except Exception as e:
            return f"❌ Ошибка получения списка пар: {e}"

    def _build_help(self) -> str:
        """Список команд: /help"""
        return (
            f"🤖 <b>Crypto Terminal VPS — Telegram Bot</b>\n"
            f"━━━━━━━━━━━━━━━━\n"
            f"Доступные команды:\n\n"
            f"📊 <b>/summary</b> — сводка по БД\n"
            f"🔍 <b>/status</b> — статус сервисов\n"
            f"❤️ <b>/health</b> — здоровье системы\n"
            f"📈 <b>/symbols</b> — список пар с trust_score\n"
            f"❓ <b>/help</b> — это сообщение\n"
            f"━━━━━━━━━━━━━━━━\n"
            f"⏰ {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}"
        )
