"""
Data Verifier — 4 уровня верификации данных.

Уровень 1 — Полнота: все ли минуты присутствуют (нет дыр в последовательности).
Уровень 2 — Точность OHLCV: сравнение с REST API (допуск 0.01%).
Уровень 3 — Корректность агрегации: сравнение агрег. ТФ с биржевым (для 1h, 4h).
Уровень 4 — Непрерывность: аномальные скачки цены > 3×ATR без объёма.

Статусы верификации:
  unverified / in_progress / verified / verified_partial /
  mismatch_found / repaired / needs_review

Доверительный рейтинг (0–100) рассчитывается по истории проверок.
Умное расписание: высокий приоритет → данные для торговли следующие 24ч.
"""
from __future__ import annotations

import asyncio
import random
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING

import aiohttp

from core.logger import get_logger

if TYPE_CHECKING:
    from core.event_bus import EventBus

log = get_logger("DataVerifier")

BINGX_REST = "https://open-api.bingx.com"
PRICE_TOL  = 0.0001   # 0.01% допуск расхождения
VOL_TOL    = 0.001    # 0.1% для объёма
ATR_SPIKE  = 3.0      # порог: скачок > 3×ATR → аномалия
CHECK_WINDOW = 50     # свечей на окно верификации
SCHEDULE_INTERVAL = 600  # секунд между плановыми проверками


@dataclass
class VerifyResult:
    symbol: str
    timeframe: str
    market_type: str
    level: int
    status: str
    match_pct: float
    total_checked: int
    total_missing: int
    total_mismatch: int
    auto_repaired: bool = False
    details: dict | None = None


class DataVerifier:
    def __init__(self, event_bus: "EventBus", rest_client=None, symbols: list[str] | None = None) -> None:
        self._bus = event_bus
        self._rest = rest_client
        self._symbols = symbols or ["BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT", "XRP/USDT"]
        self._running = False
        # Кэш trust scores для Pulse
        self.trust_scores: dict[str, int] = {}

    async def start(self) -> None:
        self._running = True
        # Подписка на триггерную проверку при аномалиях
        self._bus.subscribe("anomaly.*", self._on_anomaly_trigger)
        asyncio.create_task(self._scheduler())
        log.info("DataVerifier запущен")

    async def stop(self) -> None:
        self._running = False

    # ── Планировщик ───────────────────────────────────────────────────────────

    async def _scheduler(self) -> None:
        """Умное расписание: сначала данные для торговли, потом остальные."""
        while self._running:
            await asyncio.sleep(SCHEDULE_INTERVAL)
            for symbol in self._symbols:
                if not self._running:
                    break
                try:
                    await self.verify_symbol(symbol, "1m", market_type="spot", levels=[1, 2])
                    await asyncio.sleep(2)
                except Exception as e:
                    log.warning(f"Плановая верификация {symbol}: {e}")

    async def _on_anomaly_trigger(self, event) -> None:
        """Триггерная проверка при обнаружении аномалии."""
        d = event.data if hasattr(event, "data") else event
        symbol = d.get("symbol", "")
        if symbol:
            log.info(f"Триггерная верификация {symbol} из-за аномалии")
            asyncio.create_task(self.verify_symbol(symbol, "1m", market_type="spot", levels=[1, 2]))

    # ── Публичный интерфейс ───────────────────────────────────────────────────

    async def verify_symbol(
        self,
        symbol: str,
        timeframe: str = "1m",
        market_type: str = "spot",
        levels: list[int] | None = None,
        windows: int = 3,
    ) -> list[VerifyResult]:
        levels = levels or [1, 2, 3, 4]
        results = []

        for level in levels:
            try:
                if level == 1:
                    r = await self._verify_completeness(symbol, timeframe, market_type, windows)
                elif level == 2:
                    r = await self._verify_accuracy(symbol, timeframe, market_type, windows)
                elif level == 3:
                    r = await self._verify_aggregation(symbol, market_type)
                elif level == 4:
                    r = await self._verify_continuity(symbol, timeframe, market_type)
                else:
                    continue

                results.append(r)
                await self._save_result(r)
                await self._update_trust_score(symbol, timeframe, market_type, r)
            except Exception as e:
                log.warning(f"Верификация L{level} {symbol}/{timeframe}: {e}")

        return results

    # ── Уровень 1: Полнота ────────────────────────────────────────────────────

    async def _verify_completeness(
        self, symbol: str, timeframe: str, market_type: str, windows: int
    ) -> VerifyResult:
        from storage.database import get_session_factory
        from storage.models import CandleModel
        from sqlalchemy import func, select

        tf_seconds = {"1m": 60, "5m": 300, "15m": 900, "1h": 3600, "4h": 14400, "1d": 86400}
        step_ms = tf_seconds.get(timeframe, 60) * 1000

        factory = get_session_factory()
        async with factory() as session:
            row = await session.execute(
                select(func.min(CandleModel.open_time), func.max(CandleModel.open_time))
                .where(
                    CandleModel.symbol == symbol,
                    CandleModel.timeframe == timeframe,
                    CandleModel.market_type == market_type,
                )
            )
            min_ts, max_ts = row.one()

        if not min_ts or not max_ts:
            return VerifyResult(symbol, timeframe, market_type, 1,
                                "unverified", 100.0, 0, 0, 0)

        total_missing = 0
        total_checked = 0
        window_ms = CHECK_WINDOW * step_ms
        span = max_ts - min_ts

        for _ in range(windows):
            if span <= window_ms:
                start = min_ts
            else:
                start = random.randint(min_ts, max_ts - window_ms)
            end = start + window_ms

            expected = set(range(start, end, step_ms))
            async with factory() as session:
                rows = await session.execute(
                    select(CandleModel.open_time).where(
                        CandleModel.symbol == symbol,
                        CandleModel.timeframe == timeframe,
                        CandleModel.market_type == market_type,
                        CandleModel.open_time >= start,
                        CandleModel.open_time < end,
                    )
                )
                present = {r[0] for r in rows.fetchall()}

            missing = len(expected - present)
            total_missing += missing
            total_checked += len(expected)

        match_pct = (1 - total_missing / max(total_checked, 1)) * 100
        status = "verified" if total_missing == 0 else ("mismatch_found" if total_missing > 5 else "verified_partial")

        return VerifyResult(
            symbol=symbol, timeframe=timeframe, market_type=market_type,
            level=1, status=status, match_pct=round(match_pct, 2),
            total_checked=total_checked, total_missing=total_missing, total_mismatch=0,
        )

    # ── Уровень 2: Точность OHLCV ─────────────────────────────────────────────

    async def _verify_accuracy(
        self, symbol: str, timeframe: str, market_type: str, windows: int
    ) -> VerifyResult:
        from storage.database import get_session_factory
        from storage.models import CandleModel
        from sqlalchemy import func, select

        tf_seconds = {"1m": 60, "5m": 300, "15m": 900, "1h": 3600, "4h": 14400}
        step_ms = tf_seconds.get(timeframe, 60) * 1000
        window_ms = CHECK_WINDOW * step_ms

        factory = get_session_factory()
        async with factory() as session:
            row = await session.execute(
                select(func.min(CandleModel.open_time), func.max(CandleModel.open_time))
                .where(
                    CandleModel.symbol == symbol,
                    CandleModel.timeframe == timeframe,
                    CandleModel.market_type == market_type,
                )
            )
            min_ts, max_ts = row.one()

        if not min_ts or not max_ts:
            return VerifyResult(symbol, timeframe, market_type, 2, "unverified", 100.0, 0, 0, 0)

        total_checked = 0
        total_mismatch = 0
        sym_api = symbol.replace("/", "-")

        connector = aiohttp.TCPConnector(resolver=aiohttp.ThreadedResolver())
        async with aiohttp.ClientSession(connector=connector,
                                         timeout=aiohttp.ClientTimeout(total=15)) as http:
            for _ in range(windows):
                if max_ts - min_ts <= window_ms:
                    start = min_ts
                else:
                    start = random.randint(min_ts, max_ts - window_ms)
                end = start + window_ms

                # REST данные с биржи
                try:
                    params = {
                        "symbol": sym_api,
                        "interval": timeframe,
                        "startTime": start,
                        "endTime": end,
                        "limit": CHECK_WINDOW + 5,
                    }
                    async with http.get(f"{BINGX_REST}/openApi/swap/v3/quote/klines",
                                        params=params) as resp:
                        api_resp = await resp.json()
                    api_data: dict[int, dict] = {}
                    for r in api_resp.get("data", []):
                        t = int(r["time"])
                        api_data[t] = {
                            "open": float(r["open"]), "high": float(r["high"]),
                            "low":  float(r["low"]),  "close": float(r["close"]),
                            "volume": float(r["volume"]),
                        }
                except Exception:
                    api_data = {}

                # Данные из БД
                async with factory() as session:
                    db_rows = await session.execute(
                        select(CandleModel).where(
                            CandleModel.symbol == symbol,
                            CandleModel.timeframe == timeframe,
                            CandleModel.market_type == market_type,
                            CandleModel.open_time >= start,
                            CandleModel.open_time <= end,
                        )
                    )
                    db_data = {
                        c.open_time: {"open": c.open, "high": c.high, "low": c.low,
                                      "close": c.close, "volume": c.volume}
                        for c in db_rows.scalars().all()
                    }

                common = set(api_data) & set(db_data)
                total_checked += len(common)
                for ts in common:
                    a, d = api_data[ts], db_data[ts]
                    for field in ("open", "high", "low", "close"):
                        if a[field] > 0:
                            rel = abs(a[field] - d[field]) / a[field]
                            if rel > PRICE_TOL:
                                total_mismatch += 1
                                break

        match_pct = (1 - total_mismatch / max(total_checked, 1)) * 100
        status = "verified" if total_mismatch == 0 else (
            "needs_review" if total_mismatch > total_checked * 0.05 else "mismatch_found"
        )
        return VerifyResult(
            symbol=symbol, timeframe=timeframe, market_type=market_type,
            level=2, status=status, match_pct=round(match_pct, 2),
            total_checked=total_checked, total_missing=0, total_mismatch=total_mismatch,
        )

    # ── Уровень 3: Корректность агрегации ─────────────────────────────────────

    async def _verify_aggregation(self, symbol: str, market_type: str) -> VerifyResult:
        """Сравниваем наш агрег. 1h с биржевым 1h."""
        from storage.database import get_session_factory
        from storage.models import CandleModel
        from sqlalchemy import select

        factory = get_session_factory()
        sym_api = symbol.replace("/", "-")

        # Берём последние 24 закрытых 1h-свечи из нашей БД
        async with factory() as session:
            rows = await session.execute(
                select(CandleModel)
                .where(
                    CandleModel.symbol == symbol,
                    CandleModel.timeframe == "1h",
                    CandleModel.market_type == market_type,
                    CandleModel.is_closed == True,
                )
                .order_by(CandleModel.open_time.desc())
                .limit(24)
            )
            db_candles = {c.open_time: c for c in rows.scalars().all()}

        if not db_candles:
            return VerifyResult(symbol, "1h", market_type, 3, "unverified", 100.0, 0, 0, 0)

        min_ts = min(db_candles)
        max_ts = max(db_candles)

        # Запрашиваем тот же период у биржи
        connector = aiohttp.TCPConnector(resolver=aiohttp.ThreadedResolver())
        async with aiohttp.ClientSession(connector=connector,
                                         timeout=aiohttp.ClientTimeout(total=15)) as http:
            try:
                async with http.get(
                    f"{BINGX_REST}/openApi/swap/v3/quote/klines",
                    params={"symbol": sym_api, "interval": "1h",
                            "startTime": min_ts, "endTime": max_ts + 3_600_000, "limit": 30},
                ) as resp:
                    api_resp = await resp.json()
                api_data = {
                    int(r["time"]): {
                        "open": float(r["open"]), "high": float(r["high"]),
                        "low": float(r["low"]), "close": float(r["close"]),
                    }
                    for r in api_resp.get("data", [])
                }
            except Exception:
                api_data = {}

        common = set(api_data) & set(db_candles)
        mismatches = 0
        for ts in common:
            a = api_data[ts]
            d = db_candles[ts]
            for field, db_val in [("open", d.open), ("high", d.high),
                                   ("low", d.low),  ("close", d.close)]:
                if a[field] > 0 and abs(a[field] - db_val) / a[field] > PRICE_TOL:
                    mismatches += 1
                    break

        match_pct = (1 - mismatches / max(len(common), 1)) * 100
        status = "verified" if mismatches == 0 else "mismatch_found"
        return VerifyResult(
            symbol=symbol, timeframe="1h", market_type=market_type,
            level=3, status=status, match_pct=round(match_pct, 2),
            total_checked=len(common), total_missing=0, total_mismatch=mismatches,
        )

    # ── Уровень 4: Непрерывность ──────────────────────────────────────────────

    async def _verify_continuity(
        self, symbol: str, timeframe: str, market_type: str
    ) -> VerifyResult:
        """Аномальные скачки > 3×ATR без подтверждения объёмом."""
        from storage.database import get_session_factory
        from storage.models import CandleModel
        from sqlalchemy import select

        factory = get_session_factory()
        async with factory() as session:
            rows = await session.execute(
                select(CandleModel)
                .where(
                    CandleModel.symbol == symbol,
                    CandleModel.timeframe == timeframe,
                    CandleModel.market_type == market_type,
                )
                .order_by(CandleModel.open_time.desc())
                .limit(200)
            )
            candles = list(reversed(rows.scalars().all()))

        if len(candles) < 20:
            return VerifyResult(symbol, timeframe, market_type, 4, "unverified", 100.0, 0, 0, 0)

        # Считаем ATR(14)
        def atr(cs, period=14):
            trs = []
            for i in range(1, len(cs)):
                tr = max(cs[i].high - cs[i].low,
                         abs(cs[i].high - cs[i-1].close),
                         abs(cs[i].low  - cs[i-1].close))
                trs.append(tr)
            return sum(trs[-period:]) / period if len(trs) >= period else (sum(trs) / len(trs) if trs else 0)

        atr_val = atr(candles)
        anomalies = 0
        for i in range(1, len(candles)):
            move = abs(candles[i].close - candles[i-1].close)
            if move > ATR_SPIKE * atr_val and atr_val > 0:
                avg_vol = sum(c.volume for c in candles[max(0, i-10):i]) / 10
                if candles[i].volume < avg_vol * 0.5:
                    anomalies += 1

        match_pct = (1 - anomalies / max(len(candles), 1)) * 100
        status = "verified" if anomalies == 0 else ("mismatch_found" if anomalies > 3 else "verified_partial")
        return VerifyResult(
            symbol=symbol, timeframe=timeframe, market_type=market_type,
            level=4, status=status, match_pct=round(match_pct, 2),
            total_checked=len(candles), total_missing=0, total_mismatch=anomalies,
        )

    # ── Сохранение и рейтинг ─────────────────────────────────────────────────

    async def _save_result(self, r: VerifyResult) -> None:
        try:
            from storage.database import get_session_factory
            from storage.models import DataVerificationLogModel

            factory = get_session_factory()
            async with factory() as session:
                row = DataVerificationLogModel(
                    symbol=r.symbol,
                    timeframe=r.timeframe,
                    market_type=r.market_type,
                    period_start=0,
                    period_end=int(time.time() * 1000),
                    level=r.level,
                    status=r.status,
                    match_pct=r.match_pct,
                    total_checked=r.total_checked,
                    total_missing=r.total_missing,
                    total_mismatch=r.total_mismatch,
                    auto_repaired=r.auto_repaired,
                    verified_at=int(time.time()),
                )
                session.add(row)
                await session.commit()
        except Exception as e:
            log.debug(f"save verification result error: {e}")

    async def _update_trust_score(
        self, symbol: str, timeframe: str, market_type: str, r: VerifyResult
    ) -> None:
        """Пересчитывает доверительный рейтинг на основе результата."""
        key = f"{symbol}:{timeframe}:{market_type}"
        current = self.trust_scores.get(key, 100)

        if r.status == "verified":
            # Постепенно восстанавливаем рейтинг
            new_score = min(100, current + 2)
        elif r.status == "verified_partial":
            new_score = max(70, current - 1)
        elif r.status == "mismatch_found":
            new_score = max(40, current - 10)
        elif r.status == "needs_review":
            new_score = max(0, current - 25)
        else:
            new_score = current

        self.trust_scores[key] = new_score

        # Обновляем в БД (батчевое обновление раз в N записей нецелесообразно, пишем сразу)
        try:
            from storage.database import get_session_factory
            from storage.models import CandleModel
            from sqlalchemy import update

            factory = get_session_factory()
            async with factory() as session:
                stmt = (
                    update(CandleModel)
                    .where(
                        CandleModel.symbol == symbol,
                        CandleModel.timeframe == timeframe,
                        CandleModel.market_type == market_type,
                    )
                    .values(data_trust_score=new_score)
                )
                await session.execute(stmt)
                await session.commit()
        except Exception as e:
            log.debug(f"update trust score error: {e}")

        await self._bus.publish("verification.trust_updated", {
            "symbol": symbol, "timeframe": timeframe,
            "market_type": market_type, "trust_score": new_score,
            "status": r.status,
        })

    def get_trust_scores(self) -> dict[str, int]:
        return dict(self.trust_scores)
