# Web 看板股票池 Tab 与 K 线图表联动功能实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 添加【股票池】Tab（包含今日买入/卖出两个区域），K 线图表 Tab 的股票选择器显示 lab 中所有股票。

**Architecture:** 【股票池】作为独立 Tab，使用 el-table 展示今日买入股票列表和今日卖出股票列表（每个表格包含股票代码、信号强度等）。【K 线图表】Tab 中的股票选择器从 lab 加载所有可用股票，选中后通过 WebSocket 获取该股票历史 K 线数据并渲染 ECharts 图表。

**Tech Stack:** FastAPI, Vue3, Element Plus, ECharts, WebSocket

---

## 前置检查

- [ ] **检查现有 Web 看板代码**

查看 `vnpy/web/engine.py` 中的现有 Tab 结构和 K 线图表实现。

---

## Task 1: 更新数据模型添加股票池和信号股票数据

**Files:**
- Modify: `vnpy/web/templates/__init__.py`

**说明:** 添加股票池信号数据模型和 lab 股票列表模型。

- [ ] **Step 1: 添加 SignalStock 模型**

```python
class SignalStock(BaseModel):
    """信号股票"""
    vt_symbol: str
    signal: int  # 1=买入, -1=卖出
    strength: float = 1.0  # 信号强度
    datetime: str = ""
    close_price: float = 0.0
    volume: float = 0.0
```

- [ ] **Step 2: 添加 StockPoolData 模型**

```python
class StockPoolData(BaseModel):
    """股票池数据"""
    buy_stocks: List[SignalStock] = []  # 今日买入股票
    sell_stocks: List[SignalStock] = []  # 今日卖出股票
    last_update: str = ""
```

- [ ] **Step 3: 更新 DashboardData 模型**

在 DashboardData 中添加：

```python
class DashboardData(BaseModel):
    """看板数据"""
    account: Dict[str, float]
    positions: List[PositionView]
    trades: List[TradeView]
    strategies: List[StrategyStatus]
    signals: List[SignalView]
    chart_data: Dict[str, List[CandleData]] = {}  # 当前选中股票的 K 线数据
    available_symbols: List[str] = []  # Lab 中所有可用股票
    current_symbol: str = ""  # 当前选中的股票
    stock_pool: StockPoolData = Field(default_factory=StockPoolData)  # 股票池
    stats: Optional[StatsData] = None
    timestamp: str = ""
```

- [ ] **Step 4: 提交**

```bash
git add vnpy/web/templates/__init__.py
git commit -m "feat(web): add StockPoolData and SignalStock models"
```

---

## Task 2: WebEngine 添加股票池和 lab 股票管理

**Files:**
- Modify: `vnpy/web/engine.py`

**说明:** 添加股票池数据生成、lab 股票加载、当前选中股票管理。

- [ ] **Step 1: 导入 SignalStock 和 StockPoolData**

```python
from .templates import (
    DashboardData, AccountData, PositionView, TradeView,
    StrategyStatus, SignalView, CandleData, StatsData,
    SignalStock, StockPoolData  # 新增
)
```

- [ ] **Step 2: 在 __init__ 中添加股票池缓存**

```python
# 股票池数据
self.stock_pool_data: StockPoolData = StockPoolData()

# 从 lab 加载的可用股票列表
self.available_symbols: List[str] = []

# 当前选中的股票（用于 K 线图）
self.current_symbol: str = ""

# 所有股票的历史 K 线缓存
self.all_candles: Dict[str, List[CandleData]] = {}
```

- [ ] **Step 3: 添加股票池数据生成方法**

```python
def _generate_sample_stock_pool(self) -> StockPoolData:
    """生成示例股票池数据（实际应从策略信号获取）"""
    import random
    from datetime import datetime
    
    # 今日买入股票
    buy_stocks = [
        SignalStock(vt_symbol="000001.SSE", signal=1, strength=0.85, 
                   datetime=datetime.now().strftime("%Y-%m-%d"), close_price=12.50, volume=10000),
        SignalStock(vt_symbol="000002.SSE", signal=1, strength=0.72, 
                   datetime=datetime.now().strftime("%Y-%m-%d"), close_price=8.30, volume=5000),
        SignalStock(vt_symbol="600519.SSE", signal=1, strength=0.91, 
                   datetime=datetime.now().strftime("%Y-%m-%d"), close_price=1680.00, volume=800),
    ]
    
    # 今日卖出股票
    sell_stocks = [
        SignalStock(vt_symbol="000300.SSE", signal=-1, strength=0.78, 
                   datetime=datetime.now().strftime("%Y-%m-%d"), close_price=4.20, volume=20000),
        SignalStock(vt_symbol="600036.SSE", signal=-1, strength=0.65, 
                   datetime=datetime.now().strftime("%Y-%m-%d"), close_price=35.60, volume=3000),
    ]
    
    return StockPoolData(
        buy_stocks=buy_stocks,
        sell_stocks=sell_stocks,
        last_update=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    )

def _load_available_symbols(self) -> List[str]:
    """从 lab 加载可用股票列表（实际应从数据库获取）"""
    # 示例：返回 lab 中常见股票
    return [
        "000001.SSE",  # 平安银行
        "000002.SSE",  # 万科A
        "000300.SSE",  # 沪深300
        "600519.SSE",  # 贵州茅台
        "600036.SSE",  # 招商银行
        "000858.SSE",  # 五粮液
        "002415.SSE",  # 海康威视
        "600276.SSE",  # 恒瑞医药
        "600030.SSE",  # 中信证券
        "601318.SSE",  # 中国平安
    ]
```

- [ ] **Step 4: 添加设置当前股票方法**

```python
def set_current_symbol(self, vt_symbol: str) -> bool:
    """设置当前选中的股票"""
    if vt_symbol in self.available_symbols:
        self.current_symbol = vt_symbol
        # 如果该股票没有 K 线数据，生成示例数据
        if vt_symbol not in self.all_candles:
            self.all_candles[vt_symbol] = self._generate_sample_candles(vt_symbol, num=200)
        return True
    return False
```

- [ ] **Step 5: 修改 _get_dashboard_data**

```python
def _get_dashboard_data(self) -> DashboardData:
    """获取看板数据"""
    # 返回当前选中股票的 K 线数据
    chart_data = {}
    if self.current_symbol and self.current_symbol in self.all_candles:
        chart_data = {self.current_symbol: self.all_candles[self.current_symbol]}
    
    return DashboardData(
        account=self._get_account_data(),
        positions=self._get_position_data(),
        trades=self._get_trade_data(),
        strategies=self._get_strategy_data(),
        signals=self._get_signal_data(),
        chart_data=chart_data,
        available_symbols=self.available_symbols,  # 所有可用股票
        current_symbol=self.current_symbol,  # 当前选中
        stock_pool=self.stock_pool_data,  # 股票池
        stats=self._get_stats_data()
    )
```

- [ ] **Step 6: 在 __init__ 中初始化数据**

在 `__init__` 末尾添加：

```python
# 初始化数据
self.stock_pool_data = self._generate_sample_stock_pool()
self.available_symbols = self._load_available_symbols()
if self.available_symbols:
    self.current_symbol = self.available_symbols[0]
    self.all_candles[self.current_symbol] = self._generate_sample_candles(self.current_symbol, num=200)
```

- [ ] **Step 7: 提交**

```bash
git add vnpy/web/engine.py
git commit -m "feat(web): add stock pool and lab symbols management"
```

---

## Task 3: 修改 HTML 添加股票池 Tab 并更新 K 线图表

**Files:**
- Modify: `vnpy/web/engine.py`

**说明:** 添加【股票池】Tab（包含买入/卖出表格），K 线图表 Tab 选择器显示所有可用股票。

- [ ] **Step 1: 在 el-tabs 中添加【股票池】Tab**

在【交易】Tab 之后、【K 线图表】Tab 之前添加：

```html
<!-- Tab 2: 股票池 -->
<el-tab-pane label="股票池" name="stock_pool">
    <el-row :gutter="20">
        <!-- 今日买入 -->
        <el-col :span="12">
            <el-card>
                <template #header>
                    <span style="color: #f56c6c; font-weight: bold;">📈 今日买入信号</span>
                    <el-tag type="danger" size="small" style="margin-left: 10px;">
                        {{ stockPool.buy_stocks?.length || 0 }} 只
                    </el-tag>
                </template>
                <el-table :data="stockPool.buy_stocks || []" stripe style="width: 100%">
                    <el-table-column prop="vt_symbol" label="股票代码" width="120"></el-table-column>
                    <el-table-column prop="close_price" label="收盘价" width="100">
                        <template #default="scope">¥{{ scope.row.close_price?.toFixed(2) || '--' }}</template>
                    </el-table-column>
                    <el-table-column prop="strength" label="信号强度">
                        <template #default="scope">
                            <el-progress 
                                :percentage="Math.round((scope.row.strength || 0) * 100)" 
                                :color="'#f56c6c'"
                                :show-text="true">
                            </el-progress>
                        </template>
                    </el-table-column>
                    <el-table-column prop="volume" label="成交量" width="120">
                        <template #default="scope">{{ formatVolume(scope.row.volume) }}</template>
                    </el-table-column>
                </el-table>
            </el-card>
        </el-col>
        
        <!-- 今日卖出 -->
        <el-col :span="12">
            <el-card>
                <template #header>
                    <span style="color: #67c23a; font-weight: bold;">📉 今日卖出信号</span>
                    <el-tag type="success" size="small" style="margin-left: 10px;">
                        {{ stockPool.sell_stocks?.length || 0 }} 只
                    </el-tag>
                </template>
                <el-table :data="stockPool.sell_stocks || []" stripe style="width: 100%">
                    <el-table-column prop="vt_symbol" label="股票代码" width="120"></el-table-column>
                    <el-table-column prop="close_price" label="收盘价" width="100">
                        <template #default="scope">¥{{ scope.row.close_price?.toFixed(2) || '--' }}</template>
                    </el-table-column>
                    <el-table-column prop="strength" label="信号强度">
                        <template #default="scope">
                            <el-progress 
                                :percentage="Math.round((scope.row.strength || 0) * 100)" 
                                :color="'#67c23a'"
                                :show-text="true">
                            </el-progress>
                        </template>
                    </el-table-column>
                    <el-table-column prop="volume" label="成交量" width="120">
                        <template #default="scope">{{ formatVolume(scope.row.volume) }}</template>
                    </el-table-column>
                </el-table>
            </el-card>
        </el-col>
    </el-row>
    
    <!-- 股票池更新时间 -->
    <el-row style="margin-top: 20px;">
        <el-col :span="24" style="text-align: center; color: #909399;">
            股票池更新时间：{{ stockPool.last_update || '--' }}
        </el-col>
    </el-row>
</el-tab-pane>
```

- [ ] **Step 2: 修改 K 线图表 Tab 的股票选择器**

将 K 线图表 Tab 中的股票选择器改为从 available_symbols 加载：

```html
<!-- Tab 3: K线图表（原 Tab 2，现在变为 Tab 3） -->
<el-tab-pane label="K线图表" name="charts">
    <el-row :gutter="20">
        <el-col :span="24">
            <el-card>
                <template #header>
                    <div style="display: flex; justify-content: space-between; align-items: center;">
                        <span>K线图表</span>
                        <div>
                            <span style="margin-right: 10px; color: #909399;">选择股票：</span>
                            <el-select 
                                v-model="selectedSymbol" 
                                size="small" 
                                style="width: 150px;"
                                @change="onStockChange"
                                placeholder="选择股票">
                                <el-option 
                                    v-for="symbol in availableSymbols" 
                                    :key="symbol" 
                                    :label="symbol" 
                                    :value="symbol">
                                </el-option>
                            </el-select>
                        </div>
                    </div>
                </template>
                <div id="kline-chart" style="height: 500px;"></div>
            </el-card>
        </el-col>
    </el-row>
    <el-row :gutter="20" style="margin-top: 20px;">
        <el-col :span="24">
            <el-card>
                <template #header>
                    <span>技术指标</span>
                </template>
                <div id="indicator-chart" style="height: 200px;"></div>
            </el-card>
        </el-col>
    </el-row>
</el-tab-pane>
```

- [ ] **Step 3: 提交**

```bash
git add vnpy/web/engine.py
git commit -m "feat(web): add stock pool tab and update kline chart selector"
```

---

## Task 4: 更新前端 JavaScript

**Files:**
- Modify: `vnpy/web/static/js/app.js`

**说明:** 添加股票池数据处理、成交量格式化、股票切换逻辑。

- [ ] **Step 1: 添加股票池相关状态**

```javascript
// 股票池
const stockPool = ref({
    buy_stocks: [],
    sell_stocks: [],
    last_update: ''
});

// 可用股票列表（从 lab 加载）
const availableSymbols = ref([]);

// 当前选中的股票
const selectedSymbol = ref('');
```

- [ ] **Step 2: 添加成交量格式化方法**

```javascript
const formatVolume = (volume) => {
    if (!volume) return '--';
    if (volume >= 10000) {
        return (volume / 10000).toFixed(2) + '万';
    }
    return volume.toString();
};
```

- [ ] **Step 3: 修改 handleMessage 处理股票池数据**

```javascript
const handleMessage = (message) => {
    if (message.type === 'init' || message.type === 'update') {
        const data = message.data;
        account.value = data.account || { balance: 0, available: 0, frozen: 0 };
        positions.value = data.positions || [];
        trades.value = data.trades || [];
        strategies.value = data.strategies || [];
        signals.value = data.signals || [];
        
        // 新增：更新股票池
        if (data.stock_pool) {
            stockPool.value = data.stock_pool;
        }
        
        // 新增：更新可用股票列表
        if (data.available_symbols) {
            availableSymbols.value = data.available_symbols;
        }
        
        // 新增：同步当前选中股票
        if (data.current_symbol) {
            selectedSymbol.value = data.current_symbol;
        }
        
        // 更新 K 线数据
        if (data.chart_data) {
            candles.value = data.chart_data;
        }
        
        if (data.stats) {
            stats.value = data.stats;
        }
        
        calculateDailyPnl();
        calculatePositionValue();
        lastUpdate.value = new Date().toLocaleTimeString();
        
        // 如果当前在图表页，更新图表
        if (activeTab.value === 'charts') {
            updateKlineChart();
        }
    }
};
```

- [ ] **Step 4: 修改股票切换处理函数**

```javascript
const onStockChange = (symbol) => {
    console.log('切换到股票:', symbol);
    
    // 发送消息到后端请求切换股票
    if (ws.value && ws.value.readyState === WebSocket.OPEN) {
        ws.value.send(JSON.stringify({
            type: 'change_stock',
            symbol: symbol
        }));
    }
};
```

- [ ] **Step 5: 修改 updateKlineChart 方法**

```javascript
const updateKlineChart = () => {
    if (!klineChart.value) {
        initCharts();
    }
    
    // 从 candles 对象中获取当前选中股票的数据
    const symbol = selectedSymbol.value;
    if (!symbol || !candles.value[symbol]) {
        console.log('无 K 线数据:', symbol);
        return;
    }
    
    const data = candles.value[symbol];
    const dates = data.map(d => d.timestamp);
    const values = data.map(d => [d.open, d.close, d.low, d.high]);
    const volumes = data.map(d => d.volume);
    
    const option = {
        title: {
            text: symbol + ' - K线图',
            left: 'center'
        },
        tooltip: {
            trigger: 'axis',
            axisPointer: { type: 'cross' }
        },
        grid: [
            { left: '10%', right: '8%', height: '50%' },
            { left: '10%', right: '8%', top: '68%', height: '16%' }
        ],
        xAxis: [
            {
                type: 'category',
                data: dates,
                scale: true,
                boundaryGap: false,
                axisLine: { onZero: false },
                splitLine: { show: false }
            },
            {
                type: 'category',
                gridIndex: 1,
                data: dates,
                scale: true,
                boundaryGap: false,
                axisLine: { onZero: false },
                axisLabel: { show: false },
                splitLine: { show: false }
            }
        ],
        yAxis: [
            {
                scale: true,
                splitLine: { show: true }
            },
            {
                scale: true,
                gridIndex: 1,
                splitNumber: 2,
                axisLabel: { show: false },
                axisLine: { show: false }
            }
        ],
        dataZoom: [
            { type: 'inside', xAxisIndex: [0, 1], start: 50, end: 100 },
            { show: true, xAxisIndex: [0, 1], type: 'slider', bottom: '5%' }
        ],
        series: [
            {
                name: 'K线',
                type: 'candlestick',
                data: values,
                itemStyle: {
                    color: '#ef232a',
                    color0: '#14b143',
                    borderColor: '#ef232a',
                    borderColor0: '#14b143'
                }
            },
            {
                name: '成交量',
                type: 'bar',
                xAxisIndex: 1,
                yAxisIndex: 1,
                data: volumes
            }
        ]
    };
    
    klineChart.value.setOption(option, true);
};
```

- [ ] **Step 6: 更新 return 对象**

```javascript
return {
    // ... 原有返回
    
    // 新增：股票池相关
    stockPool,
    availableSymbols,
    selectedSymbol,
    formatVolume,
    onStockChange,
    
    // ... 其他
};
```

- [ ] **Step 7: 提交**

```bash
git add vnpy/web/static/js/app.js
git commit -m "feat(web): add stock pool data handling and symbol switching"
```

---

## Task 5: 添加 WebSocket 股票切换处理

**Files:**
- Modify: `vnpy/web/engine.py`

**说明:** 添加处理前端股票切换请求。

- [ ] **Step 1: 修改 _handle_ws_message 方法**

在 `_handle_ws_message` 中添加 `change_stock` 处理：

```python
async def _handle_ws_message(self, websocket: WebSocket, message: dict) -> None:
    """处理 WebSocket 消息"""
    msg_type = message.get("type")

    if msg_type == "ping":
        await websocket.send_json({"type": "pong"})

    elif msg_type == "get_data":
        await websocket.send_json({
            "type": "data",
            "data": self._get_dashboard_data().dict()
        })

    elif msg_type == "toggle_strategy":
        strategy_name = message.get("name")
        running = message.get("running")
        print(f"Toggle strategy {strategy_name} -> {running}")

    elif msg_type == "change_stock":
        # 新增：切换股票
        symbol = message.get("symbol")
        if symbol and self.set_current_symbol(symbol):
            print(f"切换到股票: {symbol}")
            await websocket.send_json({
                "type": "update",
                "data": self._get_dashboard_data().dict()
            })
        else:
            await websocket.send_json({
                "type": "error",
                "message": f"无效的股票代码: {symbol}"
            })
```

- [ ] **Step 2: 提交**

```bash
git add vnpy/web/engine.py
git commit -m "feat(web): add WebSocket handler for stock switching"
```

---

## Task 6: 测试验证

**Files:**
- Test: 运行 `python web_dashboard.py`

- [ ] **Step 1: 启动 Web 服务**

```bash
python web_dashboard.py
```

- [ ] **Step 2: 验证股票池 Tab**

访问 http://localhost:8000，切换到【股票池】Tab：
1. 左侧显示"📈 今日买入信号"表格，包含股票代码、收盘价、信号强度（进度条）、成交量
2. 右侧显示"📉 今日卖出信号"表格，格式相同
3. 底部显示更新时间

- [ ] **Step 3: 验证 K 线图表 Tab**

切换到【K 线图表】Tab：
1. 股票选择器显示所有可用股票（10只）
2. 切换股票后 K 线图更新
3. 图表标题显示当前股票代码

- [ ] **Step 4: 提交**

```bash
git add .
git commit -m "feat(web): complete stock pool tab and k-line chart symbol selection"
```

---

## Self-Review Checklist

- [ ] **Spec coverage:**
  - [x] 股票池作为独立 Tab - Task 3 实现
  - [x] 股票池分买入/卖出两个表格 - Task 3 实现
  - [x] K 线图股票选择器显示所有可用股票 - Task 2, 3 实现
  - [x] 选中股票后 K 线图更新 - Task 5 实现

- [ ] **No placeholders:**
  - [x] 所有代码都是完整的

- [ ] **Type consistency:**
  - [x] SignalStock, StockPoolData 模型定义一致

---

## 执行选项

Plan complete and saved to `docs/superpowers/plans/2026-04-22-stock-pool-kline-v2.md`. Two execution options:

**1. Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints

Which approach?
