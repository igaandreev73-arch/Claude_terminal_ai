"""
Принудительное восстановление БД через sqlite3 .clone и .dump.
Создаёт новую БД, копирует все данные из старой.
"""
import subprocess
import sys
from pathlib import Path

DB_PATH = Path("/opt/collector/data/terminal.db")
TMP_PATH = Path("/opt/collector/data/terminal_tmp.db")
OLD_PATH = Path("/opt/collector/data/terminal_corrupted.db")

print(f"Исходная БД: {DB_PATH} ({DB_PATH.stat().st_size / 1024 / 1024:.1f} MB)")

# Способ 1: .clone через Python
print("\n=== Способ 1: .clone через Python ===")
try:
    import sqlite3
    
    # Открываем с ignore_init
    old_conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro&ignore_init=1", uri=True)
    new_conn = sqlite3.connect(str(TMP_PATH))
    
    # Копируем через backup (работает даже с повреждёнными страницами)
    old_conn.backup(new_conn, pages=1000, progress=lambda *a: None)
    old_conn.close()
    new_conn.close()
    
    print(f"  Создана временная БД: {TMP_PATH} ({TMP_PATH.stat().st_size / 1024 / 1024:.1f} MB)")
    
    # Проверяем новую БД
    check_conn = sqlite3.connect(str(TMP_PATH))
    cur = check_conn.cursor()
    cur.execute("PRAGMA integrity_check")
    result = cur.fetchone()
    print(f"  Integrity check: {result[0]}")
    
    if result[0] == "ok":
        cur.execute("SELECT COUNT(*) FROM candles")
        print(f"  Свечей: {cur.fetchone()[0]:,}")
        
        # Заменяем старую БД на новую
        import shutil
        shutil.move(str(DB_PATH), str(OLD_PATH))
        shutil.move(str(TMP_PATH), str(DB_PATH))
        print(f"  ✅ БД восстановлена! Старая сохранена как {OLD_PATH.name}")
    else:
        print(f"  ❌ Новая БД тоже повреждена")
        TMP_PATH.unlink(missing_ok=True)
        
except Exception as e:
    print(f"  ❌ Ошибка: {e}")

# Финальная проверка
print("\n=== Финальная проверка ===")
try:
    import sqlite3
    conn = sqlite3.connect(str(DB_PATH))
    cur = conn.cursor()
    cur.execute("PRAGMA integrity_check")
    print(f"Integrity: {cur.fetchone()[0]}")
    
    cur.execute("SELECT COUNT(*) FROM candles")
    print(f"Свечей: {cur.fetchone()[0]:,}")
    
    # По market_type
    for mt in ['spot', 'futures']:
        cur.execute("SELECT COUNT(*), MIN(open_time), MAX(open_time) FROM candles WHERE market_type=?", (mt,))
        c, mn, mx = cur.fetchone()
        from datetime import datetime
        from_d = datetime.utcfromtimestamp(mn/1000).strftime('%Y-%m-%d') if mn else 'N/A'
        to_d = datetime.utcfromtimestamp(mx/1000).strftime('%Y-%m-%d') if mx else 'N/A'
        print(f"  {mt}: {c:,} | {from_d} -> {to_d}")
    
    conn.close()
except Exception as e:
    print(f"Ошибка: {e}")

print(f"\nРазмер БД: {DB_PATH.stat().st_size / 1024 / 1024:.1f} MB")
print("ГОТОВО")
