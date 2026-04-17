# UI Design Specification
## Криптовалютный торговый терминал — Desktop Dashboard

> Этот документ передаётся в Claude Code для реализации интерфейса.  
> Референс: скриншот DeFiFusion dashboard (тёмная тема).

---

## 1. Дизайн-концепция

**Стиль:** Dark финтех — профессиональный, плотный, информационный.  
**Тема:** Исключительно тёмная. Без светлого режима.  
**Ощущение:** Bloomberg Terminal meets modern crypto — данные на первом месте, красота — в деталях.  
**Запоминающееся:** Неоновые акценты на чёрном фоне, плавные анимации данных, живые графики.

---

## 2. Цветовая палитра (CSS переменные)

```css
:root {
  /* Фоны / Backgrounds */
  --bg-app:        #0d0d0f;   /* самый тёмный — фон приложения */
  --bg-surface:    #141418;   /* карточки, панели */
  --bg-elevated:   #1c1c22;   /* поднятые элементы, hover */
  --bg-input:      #1e1e26;   /* поля ввода */
  --bg-overlay:    #16161d;   /* оверлеи, дропдауны */

  /* Акценты / Accents */
  --accent-blue:   #3b82f6;   /* основная кнопка, активные вкладки */
  --accent-green:  #22d3a5;   /* рост, прибыль, positive */
  --accent-red:    #f43f5e;   /* падение, убыток, negative */
  --accent-orange: #f59e0b;   /* BTC, предупреждения */
  --accent-purple: #a78bfa;   /* ETH, вторичные акценты */
  --accent-teal:   #14b8a6;   /* USDT, индикаторы */

  /* Текст / Typography */
  --text-primary:   #f1f1f3;  /* заголовки, важные числа */
  --text-secondary: #9898a8;  /* подписи, вторичная информация */
  --text-muted:     #55555f;  /* плейсхолдеры, disabled */
  --text-inverse:   #0d0d0f;  /* текст на акцентных кнопках */

  /* Границы / Borders */
  --border-subtle:  rgba(255,255,255,0.06);
  --border-default: rgba(255,255,255,0.10);
  --border-strong:  rgba(255,255,255,0.18);

  /* Тени / Shadows */
  --shadow-card:    0 4px 24px rgba(0,0,0,0.4);
  --shadow-elevated: 0 8px 40px rgba(0,0,0,0.6);
  --shadow-green:   0 0 20px rgba(34,211,165,0.15);
  --shadow-blue:    0 0 20px rgba(59,130,246,0.20);

  /* Радиусы / Radius */
  --radius-sm:  6px;
  --radius-md:  10px;
  --radius-lg:  14px;
  --radius-xl:  20px;
  --radius-pill: 999px;

  /* Шрифты / Fonts */
  --font-display: 'Space Grotesk', sans-serif;  /* числа, заголовки */
  --font-body:    'DM Sans', sans-serif;         /* интерфейс */
  --font-mono:    'JetBrains Mono', monospace;   /* цены, хэши, логи */
}
```

---

## 3. Типографика

```css
/* Импорт шрифтов */
@import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;500;600;700&family=DM+Sans:wght@300;400;500&family=JetBrains+Mono:wght@400;500&display=swap');

/* Шкала */
--text-xs:   11px;  /* метки, бейджи */
--text-sm:   12px;  /* вторичный текст */
--text-base: 13px;  /* основной текст интерфейса */
--text-md:   15px;  /* подзаголовки карточек */
--text-lg:   18px;  /* заголовки секций */
--text-xl:   24px;  /* крупные числа */
--text-2xl:  32px;  /* главный баланс */
--text-3xl:  40px;  /* hero числа */

/* Числа всегда — Space Grotesk, tabular-nums */
.price, .balance, .percent {
  font-family: var(--font-display);
  font-variant-numeric: tabular-nums;
  letter-spacing: -0.02em;
}

/* Положительное/отрицательное значение */
.positive { color: var(--accent-green); }
.negative { color: var(--accent-red); }
```

---

## 4. Компоненты

### 4.1 Карточка (Card)

```css
.card {
  background: var(--bg-surface);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-lg);
  padding: 20px;
  position: relative;
  overflow: hidden;
  transition: border-color 0.2s ease, box-shadow 0.2s ease;
}

.card:hover {
  border-color: var(--border-default);
  box-shadow: var(--shadow-card);
}

/* Тонкая светящаяся линия сверху карточки при hover */
.card::before {
  content: '';
  position: absolute;
  top: 0; left: 0; right: 0;
  height: 1px;
  background: linear-gradient(90deg,
    transparent 0%,
    var(--accent-blue) 50%,
    transparent 100%
  );
  opacity: 0;
  transition: opacity 0.3s ease;
}

.card:hover::before { opacity: 1; }
```

### 4.2 Топ-бар / Navigation

```css
.topbar {
  height: 56px;
  background: var(--bg-surface);
  border-bottom: 1px solid var(--border-subtle);
  display: flex;
  align-items: center;
  padding: 0 24px;
  gap: 32px;
  position: sticky;
  top: 0;
  z-index: 100;
  backdrop-filter: blur(12px);
}

.nav-link {
  font-family: var(--font-body);
  font-size: var(--text-base);
  color: var(--text-secondary);
  transition: color 0.15s;
}

.nav-link.active, .nav-link:hover {
  color: var(--text-primary);
}

.nav-link.active {
  position: relative;
}

/* Подчёркивание активного пункта */
.nav-link.active::after {
  content: '';
  position: absolute;
  bottom: -18px;
  left: 0; right: 0;
  height: 2px;
  background: var(--accent-blue);
  border-radius: 2px;
}
```

### 4.3 Кнопки

```css
/* Primary — синяя */
.btn-primary {
  background: var(--accent-blue);
  color: #fff;
  border: none;
  border-radius: var(--radius-pill);
  padding: 12px 24px;
  font-family: var(--font-body);
  font-size: var(--text-base);
  font-weight: 500;
  cursor: pointer;
  transition: opacity 0.15s, transform 0.1s, box-shadow 0.2s;
}

.btn-primary:hover {
  opacity: 0.92;
  box-shadow: var(--shadow-blue);
}

.btn-primary:active {
  transform: scale(0.98);
}

/* Ghost — прозрачная с рамкой */
.btn-ghost {
  background: transparent;
  color: var(--text-secondary);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
  padding: 6px 12px;
  font-size: var(--text-sm);
  transition: border-color 0.15s, color 0.15s;
}

.btn-ghost:hover {
  border-color: var(--border-strong);
  color: var(--text-primary);
}
```

### 4.4 Бейджи изменения цены

```css
.badge-change {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  font-family: var(--font-display);
  font-size: var(--text-sm);
  font-weight: 600;
  padding: 2px 0;
}

.badge-change.up   { color: var(--accent-green); }
.badge-change.down { color: var(--accent-red); }

/* Стрелки */
.badge-change.up::before  { content: '↑'; }
.badge-change.down::before { content: '↓'; }
```

### 4.5 Строка транзакции

```css
.tx-row {
  display: grid;
  grid-template-columns: 32px 1fr auto auto;
  align-items: center;
  gap: 12px;
  padding: 10px 0;
  border-bottom: 1px solid var(--border-subtle);
  transition: background 0.15s;
}

.tx-row:hover {
  background: var(--bg-elevated);
  margin: 0 -20px;
  padding: 10px 20px;
  border-radius: var(--radius-sm);
}

.tx-icon {
  width: 32px; height: 32px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
}

.tx-type-send   { color: var(--accent-red); }
.tx-type-receive { color: var(--accent-green); }
```

### 4.6 Поле ввода (Exchange form)

```css
.input-field {
  background: var(--bg-input);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-md);
  padding: 12px 16px;
  color: var(--text-primary);
  font-family: var(--font-mono);
  font-size: var(--text-md);
  width: 100%;
  transition: border-color 0.2s;
}

.input-field:focus {
  outline: none;
  border-color: var(--accent-blue);
  box-shadow: 0 0 0 3px rgba(59,130,246,0.12);
}
```

### 4.7 Coin-карточка (нижняя строка)

```css
.coin-card {
  background: var(--bg-surface);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-lg);
  padding: 16px 20px;
  display: flex;
  flex-direction: column;
  gap: 8px;
  transition: transform 0.2s ease, box-shadow 0.2s ease;
}

.coin-card:hover {
  transform: translateY(-2px);
  box-shadow: var(--shadow-card);
}

.coin-mini-chart {
  height: 36px;
  /* SVG sparkline */
}
```

### 4.8 Donut-чарт (Wallet)

Реализуется через SVG с `stroke-dasharray`:

```css
.donut-ring {
  fill: none;
  stroke-width: 12;
  stroke-linecap: round;
  transition: stroke-dashoffset 0.8s cubic-bezier(0.4, 0, 0.2, 1);
}

/* Сегменты */
.segment-btc  { stroke: var(--accent-orange); }
.segment-eth  { stroke: var(--accent-purple); }
.segment-usdt { stroke: var(--accent-teal); }
.segment-bg   { stroke: var(--bg-elevated); }
```

---

## 5. Сетка и Layout

```css
/* Основной layout */
.app-layout {
  display: grid;
  grid-template-rows: 56px 1fr;
  min-height: 100vh;
  background: var(--bg-app);
}

.main-content {
  padding: 20px 24px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

/* Верхний ряд: 3 карточки */
.top-row {
  display: grid;
  grid-template-columns: 1fr 1.2fr 1.2fr;
  gap: 16px;
}

/* Средний ряд: Exchange (узкая) + Chart (широкая) */
.mid-row {
  display: grid;
  grid-template-columns: 300px 1fr;
  gap: 16px;
}

/* Нижний ряд: 4 Coin-карточки */
.bottom-row {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 16px;
}
```

---

## 6. Иконки монет (SVG-аватары)

```css
/* Круглые иконки монет */
.coin-avatar {
  width: 32px; height: 32px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 14px;
  font-weight: 700;
  flex-shrink: 0;
}

.coin-btc  { background: #f7931a; color: #fff; }
.coin-eth  { background: #627eea; color: #fff; }
.coin-usdt { background: #26a17b; color: #fff; }
.coin-bnb  { background: #f3ba2f; color: #fff; }
```

---

## 7. Анимации

### 7.1 Появление карточек при загрузке

```css
@keyframes cardReveal {
  from {
    opacity: 0;
    transform: translateY(16px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

.card {
  animation: cardReveal 0.4s ease forwards;
  opacity: 0;
}

/* Staggered delay — каждая карточка появляется с задержкой */
.card:nth-child(1) { animation-delay: 0.05s; }
.card:nth-child(2) { animation-delay: 0.10s; }
.card:nth-child(3) { animation-delay: 0.15s; }
.card:nth-child(4) { animation-delay: 0.20s; }
.card:nth-child(5) { animation-delay: 0.25s; }
.card:nth-child(6) { animation-delay: 0.30s; }
```

### 7.2 Счётчик числа (цена меняется)

```css
@keyframes numberFlash {
  0%   { opacity: 1; }
  30%  { opacity: 0.4; color: var(--accent-green); }
  100% { opacity: 1; }
}

.price-updating {
  animation: numberFlash 0.4s ease;
}

/* При падении — красный */
.price-down {
  animation: numberFlash 0.4s ease;
  --flash-color: var(--accent-red);
}
```

### 7.3 Donut-чарт — появление

```css
@keyframes donutDraw {
  from { stroke-dashoffset: 440; }  /* периметр окружности */
  to   { stroke-dashoffset: var(--target-offset); }
}

.donut-ring {
  stroke-dasharray: 440;
  animation: donutDraw 1s cubic-bezier(0.4, 0, 0.2, 1) forwards;
  animation-delay: 0.3s;
}
```

### 7.4 Sparkline-мини-графики (Coin карточки)

```css
@keyframes lineReveal {
  from { stroke-dashoffset: var(--line-length); }
  to   { stroke-dashoffset: 0; }
}

.sparkline-path {
  stroke-dasharray: var(--line-length);
  stroke-dashoffset: var(--line-length);
  animation: lineReveal 1.2s ease forwards;
  animation-delay: 0.5s;
}
```

### 7.5 Пульсирующая точка — live индикатор

```css
@keyframes livePulse {
  0%   { box-shadow: 0 0 0 0 rgba(34,211,165, 0.6); }
  70%  { box-shadow: 0 0 0 6px rgba(34,211,165, 0); }
  100% { box-shadow: 0 0 0 0 rgba(34,211,165, 0); }
}

.live-dot {
  width: 7px; height: 7px;
  border-radius: 50%;
  background: var(--accent-green);
  animation: livePulse 2s ease infinite;
}
```

### 7.6 Event Bus Monitor — поток событий

```css
@keyframes eventSlideIn {
  from {
    opacity: 0;
    transform: translateX(-8px);
  }
  to {
    opacity: 1;
    transform: translateX(0);
  }
}

.event-row-new {
  animation: eventSlideIn 0.2s ease forwards;
}

/* Строки исчезают снизу */
@keyframes eventFadeOut {
  to { opacity: 0; height: 0; padding: 0; }
}
```

### 7.7 Hover-эффект на строках таблицы

```css
@keyframes rowHighlight {
  0%   { background: rgba(59,130,246,0.08); }
  100% { background: transparent; }
}

/* Новая транзакция появляется с подсветкой */
.tx-row-new {
  animation: rowHighlight 1.5s ease forwards;
}
```

### 7.8 Кнопка Exchange — shimmer эффект

```css
@keyframes shimmer {
  0%   { background-position: -200% center; }
  100% { background-position: 200% center; }
}

.btn-primary:hover {
  background: linear-gradient(
    90deg,
    var(--accent-blue) 0%,
    #60a5fa 40%,
    var(--accent-blue) 100%
  );
  background-size: 200% auto;
  animation: shimmer 1.5s linear infinite;
}
```

### 7.9 Скелетон загрузки

```css
@keyframes skeletonPulse {
  0%, 100% { opacity: 0.4; }
  50%       { opacity: 0.8; }
}

.skeleton {
  background: var(--bg-elevated);
  border-radius: var(--radius-sm);
  animation: skeletonPulse 1.5s ease infinite;
}
```

---

## 8. Линейный график (Overall Growth)

Реализуется через **Chart.js** или **Recharts**.

```javascript
// Настройки Chart.js
const chartConfig = {
  type: 'line',
  options: {
    responsive: true,
    plugins: {
      legend: { display: false },
      tooltip: {
        backgroundColor: '#1c1c22',
        borderColor: 'rgba(255,255,255,0.1)',
        borderWidth: 1,
        titleColor: '#f1f1f3',
        bodyColor: '#9898a8',
        padding: 12,
        cornerRadius: 10,
      }
    },
    scales: {
      x: {
        grid: { color: 'rgba(255,255,255,0.04)' },
        ticks: { color: '#55555f', font: { family: 'JetBrains Mono', size: 11 } }
      },
      y: {
        grid: { color: 'rgba(255,255,255,0.04)' },
        ticks: { color: '#55555f' }
      }
    },
    animation: {
      duration: 1000,
      easing: 'easeInOutQuart'
    }
  }
};

// Датасеты
const datasets = [
  {
    label: 'BTC',
    borderColor: '#f59e0b',
    borderWidth: 2,
    pointRadius: 0,
    tension: 0.4,
    fill: false,
  },
  {
    label: 'ETH',
    borderColor: '#a78bfa',
    borderWidth: 2,
    pointRadius: 0,
    tension: 0.4,
    fill: false,
  },
  {
    label: 'USDT',
    borderColor: '#22d3a5',
    borderWidth: 2,
    pointRadius: 0,
    tension: 0.4,
    fill: false,
  },
];

// Столбчатый объём под графиком
const volumeDataset = {
  type: 'bar',
  backgroundColor: 'rgba(59,130,246,0.15)',
  borderRadius: 2,
};
```

---

## 9. Специфические детали из референса

### Топ-бар
- Логотип: bold текст + точка-акцент синего цвета (`DeFiFusion.`)
- Поиск: `border-radius: pill`, `background: var(--bg-input)`, иконка лупы справа
- Уведомления: иконка колокола, dot-индикатор непрочитанных
- Аватар: круглый, 32px

### Balance карточка (левая верхняя)
- Маленький % сверху — зелёный с стрелкой вверх
- Главное число — `font-size: 32px`, `font-weight: 700`, `Space Grotesk`
- Income/Expenses — двухколоночная сетка внутри, разделители тонкие

### Wallet карточка (центральная верхняя)
- Donut chart: SVG, три сегмента, центральная подпись `+2.31%` зелёная
- Справа — список монет: иконка, название, процент
- Размер Donut: ~120px

### Transaction карточка (правая верхняя)
- Фильтр `All` — кнопка-пилюля справа
- Каждая строка: иконка монеты | название | тип (Receive/Send) + стрелка | сумма
- Receive — зелёная стрелка вниз, Send — красная стрелка вверх

### Exchange панель (левая средняя)
- Конвертер: `1 BTC → 53,260.20 USD`
- Два поля ввода с дропдаунами выбора монеты
- Кнопка обмена (⇄) в правом верхнем углу карточки — для переворота пары
- Кнопка Exchange — полная ширина, синяя, pill-форма

### Overall Growth (правая средняя — широкая)
- Табы таймфрейма: `1 min`, `3 min`, `30 min`, `1 hour`, `24 hour`, `1 day`, `1 week`
- Активный таб: тёмный бейдж с белым текстом, `border-radius: pill`
- Tooltip при hover: тёмная карточка с тремя монетами и их % — как показано на референсе
- Бары объёма: синие, низкие, под основным графиком

### Coin карточки (нижний ряд, 4 штуки)
- Иконка монеты 40px + sparkline справа (одна линия)
- Под sparkline — % изменения (зелёный/красный)
- Название и полная цена внизу: крупно
- Тикер (BTC, ETH) — серый, маленький

---

## 10. Специфика для Electron + React

```typescript
// globals.d.ts — типы для Electron IPC
interface ElectronAPI {
  onMarketData: (callback: (data: MarketData) => void) => void;
  onSignal: (callback: (signal: Signal) => void) => void;
  onEventBus: (callback: (event: BusEvent) => void) => void;
}

// Пример компонента с анимацией числа
// Использовать framer-motion для React:
import { motion, useSpring, useTransform } from 'framer-motion';

function AnimatedPrice({ value }: { value: number }) {
  const spring = useSpring(value, { stiffness: 100, damping: 20 });
  // Число плавно "доезжает" до нового значения
}
```

### Зависимости для package.json

```json
{
  "dependencies": {
    "react": "^18",
    "framer-motion": "^11",
    "recharts": "^2",
    "lightweight-charts": "^4",
    "lucide-react": "^0.383",
    "clsx": "^2",
    "tailwindcss": "^3"
  }
}
```

### Tailwind — расширение конфига

```javascript
// tailwind.config.js
module.exports = {
  theme: {
    extend: {
      colors: {
        surface:  '#141418',
        elevated: '#1c1c22',
        accent: {
          blue:   '#3b82f6',
          green:  '#22d3a5',
          red:    '#f43f5e',
          orange: '#f59e0b',
          purple: '#a78bfa',
        }
      },
      fontFamily: {
        display: ['Space Grotesk', 'sans-serif'],
        body:    ['DM Sans', 'sans-serif'],
        mono:    ['JetBrains Mono', 'monospace'],
      },
      animation: {
        'card-reveal': 'cardReveal 0.4s ease forwards',
        'live-pulse':  'livePulse 2s ease infinite',
        'shimmer':     'shimmer 1.5s linear infinite',
        'skeleton':    'skeletonPulse 1.5s ease infinite',
      }
    }
  }
}
```

---

## 11. Структура компонентов React

```
src/components/
├── layout/
│   ├── TopBar.tsx           -- навигация, поиск, аватар
│   └── AppLayout.tsx        -- grid layout обёртка
│
├── cards/
│   ├── BalanceCard.tsx      -- баланс + income/expenses
│   ├── WalletCard.tsx       -- donut chart + список монет
│   ├── TransactionCard.tsx  -- список транзакций
│   └── CoinCard.tsx         -- мини-карточка монеты (нижний ряд)
│
├── exchange/
│   └── ExchangePanel.tsx    -- конвертер + кнопка
│
├── chart/
│   ├── GrowthChart.tsx      -- линейный график + табы ТФ
│   └── Sparkline.tsx        -- мини-график для CoinCard
│
├── monitor/
│   ├── EventBusMonitor.tsx  -- живой поток событий
│   └── ModuleStatus.tsx     -- статус каждого модуля
│
├── trading/
│   ├── TradePanel.tsx       -- открытие позиций
│   └── SignalCard.tsx       -- входящий сигнал с кнопкой подтверждения
│
└── ui/
    ├── Card.tsx             -- базовая карточка
    ├── Badge.tsx            -- бейдж %
    ├── CoinAvatar.tsx       -- иконка монеты
    ├── AnimatedNumber.tsx   -- число с анимацией
    ├── LiveDot.tsx          -- пульсирующий индикатор
    └── Skeleton.tsx         -- скелетон загрузки
```

---

## 12. Инструкция для Claude Code

При реализации соблюдать порядок:

1. **Сначала** — базовые CSS-переменные и Tailwind конфиг
2. **Затем** — UI-примитивы: `Card`, `Badge`, `CoinAvatar`, `AnimatedNumber`
3. **Затем** — Layout: `TopBar`, `AppLayout` с сеткой
4. **Затем** — Карточки верхнего ряда: Balance → Wallet (с Donut) → Transactions
5. **Затем** — Средний ряд: Exchange Panel → Growth Chart
6. **Затем** — Нижний ряд: Coin Cards со Sparkline
7. **В конце** — анимации: stagger reveal, live updates, price flash

**Данные на старте** — использовать моковые данные (`mock/marketData.ts`).  
**Подключение к Python backend** — через WebSocket на `ws://localhost:8765`.  
**Реальные данные** заменяют моки автоматически при подключении сокета.

---

*Документ создан: апрель 2026*  
*Версия: 1.0*  
*Обновлять при изменении дизайн-системы*
