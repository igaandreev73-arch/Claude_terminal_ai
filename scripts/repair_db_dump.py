"""
Восстановление БД через sqlite3 .dump и пересоздание.
Использует subprocess для вызова sqlite3 .dump с ignore_init.
"""
import subprocess
import sys
from pathlib import Path

DB_PATH = Path("/opt/collector/data/terminal.db")
TMP_DUMP = Path("/opt/collector/data/terminal_dump.sql")
NEW_DB = Path("/opt/collector/data/terminal_new.db")
OLD_DB = Path("/opt/collector/data/terminal_corrupted.db")

print(f"Исходная БД: {DB_PATH} ({DB_PATH.stat().st_size / 1024 / 1024:.1f} MB)")

# Шаг 1: Дамп через sqlite3 с ignore_init
print("\n=== Шаг 1: Дамп данных ===")
try:
    # Используем Python для дампа с ignore_init
    import sqlite3
    
    # Открываем с ignore_init — пропускаем повреждённые страницы
    old_conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro&ignore_init=1", uri=True)
    
    # Создаём новую БД
    new_conn = sqlite3.connect(str(NEW_DB))
    
    # Копируем схему
    print("  Копируем схему...")
    for line in old_conn.iterdump():
        if line.startswith("CREATE TABLE") or line.startswith("CREATE INDEX") or line.startswith("CREATE UNIQUE"):
            try:
                new_conn.executescript(line)
            except Exception as e:
                print(f"  ⚠️ Ошибка схемы: {e}")
    
    new_conn.commit()
    
    # Копируем данные по таблицам
    print("  Копируем данные...")
    cur_old = old_conn.cursor()
    
    # Получаем список таблиц
    cur_old.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = [row[0] for row in cur_old.fetchall()]
    print(f"  Таблицы: {tables}")
    
    total_rows = 0
    for table in tables:
        try:
            # Получаем количество строк
            cur_old.execute(f"SELECT COUNT(*) FROM \"{table}\"")
            count = cur_old.fetchone()[0]
            print(f"  {table}: {count:,} строк")
            
            # Копируем данные
            cur_old.execute(f"SELECT * FROM \"{table}\"")
            columns = [desc[0] for desc in cur_old.description]
            placeholders = ",".join(["?" for _ in columns])
            col_names = ",".join(f'"{c}"' for c in columns)
            
            batch = []
            for row in cur_old:
                batch.append(row)
                if len(batch) >= 1000:
                    try:
                        new_conn.execute(
                            f"INSERT OR IGNORE INTO \"{table}\" ({col_names}) VALUES ({placeholders})",
                            batch
                        )
                        new_conn.commit()
                    except Exception as e:
                        print(f"    ⚠️ Ошибка вставки батча: {e}")
                    batch = []
            
            if batch:
                try:
                    new_conn.execute(
                        f"INSERT OR IGNORE INTO \"{table}\" ({col_names}) VALUES ({placeholders})",
                        batch
                    )
                    new_conn.commit()
                except Exception as e:
                    print(f"    ⚠️ Ошибка вставки: {e}")
            
            total_rows += count
            
        except Exception as e:
            print(f"  ❌ Ошибка таблицы {table}: {e}")
    
    old_conn.close()
    new_conn.close()
    
    print(f"\n  Всего строк скопировано: {total_rows:,}")
    print(f"  Новая БД: {NEW_DB} ({NEW_DB.stat().st_size / 1024 / 1024:.1f} MB)")
    
except Exception as e:
    print(f"❌ Ошибка: {e}")
    import traceback
    traceback.print_exc()

# Шаг 2: Проверка новой БД
print("\n=== Шаг 2: Проверка новой БД ===")
try:
    check_conn = sqlite3.connect(str(NEW_DB))
    cur = check_conn.cursor()
    cur.execute("PRAGMA integrity_check")
    result = cur.fetchone()
    print(f"  Integrity: {result[0]}")
    
    if result[0] == "ok":
        cur.execute("SELECT COUNT(*) FROM candles")
        print(f"  Свечей: {cur.fetchone()[0]:,}")
        
        # По market_type
        for mt in ['spot', 'futures']:
            cur.execute("SELECT COUNT(*), MIN(open_time), MAX(open_time) FROM candles WHERE market_type=?", (mt,))
            c, mn, mx = cur.fetchone()
            from datetime import datetime
            from_d = datetime.utcfromtimestamp(mn/1000).strftime('%Y-%m-%d') if mn else 'N/A'
            to_d = datetime.utcfromtimestamp(mx/1000).strftime('%Y-%m-%d') if mx else 'N/A'
            print(f"    {mt}: {c:,} | {from_d} -> {to_d}")
        
        check_conn.close()
        
        # Заменяем старую БД
        import shutil
        shutil.move(str(DB_PATH), str(OLD_DB))
        shutil.move(str(NEW_DB), str(DB_PATH))
        print(f"\n  ✅ БД восстановлена! Старая: {OLD_DB.name}")
    else:
        print(f"  ❌ Новая БД повреждена")
        
except Exception as e:
    print(f"  ❌ Ошибка проверки: {e}")

print(f"\nРазмер: {DB_PATH.stat().st_size / 1024 / 1024:.1f} MB")
print("ГОТОВО")
