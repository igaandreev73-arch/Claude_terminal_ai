"""
Агрегация 1m свечей в старшие таймфреймы (5m, 15m, 1h, 1d, 1W).

Стратегия:
- Берёт 1m свечи из БД (market_type='futures')
- Агрегирует их в 5m, 15m, 1h, 1d, 1W
- Сохраняет обратно в таблицу candles с соответствующим timeframe
- Использует INSERT OR IGNORE — пропускает уже существующие

Запуск: python scripts/aggregate_timeframes.py [--market-type futures] [--symbols BTC/USDT ETH/USDT]
"""
import argparse
import sqlite3
import time
from datetime import datetime
from pathlib import Path

DB_PATH = Path("/opt/collector/data/terminal.db")

# Маппинг: таймфрейм -> количество минут
TF_MINUTES = {
    "5m": 5,
    "15m": 15,
    "1h": 60,
    "4h": 240,
    "1d": 1440,
    "1W": 10080,
}


def get_1m_range(conn, market_type, symbol):
    """Возвращает MIN и MAX open_time для 1m свечей."""
    cur = conn.cursor()
    cur.execute(
        "SELECT MIN(open_time), MAX(open_time) FROM candles "
        "WHERE timeframe='1m' AND market_type=? AND symbol=?",
        (market_type, symbol),
    )
    return cur.fetchone()


def aggregate_timeframe(conn, market_type, symbol, tf, tf_minutes):
    """Агрегирует 1m свечи в указанный таймфрейм."""
    cur = conn.cursor()
    tf_ms = tf_minutes * 60 * 1000

    # Получаем все 1m свечи, сгруппированные по периодам
    cur.execute(
        """SELECT
            (? / ?) * ? AS bucket,
            MIN(open) AS open,
            MAX(high) AS high,
            MIN(low) AS low,
            last_value(close) OVER (PARTITION BY (open_time / ?) ORDER BY open_time) AS close,
            SUM(volume) AS volume,
            COUNT(*) AS cnt
        FROM candles
        WHERE timeframe='1m' AND market_type=? AND symbol=?
        GROUP BY bucket
        ORDER BY bucket""",
        ("open_time", tf_ms, tf_ms, tf_ms, market_type, symbol),
    )

    # SQLite не поддерживает LAST_VALUE в GROUP BY, поэтому делаем иначе
    cur.execute(
        """SELECT
            (open_time / ?) * ? AS bucket,
            MIN(open),
            MAX(high),
            MIN(low),
            SUM(volume),
            COUNT(*)
        FROM candles
        WHERE timeframe='1m' AND market_type=? AND symbol=?
        GROUP BY bucket
        ORDER BY bucket""",
        (tf_ms, tf_ms, market_type, symbol),
    )
    rows = cur.fetchall()

    if not rows:
        return 0

    # Для каждого bucket'а получаем close из последней 1m свечи
    written = 0
    now_ts = int(time.time())

    for bucket, open_p, high, low, volume, cnt in rows:
        if cnt < tf_minutes * 0.5:  # Нужно минимум 50% данных
            continue

        # Получаем close из последней 1m свечи в этом bucket'е
        cur.execute(
            "SELECT close FROM candles WHERE timeframe='1m' AND market_type=? AND symbol=? AND open_time=?",
            (market_type, symbol, bucket + (tf_ms - 60000)),
        )
        close_row = cur.fetchone()
        if not close_row:
            # Берём самую позднюю доступную
            cur.execute(
                "SELECT close FROM candles WHERE timeframe='1m' AND market_type=? AND symbol=? AND open_time BETWEEN ? AND ? ORDER BY open_time DESC LIMIT 1",
                (market_type, symbol, bucket, bucket + tf_ms),
            )
            close_row = cur.fetchone()
            if not close_row:
                continue
        close = close_row[0]

        cur.execute(
            """INSERT OR IGNORE INTO candles
               (symbol, timeframe, open_time, market_type,
                open, high, low, close, volume,
                is_closed, source, data_trust_score, created_at)
               VALUES (?, ?, ?, ?,
                       ?, ?, ?, ?, ?,
                       1, 'aggregated', 99, ?)""",
            (symbol, tf, bucket, market_type,
             open_p, high, low, close, volume, now_ts),
        )
        if cur.rowcount > 0:
            written += 1

    conn.commit()
    return written


def main():
    parser = argparse.ArgumentParser(description="Агрегация 1m в старшие таймфреймы")
    parser.add_argument("--market-type", default="futures", choices=["spot", "futures"])
    parser.add_argument("--symbols", nargs="+", default=None,
                        help="Символы (по умолчанию все)")
    parser.add_argument("--timeframes", nargs="+",
                        default=["5m", "15m", "1h", "4h", "1d", "1W"],
                        help="Таймфреймы для агрегации")
    args = parser.parse_args()

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    # Получаем список символов
    if args.symbols:
        symbols = args.symbols
    else:
        cur.execute(
            "SELECT DISTINCT symbol FROM candles WHERE market_type=? AND timeframe='1m'",
            (args.market_type,),
        )
        symbols = [row[0] for row in cur.fetchall()]

    print("=" * 60)
    print(f"АГРЕГАЦИЯ ТАЙМФРЕЙМОВ")
    print(f"Рынок: {args.market_type}")
    print(f"Символы: {', '.join(symbols)}")
    print(f"Таймфреймы: {', '.join(args.timeframes)}")
    print("=" * 60)

    total_written = 0
    for symbol in symbols:
        mn, mx = get_1m_range(conn, args.market_type, symbol)
        if not mn or not mx:
            print(f"\n❌ {symbol}: нет 1m данных")
            continue

        days = (mx - mn) / 86400000
        print(f"\n📈 {symbol}: {days:.0f} дней 1m данных")

        for tf in args.timeframes:
            tf_min = TF_MINUTES.get(tf)
            if not tf_min:
                print(f"  ⚠️ {tf}: неизвестный таймфрейм, пропускаю")
                continue

            t0 = time.time()
            written = aggregate_timeframe(conn, args.market_type, symbol, tf, tf_min)
            elapsed = time.time() - t0
            total_written += written
            print(f"  {tf}: +{written:,} свечей ({elapsed:.1f}с)")

    print("\n" + "=" * 60)
    print(f"📊 ИТОГО: {total_written:,} свечей агрегировано")
    print("=" * 60)

    conn.close()


if __name__ == "__main__":
    main()
