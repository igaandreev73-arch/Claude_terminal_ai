# Инструкция: подключение к VPS (132.243.235.173)

## Инструменты

На Windows установлен PuTTY suite:
- `C:\tools\plink.exe` — консольный SSH-клиент (для команд)
- `C:\tools\pscp.exe` — копирование файлов по SCP

Также доступен стандартный `ssh.exe` (встроенный в Windows 10/11).

## Параметры подключения

| Параметр | Значение |
|----------|----------|
| Адрес | `132.243.235.173` |
| Пользователь | `root` |
| Пароль | `Tppy9h63FG6Sv` |
| Host key | `ssh-ed25519 255 SHA256:2qbP/giHPeMqFA55iVkzMR7AcKMTLbog9XzekgNWul4` |
| SSH-ключ | Добавлен в `~/.ssh/authorized_keys` (аутентификация без пароля) |

## Проект на VPS

- **Путь проекта:** `/root/crypto-telemetry/` (НЕ `/opt/collector/`)
- **БД:** `/root/crypto-telemetry/data/telemetry.db`
- **Сервис collector:** `crypto-telemetry.service` (systemd) — RUN_MODE=collector
- **Сервис API:** `crypto-telemetry-api.service` (systemd) — uvicorn server.py :8800
- **REST API:** `http://localhost:8800/...?api_key=vps_telemetry_key_2026`
- **Telegram Bot:** long-polling внутри collector (команды: /summary, /status, /health, /symbols, /backfill, /errors, /help)

## Аутентификация

Есть **два способа** подключения:

### 1. По паролю (через plink)

Используется, когда SSH-ключ не добавлен. Требует `plink.exe`.

### 2. По SSH-ключу (через ssh или plink без -pw)

SSH-ключ уже добавлен в `authorized_keys` на VPS. Можно подключаться **без пароля**:
- Через стандартный `ssh.exe` (встроенный в Windows)
- Через `plink.exe` без флага `-pw`

## Выполнение команд

### plink (по паролю)

```powershell
& 'C:\tools\plink.exe' -batch -ssh -pw 'Tppy9h63FG6Sv' `
    -hostkey 'ssh-ed25519 255 SHA256:2qbP/giHPeMqFA55iVkzMR7AcKMTLbog9XzekgNWul4' `
    root@132.243.235.173 'команда'
```

### ssh (по ключу, без пароля)

```powershell
ssh -o StrictHostKeyChecking=no root@132.243.235.173 'команда'
```

### plink (по ключу, без пароля)

```powershell
& 'C:\tools\plink.exe' -batch -ssh `
    -hostkey 'ssh-ed25519 255 SHA256:2qbP/giHPeMqFA55iVkzMR7AcKMTLbog9XzekgNWul4' `
    root@132.243.235.173 'команда'
```

### Примеры:

```powershell
# --- По паролю (plink) ---

# Статус collector
& 'C:\tools\plink.exe' -batch -ssh -pw 'Tppy9h63FG6Sv' `
    -hostkey 'ssh-ed25519 255 SHA256:2qbP/giHPeMqFA55iVkzMR7AcKMTLbog9XzekgNWul4' `
    root@132.243.235.173 'systemctl status crypto-telemetry'

# Статус API
& 'C:\tools\plink.exe' -batch -ssh -pw 'Tppy9h63FG6Sv' `
    -hostkey 'ssh-ed25519 255 SHA256:2qbP/giHPeMqFA55iVkzMR7AcKMTLbog9XzekgNWul4' `
    root@132.243.235.173 'systemctl status crypto-telemetry-api'

# Логи collector
& 'C:\tools\plink.exe' -batch -ssh -pw 'Tppy9h63FG6Sv' `
    -hostkey 'ssh-ed25519 255 SHA256:2qbP/giHPeMqFA55iVkzMR7AcKMTLbog9XzekgNWul4' `
    root@132.243.235.173 'journalctl -u crypto-telemetry --no-pager -n 50'

# Перезапуск collector
& 'C:\tools\plink.exe' -batch -ssh -pw 'Tppy9h63FG6Sv' `
    -hostkey 'ssh-ed25519 255 SHA256:2qbP/giHPeMqFA55iVkzMR7AcKMTLbog9XzekgNWul4' `
    root@132.243.235.173 'systemctl restart crypto-telemetry'

# Деплой: git pull + перезапуск collector
& 'C:\tools\plink.exe' -batch -ssh -pw 'Tppy9h63FG6Sv' `
    -hostkey 'ssh-ed25519 255 SHA256:2qbP/giHPeMqFA55iVkzMR7AcKMTLbog9XzekgNWul4' `
    root@132.243.235.173 'cd /root/crypto-telemetry && git pull origin main && systemctl restart crypto-telemetry && systemctl restart crypto-telemetry-api && echo OK_DONE'

# --- По ключу (ssh) ---

# Статус collector
ssh -o StrictHostKeyChecking=no root@132.243.235.173 'systemctl status crypto-telemetry'

# Статус API
ssh -o StrictHostKeyChecking=no root@132.243.235.173 'systemctl status crypto-telemetry-api'

# Логи collector
ssh -o StrictHostKeyChecking=no root@132.243.235.173 'journalctl -u crypto-telemetry --no-pager -n 50'

# Перезапуск collector
ssh -o StrictHostKeyChecking=no root@132.243.235.173 'systemctl restart crypto-telemetry'

# Деплой: git pull + перезапуск обоих сервисов
ssh -o StrictHostKeyChecking=no root@132.243.235.173 'cd /root/crypto-telemetry && git pull origin main && systemctl restart crypto-telemetry && systemctl restart crypto-telemetry-api && echo OK_DONE'

# REST API через localhost на VPS (curl)
ssh -o StrictHostKeyChecking=no root@132.243.235.173 'curl -s http://localhost:8800/status?api_key=vps_telemetry_key_2026'
```

## Копирование файлов

### pscp (по паролю)

```powershell
& 'C:\tools\pscp.exe' -batch -pw 'Tppy9h63FG6Sv' `
    -hostkey 'ssh-ed25519 255 SHA256:2qbP/giHPeMqFA55iVkzMR7AcKMTLbog9XzekgNWul4' `
    'C:\путь\к\файлу.py' 'root@132.243.235.173:/root/crypto-telemetry/scripts/файл.py'
```

### scp (по ключу, без пароля)

```powershell
scp -o StrictHostKeyChecking=no 'C:\путь\к\файлу.py' root@132.243.235.173:/root/crypto-telemetry/scripts/файл.py
```

## REST API VPS (без SSH)

VPS также доступен через HTTP API на порту 8800:

```powershell
# Статус
Invoke-WebRequest -Uri 'http://132.243.235.173:8800/status?api_key=vps_telemetry_key_2026'

# Health
Invoke-WebRequest -Uri 'http://132.243.235.173:8800/health?api_key=vps_telemetry_key_2026'

# Данные по символам
Invoke-WebRequest -Uri 'http://132.243.235.173:8800/data/status?api_key=vps_telemetry_key_2026'

# Перезапуск модуля (futures_ws / spot_ws / rest_poller / service)
Invoke-WebRequest -Uri 'http://132.243.235.173:8800/commands/restart/futures_ws?api_key=vps_telemetry_key_2026' -Method POST
```

## Быстрый деплой (одна команда)

```powershell
& 'C:\tools\plink.exe' -batch -ssh -pw 'Tppy9h63FG6Sv' `
    -hostkey 'ssh-ed25519 255 SHA256:2qbP/giHPeMqFA55iVkzMR7AcKMTLbog9XzekgNWul4' `
    root@132.243.235.173 'cd /root/crypto-telemetry && git pull origin main && systemctl restart crypto-telemetry && systemctl restart crypto-telemetry-api && echo OK_DONE'
```
