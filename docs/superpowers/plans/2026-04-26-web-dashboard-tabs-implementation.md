# Web Dashboard 三标签页重构实现计划

> **执行方式:** 按任务顺序逐步实现，每个任务完成提交后通知你审核。

**目标:** 将 Web Dashboard 重构为三个标签页：Dashboard（总览）、Trade（交易）、Logs（日志），参照 freqUI 设计风格。

**技术栈:** Vue 3, Element Plus, ECharts, WebSocket

---

## 已确认的设计（来自用户澄清）

### Dashboard 标签页（首页）

**顶部指标栏:**
- 收益率曲线 (mini chart)
- 当日盈亏
- 总资产
- 持仓市值
- 总收益率

**当前持仓表格字段顺序:**
1. 名称
2. 代码
3. 订单ID
4. 方向（多/空）
5. 持仓量
6. 总筹码
7. 开仓价格
8. 最新价
9. 涨跌幅
10. 开始时间

**历史成交表格字段顺序:**
1. 名称
2. 代码
3. 订单ID
4. 方向（多/空）
5. 持仓量
6. 总筹码
7. 开仓价格
8. 空仓价格
9. 涨跌幅
10. 开始时间
11. 结束时间
12. 结束原因

### Trade 标签页
- 左侧：股票列表（名称、代码、涨跌幅）
- 中间：K线图（技术分析 + 指标）
- 右侧：交易面板（当前股票、最新价、涨跌幅、买入/卖出、价格、数量、下单按钮）

### Logs 标签页
- 筛选栏：级别、来源、关键词搜索、刷新按钮、清空按钮
- 日志列表：时间、级别、来源、消息

---

## 文件结构

**修改文件：**
- `web_dashboard/static/index.html` - HTML 结构和标签页布局
- `web_dashboard/static/js/app.js` - Vue 应用逻辑和状态管理
- `web_dashboard/static/css/style.css` - 样式和布局

**后端文件：**
- `run_trading_dashboard.py` - 添加 /logs API

---

## Task 1: 重构 HTML 结构

**目标:** 将原有的账户概览 + 四个小标签页，改为三个大标签页结构。

### 步骤

1. **删除旧结构** (index.html lines 95-234)
   - 删除账户概览卡片
   - 删除原有的 el-tabs（持仓明细/成交记录/委托记录/K线图表）

2. **添加新标签页结构**
   - Tab 1: 总览 (dashboard) - 顶部指标 + 当前持仓表格 + 历史成交表格
   - Tab 2: 交易 (trade) - 左侧股票列表 + 中间K线图 + 右侧交易面板
   - Tab 3: 日志 (logs) - 筛选栏 + 日志列表

3. **验证点:**
   - 三个标签页结构完整
   - 表格字段顺序与用户确认的一致
   - 右侧边栏保留策略状态、买卖信号、统计分析

---

## Task 2: 更新 JavaScript 逻辑

**目标:** 添加新的状态和方法支持三标签页功能。

### 步骤

1. **修改默认标签页**
   - `activeTab` 默认值从 'positions' 改为 'dashboard'

2. **添加 Dashboard 状态**
   - `dashboardMetrics` - 顶部指标计算属性
   - `closedTrades` - 历史成交数据数组

3. **添加 Trade 状态**
   - `tradeForm` - 交易表单（direction, price, volume）
   - `stockList` - 股票列表
   - `stockSearch` - 搜索关键词
   - `filteredStocks` - 过滤后的股票列表
   - `selectedStock` - 当前选中的股票

4. **添加 Logs 状态**
   - `logFilter` - 筛选条件（level, source, keyword）
   - `logs` - 日志列表
   - `filteredLogs` - 过滤后的日志
   - `getLogLevelColor` - 日志级别颜色函数

5. **添加新方法**
   - `selectStock(stock)` - 选择股票
   - `changePeriod(period)` - 切换K线周期
   - `submitOrder()` - 提交订单
   - `fetchLogs()` - 获取日志
   - `clearLogs()` - 清空日志

6. **修改标签页切换监听**
   - trade 标签激活时初始化图表并加载股票列表
   - logs 标签激活时获取日志

---

## Task 3: 添加 CSS 样式

**目标:** 为新标签页添加布局和样式。

### 步骤

1. **Dashboard 样式**
   - `.dashboard-container` - 容器
   - `.metrics-bar` - 指标栏网格布局
   - `.metric-card` - 指标卡片
   - `.header-count` - 表格标题计数

2. **Trade 样式**
   - `.trade-container` - 三栏布局（flex）
   - `.stock-list-panel` - 左侧股票列表
   - `.stock-item` - 股票项（含选中状态）
   - `.chart-panel` - 中间图表区域
   - `.trading-panel` - 右侧交易面板
   - `.direction-group` - 买卖方向按钮组

3. **Logs 样式**
   - `.logs-container` - 容器
   - `.logs-filter-bar` - 筛选栏
   - `.logs-list` - 日志列表（深色背景）
   - `.log-entry` - 日志条目
   - 日志级别颜色（info/warning/error）

4. **响应式样式**
   - 1200px以下：Trade 标签页变为垂直布局
   - 768px以下：Dashboard 指标变为两列

---

## Task 4: 添加后端 Logs API

**目标:** 添加日志存储和查询接口。

### 步骤

1. **添加日志存储**
   - 使用 `deque(maxlen=1000)` 存储最近1000条日志
   - `add_log(level, source, message)` 辅助函数

2. **添加 /logs 端点**
   - GET /logs - 支持 level、source、keyword 过滤参数

3. **在关键位置插入日志**
   - 下单时：trade 级别日志
   - 成交时：trade 级别日志
   - 策略启动/停止：strategy 级别日志
   - 连接错误：system 级别日志

---

## Task 5: 测试验证

### 验证清单

**Dashboard 标签页:**
- [ ] 默认显示 Dashboard 标签
- [ ] 顶部指标卡片显示正确（总资产、可用资金、当日盈亏、持仓市值、总收益率）
- [ ] 当前持仓表格字段顺序正确：名称→代码→订单ID→方向→持仓量→总筹码→开仓价格→最新价→涨跌幅→开始时间
- [ ] 历史成交表格字段完整：包含空仓价格、结束时间、结束原因

**Trade 标签页:**
- [ ] 切换到 Trade 标签
- [ ] 左侧股票列表显示（名称、代码、涨跌幅）
- [ ] 点击股票，K线图更新
- [ ] 买卖方向切换正常
- [ ] 下单按钮可用

**Logs 标签页:**
- [ ] 切换到 Logs 标签
- [ ] 日志列表加载
- [ ] 级别筛选正常
- [ ] 来源筛选正常
- [ ] 关键词搜索正常

**响应式布局:**
- [ ] 缩小窗口到 1200px 以下，Trade 标签变为垂直布局
- [ ] 缩小到 768px 以下，Dashboard 指标变为两列

---

## 执行顺序

1. Task 1: HTML 结构 → 提交 → 通知审核
2. Task 2: JavaScript 逻辑 → 提交 → 通知审核
3. Task 3: CSS 样式 → 提交 → 通知审核
4. Task 4: 后端 Logs API → 提交 → 通知审核
5. Task 5: 测试验证 → 提交

---

**计划已按你确认的设计编写完成。是否开始执行 Task 1？**
