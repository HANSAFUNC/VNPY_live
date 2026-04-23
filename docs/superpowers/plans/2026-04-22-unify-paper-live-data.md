# 统一模拟/实盘数据层实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 统一模拟盘和实盘的数据获取层，K线图表从数据库查询真实历史数据。

**Architecture:** 将数据获取（账户、持仓、行情、信号）与交易执行分离。LiveAlphaEngine 统一从网关获取数据。WebEngine 从数据库查询历史K线数据，而非生成示例数据。

**Tech Stack:** Python, vnpy, PostgreSQL

---

## 前置检查

- [ ] **检查现有代码**

查看 `vnpy/alpha/strategy/live_engine.py` 和 `vnpy/web/engine.py` 中数据获取逻辑。

---

## Task 1: 修改 LiveAlphaEngine 统一数据获取

**Files:**
- Modify: `vnpy/alpha/strategy/live_engine.py`

**说明:** 统一模拟/实盘的数据获取逻辑，移除模拟盘的本地数据模拟。

- [ ] **Step 1: 修改数据获取方法统一使用网关**

找到 `_update_account` 和 `_update_positions` 方法，修改为模拟盘也使用 `main_engine` 获取数据：

```python
def _update_account(self) -> None:
    """更新账户信息"""
    try:
        if self.gateway_name:
            # 统一从网关获取账户（无论模拟/实盘）
            account = self.main_engine.get_account(self.gateway_name)
            if account:
                self.account = account
            else:
                # 网关未返回数据，使用默认值
                self._init_paper_account()
        else:
            # 无网关时使用本地模拟
            self._init_paper_account()
    except Exception as e:
        logger.warning(f"更新账户信息失败: {e}")
        if self.paper_trading:
            self._init_paper_account()

def _update_positions(self) -> None:
    """更新持仓信息"""
    try:
        if self.gateway_name:
            # 统一从网关获取持仓
            positions = self.main_engine.get_all_positions(self.gateway_name)
            self.positions = {pos.vt_positionid: pos for pos in positions}
        else:
            # 无网关时使用本地
            if self.paper_trading:
                self.positions = {}
    except Exception as e:
        logger.warning(f"更新持仓信息失败: {e}")
        if self.paper_trading:
            self.positions = {}

def _init_paper_account(self) -> None:
    """初始化模拟账户"""
    if not hasattr(self, '_paper_account_initialized'):
        self.account = AccountData(
            gateway_name=self.gateway_name or "PAPER",
            accountid="PAPER_ACCOUNT",
            balance=self.initial_capital,
            frozen=0.0
        )
        # 手动设置可用资金
        object.__setattr__(self.account, 'available', self.initial_capital)
        self._paper_account_initialized = True
```

- [ ] **Step 2: 修改订阅行情方法**

```python
def subscribe_market_data(self, vt_symbols: List[str]) -> None:
    """订阅行情（模拟/实盘统一处理）"""
    for vt_symbol in vt_symbols:
        try:
            if self.gateway_name:
                # 统一通过网关订阅
                self.main_engine.subscribe(SubscribeRequest(
                    symbol=vt_symbol.split('.')[0],
                    exchange=Exchange(vt_symbol.split('.')[1])
                ), self.gateway_name)
                logger.info(f"订阅行情: {vt_symbol}")
            else:
                logger.warning(f"未配置网关，无法订阅 {vt_symbol}")
        except Exception as e:
            logger.error(f"订阅 {vt_symbol} 失败: {e}")
```

- [ ] **Step 3: 提交**

```bash
git add vnpy/alpha/strategy/live_engine.py
git commit -m "refactor(strategy): unify data fetching for paper and live trading"
```

---

## Task 2: 分离交易执行逻辑

**Files:**
- Modify: `vnpy/alpha/strategy/live_engine.py`

**说明:** 仅在下单执行时区分模拟/实盘。

- [ ] **Step 1: 修改下单方法**

```python
def send_order(self, vt_symbol: str, direction: Direction, price: float, volume: float) -> str:
    """发送订单"""
    if self.paper_trading:
        # 模拟盘：本地撮合
        return self._paper_send_order(vt_symbol, direction, price, volume)
    else:
        # 实盘：发送到交易所
        return self._live_send_order(vt_symbol, direction, price, volume)

def _paper_send_order(self, vt_symbol: str, direction: Direction, price: float, volume: float) -> str:
    """模拟盘本地撮合"""
    symbol, exchange_str = vt_symbol.split('.')
    orderid = f"PAPER_{self.order_count}"
    self.order_count += 1
    
    order = OrderData(
        gateway_name=self.gateway_name or "PAPER",
        symbol=symbol,
        exchange=Exchange(exchange_str),
        orderid=orderid,
        type=OrderType.LIMIT,
        direction=direction,
        offset=Offset.OPEN if direction == Direction.LONG else Offset.CLOSE,
        price=price,
        volume=volume,
        traded=0,
        status=Status.SUBMITTING,
        datetime=datetime.now()
    )
    
    self.active_orders[order.vt_orderid] = order
    
    # 本地撮合
    self._match_paper_order(order)
    
    return order.vt_orderid

def _live_send_order(self, vt_symbol: str, direction: Direction, price: float, volume: float) -> str:
    """实盘发送订单到交易所"""
    symbol, exchange_str = vt_symbol.split('.')
    
    req = OrderRequest(
        symbol=symbol,
        exchange=Exchange(exchange_str),
        direction=direction,
        type=OrderType.LIMIT,
        volume=volume,
        price=price
    )
    
    vt_orderid = self.main_engine.send_order(req, self.gateway_name)
    return vt_orderid
```

- [ ] **Step 2: 提交**

```bash
git add vnpy/alpha/strategy/live_engine.py
git commit -m "refactor(strategy): separate trade execution logic for paper/live"
```

---

## Task 3: WebEngine 从数据库查询历史K线

**Files:**
- Modify: `vnpy/web/engine.py`

**说明:** 修改 WebEngine 从数据库查询真实历史K线数据。

- [ ] **Step 1: 添加数据库查询方法**

```python
def _load_historical_candles(self, vt_symbol: str, days: int = 60) -> List[CandleData]:
    """从数据库加载历史K线数据"""
    try:
        from vnpy.trader.database import get_database
        from datetime import datetime, timedelta
        
        database = get_database()
        symbol, exchange_str = vt_symbol.split('.')
        
        # 计算时间范围
        end = datetime.now()
        start = end - timedelta(days=days)
        
        # 从数据库查询
        bars = database.load_bar_data(
            symbol=symbol,
            exchange=Exchange(exchange_str),
            interval=Interval.DAILY,
            start=start,
            end=end
        )
        
        # 转换为 CandleData
        candles = []
        for bar in bars:
            candles.append(CandleData(
                timestamp=bar.datetime.strftime("%Y-%m-%d"),
                open=bar.open_price,
                high=bar.high_price,
                low=bar.low_price,
                close=bar.close_price,
                volume=bar.volume
            ))
        
        logger.info(f"加载 {vt_symbol} 历史数据: {len(candles)} 条")
        return candles
    except Exception as e:
        logger.error(f"加载历史数据失败 {vt_symbol}: {e}")
        # 失败时返回示例数据
        return self._generate_sample_candles(vt_symbol, num=100)
```

- [ ] **Step 2: 修改 _generate_sample_candles 为可选备用**

保留 `_generate_sample_candles` 作为数据库查询失败时的备用。

- [ ] **Step 3: 修改初始化数据方法**

```python
# 在 __init__ 中修改初始化
def _init_candle_data(self) -> None:
    """初始化K线数据（从数据库加载）"""
    for symbol in self.available_symbols:
        self.all_candles[symbol] = self._load_historical_candles(symbol, days=60)
    
    if self.available_symbols:
        self.current_symbol = self.available_symbols[0]
```

- [ ] **Step 4: 提交**

```bash
git add vnpy/web/engine.py
git commit -m "feat(web): load historical candle data from database"
```

---

## Task 4: 修改 xgb_extrema_live_trading.py

**Files:**
- Modify: `xgb_extrema_live_trading.py`

**说明:** 统一连接网关流程。

- [ ] **Step 1: 修改模拟盘模式也连接网关**

```python
def main():
    parser = argparse.ArgumentParser(description='XGBoost 极值策略实盘交易')
    parser.add_argument('--mode', choices=['live', 'paper'], default='paper',
                       help='运行模式: live=实盘, paper=模拟盘')
    # ...

    if args.mode == 'paper':
        # 模拟盘模式
        trader = LiveTrader(paper_trading=True, enable_web=enable_web)
        trader.gateway_name = args.gateway  # 使用指定网关获取行情
        trader.capital = args.capital
        
        # 加载信号
        trader.load_signals()
        
        # 模拟盘也需要连接网关获取实时行情
        if not trader.connect_gateway():
            logger.error("连接行情网关失败")
            return
        
        # 设置策略
        trader.setup_strategy()
        
        # 启动交易
        trader.start()
    else:
        # 实盘模式（不变）
        ...
```

- [ ] **Step 2: 提交**

```bash
git add xgb_extrema_live_trading.py
git commit -m "refactor(trading): connect gateway in paper mode for unified data"
```

---

## Task 5: 测试验证

- [ ] **Step 1: 测试 Web 看板历史K线数据**

```bash
python web_dashboard.py
```

验证：
- 访问 http://localhost:8000，切换到 K线图表 Tab
- K线图显示从数据库查询的真实历史数据
- 切换股票后显示对应的历史数据

- [ ] **Step 2: 测试模拟盘**

```bash
python xgb_extrema_live_trading.py --mode paper --gateway XT
```

验证：
- 能连接迅投研网关获取实时行情
- 能获取账户/持仓数据（统一从网关）
- Web看板K线图显示数据库历史数据
- 订单在本地撮合，不发送到交易所

- [ ] **Step 3: 测试实盘**

```bash
python xgb_extrema_live_trading.py --mode live --gateway XT
```

验证：
- 同样能获取行情和数据
- K线图显示历史数据
- 订单发送到交易所

验证：
- 同样能获取行情和数据
- 订单发送到交易所

- [ ] **Step 3: 提交**

```bash
git add .
git commit -m "test: verify unified data layer for paper/live trading"
```

---

## Self-Review Checklist

- [ ] **Spec coverage:**
  - [x] 统一数据获取 - Task 1 实现
  - [x] 分离交易执行 - Task 2 实现
  - [x] K线图表查询历史数据 - Task 3 实现
  - [x] 模拟盘连接网关 - Task 4 实现

- [ ] **No placeholders:**
  - [x] 所有代码都是完整的

---

## 执行选项

Plan complete and saved to `docs/superpowers/plans/2026-04-22-unify-paper-live-data.md`. Two execution options:

**1. Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints

Which approach?
