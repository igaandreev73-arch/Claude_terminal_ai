"""
Попытка восстановить данные из повреждённых таблиц candles и orderbook_snapshots.
Использует ignore_init для пропуска повреждённых страниц.
"""
import sqlite3
from pathlib import Path

DB_PATH = Path("/opt/collector/data/terminal.db")
TMP_PATH = Path("/opt/collector/data/terminal_recovered.db")

print(f"БД: {DB_PATH} ({DB_PATH.stat().st_size / 1024 / 1024:.1f} MB)")
print(f"SQLite: {sqlite3.sqlite_version}")

# Создаём новую БД со схемой
new_conn = sqlite3.connect(str(TMP_PATH))
new_cur = new_conn.cursor()

# Создаём таблицы
new_cur.executescript("""
    CREATE TABLE IF NOT EXISTS candles (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        symbol TEXT NOT NULL,
        timeframe TEXT NOT NULL,
        open_time INTEGER NOT NULL,
        market_type TEXT DEFAULT 'spot',
        open REAL NOT NULL,
        high REAL NOT NULL,
        low REAL NOT NULL,
        close REAL NOT NULL,
        volume REAL NOT NULL,
        is_closed INTEGER DEFAULT 1,
        source TEXT DEFAULT 'exchange',
        data_trust_score INTEGER DEFAULT 99,
        created_at INTEGER
    );
    CREATE UNIQUE INDEX IF NOT EXISTS uq_candles ON candles(symbol, timeframe, open_time);
    CREATE INDEX IF NOT EXISTS idx_candles_lookup ON candles(symbol, timeframe, market_type, open_time);
    
    CREATE TABLE IF NOT EXISTS orderbook_snapshots (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        symbol TEXT NOT NULL,
        timestamp INTEGER NOT NULL,
        market_type TEXT DEFAULT 'spot',
        bids TEXT,
        asks TEXT,
        bid_volume REAL DEFAULT 0,
        ask_volume REAL DEFAULT 0,
        spread REAL DEFAULT 0,
        mid_price REAL DEFAULT 0,
        imbalance REAL DEFAULT 0
    );
""")
new_conn.commit()

# Пытаемся открыть старую БД с ignore_init
print("\n=== Попытка чтения candles с ignore_init ===")
try:
    old_conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro&ignore_init=1", uri=True)
    old_cur = old_conn.cursor()
    
    # Пробуем читать по одному символу
    symbols = ["BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT", "XRP/USDT"]
    total = 0
    
    for sym in symbols:
        try:
            old_cur.execute(
                "SELECT symbol, timeframe, open_time, market_type, open, high, low, close, volume, is_closed, source, data_trust_score, created_at FROM candles WHERE symbol=? ORDER BY open_time",
                (sym,)
            )
            batch = []
            count = 0
            while True:
                try:
                    row = old_cur.fetchone()
                    if row is None:
                        break
                    batch.append(row)
                    count += 1
                    if len(batch) >= 500:
                        new_cur.executemany(
                            "INSERT OR IGNORE INTO candles (symbol, timeframe, open_time, market_type, open, high, low, close, volume, is_closed, source, data_trust_score, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                            batch
                        )
                        new_conn.commit()
                        total += len(batch)
                        batch = []
            if batch:
                new_cur.executemany(
                    "INSERT OR IGNORE INTO candles (symbol, timeframe, open_time, market_type, open, high, low, close, volume, is_closed, source, data_trust_score, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    batch
                )
                new_conn.commit()
                total += len(batch)
            print(f"  {sym}: {count:,} строк")
        except Exception as e:
            print(f"  {sym}: ❌ {str(e)[:80]}")
    
    print(f"\n  Всего candles: {total:,}")
    
    # Пробуем orderbook_snapshots
    print("\n=== Попытка чтения orderbook_snapshots с ignore_init ===")
    try:
        old_cur.execute("SELECT COUNT(*) FROM orderbook_snapshots")
        ob_count = old_cur.fetchone()[0]
        print(f"  Всего: {ob_count:,}")
        
        old_cur.execute("SELECT * FROM orderbook_snapshots ORDER BY timestamp")
        batch = []
        ob_total = 0
        while True:
            try:
                row = old_cur.fetchone()
                if row is None:
                    break
                batch.append(row[1:])  # пропускаем id
                ob_total += 1
                if len(batch) >= 500:
                    new_cur.executemany(
                        "INSERT INTO orderbook_snapshots (symbol, timestamp, market_type, bids, asks, bid_volume, ask_volume, spread, mid_price, imbalance) VALUES (?,?,?,?,?,?,?,?,?,?)",
                        batch
                    )
                    new_conn.commit()
                    batch = []
        if batch:
            new_cur.executemany(
                "INSERT INTO orderbook_snapshots (symbol, timestamp, market_type, bids, asks, bid_volume, ask_volume, spread, mid_price, imbalance) VALUES (?,?,?,?,?,?,?,?,?,?)",
                batch
            )
            new_conn.commit()
        print(f"  Скопировано: {ob_total:,}")
    except Exception as e:
        print(f"  ❌ {str(e)[:80]}")
    
    old_conn.close()
    
except Exception as e:
    print(f"❌ Не удалось открыть: {e}")

new_conn.close()

print(f"\n=== ИТОГ ===")
print(f"Новая БД: {TMP_PATH} ({TMP_PATH.stat().st_size / 1024 / 1024:.1f} MB)")

# Проверка
check = sqlite3.connect(str(TMP_PATH))
cur = check.cursor()
cur.execute("PRAGMA integrity_check")
print(f"Integrity: {cur.fetchone()[0]}")
cur.execute("SELECT COUNT(*) FROM candles")
print(f"Candles: {cur.fetchone()[0]:,}")
cur.execute("SELECT COUNT(*) FROM orderbook_snapshots")
print(f"OB Snapshots: {cur.fetchone()[0]:,}")
check.close()

print("\nГОТОВО")
