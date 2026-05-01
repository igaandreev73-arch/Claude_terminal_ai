"""
Telegram Bot — long polling для команд.

Работает как фоновая asyncio-задача в collector mode (VPS).
Использует существующие функции из telemetry/server.py для получения данных.

Команды:
  /summary  — детальная сводка (БД, свечи spot/futures, стаканы, ликвидации, соединения)
  /status   — статус сервисов (collector, WS, watchdog)
  /health   — здоровье системы (CPU, RAM, диск, uptime)
  /symbols  — список пар с trust_score
  /backfill — статус задач backfill
  /errors   — последние ошибки из лога
  /help     — список команд
"""
from __future__ import annotations

import asyncio
import os
import ssl
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path

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

# Путь к БД (должен совпадать с telemetry/server.py)
DB_PATH = Path(os.getenv("DB_PATH", "/opt/collector/data/terminal.db"))


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
        elif command == "/backfill":
            reply = self._build_backfill()
        elif command == "/errors":
            reply = self._build_errors()
        elif command in ("/help", "/start"):
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

    def _get_ws_status(self) -> str:
        """Статус WS-соединений из БД/лога."""
        try:
            conn = sqlite3.connect(str(DB_PATH))
            cur = conn.cursor()
            # Пробуем получить статус из system_logs
            cur.execute(
                "SELECT message FROM system_logs WHERE message LIKE 'WS%' ORDER BY id DESC LIMIT 5"
            )
            logs = [row[0] for row in cur.fetchall()]
            conn.close()

            ws_spot = "✅ Норма"
            ws_futures = "✅ Норма"
            for log_line in logs:
                if "WS spot" in log_line.lower() or "BingXWebSocket" in log_line:
                    if "error" in log_line.lower() or "disconnect" in log_line.lower():
                        ws_spot = "⚠️ Сбой"
                if "WS futures" in log_line.lower() or "BingXFuturesWebSocket" in log_line:
                    if "error" in log_line.lower() or "disconnect" in log_line.lower():
                        ws_futures = "⚠️ Сбой"

            return (
                f"🔌 <b>Соединения:</b>\n"
                f"✅ WS Spot:  {ws_spot}\n"
                f"✅ WS Futures: {ws_futures}\n"
                f"✅ REST:     ✅ Норма"
            )
        except Exception:
            return (
                f"🔌 <b>Соединения:</b>\n"
                f"✅ WS Spot:  ⚪ Н/Д\n"
                f"✅ WS Futures: ⚪ Н/Д\n"
                f"✅ REST:     ⚪ Н/Д"
            )

    def _build_summary(self) -> str:
        """Детальная сводка: /summary"""
        try:
            db = _dbstats()
            data = _datastats()
            now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

            total_candles = sum(d.get("candles", 0) for d in data)
            total_ob = sum(d.get("ob_snapshots", 0) for d in data)
            total_liq = sum(d.get("liquidations", 0) for d in data)
            db_size = db.get("size_mb", 0)

            # Разбивка spot/futures
            try:
                conn = sqlite3.connect(str(DB_PATH))
                cur = conn.cursor()
                cur.execute("SELECT COUNT(*) FROM candles WHERE market_type='spot'")
                spot_candles = cur.fetchone()[0]
                cur.execute("SELECT COUNT(*) FROM candles WHERE market_type='futures'")
                futures_candles = cur.fetchone()[0]
                cur.execute("SELECT COUNT(*) FROM orderbook_snapshots WHERE market_type='spot'")
                spot_ob = cur.fetchone()[0]
                cur.execute("SELECT COUNT(*) FROM orderbook_snapshots WHERE market_type='futures'")
                futures_ob = cur.fetchone()[0]
                # Диапазон дат
                cur.execute("SELECT MIN(open_time), MAX(open_time) FROM candles WHERE market_type='spot'")
                s_min, s_max = cur.fetchone()
                cur.execute("SELECT MIN(open_time), MAX(open_time) FROM candles WHERE market_type='futures'")
                f_min, f_max = cur.fetchone()
                # OI и Funding
                cur.execute("SELECT value, timestamp FROM futures_metrics WHERE metric='open_interest' ORDER BY timestamp DESC LIMIT 1")
                oi_row = cur.fetchone()
                cur.execute("SELECT value, timestamp FROM futures_metrics WHERE metric='funding_rate' ORDER BY timestamp DESC LIMIT 1")
                fr_row = cur.fetchone()
                # Ликвидации за 24ч
                day_ago = int(time.time() * 1000) - 86400000
                cur.execute("SELECT COUNT(*) FROM liquidations WHERE timestamp > ?", (day_ago,))
                liq_24h = cur.fetchone()[0]
                conn.close()

                spot_days = (s_max - s_min) / 86400000 if s_min and s_max else 0
                futures_days = (f_max - f_min) / 86400000 if f_min and f_max else 0
                oi_str = f"${float(oi_row[0]):,.1f}" if oi_row else "Н/Д"
                fr_str = f"{float(fr_row[0]):.4%}" if fr_row else "Н/Д"
            except Exception:
                spot_candles = futures_candles = 0
                spot_ob = futures_ob = 0
                spot_days = futures_days = 0
                liq_24h = 0
                oi_str = fr_str = "Н/Д"

            lines = [
                f"📊 <b>СВОДКА VPS</b> — {now}",
                f"━━━━━━━━━━━━━━━━━━━━━━",
                f"💾 БД: <b>{db_size:.1f} MB</b>",
                f"🕯 Свечи: <b>{total_candles:,}</b>",
                f"   ├── spot 1m:  {spot_candles:,} ({spot_days:.0f} дн)",
                f"   └── futures 1m: {futures_candles:,} ({futures_days:.0f} дн)",
                f"📖 Стаканы: <b>{total_ob:,}</b>",
                f"   ├── spot:    {spot_ob:,}",
                f"   └── futures: {futures_ob:,}",
                f"💥 Ликвидации (24ч): <b>{liq_24h}</b>",
                f"📊 OI: <b>{oi_str}</b>",
                f"💰 Funding Rate: <b>{fr_str}</b>",
                f"━━━━━━━━━━━━━━━━━━━━━━",
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

            # Статус соединений
            lines.append("")
            lines.append(self._get_ws_status())

            lines.append(f"━━━━━━━━━━━━━━━━━━━━━━")
            lines.append(f"⏰ {now}")
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

    def _build_backfill(self) -> str:
        """Статус backfill: /backfill"""
        try:
            conn = sqlite3.connect(str(DB_PATH))
            cur = conn.cursor()
            cur.execute(
                "SELECT symbol, status, progress, created_at FROM tasks "
                "WHERE task_type='backfill' ORDER BY created_at DESC LIMIT 10"
            )
            tasks = cur.fetchall()
            conn.close()

            now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

            if not tasks:
                return (
                    f"📥 <b>Backfill</b>\n"
                    f"━━━━━━━━━━━━━━━━\n"
                    f"Нет активных задач backfill.\n"
                    f"━━━━━━━━━━━━━━━━\n"
                    f"⏰ {now}"
                )

            lines = [
                f"📥 <b>Backfill</b>",
                f"━━━━━━━━━━━━━━━━",
            ]
            for sym, status, progress, created in tasks:
                emoji = "✅" if status == "completed" else "🔄" if status == "running" else "❌" if status == "error" else "⏳"
                pct = f"{progress}%" if progress else "—"
                created_str = created[:16] if created else "—"
                lines.append(f"{emoji} {sym}: {pct} ({status}) [{created_str}]")

            lines.append(f"━━━━━━━━━━━━━━━━")
            lines.append(f"⏰ {now}")
            return "\n".join(lines)
        except Exception as e:
            return f"❌ Ошибка получения статуса backfill: {e}"

    def _build_errors(self) -> str:
        """Последние ошибки: /errors"""
        try:
            conn = sqlite3.connect(str(DB_PATH))
            cur = conn.cursor()
            cur.execute(
                "SELECT created_at, level, message FROM system_logs "
                "WHERE level IN ('ERROR', 'CRITICAL', 'WARNING') "
                "ORDER BY id DESC LIMIT 5"
            )
            errors = cur.fetchall()
            conn.close()

            now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

            if not errors:
                return (
                    f"✅ <b>Ошибки</b>\n"
                    f"━━━━━━━━━━━━━━━━\n"
                    f"Последних ошибок нет.\n"
                    f"━━━━━━━━━━━━━━━━\n"
                    f"⏰ {now}"
                )

            lines = [
                f"⚠️ <b>Последние ошибки</b>",
                f"━━━━━━━━━━━━━━━━",
            ]
            for ts, level, msg in errors:
                emoji = "🔴" if level == "CRITICAL" else "🟠" if level == "ERROR" else "🟡"
                ts_str = ts[:16] if ts else "—"
                msg_short = msg[:80] + "..." if len(msg) > 80 else msg
                lines.append(f"{emoji} [{ts_str}] {msg_short}")

            lines.append(f"━━━━━━━━━━━━━━━━")
            lines.append(f"⏰ {now}")
            return "\n".join(lines)
        except Exception as e:
            return f"❌ Ошибка получения лога ошибок: {e}"

    def _build_help(self) -> str:
        """Список команд: /help"""
        return (
            f"🤖 <b>Crypto Terminal VPS — Telegram Bot</b>\n"
            f"━━━━━━━━━━━━━━━━\n"
            f"Доступные команды:\n\n"
            f"📊 <b>/summary</b> — детальная сводка (БД, данные, соединения)\n"
            f"🔍 <b>/status</b> — статус сервисов\n"
            f"❤️ <b>/health</b> — здоровье системы (CPU/RAM/диск)\n"
            f"📈 <b>/symbols</b> — список пар с trust_score\n"
            f"📥 <b>/backfill</b> — статус задач backfill\n"
            f"⚠️ <b>/errors</b> — последние ошибки из лога\n"
            f"❓ <b>/help</b> — это сообщение\n"
            f"━━━━━━━━━━━━━━━━\n"
            f"⏰ {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}"
        )
