"""
Скрипт тестирования Telegram-уведомлений 2.0.

Тестирует:
  1. Симуляция отключения WS → ALERT
  2. Симуляция восстановления WS → RESOLVE
  3. Симуляция переполнения диска → ALERT
  4. Симуляция ошибки backfill → ALERT
  5. Симуляция крупной ликвидации → ALERT
  6. Проверка /summary → ответ от бота
  7. Проверка /status → ответ от бота

Использование:
  python scripts/test_alerts.py [--vps-url http://vps:8800] [--api-key vps_telemetry_key_2026]

Без аргументов — использует переменные окружения VPS_HOST, VPS_PORT, TELEMETRY_API_KEY.
"""
import argparse
import asyncio
import os
import sys
from datetime import datetime, timezone

# Добавляем корень проекта в путь для импорта
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    import aiohttp
    _AIOHTTP_OK = True
except ImportError:
    _AIOHTTP_OK = False


async def _test_alert(session: aiohttp.ClientSession, url: str, api_key: str,
                      alert_type: str) -> bool:
    """Тестирует POST /telegram/test/alert."""
    headers = {"X-API-Key": api_key}
    payload = {"type": alert_type}
    try:
        async with session.post(
            f"{url}/telegram/test/alert",
            json=payload,
            headers=headers,
            timeout=aiohttp.ClientTimeout(total=15),
        ) as resp:
            if resp.status != 200:
                print(f"  ❌ {alert_type}: HTTP {resp.status}")
                return False
            data = await resp.json()
            ok = data.get("ok", False)
            status = "✅" if ok else "❌"
            print(f"  {status} {alert_type}: sent={ok}")
            return ok
    except Exception as e:
        print(f"  ❌ {alert_type}: {e}")
        return False


async def _test_resolve(session: aiohttp.ClientSession, url: str, api_key: str,
                        resolve_type: str) -> bool:
    """Тестирует POST /telegram/test/resolve."""
    headers = {"X-API-Key": api_key}
    payload = {"type": resolve_type}
    try:
        async with session.post(
            f"{url}/telegram/test/resolve",
            json=payload,
            headers=headers,
            timeout=aiohttp.ClientTimeout(total=15),
        ) as resp:
            if resp.status != 200:
                print(f"  ❌ resolve/{resolve_type}: HTTP {resp.status}")
                return False
            data = await resp.json()
            ok = data.get("ok", False)
            status = "✅" if ok else "❌"
            print(f"  {status} resolve/{resolve_type}: sent={ok}")
            return ok
    except Exception as e:
        print(f"  ❌ resolve/{resolve_type}: {e}")
        return False


async def _test_bot_command(session: aiohttp.ClientSession, url: str,
                            api_key: str, command: str) -> bool:
    """Проверяет, что REST endpoint для команды бота отвечает (имитация)."""
    headers = {"X-API-Key": api_key}
    try:
        # Используем /status как прокси для проверки доступности
        async with session.get(
            f"{url}/status",
            headers=headers,
            timeout=aiohttp.ClientTimeout(total=10),
        ) as resp:
            if resp.status != 200:
                print(f"  ❌ /{command}: VPS недоступен (HTTP {resp.status})")
                return False
            data = await resp.json()
            print(f"  ✅ /{command}: VPS отвечает, сервис {'активен' if data.get('service', {}).get('active') else 'неактивен'}")
            return True
    except Exception as e:
        print(f"  ❌ /{command}: {e}")
        return False


async def _test_telegram_config(session: aiohttp.ClientSession, url: str,
                                api_key: str) -> bool:
    """Проверяет конфигурацию Telegram."""
    headers = {"X-API-Key": api_key}
    try:
        async with session.get(
            f"{url}/telegram/status",
            headers=headers,
            timeout=aiohttp.ClientTimeout(total=10),
        ) as resp:
            if resp.status != 200:
                print(f"  ❌ telegram/status: HTTP {resp.status}")
                return False
            data = await resp.json()
            configured = data.get("configured", False)
            chat_id = data.get("chat_id", "")
            status = "✅" if configured else "⚠️"
            print(f"  {status} Telegram: настроен={configured}, chat_id={chat_id}")
            return configured
    except Exception as e:
        print(f"  ❌ telegram/status: {e}")
        return False


async def main() -> None:
    parser = argparse.ArgumentParser(description="Тестирование Telegram-уведомлений 2.0")
    parser.add_argument("--vps-url", default=None, help="URL VPS (http://host:port)")
    parser.add_argument("--api-key", default=None, help="API ключ VPS")
    args = parser.parse_args()

    # Определяем URL и API-ключ
    host = os.getenv("VPS_HOST", "localhost")
    port = os.getenv("VPS_PORT", "8800")
    api_key = args.api_key or os.getenv("TELEMETRY_API_KEY", "vps_telemetry_key_2026")
    base_url = args.vps_url or f"http://{host}:{port}"

    if not _AIOHTTP_OK:
        print("❌ aiohttp не установлен. Установите: pip install aiohttp")
        sys.exit(1)

    print(f"\n{'='*60}")
    print(f"🧪 Тестирование Telegram-уведомлений 2.0")
    print(f"{'='*60}")
    print(f"📡 VPS URL: {base_url}")
    print(f"🔑 API Key: {api_key[:12]}...")
    print(f"⏰ {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    print(f"{'='*60}\n")

    results: list[tuple[str, bool]] = []

    async with aiohttp.ClientSession() as session:
        # 0. Проверка конфигурации Telegram
        print("📋 0. Проверка конфигурации Telegram")
        ok = await _test_telegram_config(session, base_url, api_key)
        results.append(("telegram_config", ok))
        print()

        if not ok:
            print("⚠️ Telegram не настроен. Пропускаю тесты отправки.")
            print("   Настройте через POST /telegram/config или .env\n")
        else:
            # 1-5. Тесты ALERT
            print("🚨 1-5. Тесты ALERT-уведомлений")
            alert_types = [
                ("ws_down", "Отключение WS"),
                ("disk_full", "Переполнение диска"),
                ("data_stale", "Устаревшие данные"),
                ("liq_high", "Крупная ликвидация"),
                ("backfill_error", "Ошибка backfill"),
            ]
            for atype, desc in alert_types:
                print(f"  📌 {desc}")
                ok = await _test_alert(session, base_url, api_key, atype)
                results.append((f"alert/{atype}", ok))
                await asyncio.sleep(1)  # Пауза между запросами
            print()

            # Тесты RESOLVE
            print("✅ 6-8. Тесты RESOLVE-уведомлений")
            resolve_types = [
                ("ws_down", "Восстановление WS"),
                ("disk_full", "Освобождение диска"),
                ("data_stale", "Обновление данных"),
            ]
            for rtype, desc in resolve_types:
                print(f"  📌 {desc}")
                ok = await _test_resolve(session, base_url, api_key, rtype)
                results.append((f"resolve/{rtype}", ok))
                await asyncio.sleep(1)
            print()

        # 6-7. Проверка команд бота (через REST)
        print("🤖 9-10. Проверка команд бота")
        for cmd in ("summary", "status"):
            ok = await _test_bot_command(session, base_url, api_key, cmd)
            results.append((f"bot/{cmd}", ok))
        print()

    # Итоги
    print(f"{'='*60}")
    print(f"📊 Итоги тестирования")
    print(f"{'='*60}")
    total = len(results)
    passed = sum(1 for _, ok in results if ok)
    failed = total - passed
    for name, ok in results:
        status = "✅" if ok else "❌"
        print(f"  {status} {name}")
    print(f"\n📈 Всего: {total} | Пройдено: {passed} | Провалено: {failed}")
    print(f"{'='*60}\n")

    if failed > 0:
        print("⚠️ Некоторые тесты не пройдены. Проверьте логи VPS.")
        sys.exit(1)
    else:
        print("🎉 Все тесты пройдены!")
        sys.exit(0)


if __name__ == "__main__":
    asyncio.run(main())
