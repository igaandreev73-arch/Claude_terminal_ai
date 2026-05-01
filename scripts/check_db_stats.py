"""
Проверка статистики БД — сколько данных уже загружено.
"""
import sqlite3
from datetime import datetime
from pathlib import Path

DB_PATH = Path("/opt/collector/data/terminal.db")
conn = sqlite3.connect(DB_PATH)
cur = conn.cursor()

print("=== СТАТИСТИКА БД ===")
cur.execute("SELECT COUNT(*), MIN(open_time), MAX(open_time) FROM candles")
cnt, mn, mx = cur.fetchone()
print(f"Всего свечей: {cnt:,}")
print(f"Первая: {datetime.utcfromtimestamp(mn/1000).strftime('%Y-%m-%d') if mn else 'N/A'}")
print(f"Последняя: {datetime.utcfromtimestamp(mx/1000).strftime('%Y-%m-%d') if mx else 'N/A'}")
print(f"Размер БД: {DB_PATH.stat().st_size / 1024 / 1024:.1f} MB")

print("\n=== ПО ТИПУ РЫНКА ===")
for mt in ['spot', 'futures']:
    cur.execute("SELECT COUNT(*), MIN(open_time), MAX(open_time) FROM candles WHERE market_type=?", (mt,))
    c, mn, mx = cur.fetchone()
    print(f"{mt}: {c:,} свечей | {datetime.utcfromtimestamp(mn/1000).strftime('%Y-%m-%d') if mn else 'N/A'} -> {datetime.utcfromtimestamp(mx/1000).strftime('%Y-%m-%d') if mx else 'N/A'}")

print("\n=== 1m FUTURES ПО СИМВОЛАМ ===")
cur.execute("""
    SELECT symbol, COUNT(*), MIN(open_time), MAX(open_time)
    FROM candles
    WHERE timeframe='1m' AND market_type='futures'
    GROUP BY symbol ORDER BY COUNT(*) DESC
""")
for row in cur.fetchall():
    sym, c, mn, mx = row
    from_d = datetime.utcfromtimestamp(mn/1000).strftime('%Y-%m-%d') if mn else 'N/A'
    to_d = datetime.utcfromtimestamp(mx/1000).strftime('%Y-%m-%d') if mx else 'N/A'
    days = (mx - mn) / 86400000 if mn and mx else 0
    print(f"  {sym}: {c:,} свечей | {from_d} -> {to_d} ({days:.0f} дн)")

print("\n=== 1m SPOT ПО СИМВОЛАМ ===")
cur.execute("""
    SELECT symbol, COUNT(*), MIN(open_time), MAX(open_time)
    FROM candles
    WHERE timeframe='1m' AND market_type='spot'
    GROUP BY symbol ORDER BY COUNT(*) DESC
""")
for row in cur.fetchall():
    sym, c, mn, mx = row
    from_d = datetime.utcfromtimestamp(mn/1000).strftime('%Y-%m-%d') if mn else 'N/A'
    to_d = datetime.utcfromtimestamp(mx/1000).strftime('%Y-%m-%d') if mx else 'N/A'
    days = (mx - mn) / 86400000 if mn and mx else 0
    print(f"  {sym}: {c:,} свечей | {from_d} -> {to_d} ({days:.0f} дн)")

conn.close()
