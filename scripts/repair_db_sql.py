"""
Восстановление БД через прямой SQL с ignore_init.
Читает данные напрямую из повреждённой БД через отдельные SELECT запросы.
"""
import sqlite3
from pathlib import Path
import shutil

# Сначала возвращаем старую БД
OLD_PATH = Path("/opt/collector/data/terminal_corrupted.db")
DB_PATH = Path("/opt/collector/data/terminal.db")
TMP_PATH = Path("/opt/collector/data/terminal_tmp2.db")

if OLD_PATH.exists():
    print(f"Восстанавливаем из {OLD_PATH.name}...")
    shutil.copy(str(OLD_PATH), str(DB_PATH))
    print(f"БД восстановлена: {DB_PATH} ({DB_PATH.stat().st_size / 1024 / 1024:.1f} MB)")

print(f"\nОткрываем с ignore_init...")
try:
    # Открываем в read-only с ignore_init
    old_conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    old_conn.execute("PRAGMA ignore_check_constraints = ON")
    
    # Создаём новую БД
    new_conn = sqlite3.connect(str(TMP_PATH))
    
    old_cur = old_conn.cursor()
    new_cur = new_conn.cursor()
    
    # Получаем схему
    old_cur.execute("SELECT sql FROM sqlite_master WHERE type IN ('table','index') ORDER BY type DESC")
    schemas = old_cur.fetchall()
    
    for (sql,) in schemas:
        if sql:
            try:
                new_cur.execute(sql)
                print(f"  Схема: {sql[:60]}...")
            except Exception as e:
                print(f"  ⚠️ Ошибка схемы: {e}")
    
    new_conn.commit()
    
    # Получаем список таблиц
    old_cur.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
    tables = [row[0] for row in old_cur.fetchall()]
    print(f"\nТаблицы: {tables}")
    
    total = 0
    for table in tables:
        try:
            # Получаем колонки
            old_cur.execute(f"PRAGMA table_info(\"{table}\")")
            columns = [row[1] for row in old_cur.fetchall()]
            col_names = ",".join(f'"{c}"' for c in columns)
            placeholders = ",".join(["?" for _ in columns])
            
            # Считаем строки
            old_cur.execute(f"SELECT COUNT(*) FROM \"{table}\"")
            count = old_cur.fetchone()[0]
            print(f"\n  {table}: {count:,} строк")
            
            # Читаем и копируем по батчам
            old_cur.execute(f"SELECT * FROM \"{table}\"")
            
            batch = []
            batch_count = 0
            while True:
                row = old_cur.fetchone()
                if row is None:
                    break
                batch.append(tuple(row))
                batch_count += 1
                
                if len(batch) >= 500:
                    try:
                        new_cur.executemany(
                            f"INSERT OR IGNORE INTO \"{table}\" ({col_names}) VALUES ({placeholders})",
                            batch
                        )
                        new_conn.commit()
                    except Exception as e:
                        print(f"    ⚠️ Батч: {e}")
                    total += len(batch)
                    batch = []
                    
                    if batch_count % 10000 == 0:
                        print(f"    {batch_count:,} / {count:,}")
            
            if batch:
                try:
                    new_cur.executemany(
                        f"INSERT OR IGNORE INTO \"{table}\" ({col_names}) VALUES ({placeholders})",
                        batch
                    )
                    new_conn.commit()
                except Exception as e:
                    print(f"    ⚠️ Финальный батч: {e}")
                total += len(batch)
            
            print(f"    ✅ {table}: {batch_count:,} строк скопировано")
            
        except Exception as e:
            print(f"  ❌ {table}: {e}")
    
    old_conn.close()
    new_conn.close()
    
    print(f"\n=== ИТОГО: {total:,} строк ===")
    print(f"Новая БД: {TMP_PATH} ({TMP_PATH.stat().st_size / 1024 / 1024:.1f} MB)")
    
    # Проверка
    check = sqlite3.connect(str(TMP_PATH))
    cur = check.cursor()
    cur.execute("PRAGMA integrity_check")
    print(f"Integrity: {cur.fetchone()[0]}")
    
    if cur.fetchone()[0] == "ok":
        cur.execute("SELECT COUNT(*) FROM candles")
        print(f"Свечей: {cur.fetchone()[0]:,}")
        
        # Заменяем
        shutil.move(str(DB_PATH), str(OLD_PATH))
        shutil.move(str(TMP_PATH), str(DB_PATH))
        print(f"✅ БД восстановлена!")
    
    check.close()
    
except Exception as e:
    print(f"❌ Ошибка: {e}")
    import traceback
    traceback.print_exc()

print(f"\nРазмер: {DB_PATH.stat().st_size / 1024 / 1024:.1f} MB")
print("ГОТОВО")
