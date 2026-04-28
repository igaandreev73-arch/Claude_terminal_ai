from __future__ import annotations
import asyncio, json, os, sqlite3, subprocess, time
from datetime import datetime, timezone
from pathlib import Path
from typing import AsyncGenerator
import psutil
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

API_KEY  = os.getenv("TELEMETRY_API_KEY","vps_telemetry_key_2026")
DB_PATH  = Path(os.getenv("DB_PATH","/opt/collector/data/terminal.db"))
LOG_PATH = Path(os.getenv("LOG_PATH","/opt/collector/logs/collector.log"))
ENV_PATH = Path("/opt/collector/.env")
SERVICE  = "crypto-collector"

app = FastAPI(title="Collector Telemetry",version="1.0.0")
app.add_middleware(CORSMiddleware,allow_origins=["*"],allow_methods=["*"],allow_headers=["*"])

_log_subscribers=[]
_telegram_config={}

def _auth(r):
    k=r.headers.get("X-API-Key") or r.query_params.get("api_key")
    if k!=API_KEY: raise HTTPException(403,"Неверный API ключ")

def _db():
    c=sqlite3.connect(DB_PATH); c.row_factory=sqlite3.Row; return c

def _run(cmd):
    try:
        r=subprocess.run(cmd,shell=True,capture_output=True,text=True,timeout=10)
        return r.returncode,(r.stdout+r.stderr).strip()
    except Exception as e: return 1,str(e)

def _svc():
    _,s=_run(f"systemctl is-active {SERVICE}")
    _,u=_run(f"systemctl show {SERVICE} --property=ActiveEnterTimestamp --value")
    return {"active":s.strip()=="active","status":s.strip(),"since":u.strip()}

def _dbstats():
    try:
        sz=DB_PATH.stat().st_size/1024/1024
        conn=_db(); cur=conn.cursor()
        st={"size_mb":round(sz,2)}
        for t in ["candles","orderbook_snapshots","liquidations","trades_raw","futures_metrics"]:
            try: cur.execute(f"SELECT COUNT(*) FROM {t}"); st[t]=cur.fetchone()[0]
            except: st[t]=0
        conn.close(); return st
    except Exception as e: return {"error":str(e)}

def _sys():
    m=psutil.virtual_memory(); d=psutil.disk_usage("/")
    return {"cpu_percent":psutil.cpu_percent(0.3),
            "ram_used_mb":round(m.used/1024/1024),"ram_total_mb":round(m.total/1024/1024),
            "ram_percent":m.percent,"disk_used_gb":round(d.used/1024**3,1),
            "disk_free_gb":round(d.free/1024**3,1),"disk_percent":d.percent}

def _syms():
    try:
        for l in ENV_PATH.read_text().splitlines():
            if l.startswith("SYMBOLS="):
                return [s.strip() for s in l.split("=",1)[1].split(",") if s.strip()]
    except: pass
    return ["BTC/USDT","ETH/USDT","SOL/USDT","BNB/USDT","XRP/USDT"]

def _upd_env(k,v):
    t=ENV_PATH.read_text(); ls=t.splitlines(); found=False
    for i,l in enumerate(ls):
        if l.startswith(f"{k}="):
            ls[i]=f"{k}={v}"; found=True; break
    if not found: ls.append(f"{k}={v}")
    ENV_PATH.write_text(chr(10).join(ls)+chr(10))

def _datastats():
    syms=_syms(); res=[]
    try:
        conn=_db(); cur=conn.cursor()
        for s in syms:
            cur.execute("SELECT COUNT(*),MIN(open_time),MAX(open_time) FROM candles WHERE symbol=?",(s,))
            cnt,f,l=cur.fetchone()
            cur.execute("SELECT COUNT(*) FROM orderbook_snapshots WHERE symbol=?",(s,))
            ob=cur.fetchone()[0]
            cur.execute("SELECT COUNT(*) FROM liquidations WHERE symbol=?",(s,))
            liq=cur.fetchone()[0]
            res.append({"symbol":s,"candles":cnt,
                "first_candle":datetime.fromtimestamp(f/1000).isoformat() if f else None,
                "last_candle":datetime.fromtimestamp(l/1000).isoformat() if l else None,
                "ob_snapshots":ob,"liquidations":liq,
                "trust_score":min(100,round(cnt/max(180*24*60,1)*100))})
        conn.close()
    except Exception as e: return [{"error":str(e)}]
    return res

async def _tg(msg):
    if not _telegram_config.get("token"): return False
    try:
        import aiohttp,ssl,certifi
        ctx=ssl.create_default_context(cafile=certifi.where())
        c=aiohttp.TCPConnector(ssl=ctx)
        url=f"https://api.telegram.org/bot{_telegram_config[chr(116)+chr(111)+chr(107)+chr(101)+chr(110)]}/sendMessage"
        async with aiohttp.ClientSession(connector=c) as s:
            async with s.post(url,json={"chat_id":_telegram_config["chat_id"],"text":msg,"parse_mode":"HTML"}) as r:
                return r.status==200
    except: return False

async def _watch():
    try:
        with open(LOG_PATH,"r",encoding="utf-8",errors="replace") as f:
            f.seek(0,2)
            while True:
                l=f.readline()
                if l:
                    for q in list(_log_subscribers):
                        try: q.put_nowait(l.rstrip())
                        except: pass
                else: await asyncio.sleep(0.3)
    except: await asyncio.sleep(5)

@app.on_event("startup")
async def startup():
    asyncio.create_task(_watch())
    try:
        for l in ENV_PATH.read_text().splitlines():
            if l.startswith("TELEGRAM_TOKEN="): _telegram_config["token"]=l.split("=",1)[1]
            if l.startswith("TELEGRAM_CHAT_ID="): _telegram_config["chat_id"]=l.split("=",1)[1]
    except: pass

@app.get("/health")
async def health(request:Request):
    _auth(request)
    return {"timestamp":datetime.now(timezone.utc).isoformat(),"service":_svc(),"db_reachable":DB_PATH.exists()}

@app.get("/metrics")
async def metrics(request:Request):
    _auth(request)
    return {"timestamp":datetime.now(timezone.utc).isoformat(),"system":_sys(),"database":_dbstats(),"service":_svc()}

@app.get("/status")
async def status(request:Request):
    _auth(request)
    return {"timestamp":datetime.now(timezone.utc).isoformat(),"service":_svc(),"system":_sys(),"database":_dbstats(),"data":_datastats(),"symbols":_syms(),"telegram_ok":bool(_telegram_config.get("token"))}

@app.get("/data/status")
async def data_status(request:Request):
    _auth(request); return {"timestamp":datetime.now(timezone.utc).isoformat(),"symbols":_datastats()}

@app.get("/data/validate")
async def data_validate(request:Request,symbol:str="BTC/USDT",days:int=1):
    _auth(request)
    conn=_db(); cur=conn.cursor()
    cutoff=int((time.time()-days*86400)*1000)
    cur.execute("SELECT COUNT(*) FROM candles WHERE symbol=? AND open_time>=?",(symbol,cutoff))
    cnt=cur.fetchone()[0]; conn.close()
    exp=days*24*60; gap=round((1-cnt/max(exp,1))*100,1)
    return {"symbol":symbol,"days":days,"expected_1m":exp,"found_in_db":cnt,"gap_percent":gap,
            "status":"ok" if gap<5 else "warning" if gap<20 else "critical"}

@app.get("/data/gaps")
async def data_gaps(request:Request):
    _auth(request)
    conn=_db(); cur=conn.cursor()
    cur.execute("SELECT * FROM data_gaps ORDER BY gap_start DESC LIMIT 100")
    gaps=[dict(r) for r in cur.fetchall()]; conn.close()
    return {"gaps":gaps,"total":len(gaps)}

@app.get("/symbols")
async def get_symbols(request:Request):
    _auth(request); return {"symbols":_syms()}

class SymReq(BaseModel): symbol:str; market_type:str='spot'

@app.post("/symbols/add")
async def add_sym(body:SymReq,request:Request):
    _auth(request); syms=_syms(); sym=body.symbol.upper().replace("-","/")
    env_key = "SYMBOLS" if body.market_type == "spot" else "FUTURES_SYMBOLS"
    if sym in syms: return {"status":"exists","symbol":sym,"market_type":body.market_type}
    syms.append(sym); _upd_env(env_key,",".join(syms)); _run(f"systemctl restart {SERVICE}")
    return {"status":"added","symbol":sym,"market_type":body.market_type,"all_symbols":syms}

@app.post("/symbols/remove")
async def rm_sym(body:SymReq,request:Request):
    _auth(request); syms=_syms(); sym=body.symbol.upper().replace("-","/")
    if sym not in syms: raise HTTPException(404,f"{sym} не найден")
    syms.remove(sym); _upd_env("SYMBOLS",",".join(syms)); _run(f"systemctl restart {SERVICE}")
    return {"status":"removed","symbol":sym,"all_symbols":syms}

class BfReq(BaseModel): symbol:str|None=None; days:int=30; limit_per_sec:int=25; market_type:str='spot'

@app.post("/backfill")
async def backfill(body:BfReq,request:Request):
    _auth(request)
    s=f"--symbols {body.symbol}" if body.symbol else ""
    s_arg = f"--symbols {body.symbol}" if body.symbol else ""
    mt_arg = f"--market_type {body.market_type}"
    lr_arg = f"--limit_per_sec {body.limit_per_sec}"
    script = "clean_backfill.py" if body.market_type == "spot" else "sync_history.py"
    _run(f"bash -c 'cd /opt/collector && source venv/bin/activate && nohup python3.11 -u scripts/{script} {s_arg} {mt_arg} {lr_arg} > /opt/collector/logs/backfill.log 2>&1 &'")
    return {"status":"started","symbol":body.symbol or "all","days":body.days}

@app.post("/commands/restart/{module}")
async def restart(module:str,request:Request):
    _auth(request)
    if module not in ["spot_ws","futures_ws","rest_poller","service"]:
        raise HTTPException(400,"Недопустимый модуль")
    _run(f"systemctl restart {SERVICE}")
    return {"status":"restarted","module":module}

@app.get("/logs/stream")
async def logs(request:Request):
    _auth(request); q=asyncio.Queue(200); _log_subscribers.append(q)
    async def gen():
        try:
            for l in LOG_PATH.read_text(errors="replace").splitlines()[-50:]:
                yield f"data: {json.dumps(dict(line=l,ts=time.time()))}\n"
            while True:
                if await request.is_disconnected(): break
                try:
                    l=await asyncio.wait_for(q.get(),5)
                    yield f"data: {json.dumps(dict(line=l,ts=time.time()))}\n"
                except asyncio.TimeoutError:
                    yield 'data: {"heartbeat":true}\n\n'
        finally:
            if q in _log_subscribers: _log_subscribers.remove(q)
    return StreamingResponse(gen(),media_type="text/event-stream")

@app.get("/telegram/status")
async def tg_status(request:Request):
    _auth(request)
    return {"configured":bool(_telegram_config.get("token")),"chat_id":_telegram_config.get("chat_id")}

class TgCfg(BaseModel): token:str; chat_id:str

@app.post("/telegram/config")
async def tg_cfg(body:TgCfg,request:Request):
    _auth(request); _telegram_config.update({"token":body.token,"chat_id":body.chat_id})
    _upd_env("TELEGRAM_TOKEN",body.token); _upd_env("TELEGRAM_CHAT_ID",body.chat_id)
    return {"status":"configured"}

@app.post("/telegram/test")
async def tg_test(request:Request):
    _auth(request)
    ok=await _tg(f"Test VPS {datetime.now().strftime(chr(37)+chr(72)+chr(58)+chr(37)+chr(77)+chr(58)+chr(37)+chr(83))}")
    return {"sent":ok}
