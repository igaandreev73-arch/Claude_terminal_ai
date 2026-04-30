"""VPS Telemetry Server — FastAPI :8800.

Транслирует события Event Bus VPS → Desktop через WebSocket.
Предоставляет REST API для исторических данных и управления.
"""
from __future__ import annotations

import asyncio
import json
import os
import sqlite3
import subprocess
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, AsyncGenerator

import psutil
from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from core.event_bus import Event, EventBus
from core.logger import get_logger

log = get_logger("Telemetry")

API_KEY = os.getenv("TELEMETRY_API_KEY", "vps_telemetry_key_2026")
DB_PATH = Path(os.getenv("DB_PATH", "/opt/collector/data/terminal.db"))
LOG_PATH = Path(os.getenv("LOG_PATH", "/opt/collector/logs/collector.log"))
ENV_PATH = Path("/opt/collector/.env")
SERVICE = "crypto-collector"

_log_subscribers: list[asyncio.Queue] = []
_telegram_config: dict[str, str] = {}

# События, транслируемые Desktop'у через WS
BROADCAST_EVENTS: set[str] = {
    "candle.1m.tick", "candle.1m.closed",
    "futures.candle.1m.closed",
    "orderbook.update",
    "futures.orderbook.update",
    "futures.liquidation",
    "futures.basis.updated",
    "watchdog.degraded", "watchdog.lost", "watchdog.dead",
    "watchdog.recovered", "watchdog.reconnecting",
    "backfill.progress", "backfill.complete", "backfill.error",
    "validation.result",
    "HEALTH_UPDATE",
}


# ── Heartbeat ────────────────────────────────────────────────────────────────
_heartbeat_data: dict = {
    "cpu_percent": 0.0,
    "ram_used_mb": 0.0,
    "ram_total_mb": 0.0,
    "uptime_sec": 0,
}


async def _heartbeat_loop() -> None:
    """Отправляет heartbeat всем подключённым WS-клиентам раз в 5 секунд."""
    import psutil
    while True:
        await asyncio.sleep(5)
        if not _ws_clients:
            continue
        try:
            cpu = psutil.cpu_percent()
            ram = psutil.virtual_memory()
            uptime = time.time() - psutil.boot_time()
            _heartbeat_data.update(
                cpu_percent=cpu,
                ram_used_mb=round(ram.used / 1024 / 1024, 1),
                ram_total_mb=round(ram.total / 1024 / 1024, 1),
                uptime_sec=int(uptime),
            )
            msg = {
                "type": "heartbeat",
                **_heartbeat_data,
                "ts": int(time.time() * 1000),
            }
            await _broadcast(msg)
        except Exception as exc:
            log.warning(f"Heartbeat error: {exc}")


# ── Lifespan (замена on_event("startup")/on_event("shutdown")) ──────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Управляет жизненным циклом приложения."""
    # Startup
    asyncio.create_task(_watch())
    asyncio.create_task(_heartbeat_loop())
    try:
        for line in ENV_PATH.read_text().splitlines():
            if line.startswith("TELEGRAM_TOKEN="):
                _telegram_config["token"] = line.split("=", 1)[1]
            if line.startswith("TELEGRAM_CHAT_ID="):
                _telegram_config["chat_id"] = line.split("=", 1)[1]
    except Exception:
        pass
    log.info("Telemetry server started")
    yield
    # Shutdown
    log.info("Telemetry server stopped")


app = FastAPI(title="Collector Telemetry", version="1.0.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# Event Bus (подключается из main.py collector)
_event_bus: EventBus | None = None
_ws_clients: set[WebSocket] = set()
_broadcast_task: asyncio.Task | None = None


def set_event_bus(bus: EventBus) -> None:
    """Устанавливает Event Bus для трансляции событий в WS клиенты."""
    global _event_bus
    _event_bus = bus


# ── Вспомогательные функции ─────────────────────────────────────────────────
def _auth(r: Request) -> None:
    k = r.headers.get("X-API-Key") or r.query_params.get("api_key")
    if k != API_KEY:
        raise HTTPException(403, "Неверный API ключ")


def _db():
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    return c


def _run(cmd: str) -> tuple[int, str]:
    try:
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=10)
        return r.returncode, (r.stdout + r.stderr).strip()
    except Exception as e:
        return 1, str(e)


def _svc() -> dict:
    _, s = _run(f"systemctl is-active {SERVICE}")
    _, u = _run(f"systemctl show {SERVICE} --property=ActiveEnterTimestamp --value")
    return {"active": s.strip() == "active", "status": s.strip(), "since": u.strip()}


def _dbstats() -> dict:
    try:
        sz = DB_PATH.stat().st_size / 1024 / 1024
        conn = _db()
        cur = conn.cursor()
        st = {"size_mb": round(sz, 2)}
        for t in ["candles", "orderbook_snapshots", "liquidations", "trades_raw", "futures_metrics"]:
            try:
                cur.execute(f"SELECT COUNT(*) FROM {t}")
                st[t] = cur.fetchone()[0]
            except Exception:
                st[t] = 0
        conn.close()
        return st
    except Exception as e:
        return {"error": str(e)}


def _sys() -> dict:
    m = psutil.virtual_memory()
    d = psutil.disk_usage("/")
    return {
        "cpu_percent": psutil.cpu_percent(0.3),
        "ram_used_mb": round(m.used / 1024 / 1024),
        "ram_total_mb": round(m.total / 1024 / 1024),
        "ram_percent": m.percent,
        "disk_used_gb": round(d.used / 1024 ** 3, 1),
        "disk_free_gb": round(d.free / 1024 ** 3, 1),
        "disk_percent": d.percent,
    }


def _syms() -> list[str]:
    try:
        for line in ENV_PATH.read_text().splitlines():
            if line.startswith("SYMBOLS="):
                return [s.strip() for s in line.split("=", 1)[1].split(",") if s.strip()]
    except Exception:
        pass
    return ["BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT", "XRP/USDT"]


def _upd_env(k: str, v: str) -> None:
    text = ENV_PATH.read_text()
    lines = text.splitlines()
    found = False
    for i, line in enumerate(lines):
        if line.startswith(f"{k}="):
            lines[i] = f"{k}={v}"
            found = True
            break
    if not found:
        lines.append(f"{k}={v}")
    ENV_PATH.write_text("\n".join(lines) + "\n")


def _datastats() -> list[dict]:
    syms = _syms()
    res = []
    try:
        conn = _db()
        cur = conn.cursor()
        for s in syms:
            cur.execute(
                "SELECT COUNT(*), MIN(open_time), MAX(open_time) FROM candles WHERE symbol=?",
                (s,),
            )
            cnt, f, l = cur.fetchone()
            cur.execute("SELECT COUNT(*) FROM orderbook_snapshots WHERE symbol=?", (s,))
            ob = cur.fetchone()[0]
            cur.execute("SELECT COUNT(*) FROM liquidations WHERE symbol=?", (s,))
            liq = cur.fetchone()[0]
            res.append({
                "symbol": s,
                "candles": cnt,
                "first_candle": datetime.fromtimestamp(f / 1000).isoformat() if f else None,
                "last_candle": datetime.fromtimestamp(l / 1000).isoformat() if l else None,
                "ob_snapshots": ob,
                "liquidations": liq,
                "trust_score": min(100, round(cnt / max(180 * 24 * 60, 1) * 100)),
            })
        conn.close()
    except Exception as e:
        return [{"error": str(e)}]
    return res


async def _tg(msg: str) -> bool:
    if not _telegram_config.get("token"):
        return False
    try:
        import ssl
        import aiohttp
        import certifi
        ctx = ssl.create_default_context(cafile=certifi.where())
        connector = aiohttp.TCPConnector(ssl=ctx)
        url = f"https://api.telegram.org/bot{_telegram_config['token']}/sendMessage"
        async with aiohttp.ClientSession(connector=connector) as session:
            async with session.post(
                url,
                json={
                    "chat_id": _telegram_config["chat_id"],
                    "text": msg,
                    "parse_mode": "HTML",
                },
            ) as r:
                return r.status == 200
    except Exception:
        return False


async def _watch() -> None:
    """Наблюдает за лог-файлом и транслирует в SSE подписчиков."""
    try:
        with open(LOG_PATH, "r", encoding="utf-8", errors="replace") as f:
            f.seek(0, 2)
            while True:
                line = f.readline()
                if line:
                    for q in list(_log_subscribers):
                        try:
                            q.put_nowait(line.rstrip())
                        except Exception:
                            pass
                else:
                    await asyncio.sleep(0.3)
    except Exception:
        await asyncio.sleep(5)


def _serialise(data: Any) -> Any:
    """Делает данные JSON-сериализуемыми (рекурсивно)."""
    if hasattr(data, "isoformat"):
        return data.isoformat()
    if isinstance(data, dict):
        return {k: _serialise(v) for k, v in data.items()}
    if isinstance(data, (list, tuple)):
        return [_serialise(v) for v in data]
    if hasattr(data, "__dict__"):
        return {k: _serialise(v) for k, v in data.__dict__.items() if not k.startswith("_")}
    return data


# ── Фоновая задача: трансляция Event Bus → WS клиенты ──────────────────────
async def _broadcast_loop() -> None:
    """Подписывается на Event Bus и транслирует события всем WS клиентам."""
    global _event_bus
    # Ждём пока Event Bus будет установлен
    while _event_bus is None:
        await asyncio.sleep(0.5)

    bus = _event_bus

    # Подписываемся на все транслируемые события
    for event_type in BROADCAST_EVENTS:
        bus.subscribe(event_type, _forward_to_ws)

    log.info(f"WS broadcast loop started, subscribed to {len(BROADCAST_EVENTS)} event types")


async def _forward_to_ws(event: Event) -> None:
    """Отправляет событие всем подключённым WS клиентам."""
    if not _ws_clients:
        return

    message = {
        "type": "event",
        "event_type": event.type,
        "data": _serialise(event.data),
        "ts": datetime.now(timezone.utc).isoformat(),
    }
    payload = json.dumps(message, default=str)
    dead: list[WebSocket] = []
    for ws in list(_ws_clients):
        try:
            await ws.send_text(payload)
        except Exception:
            dead.append(ws)
    for ws in dead:
        _ws_clients.discard(ws)


# ── WS Endpoint ─────────────────────────────────────────────────────────────
@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket) -> None:
    """WebSocket endpoint для Desktop.

    Desktop подключается и получает все транслируемые события.
    Аутентификация: первый JSON-пакет должен содержать {"api_key": "..."}.
    """
    # Проверяем API-ключ при подключении
    query_key = ws.query_params.get("api_key", "")
    if query_key and query_key != API_KEY:
        await ws.close(code=4001, reason="Invalid API key")
        return

    await ws.accept()
    _ws_clients.add(ws)
    client_host = ws.client.host if ws.client else "unknown"
    log.info(f"WS client connected: {client_host}")

    try:
        while True:
            raw = await ws.receive_text()
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                await ws.send_text(json.dumps({"type": "error", "message": "Invalid JSON"}))
                continue

            msg_type = msg.get("type", "")

            # Аутентификация по первому сообщению (если не было в query)
            if msg_type == "auth":
                key = msg.get("api_key", "")
                if key != API_KEY:
                    await ws.send_text(json.dumps({"type": "auth_error", "message": "Invalid API key"}))
                    await ws.close(code=4001, reason="Invalid API key")
                    return
                await ws.send_text(json.dumps({"type": "auth_ok"}))
                log.info(f"WS client authenticated: {client_host}")
                continue

            # Ping/Pong
            if msg_type == "ping":
                await ws.send_text(json.dumps({"type": "pong"}))
                continue

            # Команды от Desktop
            if msg_type == "command":
                command = msg.get("command", "")
                payload = msg.get("payload", {})

                if command == "get_state":
                    # Отправляем текущее состояние VPS
                    await ws.send_text(json.dumps({
                        "type": "state",
                        "symbols": _syms(),
                        "database": _dbstats(),
                        "system": _sys(),
                        "service": _svc(),
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    }))
                else:
                    await ws.send_text(json.dumps({
                        "type": "error",
                        "message": f"Unknown command: {command}",
                    }))
                continue

    except WebSocketDisconnect:
        log.info(f"WS client disconnected: {client_host}")
    except Exception as e:
        log.error(f"WS error ({client_host}): {e}")
    finally:
        _ws_clients.discard(ws)


# ── REST Endpoints ──────────────────────────────────────────────────────────

@app.get("/api/candles")
async def get_candles(
    request: Request,
    symbol: str = "BTC/USDT",
    tf: str = "1m",
    limit: int = 500,
    market_type: str = "spot",
):
    """Возвращает исторические свечи из БД VPS.

    Аналог ui/ws_server.py → _candles_http_handler().
    """
    _auth(request)
    conn = _db()
    cur = conn.cursor()
    try:
        cur.execute(
            """SELECT open_time, open, high, low, close, volume, is_closed
               FROM candles
               WHERE symbol=? AND timeframe=? AND market_type=?
               ORDER BY open_time DESC
               LIMIT ?""",
            (symbol, tf, market_type, limit),
        )
        rows = cur.fetchall()
        candles = [
            {
                "open_time": r["open_time"],
                "open": r["open"],
                "high": r["high"],
                "low": r["low"],
                "close": r["close"],
                "volume": r["volume"],
                "is_closed": bool(r["is_closed"]),
            }
            for r in reversed(rows)  # хронологический порядок
        ]
        return {
            "symbol": symbol,
            "timeframe": tf,
            "market_type": market_type,
            "count": len(candles),
            "candles": candles,
        }
    except Exception as e:
        raise HTTPException(500, f"DB error: {e}")
    finally:
        conn.close()


# ── Существующие REST endpoints ────────────────────────────────────────────

@app.get("/health")
async def health(request: Request):
    _auth(request)
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "service": _svc(),
        "db_reachable": DB_PATH.exists(),
    }


@app.get("/metrics")
async def metrics(request: Request):
    _auth(request)
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "system": _sys(),
        "database": _dbstats(),
        "service": _svc(),
    }


@app.get("/status")
async def status(request: Request):
    _auth(request)
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "service": _svc(),
        "system": _sys(),
        "database": _dbstats(),
        "data": _datastats(),
        "symbols": _syms(),
        "telegram_ok": bool(_telegram_config.get("token")),
    }


@app.get("/data/status")
async def data_status(request: Request):
    _auth(request)
    return {"timestamp": datetime.now(timezone.utc).isoformat(), "symbols": _datastats()}


@app.get("/data/validate")
async def data_validate(request: Request, symbol: str = "BTC/USDT", days: int = 1):
    _auth(request)
    conn = _db()
    cur = conn.cursor()
    cutoff = int((time.time() - days * 86400) * 1000)
    cur.execute(
        "SELECT COUNT(*) FROM candles WHERE symbol=? AND open_time>=?",
        (symbol, cutoff),
    )
    cnt = cur.fetchone()[0]
    conn.close()
    exp = days * 24 * 60
    gap = round((1 - cnt / max(exp, 1)) * 100, 1)
    return {
        "symbol": symbol,
        "days": days,
        "expected_1m": exp,
        "found_in_db": cnt,
        "gap_percent": gap,
        "status": "ok" if gap < 5 else "warning" if gap < 20 else "critical",
    }


@app.get("/data/gaps")
async def data_gaps(request: Request):
    _auth(request)
    conn = _db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM data_gaps ORDER BY gap_start DESC LIMIT 100")
    gaps = [dict(r) for r in cur.fetchall()]
    conn.close()
    return {"gaps": gaps, "total": len(gaps)}


@app.get("/symbols")
async def get_symbols(request: Request):
    _auth(request)
    return {"symbols": _syms()}


class SymReq(BaseModel):
    symbol: str
    market_type: str = "spot"


@app.post("/symbols/add")
async def add_sym(body: SymReq, request: Request):
    _auth(request)
    syms = _syms()
    sym = body.symbol.upper().replace("-", "/")
    env_key = "SYMBOLS" if body.market_type == "spot" else "FUTURES_SYMBOLS"
    if sym in syms:
        return {"status": "exists", "symbol": sym, "market_type": body.market_type}
    syms.append(sym)
    _upd_env(env_key, ",".join(syms))
    _run(f"systemctl restart {SERVICE}")
    return {"status": "added", "symbol": sym, "market_type": body.market_type, "all_symbols": syms}


@app.post("/symbols/remove")
async def rm_sym(body: SymReq, request: Request):
    _auth(request)
    syms = _syms()
    sym = body.symbol.upper().replace("-", "/")
    if sym not in syms:
        raise HTTPException(404, f"{sym} не найден")
    syms.remove(sym)
    _upd_env("SYMBOLS", ",".join(syms))
    _run(f"systemctl restart {SERVICE}")
    return {"status": "removed", "symbol": sym, "all_symbols": syms}


class BfReq(BaseModel):
    symbol: str | None = None
    days: int = 30
    limit_per_sec: int = 25
    market_type: str = "spot"


@app.post("/backfill")
async def backfill(body: BfReq, request: Request):
    _auth(request)
    s_arg = f"--symbols {body.symbol}" if body.symbol else ""
    mt_arg = f"--market_type {body.market_type}"
    lr_arg = f"--limit_per_sec {body.limit_per_sec}"
    script = "clean_backfill.py" if body.market_type == "spot" else "sync_history.py"
    _run(
        f"bash -c 'cd /opt/collector && source venv/bin/activate && "
        f"nohup python3.11 -u scripts/{script} {s_arg} {mt_arg} {lr_arg} "
        f"> /opt/collector/logs/backfill.log 2>&1 &'"
    )
    return {"status": "started", "symbol": body.symbol or "all", "days": body.days}


@app.post("/commands/restart/{module}")
async def restart(module: str, request: Request):
    _auth(request)
    if module not in ["spot_ws", "futures_ws", "rest_poller", "service"]:
        raise HTTPException(400, "Недопустимый модуль")
    _run(f"systemctl restart {SERVICE}")
    return {"status": "restarted", "module": module}


@app.get("/logs/stream")
async def logs(request: Request):
    _auth(request)
    q: asyncio.Queue = asyncio.Queue(200)
    _log_subscribers.append(q)

    async def gen() -> AsyncGenerator[str, None]:
        try:
            for line in LOG_PATH.read_text(errors="replace").splitlines()[-50:]:
                yield f"data: {json.dumps({'line': line, 'ts': time.time()})}\n\n"
            while True:
                if await request.is_disconnected():
                    break
                try:
                    line = await asyncio.wait_for(q.get(), 5)
                    yield f"data: {json.dumps({'line': line, 'ts': time.time()})}\n\n"
                except asyncio.TimeoutError:
                    yield 'data: {"heartbeat":true}\n\n'
        finally:
            if q in _log_subscribers:
                _log_subscribers.remove(q)

    return StreamingResponse(gen(), media_type="text/event-stream")


@app.get("/telegram/status")
async def tg_status(request: Request):
    _auth(request)
    return {
        "configured": bool(_telegram_config.get("token")),
        "chat_id": _telegram_config.get("chat_id"),
    }


class TgCfg(BaseModel):
    token: str
    chat_id: str


class ApiKeyCfg(BaseModel):
    api_key: str
    api_secret: str


@app.post("/telegram/config")
async def tg_cfg(body: TgCfg, request: Request):
    _auth(request)
    _telegram_config.update({"token": body.token, "chat_id": body.chat_id})
    _upd_env("TELEGRAM_TOKEN", body.token)
    _upd_env("TELEGRAM_CHAT_ID", body.chat_id)
    return {"status": "configured"}


@app.post("/telegram/test")
async def tg_test(request: Request):
    _auth(request)
    ok = await _tg(f"Test VPS {datetime.now().strftime('%H:%M:%S')}")
    return {"sent": ok}


@app.get("/apikeys/status")
async def apikeys_status(request: Request):
    _auth(request)
    key = ""
    secret = ""
    try:
        for line in ENV_PATH.read_text().splitlines():
            if line.startswith("BINGX_API_KEY="):
                key = line.split("=", 1)[1].strip()
            if line.startswith("BINGX_API_SECRET="):
                secret = line.split("=", 1)[1].strip()
    except Exception:
        pass
    return {
        "api_key_set": bool(key),
        "api_secret_set": bool(secret),
        "api_key_prefix": key[:8] + "..." if key else "",
    }


@app.post("/apikeys/config")
async def apikeys_config(body: ApiKeyCfg, request: Request):
    _auth(request)
    _upd_env("BINGX_API_KEY", body.api_key)
    _upd_env("BINGX_API_SECRET", body.api_secret)
    _run(f"systemctl restart {SERVICE}")
    return {"status": "configured", "api_key_prefix": body.api_key[:8] + "..."}
