# Changelog / История версий

Все значимые изменения фиксируются в этом файле.  
All notable changes are documented in this file.

Формат основан на [Keep a Changelog](https://keepachangelog.com/).  
Format based on [Keep a Changelog](https://keepachangelog.com/).

Версионирование: `MAJOR.MINOR.PATCH`
- `MAJOR` — архитектурные изменения, несовместимые с предыдущей версией
- `MINOR` — новый функционал, обратно совместимый
- `PATCH` — исправления, мелкие улучшения

---

## [Unreleased] — В разработке

### Planned / Запланировано
- Базовая инфраструктура: Event Bus, Health Monitor, Logger
- Data Collector: BingX WebSocket + REST с Rate-Limit Guard
- TF Aggregator: агрегация таймфреймов из 1m свечей
- Order Book Processor: реконструкция стакана, детектор манипуляций
- Analytics Core: TA Engine, SmartMoney, Volume Engine, MTF Confluence
- Signal Engine: генерация и скоринг сигналов
- Backtester: тестирование стратегий на исторических данных
- Execution Engine: три режима исполнения
- Desktop UI: Electron + React
- AI Advisor: встроенный ассистент с контекстом системы

---

## [0.1.0] — 2026-04-17

### Added / Добавлено
- Создан репозиторий проекта
- `PRD.md` — полная архитектура системы (20 разделов)
- `README.md` — описание проекта (RU + EN)
- `DEVLOG_RU.md` — журнал разработки на русском
- `DEVLOG_EN.md` — development log in English
- `CHANGELOG.md` — история версий

### Decisions / Решения
- Выбран стек: Python 3.11+, asyncio, Electron + React, SQLite → PostgreSQL
- Выбрана архитектура: Event-driven, независимые модули
- Определены фазы: Phase 1 Desktop → Phase 2 Web SaaS
- Биржа старта: BingX (Futures + Spot)
