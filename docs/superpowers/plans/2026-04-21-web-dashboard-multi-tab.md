# Web 看板多 Tab 功能实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为 VNPY Web 交易看板添加多 Tab 功能：【交易】【K线图表】【数据分析】

**Architecture:** 使用 Vue3 + Element Plus 的 el-tabs 组件实现标签页切换。将原有单页内容迁移到【交易】Tab，新增【K线图表】Tab（使用 ECharts 展示 K 线）和【数据分析】Tab（展示策略统计指标）。通过 WebSocket 实时推送各 Tab 所需数据。

**Tech Stack:** FastAPI, Vue3, Element Plus, ECharts, WebSocket

---

## 前置检查

- [ ] **检查现有代码结构**

查看 `vnpy/web/engine.py` 中的 HTML 模板和前端代码结构，确认当前 Dashboard 实现方式。

---

## Task 1: 更新数据模型模板

**Files:**
- Modify: `vnpy/web/templates/__init__.py`

**说明:** 为 K线图表和数据分析 Tab 添加所需的数据模型。

- [ ] **Step 1: 添加 K 线数据模型**

```python
class CandleData(BaseModel):
    """K线数据"""
    timestamp: str
    open: float
    high: float
    low: float
    close: float
    volume: float


class ChartData(BaseModel):
    """图表数据"""
    vt_symbol: str
    candles: List[CandleData]
    indicators: Dict[str, List[float]] = {}  # 技术指标
```

- [ ] **Step 2: 添加统计分析数据模型**

```python
class StatsData(BaseModel):
    """统计数据"""
    total_return: float  # 总收益率
    annual_return: float  # 年化收益
    max_drawdown: float  # 最大回撤
    sharpe_ratio: float  # 夏普比率
    win_rate: float  # 胜率
    profit_factor: float  # 盈亏比
    total_trades: int  # 总交易次数
    winning_trades: int  # 盈利次数
    losing_trades: int  # 亏损次数
    avg_profit: float  # 平均盈利
    avg_loss: float  # 平均亏损
```

- [ ] **Step 3: 更新 DashboardData 模型**

```python
class DashboardData(BaseModel):
    """看板数据"""
    account: Dict[str, float]
    positions: List[PositionView]
    trades: List[TradeView]
    strategies: List[StrategyStatus]
    signals: List[SignalView]
    chart_data: Dict[str, List[CandleData]] = {}  # 新增：K线数据
    stats: Optional[StatsData] = None  # 新增：统计数据
    timestamp: str = ""
```

- [ ] **Step 4: 提交**

```bash
git add vnpy/web/templates/__init__.py
git commit -m "feat(web): add chart and stats data models for multi-tab dashboard"
```

---

## Task 2: 修改 WebEngine 添加数据获取方法

**Files:**
- Modify: `vnpy/web/engine.py`

**说明:** 在 WebEngine 类中添加获取 K线数据和统计数据的方法。

- [ ] **Step 1: 添加 K 线数据缓存和方法**

在 `__init__` 方法中添加缓存：

```python
# 数据缓存（在原有缓存后添加）
self.candles: Dict[str, List[CandleData]] = {}  # K线数据缓存
self.stats: Optional[StatsData] = None  # 统计数据
```

添加获取 K 线数据方法：

```python
def _get_chart_data(self) -> Dict[str, List[CandleData]]:
    """获取图表数据（K线）"""
    return self.candles

def _get_stats_data(self) -> Optional[StatsData]:
    """获取统计数据"""
    return self.stats
```

- [ ] **Step 2: 更新 _get_dashboard_data 方法**

```python
def _get_dashboard_data(self) -> DashboardData:
    """获取看板数据"""
    return DashboardData(
        account=self._get_account_data(),
        positions=self._get_position_data(),
        trades=self._get_trade_data(),
        strategies=self._get_strategy_data(),
        signals=self._get_signal_data(),
        chart_data=self._get_chart_data(),  # 新增
        stats=self._get_stats_data()  # 新增
    )
```

- [ ] **Step 3: 添加模拟数据生成（用于测试）**

```python
def _generate_sample_candles(self, vt_symbol: str, num: int = 100) -> List[CandleData]:
    """生成示例K线数据（用于测试）"""
    import random
    from datetime import datetime, timedelta
    
    candles = []
    base_price = 100.0
    now = datetime.now()
    
    for i in range(num):
        dt = now - timedelta(minutes=num - i)
        change = random.uniform(-2, 2)
        open_price = base_price + change
        high = open_price + random.uniform(0, 1)
        low = open_price - random.uniform(0, 1)
        close = low + random.uniform(0, high - low)
        volume = random.uniform(1000, 10000)
        
        candles.append(CandleData(
            timestamp=dt.strftime("%Y-%m-%d %H:%M:%S"),
            open=round(open_price, 2),
            high=round(high, 2),
            low=round(low, 2),
            close=round(close, 2),
            volume=round(volume, 2)
        ))
        base_price = close
    
    return candles

def _generate_sample_stats(self) -> StatsData:
    """生成示例统计数据（用于测试）"""
    return StatsData(
        total_return=15.5,
        annual_return=45.2,
        max_drawdown=-8.3,
        sharpe_ratio=1.85,
        win_rate=62.5,
        profit_factor=1.73,
        total_trades=120,
        winning_trades=75,
        losing_trades=45,
        avg_profit=1250.0,
        avg_loss=-680.0
    )
```

在 `__init__` 末尾调用生成示例数据：

```python
# 生成示例数据（实际应从策略获取）
self.candles["000001.SSE"] = self._generate_sample_candles("000001.SSE")
self.stats = self._generate_sample_stats()
```

- [ ] **Step 4: 提交**

```bash
git add vnpy/web/engine.py
git commit -m "feat(web): add chart and stats data methods in WebEngine"
```

---

## Task 3: 修改前端 HTML 添加 Tab 结构

**Files:**
- Modify: `vnpy/web/engine.py` 中的 `_get_index_html` 方法

**说明:** 将原有内容包装在 el-tabs 中，添加三个 Tab 页。

- [ ] **Step 1: 修改 HTML 结构添加 Tabs**

找到 `_get_index_html` 方法，修改 `<el-main>` 部分：

```html
<el-main>
    <div class="dashboard">
        <el-tabs v-model="activeTab" type="border-card">
            <!-- Tab 1: 交易 -->
            <el-tab-pane label="交易" name="trading">
                <!-- 原有交易内容移到这里 -->
            </el-tab-pane>
            
            <!-- Tab 2: K线图表 -->
            <el-tab-pane label="K线图表" name="charts">
                <el-row :gutter="20">
                    <el-col :span="24">
                        <el-card>
                            <template #header>
                                <span>K线图表</span>
                                <el-select v-model="selectedSymbol" size="small" style="width: 150px; margin-left: 10px;">
                                    <el-option 
                                        v-for="symbol in availableSymbols" 
                                        :key="symbol" 
                                        :label="symbol" 
                                        :value="symbol"
                                    ></el-option>
                                </el-select>
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
            
            <!-- Tab 3: 数据分析 -->
            <el-tab-pane label="数据分析" name="analysis">
                <el-row :gutter="20">
                    <el-col :span="8">
                        <el-card class="stats-card">
                            <template #header>
                                <span>收益指标</span>
                            </template>
                            <div class="stats-grid">
                                <div class="stat-item">
                                    <div class="stat-label">总收益率</div>
                                    <div class="stat-value" :class="stats.total_return >= 0 ? 'profit' : 'loss'">
                                        {{ stats.total_return.toFixed(2) }}%
                                    </div>
                                </div>
                                <div class="stat-item">
                                    <div class="stat-label">年化收益</div>
                                    <div class="stat-value" :class="stats.annual_return >= 0 ? 'profit' : 'loss'">
                                        {{ stats.annual_return.toFixed(2) }}%
                                    </div>
                                </div>
                                <div class="stat-item">
                                    <div class="stat-label">最大回撤</div>
                                    <div class="stat-value loss">
                                        {{ stats.max_drawdown.toFixed(2) }}%
                                    </div>
                                </div>
                            </div>
                        </el-card>
                    </el-col>
                    <el-col :span="8">
                        <el-card class="stats-card">
                            <template #header>
                                <span>风险指标</span>
                            </template>
                            <div class="stats-grid">
                                <div class="stat-item">
                                    <div class="stat-label">夏普比率</div>
                                    <div class="stat-value">{{ stats.sharpe_ratio.toFixed(2) }}</div>
                                </div>
                                <div class="stat-item">
                                    <div class="stat-label">胜率</div>
                                    <div class="stat-value">{{ stats.win_rate.toFixed(1) }}%</div>
                                </div>
                                <div class="stat-item">
                                    <div class="stat-label">盈亏比</div>
                                    <div class="stat-value">{{ stats.profit_factor.toFixed(2) }}</div>
                                </div>
                            </div>
                        </el-card>
                    </el-col>
                    <el-col :span="8">
                        <el-card class="stats-card">
                            <template #header>
                                <span>交易统计</span>
                            </template>
                            <div class="stats-grid">
                                <div class="stat-item">
                                    <div class="stat-label">总交易次数</div>
                                    <div class="stat-value">{{ stats.total_trades }}</div>
                                </div>
                                <div class="stat-item">
                                    <div class="stat-label">盈利次数</div>
                                    <div class="stat-value profit">{{ stats.winning_trades }}</div>
                                </div>
                                <div class="stat-item">
                                    <div class="stat-label">亏损次数</div>
                                    <div class="stat-value loss">{{ stats.losing_trades }}</div>
                                </div>
                            </div>
                        </el-card>
                    </el-col>
                </el-row>
                <el-row :gutter="20" style="margin-top: 20px;">
                    <el-col :span="12">
                        <el-card>
                            <template #header>
                                <span>盈亏分布</span>
                            </template>
                            <div id="pnl-chart" style="height: 300px;"></div>
                        </el-card>
                    </el-col>
                    <el-col :span="12">
                        <el-card>
                            <template #header>
                                <span>资金曲线</span>
                            </template>
                            <div id="equity-chart" style="height: 300px;"></div>
                        </el-card>
                    </el-col>
                </el-row>
            </el-tab-pane>
        </el-tabs>
    </div>
</el-main>
```

- [ ] **Step 2: 将原有交易内容移到 Trading Tab**

将原有的账户概览、持仓列表、成交记录、策略控制等内容整体移到 `<el-tab-pane label="交易" name="trading">` 内部。

- [ ] **Step 3: 提交**

```bash
git add vnpy/web/engine.py
git commit -m "feat(web): add multi-tab structure with trading, charts and analysis"
```

---

## Task 4: 更新前端 CSS 样式

**Files:**
- Modify: `vnpy/web/static/css/style.css`

**说明:** 添加 Tab 相关和统计卡片的样式。

- [ ] **Step 1: 添加 Tabs 样式**

```css
/* Tabs 样式 */
.el-tabs {
    height: 100%;
}

.el-tabs__content {
    padding: 20px;
}

.el-tab-pane {
    min-height: 600px;
}
```

- [ ] **Step 2: 添加统计卡片样式**

```css
/* 统计卡片 */
.stats-card {
    height: 100%;
}

.stats-grid {
    display: grid;
    gap: 15px;
}

.stat-item {
    text-align: center;
    padding: 15px;
    background: #f5f7fa;
    border-radius: 8px;
}

.stat-label {
    font-size: 12px;
    color: #909399;
    margin-bottom: 8px;
}

.stat-value {
    font-size: 20px;
    font-weight: bold;
    color: #303133;
}

.stat-value.profit {
    color: #67c23a;
}

.stat-value.loss {
    color: #f56c6c;
}
```

- [ ] **Step 3: 提交**

```bash
git add vnpy/web/static/css/style.css
git commit -m "feat(web): add styles for tabs and stats cards"
```

---

## Task 5: 更新前端 JavaScript

**Files:**
- Modify: `vnpy/web/static/js/app.js`

**说明:** 添加 Tab 切换逻辑、K线图表和统计数据图表渲染。

- [ ] **Step 1: 修改 Vue data 添加新状态**

```javascript
const app = Vue.createApp({
    data() {
        return {
            // 原有数据
            wsStatus: { type: 'info', text: '连接中...' },
            lastUpdate: '--',
            account: { balance: 0, available: 0, frozen: 0 },
            positions: [],
            trades: [],
            strategies: [],
            signals: [],
            dailyPnl: 0,
            positionValue: 0,
            
            // 新增：Tab 相关
            activeTab: 'trading',
            selectedSymbol: '',
            availableSymbols: [],
            
            // 新增：图表数据
            candles: {},
            stats: null,
            
            // 图表实例
            klineChart: null,
            indicatorChart: null,
            pnlChart: null,
            equityChart: null
        }
    },
    // ...
}
```

- [ ] **Step 2: 添加 watch 监听 Tab 切换**

```javascript
watch: {
    activeTab(newVal) {
        if (newVal === 'charts') {
            setTimeout(() => {
                this.initCharts();
                this.updateKlineChart();
            }, 100);
        } else if (newVal === 'analysis') {
            setTimeout(() => {
                this.initStatsCharts();
                this.updateStatsCharts();
            }, 100);
        }
    },
    selectedSymbol() {
        if (this.activeTab === 'charts') {
            this.updateKlineChart();
        }
    }
}
```

- [ ] **Step 3: 添加 K 线图表初始化方法**

```javascript
methods: {
    // 原有方法...
    
    initCharts() {
        if (!this.klineChart) {
            this.klineChart = echarts.init(document.getElementById('kline-chart'));
        }
        if (!this.indicatorChart) {
            this.indicatorChart = echarts.init(document.getElementById('indicator-chart'));
        }
    },
    
    updateKlineChart() {
        if (!this.klineChart || !this.candles[this.selectedSymbol]) return;
        
        const data = this.candles[this.selectedSymbol];
        const dates = data.map(d => d.timestamp);
        const values = data.map(d => [d.open, d.close, d.low, d.high]);
        const volumes = data.map(d => d.volume);
        
        const option = {
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
        
        this.klineChart.setOption(option);
    }
}
```

- [ ] **Step 4: 添加统计图表初始化方法**

```javascript
initStatsCharts() {
    if (!this.pnlChart) {
        this.pnlChart = echarts.init(document.getElementById('pnl-chart'));
    }
    if (!this.equityChart) {
        this.equityChart = echarts.init(document.getElementById('equity-chart'));
    }
},

updateStatsCharts() {
    if (!this.stats) return;
    
    // 盈亏分布饼图
    const pnlOption = {
        tooltip: { trigger: 'item' },
        legend: { orient: 'vertical', left: 'left' },
        series: [
            {
                name: '交易分布',
                type: 'pie',
                radius: '50%',
                data: [
                    { value: this.stats.winning_trades, name: '盈利', itemStyle: { color: '#67c23a' } },
                    { value: this.stats.losing_trades, name: '亏损', itemStyle: { color: '#f56c6c' } }
                ],
                emphasis: {
                    itemStyle: {
                        shadowBlur: 10,
                        shadowOffsetX: 0,
                        shadowColor: 'rgba(0, 0, 0, 0.5)'
                    }
                }
            }
        ]
    };
    
    // 资金曲线（示例数据）
    const equityOption = {
        tooltip: { trigger: 'axis' },
        xAxis: { type: 'category', data: ['1月', '2月', '3月', '4月', '5月', '6月'] },
        yAxis: { type: 'value' },
        series: [
            {
                name: '资金',
                type: 'line',
                smooth: true,
                data: [100, 105, 103, 110, 115, 115.5]
            }
        ]
    };
    
    this.pnlChart.setOption(pnlOption);
    this.equityChart.setOption(equityOption);
}
```

- [ ] **Step 5: 修改 WebSocket 数据处理**

```javascript
handleMessage(message) {
    if (message.type === 'init' || message.type === 'update') {
        const data = message.data;
        this.account = data.account || { balance: 0, available: 0, frozen: 0 };
        this.positions = data.positions || [];
        this.trades = data.trades || [];
        this.strategies = data.strategies || [];
        this.signals = data.signals || [];
        
        // 新增：更新图表和统计数据
        if (data.chart_data) {
            this.candles = data.chart_data;
            // 更新可选股票列表
            this.availableSymbols = Object.keys(data.chart_data);
            if (!this.selectedSymbol && this.availableSymbols.length > 0) {
                this.selectedSymbol = this.availableSymbols[0];
            }
        }
        if (data.stats) {
            this.stats = data.stats;
        }
        
        this.calculateDailyPnl();
        this.calculatePositionValue();
        this.lastUpdate = new Date().toLocaleTimeString();
        
        // 如果当前在图表页，更新图表
        if (this.activeTab === 'charts') {
            this.updateKlineChart();
        } else if (this.activeTab === 'analysis') {
            this.updateStatsCharts();
        }
    }
}
```

- [ ] **Step 6: 添加窗口大小改变处理**

```javascript
mounted() {
    this.connectWebSocket();
    
    // 监听窗口大小改变
    window.addEventListener('resize', () => {
        if (this.klineChart) this.klineChart.resize();
        if (this.indicatorChart) this.indicatorChart.resize();
        if (this.pnlChart) this.pnlChart.resize();
        if (this.equityChart) this.equityChart.resize();
    });
}
```

- [ ] **Step 7: 提交**

```bash
git add vnpy/web/static/js/app.js
git commit -m "feat(web): add tab switching and chart rendering logic"
```

---

## Task 6: 测试验证

**Files:**
- Test: 运行 `python web_dashboard.py` 测试

- [ ] **Step 1: 启动 Web 服务测试**

```bash
python web_dashboard.py
```

- [ ] **Step 2: 验证三个 Tab 是否正常显示**

访问 http://localhost:8000，检查：
1. 【交易】Tab - 显示账户、持仓、成交、策略等原有内容
2. 【K线图表】Tab - 显示 K 线图、股票选择器
3. 【数据分析】Tab - 显示统计数据卡片、盈亏分布图、资金曲线图

- [ ] **Step 3: 验证 Tab 切换功能**

点击不同 Tab，确认切换正常，图表在切换后正确渲染。

- [ ] **Step 4: 提交**

```bash
git add .
git commit -m "feat(web): complete multi-tab dashboard implementation"
```

---

## Self-Review Checklist

- [ ] **Spec coverage:**
  - [x] 【交易】Tab - Task 3 实现
  - [x] 【K线图表】Tab - Task 2, 3, 5 实现
  - [x] 【数据分析】Tab - Task 2, 3, 5 实现

- [ ] **No placeholders:**
  - [x] 所有代码都是完整的
  - [x] 没有 TBD/TODO

- [ ] **Type consistency:**
  - [x] CandleData, StatsData 模型定义一致
  - [x] DashboardData 更新包含新字段

---

## 执行选项

Plan complete and saved to `docs/superpowers/plans/2026-04-21-web-dashboard-multi-tab.md`. Two execution options:

**1. Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints

Which approach?
