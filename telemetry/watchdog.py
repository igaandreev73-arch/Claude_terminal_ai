"""
Telegram watchdog — мониторит состояние сборщика.
Проверяет каждые 60 секунд:
  - crypto-collector активен
  - Свежесть онлайн данных (последняя свеча не старше 5 мин)
  - Диск заполнен > 85%
  - Ежедневный дайджест в 09:00 UTC
"""
import asyncio, os, sqlite3, subprocess, time, ssl, certifi, sys
from datetime import datetime
from pathlib import Path

import aiohttp

TOKEN   = os.getenv("TELEGRAM_TOKEN", "")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
DB_PATH = Path(os.getenv("DB_PATH", "/opt/collector/data/terminal.db"))
SERVICE = "crypto-collector"
CHECK_INTERVAL = 60

_alerted: set[str] = set()


def _run(cmd: str) -> str:
    try:
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=10)
        return (r.stdout + r.stderr).strip()
    except Exception as e:
        return str(e)


async def _send(msg: str) -> None:
    if not TOKEN or not CHAT_ID:
        print(f"[NO TG] {msg[:80]}", flush=True)
        return
    try:
        ctx  = ssl.create_default_context(cafile=certifi.where())
        conn = aiohttp.TCPConnector(ssl=ctx)
        url  = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
        async with aiohttp.ClientSession(connector=conn) as s:
            resp = await s.post(url, json={
                "chat_id":    CHAT_ID,
                "text":       msg,
                "parse_mode": "HTML",
            })
            ok = resp.status == 200
        print(f"[TG {'OK' if ok else 'FAIL'}] {msg[:60]}", flush=True)
    except Exception as e:
        print(f"[TG ERROR] {e}", flush=True)


async def _alert(key: str, msg: str) -> None:
    if key not in _alerted:
        _alerted.add(key)
        await _send(
            f"🚨 <b>ALERT</b> — Crypto Terminal VPS\n{msg}\n"
            f"⏰ {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}"
        )


async def _resolve(key: str, msg: str) -> None:
    if key in _alerted:
        _alerted.discard(key)
        await _send(
            f"✅ <b>RESOLVED</b> — Crypto Terminal VPS\n{msg}\n"
            f"⏰ {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}"
        )


async def check_loop() -> None:
    print("[WATCHDOG] Запущен. Интервал: 60с", flush=True)
    await _send(
        f"🤖 <b>Crypto Terminal VPS — Watchdog запущен</b>\n"
        f"Мониторинг каждые {CHECK_INTERVAL} секунд\n"
        f"⏰ {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}"
    )

    while True:
        try:
            # 1. Проверяем сервис
            status = _run(f"systemctl is-active {SERVICE}").strip()
            if status != "active":
                await _alert("service_down", f"❌ Сервис <b>{SERVICE}</b> не активен: {status}")
            else:
                await _resolve("service_down", f"Сервис <b>{SERVICE}</b> снова активен")

            # 2. Проверяем свежесть онлайн данных (BTC/USDT — главная пара)
            # Считаем только если нет активного backfill процесса
            backfill_running = _run("pgrep -f sync_history").strip() != ""
            if not backfill_running:
                try:
                    conn_db = sqlite3.connect(DB_PATH)
                    cur = conn_db.cursor()
                    # Берём MAX за последние 10 минут (онлайн свечи, не backfill)
                    cutoff = int((time.time() - 600) * 1000)
                    cur.execute(
                        "SELECT MAX(open_time) FROM candles WHERE symbol='BTC/USDT' AND open_time > ?",
                        (cutoff,)
                    )
                    last_ts = cur.fetchone()[0]
                    conn_db.close()

                    if last_ts is None:
                        # Нет свежих данных за 10 мин — проверяем вообще последнюю
                        conn_db = sqlite3.connect(DB_PATH)
                        cur = conn_db.cursor()
                        cur.execute("SELECT MAX(open_time) FROM candles WHERE symbol='BTC/USDT'")
                        last_ts = cur.fetchone()[0]
                        conn_db.close()

                    if last_ts:
                        age_min = (time.time() * 1000 - last_ts) / 60000
                        if age_min > 5:
                            await _alert(
                                "stale_data",
                                f"⚠️ Данные BTC/USDT устарели на <b>{age_min:.0f} мин</b>\n"
                                f"Возможна проблема с WS соединением"
                            )
                        else:
                            await _resolve("stale_data", f"Данные BTC/USDT актуальны ({age_min:.1f} мин)")
                except Exception as e:
                    print(f"[DB CHECK ERROR] {e}", flush=True)

            # 3. Проверяем диск (только критичное)
            try:
                import psutil
                disk = psutil.disk_usage("/")
                if disk.percent > 85:
                    await _alert(
                        "low_disk",
                        f"💾 Диск заполнен на <b>{disk.percent}%</b>\n"
                        f"Свободно: {disk.free // 1024**3:.1f} GB"
                    )
                else:
                    await _resolve("low_disk", f"Диск в норме: {disk.percent}%")
            except Exception as e:
                print(f"[DISK CHECK ERROR] {e}", flush=True)

            # 4. Ежедневный дайджест в 09:00 UTC
            now = datetime.utcnow()
            digest_key = f"digest_{now.date()}"
            if now.hour == 9 and now.minute < 2 and digest_key not in _alerted:
                try:
                    _alerted.add(digest_key)
                    conn_db = sqlite3.connect(DB_PATH)
                    cur = conn_db.cursor()
                    cur.execute("SELECT COUNT(*) FROM candles")
                    total_c = cur.fetchone()[0]
                    cur.execute("SELECT COUNT(*) FROM orderbook_snapshots")
                    total_ob = cur.fetchone()[0]
                    cur.execute("SELECT COUNT(*) FROM liquidations")
                    total_liq = cur.fetchone()[0]
                    conn_db.close()
                    db_mb = DB_PATH.stat().st_size / 1024 / 1024
                    import psutil
                    disk2 = psutil.disk_usage("/")
                    await _send(
                        f"📊 <b>Ежедневный дайджест VPS</b>\n"
                        f"━━━━━━━━━━━━━━━━\n"
                        f"🕯 Свечей: <b>{total_c:,}</b>\n"
                        f"📖 Снимков стакана: <b>{total_ob:,}</b>\n"
                        f"💥 Ликвидаций: <b>{total_liq:,}</b>\n"
                        f"💾 БД: <b>{db_mb:.1f} MB</b> | Диск: {disk2.percent}%\n"
                        f"━━━━━━━━━━━━━━━━\n"
                        f"⏰ {now.strftime('%Y-%m-%d %H:%M UTC')}"
                    )
                except Exception as e:
                    print(f"[DIGEST ERROR] {e}", flush=True)

        except Exception as e:
            print(f"[WATCHDOG LOOP ERROR] {e}", flush=True)

        await asyncio.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    asyncio.run(check_loop())