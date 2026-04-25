# Web Dashboard Tab Reorganization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reorganize the web dashboard into three main tabs: Trading (with K-line chart), Overview (account summary), and Logs (trading/system logs).

**Architecture:** Replace the current four tabs (positions, trades, orders, charts) with three new tabs. Move the K-line chart from its current separate tab into the new Trading tab. Each tab will be self-contained with its own data fetching and rendering logic.

**Tech Stack:** Vue 3, Element Plus, ECharts, WebSocket for real-time updates

---

## Current Structure Analysis

The current dashboard has:
- **Tabs:** 持仓明细 (positions), 成交记录 (trades), 委托记录 (orders), K线图表 (charts)
- **Right Sidebar:** Strategy status, trading signals, statistics
- **Account Overview:** Displayed above the tabs

**New Structure:**
- **Tab 1: 交易 (Trading)** - K-line chart + trading operations panel + quick order entry
- **Tab 2: 总览 (Overview)** - Account overview + positions table + trades + orders + statistics
- **Tab 3: 日志 (Logs)** - System logs + trading logs with filtering

---

## Task 1: Update HTML Structure for New Tabs

**Files:**
- Modify: `web_dashboard/static/index.html`

- [ ] **Step 1: Replace the tab definitions**

Replace the current el-tabs section (lines 129-234) with the new three-tab structure:

```html
<!-- Tab 切换区 -->
<el-tabs v-model="activeTab" type="border-card">
    <!-- 交易 Tab - 包含K线图和交易操作 -->
    <el-tab-pane label="交易" name="trading">
        <div class="trading-container" style="display: flex; height: 600px;">
            <!-- 左侧K线图 -->
            <div class="chart-section" style="flex: 1; padding: 10px;">
                <div class="chart-header" style="margin-bottom: 10px;">
                    <el-select v-model="selectedSymbol" placeholder="选择股票" style="width: 200px;" @change="onSymbolChange">
                        <el-option
                            v-for="symbol in availableSymbols"
                            :key="symbol"
                            :label="symbol"
                            :value="symbol">
                        </el-option>
                    </el-select>
                    <el-button type="primary" size="small" @click="refreshChart" style="margin-left: 10px;">
                        刷新
                    </el-button>
                </div>
                <div id="kline-chart" style="width: 100%; height: 500px;"></div>
            </div>
            <!-- 右侧交易面板 -->
            <div class="trading-panel" style="width: 300px; padding: 10px; border-left: 1px solid #ebeef5;">
                <h4 style="margin-top: 0;">快速交易</h4>
                <el-form label-width="60px">
                    <el-form-item label="代码">
                        <el-input v-model="tradeForm.symbol" placeholder="输入代码"></el-input>
                    </el-form-item>
                    <el-form-item label="方向">
                        <el-radio-group v-model="tradeForm.direction">
                            <el-radio-button label="buy">买入</el-radio-button>
                            <el-radio-button label="sell">卖出</el-radio-button>
                        </el-radio-group>
                    </el-form-item>
                    <el-form-item label="价格">
                        <el-input-number v-model="tradeForm.price" :precision="2" :step="0.01" style="width: 100%;"></el-input-number>
                    </el-form-item>
                    <el-form-item label="数量">
                        <el-input-number v-model="tradeForm.volume" :min="100" :step="100" style="width: 100%;"></el-input-number>
                    </el-form-item>
                    <el-form-item>
                        <el-button type="primary" style="width: 100%;" @click="submitOrder">
                            下单
                        </el-button>
                    </el-form-item>
                </el-form>
                <!-- 当前选中股票信息 -->
                <div v-if="selectedStockInfo" class="stock-info" style="margin-top: 20px; padding: 10px; background: #f5f7fa; border-radius: 4px;">
                    <div style="font-weight: bold; margin-bottom: 10px;">{{ selectedStockInfo.symbol }}</div>
                    <div style="display: flex; justify-content: space-between; font-size: 12px;">
                        <span>最新价:</span>
                        <span :class="selectedStockInfo.change >= 0 ? 'profit' : 'loss'">
                            {{ selectedStockInfo.price?.toFixed(2) }}
                        </span>
                    </div>
                    <div style="display: flex; justify-content: space-between; font-size: 12px; margin-top: 5px;">
                        <span>涨跌:</span>
                        <span :class="selectedStockInfo.change >= 0 ? 'profit' : 'loss'">
                            {{ selectedStockInfo.change >= 0 ? '+' : '' }}{{ selectedStockInfo.change?.toFixed(2) }}%
                        </span>
                    </div>
                </div>
            </div>
        </div>
    </el-tab-pane>

    <!-- 总览 Tab - 账户概览、持仓、成交、委托、统计 -->
    <el-tab-pane label="总览" name="overview">
        <div class="overview-container" style="padding: 10px;">
            <!-- 账户概览卡片 -->
            <div class="overview-cards" style="display: grid; grid-template-columns: repeat(5, 1fr); gap: 15px; margin-bottom: 20px;">
                <div class="stat-card-mini" style="padding: 15px; background: #fff; border-radius: 4px; box-shadow: 0 2px 12px 0 rgba(0,0,0,0.1);">
                    <div style="font-size: 12px; color: #909399;">总资产</div>
                    <div style="font-size: 20px; font-weight: bold; margin-top: 5px;">{{ formatMoney(account.balance) }}</div>
                </div>
                <div class="stat-card-mini" style="padding: 15px; background: #fff; border-radius: 4px; box-shadow: 0 2px 12px 0 rgba(0,0,0,0.1);">
                    <div style="font-size: 12px; color: #909399;">可用资金</div>
                    <div style="font-size: 20px; font-weight: bold; margin-top: 5px;">{{ formatMoney(account.available) }}</div>
                </div>
                <div class="stat-card-mini" style="padding: 15px; background: #fff; border-radius: 4px; box-shadow: 0 2px 12px 0 rgba(0,0,0,0.1);">
                    <div style="font-size: 12px; color: #909399;">冻结资金</div>
                    <div style="font-size: 20px; font-weight: bold; margin-top: 5px;">{{ formatMoney(account.frozen || 0) }}</div>
                </div>
                <div class="stat-card-mini" style="padding: 15px; background: #fff; border-radius: 4px; box-shadow: 0 2px 12px 0 rgba(0,0,0,0.1);">
                    <div style="font-size: 12px; color: #909399;">当日盈亏</div>
                    <div :class="['stat-value', dailyPnl >= 0 ? 'profit' : 'loss']" style="font-size: 20px; font-weight: bold; margin-top: 5px;">
                        {{ dailyPnl >= 0 ? '+' : '' }}{{ formatMoney(dailyPnl) }}
                    </div>
                </div>
                <div class="stat-card-mini" style="padding: 15px; background: #fff; border-radius: 4px; box-shadow: 0 2px 12px 0 rgba(0,0,0,0.1);">
                    <div style="font-size: 12px; color: #909399;">持仓市值</div>
                    <div style="font-size: 20px; font-weight: bold; margin-top: 5px;">{{ formatMoney(positionValue) }}</div>
                </div>
            </div>

            <!-- 持仓表格 -->
            <div class="section-card" style="margin-bottom: 20px;">
                <div class="card-header">
                    <h3>持仓明细 ({{ positions.length }} 只)</h3>
                </div>
                <div class="card-body">
                    <el-table :data="positions" size="small" stripe class="data-table" max-height="300">
                        <el-table-column prop="vt_symbol" label="代码" width="120"></el-table-column>
                        <el-table-column prop="direction" label="方向" width="70">
                            <template #default="{ row }">
                                <el-tag :type="row.direction === '多' ? 'danger' : 'success'" size="small">
                                    {{ row.direction }}
                                </el-tag>
                            </template>
                        </el-table-column>
                        <el-table-column prop="volume" label="持仓量" width="90"></el-table-column>
                        <el-table-column prop="price" label="持仓成本" width="100">
                            <template #default="{ row }">
                                {{ row.price?.toFixed(2) || '--' }}
                            </template>
                        </el-table-column>
                        <el-table-column prop="last_price" label="最新价" width="100">
                            <template #default="{ row }">
                                {{ row.last_price?.toFixed(2) || '--' }}
                            </template>
                        </el-table-column>
                        <el-table-column prop="pnl" label="盈亏">
                            <template #default="{ row }">
                                <span :class="row.pnl >= 0 ? 'profit' : 'loss'">
                                    {{ row.pnl >= 0 ? '+' : '' }}{{ row.pnl?.toFixed(2) || '0.00' }}
                                </span>
                            </template>
                        </el-table-column>
                    </el-table>
                </div>
            </div>

            <!-- 成交和委托并排 -->
            <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 20px;">
                <!-- 成交记录 -->
                <div class="section-card">
                    <div class="card-header">
                        <h3>成交记录 ({{ trades.length }})</h3>
                    </div>
                    <div class="card-body">
                        <el-table :data="trades.slice(0, 10)" size="small" stripe class="data-table" max-height="250">
                            <el-table-column prop="datetime" label="时间" width="160"></el-table-column>
                            <el-table-column prop="vt_symbol" label="代码" width="120"></el-table-column>
                            <el-table-column prop="direction" label="方向" width="70">
                                <template #default="{ row }">
                                    <el-tag :type="row.direction === '多' ? 'danger' : 'success'" size="small">
                                        {{ row.direction }}
                                    </el-tag>
                                </template>
                            </el-table-column>
                            <el-table-column prop="volume" label="数量" width="80"></el-table-column>
                            <el-table-column prop="price" label="价格"></el-table-column>
                        </el-table>
                    </div>
                </div>

                <!-- 委托记录 -->
                <div class="section-card">
                    <div class="card-header">
                        <h3>委托记录 ({{ orders.length }})</h3>
                    </div>
                    <div class="card-body">
                        <el-table :data="orders.slice(0, 10)" size="small" stripe class="data-table" max-height="250">
                            <el-table-column prop="datetime" label="时间" width="160"></el-table-column>
                            <el-table-column prop="vt_symbol" label="代码" width="120"></el-table-column>
                            <el-table-column prop="direction" label="方向" width="70">
                                <template #default="{ row }">
                                    <el-tag :type="row.direction === '多' ? 'danger' : 'success'" size="small">
                                        {{ row.direction }}
                                    </el-tag>
                                </template>
                            </el-table-column>
                            <el-table-column prop="volume" label="数量" width="80"></el-table-column>
                            <el-table-column prop="price" label="价格"></el-table-column>
                            <el-table-column prop="status" label="状态" width="90">
                                <template #default="{ row }">
                                    <el-tag :type="row.status === '已成交' ? 'success' : 'warning'" size="small">
                                        {{ row.status }}
                                    </el-tag>
                                </template>
                            </el-table-column>
                        </el-table>
                    </div>
                </div>
            </div>
        </div>
    </el-tab-pane>

    <!-- 日志 Tab - 系统日志和交易日志 -->
    <el-tab-pane label="日志" name="logs">
        <div class="logs-container" style="padding: 10px; height: 600px; display: flex; flex-direction: column;">
            <!-- 日志筛选 -->
            <div class="logs-filter" style="margin-bottom: 15px; display: flex; gap: 10px;">
                <el-select v-model="logFilter.level" placeholder="日志级别" style="width: 120px;">
                    <el-option label="全部" value="all"></el-option>
                    <el-option label="信息" value="info"></el-option>
                    <el-option label="警告" value="warning"></el-option>
                    <el-option label="错误" value="error"></el-option>
                </el-select>
                <el-select v-model="logFilter.source" placeholder="来源" style="width: 120px;">
                    <el-option label="全部" value="all"></el-option>
                    <el-option label="系统" value="system"></el-option>
                    <el-option label="交易" value="trade"></el-option>
                    <el-option label="策略" value="strategy"></el-option>
                </el-select>
                <el-input v-model="logFilter.keyword" placeholder="搜索关键词" style="width: 200px;"></el-input>
                <el-button type="primary" @click="fetchLogs">刷新</el-button>
                <el-button @click="clearLogs">清空</el-button>
            </div>

            <!-- 日志列表 -->
            <div class="logs-list" style="flex: 1; overflow-y: auto; background: #1e1e1e; color: #d4d4d4; padding: 10px; font-family: 'Consolas', monospace; font-size: 13px; border-radius: 4px;">
                <div v-if="logs.length === 0" class="empty-logs" style="text-align: center; padding: 50px; color: #666;">
                    暂无日志
                </div>
                <div v-for="(log, index) in filteredLogs" :key="index" class="log-entry" :class="log.level" style="margin-bottom: 5px; padding: 3px 5px; border-radius: 2px;">
                    <span class="log-time" style="color: #858585;">[{{ log.time }}]</span>
                    <span class="log-level" :style="{ color: getLogLevelColor(log.level) }">[{{ log.level.toUpperCase() }}]</span>
                    <span class="log-source" style="color: #4ec9b0;">[{{ log.source }}]</span>
                    <span class="log-message">{{ log.message }}</span>
                </div>
            </div>
        </div>
    </el-tab-pane>
</el-tabs>
```

- [ ] **Step 2: Remove old account overview section**

Remove the old account overview section (lines 96-126) since it's now in the Overview tab.

- [ ] **Step 3: Commit the changes**

```bash
git add web_dashboard/static/index.html
git commit -m "feat: reorganize dashboard into trading/overview/logs tabs"
```

---

## Task 2: Update JavaScript for New Tab Functionality

**Files:**
- Modify: `web_dashboard/static/js/app.js`

- [ ] **Step 1: Add new reactive state variables**

After line 35 (`const activeTab = ref('positions');`), add:

```javascript
// New tab state
const activeTab = ref('overview');  // Default to overview tab

// Trading tab state
const tradeForm = reactive({
    symbol: '',
    direction: 'buy',
    price: 0,
    volume: 100
});
const selectedStockInfo = ref(null);

// Log filter state
const logFilter = reactive({
    level: 'all',
    source: 'all',
    keyword: ''
});
const logs = ref([]);
```

- [ ] **Step 2: Add computed property for filtered logs**

After the computed properties section, add:

```javascript
// Filtered logs based on filter criteria
const filteredLogs = computed(() => {
    return logs.value.filter(log => {
        if (logFilter.level !== 'all' && log.level !== logFilter.level) return false;
        if (logFilter.source !== 'all' && log.source !== logFilter.source) return false;
        if (logFilter.keyword && !log.message.includes(logFilter.keyword)) return false;
        return true;
    });
});
```

- [ ] **Step 3: Add new methods for trading tab**

Add after the existing methods:

```javascript
// Trading tab methods
const onSymbolChange = (symbol) => {
    selectedSymbol.value = symbol;
    tradeForm.symbol = symbol;
    // Find stock info from positions
    const pos = positions.value.find(p => p.vt_symbol === symbol);
    if (pos) {
        selectedStockInfo.value = {
            symbol: symbol,
            price: pos.last_price,
            change: pos.pnl / (pos.volume * pos.price) * 100 // Approximate change %
        };
    }
    nextTick(() => {
        initChart();
    });
};

const submitOrder = async () => {
    if (!tradeForm.symbol || !tradeForm.price || !tradeForm.volume) {
        ElMessage.warning('请填写完整的订单信息');
        return;
    }
    try {
        const response = await fetch('/order', {
            method: 'POST',
            headers: {
                'Authorization': `Bearer ${token.value}`,
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                vt_symbol: tradeForm.symbol,
                direction: tradeForm.direction === 'buy' ? '多' : '空',
                price: tradeForm.price,
                volume: tradeForm.volume
            })
        });
        if (response.ok) {
            ElMessage.success('下单成功');
            fetchData(); // Refresh data
        } else {
            ElMessage.error('下单失败');
        }
    } catch (error) {
        console.error('下单失败:', error);
        ElMessage.error('下单失败: ' + error.message);
    }
};
```

- [ ] **Step 4: Add log-related methods**

```javascript
// Log methods
const fetchLogs = async () => {
    try {
        const response = await fetch('/logs', {
            headers: { 'Authorization': `Bearer ${token.value}` }
        });
        if (response.ok) {
            logs.value = await response.json();
        }
    } catch (error) {
        console.error('获取日志失败:', error);
    }
};

const clearLogs = () => {
    logs.value = [];
};

const getLogLevelColor = (level) => {
    const colors = {
        'info': '#3794ff',
        'warning': '#cca700',
        'error': '#f14c4c',
        'debug': '#b0b0b0'
    };
    return colors[level] || '#d4d4d4';
};
```

- [ ] **Step 5: Update watch for activeTab**

Replace the watch for activeTab to handle chart initialization:

```javascript
// Watch for tab changes to initialize components
watch(activeTab, (newTab) => {
    if (newTab === 'trading') {
        nextTick(() => {
            initChart();
        });
    } else if (newTab === 'logs') {
        fetchLogs();
    }
});
```

- [ ] **Step 6: Update return statement**

Update the return statement in setup() to expose new state and methods:

```javascript
return {
    // Existing state
    isLoggedIn, token, loginLoading, loginError,
    loginForm, ws, wsConnected, wsStatus,
    account, positions, trades, orders, lastUpdate,
    tradingMode, strategies, stockPool, signals, stats,
    selectedSymbol, availableSymbols,
    formatMoney, formatPercent, formatNumber,
    dailyPnl, positionValue,
    
    // New state
    activeTab,
    tradeForm, selectedStockInfo,
    logFilter, logs, filteredLogs,
    
    // New methods
    onSymbolChange, submitOrder,
    fetchLogs, clearLogs, getLogLevelColor,
    
    // Existing methods
    handleLogin, logout, fetchData, fetchTradingMode,
    fetchStrategies, toggleStrategy, fetchStockPool,
    fetchStats, connectWebSocket, initChart, refreshChart
};
```

- [ ] **Step 7: Commit the changes**

```bash
git add web_dashboard/static/js/app.js
git commit -m "feat: add JavaScript logic for new tabs"
```

---

## Task 3: Add Backend API Endpoint for Logs

**Files:**
- Modify: `web_dashboard/__init__.py` or main server file

- [ ] **Step 1: Add logs endpoint**

Add a new API endpoint to serve logs:

```python
@app.route('/logs', methods=['GET'])
@jwt_required()
def get_logs():
    """Get system and trading logs"""
    level = request.args.get('level', 'all')
    source = request.args.get('source', 'all')
    keyword = request.args.get('keyword', '')
    
    # This is a placeholder - implement based on your logging system
    logs = [
        {
            'time': '2024-01-01 10:00:00',
            'level': 'info',
            'source': 'system',
            'message': 'Trading engine started'
        },
        {
            'time': '2024-01-01 10:05:23',
            'level': 'info',
            'source': 'trade',
            'message': 'Order executed: 600519.SSE, Buy, 100@1800.00'
        }
    ]
    
    # Filter logs
    if level != 'all':
        logs = [l for l in logs if l['level'] == level]
    if source != 'all':
        logs = [l for l in logs if l['source'] == source]
    if keyword:
        logs = [l for l in logs if keyword in l['message']]
    
    return jsonify(logs)
```

- [ ] **Step 2: Commit the changes**

```bash
git add web_dashboard/__init__.py
git commit -m "feat: add /logs API endpoint"
```

---

## Task 4: Update CSS Styles for New Layout

**Files:**
- Modify: `web_dashboard/static/css/style.css`

- [ ] **Step 1: Add styles for log entries**

```css
/* Log entry styles */
.log-entry {
    font-family: 'Consolas', 'Monaco', monospace;
    line-height: 1.5;
}

.log-entry:hover {
    background: #2a2a2a;
}

.log-entry.info .log-level {
    color: #3794ff;
}

.log-entry.warning .log-level {
    color: #cca700;
}

.log-entry.error .log-level {
    color: #f14c4c;
}

.log-time {
    color: #858585;
    margin-right: 8px;
}

.log-source {
    color: #4ec9b0;
    margin-right: 8px;
}

/* Trading panel styles */
.trading-panel {
    background: #f5f7fa;
}

.trading-panel h4 {
    color: #303133;
    border-bottom: 1px solid #ebeef5;
    padding-bottom: 10px;
}

.stock-info {
    border: 1px solid #ebeef5;
}

/* Overview cards */
.stat-card-mini {
    transition: transform 0.2s;
}

.stat-card-mini:hover {
    transform: translateY(-2px);
}
```

- [ ] **Step 2: Commit the changes**

```bash
git add web_dashboard/static/css/style.css
git commit -m "style: add CSS for new tabs layout"
```

---

## Task 5: Test the New Dashboard

- [ ] **Step 1: Test Trading tab**

1. Open the dashboard
2. Switch to "交易" tab
3. Verify K-line chart loads
4. Test symbol selector
5. Test order form (if connected to backend)

- [ ] **Step 2: Test Overview tab**

1. Switch to "总览" tab
2. Verify account cards display correctly
3. Check positions table
4. Check trades and orders tables

- [ ] **Step 3: Test Logs tab**

1. Switch to "日志" tab
2. Verify logs display
3. Test filtering by level
4. Test filtering by source
5. Test keyword search

- [ ] **Step 4: Commit test results**

```bash
git commit -m "test: verify new tab functionality"
```

---

## Summary

**Changes made:**
1. Replaced 4 old tabs (持仓、成交、委托、图表) with 3 new tabs (交易、总览、日志)
2. Moved K-line chart from separate tab into Trading tab with trading panel
3. Created comprehensive Overview tab with account summary, positions, trades, and orders
4. Added new Logs tab with filtering capabilities
5. Added backend API for logs
6. Added CSS styling for new components

**Files modified:**
- `web_dashboard/static/index.html` - New tab structure
- `web_dashboard/static/js/app.js` - New state and methods
- `web_dashboard/__init__.py` - New logs endpoint
- `web_dashboard/static/css/style.css` - New styles

**Plan complete and saved to `docs/superpowers/plans/2026-04-26-web-dashboard-tabs.md`. Two execution options:**

**1. Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints

**Which approach?**
