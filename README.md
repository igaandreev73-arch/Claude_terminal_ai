# 🤖 Crypto Trading Terminal

**Персональная автоматизированная торговая платформа**  
**Personal automated trading platform**

---

## RU — О проекте

Криптовалютный торговый терминал с аналитическим ядром, автоматической генерацией сигналов и исполнением сделок. Разработан для торговли фьючерсами и спотом на бирже BingX.

### Возможности

- Непрерывный сбор рыночных данных (WebSocket + REST) по топ-5 парам
- Технический анализ, концепции SmartMoney, объёмный анализ — одновременно на всех таймфреймах
- Анализ стакана: детектор манипуляций, расчёт проскальзывания, дисбаланс bid/ask
- Бэктестинг стратегий с авто-оптимизацией параметров
- Три режима исполнения: авто / полуавто / только алёрт
- Встроенный AI-ассистент с доступом к состоянию всей системы
- Event Bus Monitor — живой поток всех внутренних событий
- Сбор ML-датасета с первого дня работы

### Стек

- **Backend:** Python 3.11+, asyncio, SQLAlchemy, pandas-ta
- **Frontend:** Electron + React + TypeScript (Desktop Phase 1)
- **БД:** SQLite → PostgreSQL + TimescaleDB (Phase 2)
- **Биржа:** BingX (Futures + Spot)

### Фазы

| Фаза | Описание | Статус |
|---|---|---|
| Phase 1 | Desktop-приложение, один пользователь, BingX | 🔄 В разработке |
| Phase 2 | Web SaaS, несколько пользователей, мультибиржа | ⏳ Запланировано |

---

## EN — About

A crypto trading terminal with an analytical core, automatic signal generation, and trade execution. Built for futures and spot trading on BingX exchange.

### Features

- Continuous market data collection (WebSocket + REST) for top-5 pairs
- Technical analysis, SmartMoney concepts, volume analysis — across all timeframes simultaneously
- Order book analysis: manipulation detector, slippage calculation, bid/ask imbalance
- Strategy backtesting with automatic parameter optimization
- Three execution modes: auto / semi-auto / alert only
- Built-in AI advisor with full system state access
- Event Bus Monitor — live stream of all internal events
- ML dataset collection from day one

### Stack

- **Backend:** Python 3.11+, asyncio, SQLAlchemy, pandas-ta
- **Frontend:** Electron + React + TypeScript (Desktop Phase 1)
- **DB:** SQLite → PostgreSQL + TimescaleDB (Phase 2)
- **Exchange:** BingX (Futures + Spot)

### Phases

| Phase | Description | Status |
|---|---|---|
| Phase 1 | Desktop app, single user, BingX | 🔄 In development |
| Phase 2 | Web SaaS, multi-user, multi-exchange | ⏳ Planned |

---

## Документация / Documentation

| Файл / File | Описание / Description |
|---|---|
| `PRD.md` | Полная архитектура системы / Full system architecture |
| `DEVLOG_RU.md` | Журнал разработки на русском / Development log in Russian |
| `DEVLOG_EN.md` | Development log in English |
| `CHANGELOG.md` | История версий / Version history |

---

## Быстрый старт / Quick start

```bash
# Клонировать репозиторий / Clone the repo
git clone https://github.com/YOUR_USERNAME/crypto-terminal.git
cd crypto-terminal

# Создать виртуальное окружение / Create virtual environment
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# Установить зависимости / Install dependencies
pip install -r requirements.txt

# Настроить переменные окружения / Configure environment
cp .env.example .env
# Отредактировать .env / Edit .env

# Запустить / Run
python main.py
```

---

*Разработка начата: апрель 2026 / Development started: April 2026*
