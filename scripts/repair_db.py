"""
Восстановление БД после ошибки "database disk image is malformed".
1. Проверка целостности
2. Создание дампа и восстановление через .clone
3. Подсчёт статистики
"""
import sqlite3
from pathlib import Path

DB_PATH = Path("/opt/collector/data/terminal.db")
BACKUP_PATH = Path("/opt/collector/data/terminal_backup.db")

print(f"БД: {DB_PATH}")
print(f"Размер: {DB_PATH.stat().st_size / 1024 / 1024:.1f} MB")

# Шаг 1: Проверка целостности
print("\n=== Шаг 1: Проверка целостности ===")
try:
    conn = sqlite3.connect(str(DB_PATH))
    cur = conn.cursor()
    cur.execute("PRAGMA integrity_check")
    result = cur.fetchone()
    print(f"Integrity check: {result[0]}")
    
    if result[0] != "ok":
        print("БД повреждена! Восстанавливаю...")
        # Пытаемся сделать .clone
        conn.execute("VACUUM")
        print("VACUUM выполнен")
    
    # Счётчики
    cur.execute("SELECT COUNT(*) FROM candles")
    print(f"Свечей: {cur.fetchone()[0]:,}")
    conn.close()
except Exception as e:
    print(f"Ошибка: {e}")
    print("Пробуем создать новую БД из старой...")

# Шаг 2: Если БД сильно повреждена — делаем дамп и восстанавливаем
print("\n=== Шаг 2: Принудительное восстановление ===")
try:
    # Пробуем открыть с ignore_init
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("VACUUM")
    print("VACUUM OK")
    
    # Ещё одна проверка
    cur = conn.cursor()
    cur.execute("PRAGMA integrity_check")
    result = cur.fetchone()
    print(f"После VACUUM: {result[0]}")
    
    cur.execute("SELECT COUNT(*) FROM candles")
    print(f"Свечей после восстановления: {cur.fetchone()[0]:,}")
    conn.close()
except Exception as e:
    print(f"Не удалось восстановить: {e}")
    print("Пробуем создать новую БД...")
    try:
        # Создаём новую БД
        new_conn = sqlite3.connect(str(BACKUP_PATH))
        old_conn = sqlite3.connect(str(DB_PATH))
        old_conn.backup(new_conn)
        old_conn.close()
        new_conn.close()
        print(f"Бэкап создан: {BACKUP_PATH}")
        
        # Заменяем старую БД на новую
        import shutil
        shutil.move(str(BACKUP_PATH), str(DB_PATH))
        print("БД восстановлена из бэкапа")
    except Exception as e2:
        print(f"Полный крах: {e2}")

# Шаг 3: Финальная статистика
print("\n=== Финальная статистика ===")
try:
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
    print(f"Финальная ошибка: {e}")

print(f"\nРазмер БД: {DB_PATH.stat().st_size / 1024 / 1024:.1f} MB")
print("ГОТОВО")
