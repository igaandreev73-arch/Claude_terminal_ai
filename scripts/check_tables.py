"""
Проверка целостности каждой таблицы в БД.
"""
import sqlite3
from pathlib import Path

DB_PATH = Path("/opt/collector/data/terminal.db")
print(f"БД: {DB_PATH} ({DB_PATH.stat().st_size / 1024 / 1024:.1f} MB)")

try:
    conn = sqlite3.connect(str(DB_PATH))
    cur = conn.cursor()
    
    # Версия SQLite
    cur.execute("SELECT sqlite_version()")
    print(f"SQLite version: {cur.fetchone()[0]}")
    
    # Все таблицы
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
    tables = [row[0] for row in cur.fetchall()]
    
    print(f"\n{'='*60}")
    print(f"{'Таблица':<25} {'Строки':<12} {'Статус'}")
    print(f"{'='*60}")
    
    ok_count = 0
    fail_count = 0
    
    for table in tables:
        try:
            cur.execute(f"SELECT COUNT(*) FROM \"{table}\"")
            count = cur.fetchone()[0]
            print(f"{table:<25} {count:<12,} ✅")
            ok_count += 1
        except Exception as e:
            print(f"{table:<25} {'ERROR':<12} ❌ {str(e)[:60]}")
            fail_count += 1
    
    print(f"{'='*60}")
    print(f"Целых: {ok_count} | Повреждено: {fail_count}")
    
    conn.close()
    
except Exception as e:
    print(f"❌ Не удалось открыть БД: {e}")

print("\nГОТОВО")
