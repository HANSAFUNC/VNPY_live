# Web Dashboard Tab Redesign - Design Spec

**Date:** 2026-04-26
**Topic:** Dashboard tab reorganization with Trading/Overview/Logs structure

---

## Overview

Redesign the VNPY web dashboard to use a three-tab structure inspired by freqUI:
- **Dashboard Tab** - Account overview, open positions, and closed trades (homepage)
- **Trade Tab** - K-line chart with trading operations
- **Logs Tab** - Real-time system and trading logs

---

## Tab 1: Dashboard (总览) - Homepage

### Layout
```
┌─────────────────────────────────────────────────────────────────┐
│  [收益率曲线]  [当日盈亏] [总资产] [持仓市值] [总收益率]          │
├─────────────────────────────────────────────────────────────────┤
│  📊 当前持仓 (正在持仓的交易)                                    │
├─────────────────────────────────────────────────────────────────┤
│  名称  │ 代码   │ 订单ID  │ 方向 │ 持仓量 │ 总筹码   │ 开仓价格 │
│  最新价 │ 涨跌幅 │ 开始时间                                          │
├─────────────────────────────────────────────────────────────────┤
│  贵州茅台 │ 600519 │ ORD001 │ 多  │ 100   │ ¥180000 │ ¥1800.00 │
│  ¥1850.00 │ +2.78% │ 2024-01-01 09:30:00                              │
├─────────────────────────────────────────────────────────────────┤
│  📈 历史成交 (结束的交易)                                        │
├─────────────────────────────────────────────────────────────────┤
│  名称  │ 代码   │ 订单ID  │ 方向 │ 持仓量 │ 总筹码   │ 开仓价格 │
│  空仓价格 │ 涨跌幅 │ 开始时间 │ 结束时间 │ 结束原因                    │
├─────────────────────────────────────────────────────────────────┤
│  中国平安 │ 000001 │ ORD002 │ 多  │ 200   │ ¥24000  │ ¥120.00  │
│  ¥125.00 │ +4.17% │ 2024-01-02 │ 2024-01-03 │ 止盈                    │
└─────────────────────────────────────────────────────────────────┘
```

### Components

**Top Metrics Bar**
- 收益率曲线 (mini chart)
- 当日盈亏 (with color: green/red)
- 总资产
- 持仓市值
- 总收益率

**Open Positions Table (当前持仓)**
| Field | Description |
|-------|-------------|
| 名称 | Stock name (e.g., 贵州茅台) |
| 代码 | Stock code (e.g., 600519) |
| 订单ID | Order ID |
| 方向 | 多/空 (buy/sell) |
| 持仓量 | Position size |
| 总筹码 | Total position value |
| 开仓价格 | Entry price |
| 最新价 | Current market price |
| 涨跌幅 | P&L percentage |
| 开始时间 | Position open time |

**Closed Trades Table (历史成交)**
| Field | Description |
|-------|-------------|
| 名称 | Stock name |
| 代码 | Stock code |
| 订单ID | Order ID |
| 方向 | 多/空 |
| 持仓量 | Position size |
| 总筹码 | Total position value |
| 开仓价格 | Entry price |
| 空仓价格 | Exit price |
| 涨跌幅 | P&L percentage |
| 开始时间 | Trade start time |
| 结束时间 | Trade close time |
| 结束原因 | Close reason (止盈/止损/手动) |

---

## Tab 2: Trade (交易)

### Layout
```
┌──────────────┬──────────────────────────────┬──────────────────┐
│  📋 股票列表  │      📊 K线图                │  💰 交易面板     │
│  ──────────  │   （技术分析 + 指标）          │  ─────────────  │
│  名称 代码 涨 │                              │  当前股票:       │
│  跌幅        │                              │  600519 贵州茅台 │
│              │                              │                  │
│  贵州茅台    │                              │  最新价: 1850.00 │
│  600519 +2.7%│                              │  涨跌幅: +2.78%  │
│              │                              │                  │
│  中国平安    │                              │  ─────────────  │
│  000001 +1.2%│                              │  操作:           │
│              │                              │  [买入] [卖出]   │
│              │                              │  价格: [____]    │
│              │                              │  数量: [____]    │
│              │                              │  [   下单   ]    │
└──────────────┴──────────────────────────────┴──────────────────┘
```

### Components

**Left Panel: Stock List (股票列表)**
- Columns: 名称, 代码, 涨跌幅
- Click to select stock and update chart
- Filter/search capability

**Center Panel: K-line Chart (K线图)**
- ECharts candlestick chart
- Technical indicators (MA, MACD, RSI, etc.)
- Time period selector

**Right Panel: Trading Panel (交易面板)**
- Current stock display (名称, 最新价, 涨跌幅)
- Buy/Sell toggle buttons
- Price input
- Volume input
- Submit order button

---

## Tab 3: Logs (日志)

### Layout
```
┌─────────────────────────────────────────────────────────────────┐
│  [级别▼]  [来源▼]  [关键词搜索...]  [刷新] [清空]              │
├─────────────────────────────────────────────────────────────────┤
│  [2024-01-01 10:00:00] [INFO] [system] Trading engine started   │
│  [2024-01-01 10:05:23] [INFO] [trade] Order executed: 600519    │
│  [2024-01-01 10:10:15] [WARN] [strategy] Signal timeout         │
│  [2024-01-01 10:15:00] [ERROR] [system] Connection failed       │
└─────────────────────────────────────────────────────────────────┘
```

### Components

**Filter Bar**
- 级别 (Level): 全部/信息/警告/错误
- 来源 (Source): 全部/系统/交易/策略
- 关键词搜索
- 刷新按钮
- 清空按钮

**Log List**
- Auto-scroll to newest
- Color-coded by level:
  - INFO: blue
  - WARNING: yellow
  - ERROR: red
- Columns: Time, Level, Source, Message

---

## Technical Requirements

### Data APIs Needed
1. `GET /account` - Account summary data
2. `GET /positions` - Open positions list
3. `GET /trades` - Closed trades history
4. `GET /kline/{symbol}` - K-line chart data
5. `POST /order` - Submit order
6. `GET /logs` - System and trading logs
7. `GET /stocks` - Available stock list

### State Management
- `activeTab`: Current active tab ('dashboard', 'trade', 'logs')
- `selectedSymbol`: Currently selected stock for chart
- `tradeForm`: Order form data
- `logFilter`: Log filter criteria

### Responsive Behavior
- Dashboard: Tables scroll horizontally on narrow screens
- Trade: Left panel collapses on mobile, chart takes full width
- Logs: Full width with horizontal scroll for long messages

---

## Approval

Design approved by user on 2026-04-26.
