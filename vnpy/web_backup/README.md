# VNPY Web 交易看板

类似 freqUI 的网页交易界面，实时监控交易数据和策略状态。

## 功能特性

- **实时数据监控**
  - 账户概览（总资产、可用资金、当日盈亏）
  - 持仓明细（代码、方向、成本、现价、盈亏）
  - 成交记录实时监控
  - 资金曲线图表

- **策略控制**
  - 策略启停按钮
  - 参数实时调整
  - 运行状态显示

- **交易信号**
  - 当日买入/卖出信号
  - 信号强度显示
  - 执行状态追踪

## 快速开始

### 1. 安装依赖

```bash
pip install fastapi uvicorn websockets
```

### 2. 启动 Web 看板

```bash
python web_dashboard.py
```

访问 http://localhost:8000

### 3. 与 MainEngine 集成

```python
from vnpy.web import WebEngine
from vnpy.trader.engine import MainEngine

main_engine = MainEngine(event_engine)
web_engine = main_engine.add_engine(WebEngine)
web_engine.start(host="0.0.0.0", port=8000)
```

## 目录结构

```
vnpy/web/
├── __init__.py          # 包初始化
├── engine.py            # WebEngine - 核心引擎
├── api/                 # API 路由
│   └── __init__.py      # 策略、交易、账户 API
├── templates/           # 数据模型
│   └── __init__.py      # Pydantic 模型
└── static/              # 前端静态资源
    ├── css/style.css    # 样式
    └── js/app.js        # Vue3 应用
```

## 技术栈

- **后端**: FastAPI + WebSocket
- **前端**: Vue3 + Element Plus + ECharts
- **通信**: WebSocket 实时推送

## API 接口

### 策略管理
- `GET /api/strategy/list` - 策略列表
- `POST /api/strategy/{name}/start` - 启动策略
- `POST /api/strategy/{name}/stop` - 停止策略

### 交易数据
- `GET /api/trading/positions` - 持仓列表
- `GET /api/trading/orders` - 订单列表
- `POST /api/trading/order` - 发送订单

### 账户信息
- `GET /api/account/summary` - 账户概览
- `GET /api/account/pnl` - 盈亏曲线

### WebSocket
- `ws://localhost:8000/ws` - 实时数据流

## 截图预览

界面布局：
- 顶部：账户概览卡片（总资产、可用、盈亏、持仓市值）
- 左侧：持仓明细 + 成交记录表格
- 右侧：策略控制 + 交易信号列表

## 注意事项

1. Web 看板需要与 VNPY MainEngine 一起运行
2. 确保事件引擎已启动
3. 生产环境建议使用反向代理（Nginx）

## 开发计划

- [ ] 添加 K 线图展示
- [ ] 支持多策略同时监控
- [ ] 添加历史回测可视化
- [ ] 支持移动端适配
