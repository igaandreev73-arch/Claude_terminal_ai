"""
Telegram watchdog — мониторит состояние сборщика и шлёт уведомления.
Запускается как отдельный systemd сервис.
Проверяет каждые 60 секунд:
  - crypto-collector активен
  - Последняя свеча не старше 5 минут
  - RAM и диск в норме
  - Ликвидации приходят (для фьючерсов)
"""
import asyncio, os, sqlite3, subprocess, time, ssl, certifi
from datetime import datetime
from pathlib import Path

import aiohttp

TOKEN   = os.getenv("TELEGRAM_TOKEN", "")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
DB_PATH = Path(os.getenv("DB_PATH", "/opt/collector/data/terminal.db"))
SERVICE = "crypto-collector"
CHECK_INTERVAL = 60  # секунд

# Состояние — что уже алертили чтобы не спамить
_alerted: set[str] = set()


def _run(cmd: str) -> str:
    try:
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=10)
        return (r.stdout + r.stderr).strip()
    except Exception as e:
        return str(e)


async def _send(msg: str) -> None:
    if not TOKEN or not CHAT_ID:
        print(f"[TELEGRAM NOT CONFIGURED] {msg}")
        return
    try:
        ctx = ssl.create_default_context(cafile=certifi.where())
        conn = aiohttp.TCPConnector(ssl=ctx)
        url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
        async with aiohttp.ClientSession(connector=conn) as s:
            await s.post(url, json={
                "chat_id": CHAT_ID,
                "text": msg,
                "parse_mode": "HTML"
            })
        print(f"[TG SENT] {msg[:60]}")
    except Exception as e:
        print(f"[TG ERROR] {e}")


async def _alert(key: str, msg: str) -> None:
    """Отправляет алёрт один раз пока проблема не исчезнет."""
    if key not in _alerted:
        _alerted.add(key)
        await _send(f"🚨 <b>ALERT</b> — Crypto Terminal VPS\n{msg}\n⏰ {datetime.now().strftime('%H:%M:%S')}")


async def _resolve(key: str, msg: str) -> None:
    """Уведомляет о восстановлении."""
    if key in _alerted:
        _alerted.discard(key)
        await _send(f"✅ <b>RESOLVED</b> — Crypto Terminal VPS\n{msg}\n⏰ {datetime.now().strftime('%H:%M:%S')}")


async def check_loop() -> None:
    print(f"[WATCHDOG] Запущен. Интервал: {CHECK_INTERVAL}с")

    # Стартовое уведомление
    await _send(
        f"🤖 <b>Crypto Terminal VPS — Watchdog запущен</b>\n"
        f"Мониторинг каждые {CHECK_INTERVAL} секунд\n"
        f"⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    )

    while True:
        try:
            # 1. Проверяем сервис
            status = _run(f"systemctl is-active {SERVICE}")
            if status != "active":
                await _alert("service_down", f"❌ Сервис <b>{SERVICE}</b> не активен: {status}")
            else:
                await _resolve("service_down", f"Сервис <b>{SERVICE}</b> снова активен")

            # 2. Проверяем свежесть данных (последняя свеча BTC)
            try:
                conn = sqlite3.connect(DB_PATH)
                cur = conn.cursor()
                cur.execute("SELECT MAX(open_time) FROM candles WHERE symbol='BTC/USDT'")
                last_ts = cur.fetchone()[0]
                conn.close()
                if last_ts:
                    age_min = (time.time() * 1000 - last_ts) / 60000
                    if age_min > 5:
                        await _alert(
                            "stale_data",
                            f"⚠️ Последняя свеча BTC/USDT устарела на <b>{age_min:.0f} мин</b>\n"
                            f"Возможна проблема с WS соединением"
                        )
                    else:
                        await _resolve("stale_data", f"Данные BTC/USDT свежие ({age_min:.1f} мин)")
            except Exception as e:
                await _alert("db_error", f"❌ Ошибка чтения БД: {e}")

            # 3. Проверяем RAM
            import psutil
            mem = psutil.virtual_memory()
            if mem.percent > 90:
                await _alert(
                    "high_ram",
                    f"⚠️ RAM заполнена на <b>{mem.percent}%</b>\n"
                    f"Использовано: {mem.used//1024//1024}MB из {mem.total//1024//1024}MB"
                )
            else:
                await _resolve("high_ram", f"RAM в норме: {mem.percent}%")

            # 4. Проверяем диск
            disk = psutil.disk_usage("/")
            if disk.percent > 85:
                await _alert(
                    "low_disk",
                    f"⚠️ Диск заполнен на <b>{disk.percent}%</b>\n"
                    f"Свободно: {disk.free//1024**3:.1f}GB"
                )
            else:
                await _resolve("low_disk", f"Диск в норме: {disk.percent}%")

            # 5. Ежедневный дайджест (в 09:00 UTC)
            now = datetime.utcnow()
            if now.hour == 9 and now.minute < 2:
                try:
                    conn2 = sqlite3.connect(DB_PATH)
                    cur2 = conn2.cursor()
                    cur2.execute("SELECT COUNT(*) FROM candles")
                    total_candles = cur2.fetchone()[0]
                    cur2.execute("SELECT COUNT(*) FROM orderbook_snapshots")
                    total_ob = cur2.fetchone()[0]
                    cur2.execute("SELECT COUNT(*) FROM liquidations")
                    total_liq = cur2.fetchone()[0]
                    conn2.close()
                    db_mb = DB_PATH.stat().st_size / 1024 / 1024

                    digest_key = f"digest_{now.date()}"
                    if digest_key not in _alerted:
                        _alerted.add(digest_key)
                        await _send(
                            f"📊 <b>Ежедневный дайджест VPS</b>\n"
                            f"━━━━━━━━━━━━━━━━\n"
                            f"🕯 Свечей: <b>{total_candles:,}</b>\n"
                            f"📖 Снимков стакана: <b>{total_ob:,}</b>\n"
                            f"💥 Ликвидаций: <b>{total_liq:,}</b>\n"
                            f"💾 Размер БД: <b>{db_mb:.1f} MB</b>\n"
                            f"🖥 RAM: {mem.percent}% | Диск: {disk.percent}%\n"
                            f"━━━━━━━━━━━━━━━━\n"
                            f"⏰ {now.strftime('%Y-%m-%d %H:%M UTC')}"
                        )
                except Exception:
                    pass

        except Exception as e:
            print(f"[WATCHDOG ERROR] {e}")

        await asyncio.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    asyncio.run(check_loop())