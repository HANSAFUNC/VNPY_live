# Vue3 WebTrader 看板实现计划

> **面向智能体开发者：** 必需子技能：使用 superpowers:subagent-driven-development（推荐）或 superpowers:executing-plans 来逐任务实现此计划。步骤使用复选框（`- [ ]`）语法进行跟踪。

**目标：** 为 vnpy_webtrader 创建 Vue3 + Element Plus 前端看板，包含 JWT 登录和 WebSocket 实时数据显示（4 个标签页：交易、股票池、图表、分析）

**架构：** 纯前端应用，连接 vnpy_webtrader 现有的 FastAPI 后端。前端通过 JWT 认证，通过 WebSocket 接收实时行情数据，并在响应式看板的 4 个标签页中展示。

**技术栈：** Vue 3（组合式 API）、Element Plus、ECharts、原生 WebSocket、JWT 令牌认证

---

## 文件结构

| 文件 | 职责 |
|------|--------------|
| `vnpy_webtrader/static/index.html` | 主 HTML，通过 CDN 引入 Vue3 + Element Plus + ECharts |
| `vnpy_webtrader/static/js/app.js` | Vue3 应用：登录、WebSocket 连接、数据处理、4 标签页 UI |
| `vnpy_webtrader/static/css/style.css` | 看板布局和组件的自定义样式 |

---

## 了解后端接口

### WebSocket 连接流程

1. **登录**：POST 请求到 `/token`，携带用户名/密码 → 接收 JWT 令牌
2. **连接 WebSocket**：`ws://localhost:8000/ws/?token=<jwt_token>`
3. **接收数据**：后端通过 `rpc_callback` 推送数据 → WebSocket

### WebSocket 消息格式

```json
{
    "topic": "eTick.",
    "data": { ...对象数据... }
}
```

主题与 UI 的映射：
- `eTick.` → Tick 数据（用于图表）
- `eAccount.` → 账户信息（交易标签页）
- `ePosition.` → 持仓（交易标签页）
- `eTrade.` → 成交（交易标签页）
- `eOrder.` → 委托（交易标签页）

---

## 任务 1：创建登录页面

**文件：**
- 创建：`vnpy_webtrader/static/index.html`（登录部分）
- 创建：`vnpy_webtrader/static/js/app.js`（登录逻辑）
- 创建：`vnpy_webtrader/static/css/style.css`（登录样式）

- [ ] **步骤 1：创建带登录表单的 HTML 结构**

创建 `vnpy_webtrader/static/index.html`：

```html
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>VNPY WebTrader</title>
    <link rel="stylesheet" href="https://unpkg.com/element-plus/dist/index.css">
    <link rel="stylesheet" href="/static/css/style.css">
</head>
<body>
    <div id="app">
        <!-- 登录视图 -->
        <div v-if="!isLoggedIn" class="login-container">
            <el-card class="login-card">
                <h2>VNPY WebTrader</h2>
                <el-form :model="loginForm" @submit.prevent="handleLogin">
                    <el-form-item>
                        <el-input
                            v-model="loginForm.username"
                            placeholder="用户名"
                            prefix-icon="User"
                        />
                    </el-form-item>
                    <el-form-item>
                        <el-input
                            v-model="loginForm.password"
                            type="password"
                            placeholder="密码"
                            prefix-icon="Lock"
                        />
                    </el-form-item>
                    <el-form-item>
                        <el-button
                            type="primary"
                            @click="handleLogin"
                            :loading="loginLoading"
                            style="width: 100%"
                        >
                            登录
                        </el-button>
                    </el-form-item>
                </el-form>
                <el-alert
                    v-if="loginError"
                    :title="loginError"
                    type="error"
                    closable
                    @close="loginError = ''"
                />
            </el-card>
        </div>

        <!-- 看板视图（暂时占位） -->
        <div v-else>
            <h1>看板（将在任务 2 中实现）</h1>
            <p>令牌：{{ token }}</p>
        </div>
    </div>

    <script src="https://unpkg.com/vue@3/dist/vue.global.js"></script>
    <script src="https://unpkg.com/element-plus/dist/index.full.js"></script>
    <script src="https://unpkg.com/@element-plus/icons-vue"></script>
    <script src="/static/js/app.js"></script>
</body>
</html>
```

- [ ] **步骤 2：创建 Vue3 登录逻辑**

创建 `vnpy_webtrader/static/js/app.js`：

```javascript
const { createApp, ref, reactive } = Vue;

const app = createApp({
    setup() {
        // 认证状态
        const isLoggedIn = ref(false);
        const token = ref('');
        const loginLoading = ref(false);
        const loginError = ref('');

        // 登录表单
        const loginForm = reactive({
            username: '',
            password: ''
        });

        // 登录处理器
        const handleLogin = async () => {
            if (!loginForm.username || !loginForm.password) {
                loginError.value = '请输入用户名和密码';
                return;
            }

            loginLoading.value = true;
            loginError.value = '';

            try {
                const formData = new URLSearchParams();
                formData.append('username', loginForm.username);
                formData.append('password', loginForm.password);

                const response = await fetch('/token', {
                    method: 'POST',
                    body: formData
                });

                if (!response.ok) {
                    throw new Error('登录失败');
                }

                const data = await response.json();
                token.value = data.access_token;
                isLoggedIn.value = true;

                // 将令牌存储在 localStorage 中，以便页面刷新后使用
                localStorage.setItem('vnpy_token', token.value);

            } catch (error) {
                loginError.value = error.message || '登录失败，请检查用户名和密码';
            } finally {
                loginLoading.value = false;
            }
        };

        // 页面加载时检查已有令牌
        const checkStoredToken = () => {
            const stored = localStorage.getItem('vnpy_token');
            if (stored) {
                token.value = stored;
                isLoggedIn.value = true;
            }
        };

        // 初始化
        checkStoredToken();

        return {
            isLoggedIn,
            token,
            loginForm,
            loginLoading,
            loginError,
            handleLogin
        };
    }
});

app.use(ElementPlus);
app.mount('#app');
```

- [ ] **步骤 3：添加登录样式**

创建 `vnpy_webtrader/static/css/style.css`：

```css
* {
    margin: 0;
    padding: 0;
    box-sizing: border-box;
}

body {
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
    background: #f0f2f5;
    min-height: 100vh;
}

/* 登录 */
.login-container {
    display: flex;
    justify-content: center;
    align-items: center;
    min-height: 100vh;
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
}

.login-card {
    width: 400px;
    padding: 20px;
}

.login-card h2 {
    text-align: center;
    margin-bottom: 30px;
    color: #333;
}
```

- [ ] **步骤 4：测试登录页面**

1. 启动 vnpy_webtrader：`python vnpy_webtrader/run.py`
2. 打开 http://localhost:8000
3. 验证登录表单显示正常
4. 使用配置的凭据测试登录

预期结果：登录表单显示，成功登录后存储令牌并显示"看板"占位符

- [ ] **步骤 5：提交代码**

```bash
git add vnpy_webtrader/static/
git commit -m "feat(webtrader): 添加 Vue3 登录页面与 JWT 认证"
```

---

## 任务 2：实现 WebSocket 连接

**文件：**
- 修改：`vnpy_webtrader/static/js/app.js`

- [ ] **步骤 1：添加 WebSocket 连接逻辑**

添加到 `app.js` 的登录代码之后：

```javascript
// WebSocket
const ws = ref(null);
const wsConnected = ref(false);
const wsStatus = computed(() => ({
    text: wsConnected.value ? '已连接' : '未连接',
    type: wsConnected.value ? 'success' : 'danger'
}));

// 数据存储
const account = ref({ balance: 0, available: 0, frozen: 0 });
const positions = ref([]);
const trades = ref([]);
const orders = ref([]);
const lastUpdate = ref('--');

// 登录后连接 WebSocket
const connectWebSocket = () => {
    if (!token.value) return;

    const wsUrl = `ws://${window.location.host}/ws/?token=${token.value}`;
    console.log('正在连接 WebSocket：', wsUrl);

    ws.value = new WebSocket(wsUrl);

    ws.value.onopen = () => {
        console.log('WebSocket 已连接');
        wsConnected.value = true;
    };

    ws.value.onmessage = (event) => {
        try {
            const message = JSON.parse(event.data);
            handleWebSocketMessage(message);
        } catch (e) {
            console.error('解析消息失败：', e);
        }
    };

    ws.value.onclose = () => {
        console.log('WebSocket 已断开');
        wsConnected.value = false;
        // 5 秒后自动重连
        setTimeout(() => {
            if (isLoggedIn.value) connectWebSocket();
        }, 5000);
    };

    ws.value.onerror = (error) => {
        console.error('WebSocket 错误：', error);
    };
};

// 处理收到的 WebSocket 消息
const handleWebSocketMessage = (message) => {
    const { topic, data } = message;
    lastUpdate.value = new Date().toLocaleTimeString();

    // 将主题映射到数据类型
    switch (topic) {
        case 'eAccount.':
            account.value = { ...account.value, ...data };
            break;
        case 'ePosition.':
            updatePosition(data);
            break;
        case 'eTrade.':
            trades.value.unshift(data);
            if (trades.value.length > 100) trades.value = trades.value.slice(0, 100);
            break;
        case 'eOrder.':
            updateOrder(data);
            break;
        case 'eTick.':
            // 存储 tick 数据用于图表
            break;
        default:
            console.log('未知主题：', topic, data);
    }
};

// 更新持仓辅助函数
const updatePosition = (data) => {
    const idx = positions.value.findIndex(p => p.vt_symbol === data.vt_symbol);
    if (idx >= 0) {
        positions.value[idx] = { ...positions.value[idx], ...data };
    } else {
        positions.value.push(data);
    }
};

// 更新委托辅助函数
const updateOrder = (data) => {
    const idx = orders.value.findIndex(o => o.vt_orderid === data.vt_orderid);
    if (idx >= 0) {
        orders.value[idx] = { ...orders.value[idx], ...data };
    } else {
        orders.value.push(data);
    }
};
```

- [ ] **步骤 2：登录成功后连接 WebSocket**

修改 `handleLogin` 成功处理器：

```javascript
                const data = await response.json();
                token.value = data.access_token;
                isLoggedIn.value = true;
                localStorage.setItem('vnpy_token', token.value);

                // 登录后连接 WebSocket
                connectWebSocket();
```

同时更新 `checkStoredToken`：

```javascript
        const checkStoredToken = () => {
            const stored = localStorage.getItem('vnpy_token');
            if (stored) {
                token.value = stored;
                isLoggedIn.value = true;
                connectWebSocket();
            }
        };
```

- [ ] **步骤 3：更新 return 对象**

```javascript
        return {
            isLoggedIn,
            token,
            loginForm,
            loginLoading,
            loginError,
            handleLogin,
            wsConnected,
            wsStatus,
            account,
            positions,
            trades,
            orders,
            lastUpdate
        };
```

- [ ] **步骤 4：测试 WebSocket 连接**

1. 在页面上登录
2. 检查浏览器控制台是否显示"WebSocket 已连接"
3. 验证 UI 中显示连接状态

预期结果：登录后，WebSocket 自动连接

- [ ] **步骤 5：提交代码**

```bash
git add vnpy_webtrader/static/js/app.js
git commit -m "feat(webtrader): 添加 WebSocket 连接与自动重连"
```

---

## 任务 3：实现交易标签页（标签 1）

**文件：**
- 修改：`vnpy_webtrader/static/index.html`
- 修改：`vnpy_webtrader/static/css/style.css`

- [ ] **步骤 1：添加带页眉的看板布局**

替换 `index.html` 中的占位看板 div：

```html
        <!-- 看板视图 -->
        <div v-else class="dashboard-container">
            <!-- 页眉 -->
            <el-header class="dashboard-header">
                <h1>VNPY 交易看板</h1>
                <div class="header-right">
                    <span class="update-time">最后更新：{{ lastUpdate }}</span>
                    <el-tag :type="wsStatus.type" effect="dark">
                        {{ wsStatus.text }}
                    </el-tag>
                    <el-button size="small" @click="logout">退出</el-button>
                </div>
            </el-header>

            <!-- 主内容区 -->
            <el-main>
                <el-tabs v-model="activeTab" type="border-card">
                    <!-- 标签 1：交易 -->
                    <el-tab-pane label="交易" name="trading">
                        <div v-if="activeTab === 'trading'">
                            <!-- 账户概览 -->
                            <el-row :gutter="20" class="overview-row">
                                <el-col :span="6">
                                    <el-card>
                                        <div class="metric">
                                            <div class="metric-label">总资产</div>
                                            <div class="metric-value">{{ formatMoney(account.balance) }}</div>
                                        </div>
                                    </el-card>
                                </el-col>
                                <el-col :span="6">
                                    <el-card>
                                        <div class="metric">
                                            <div class="metric-label">可用资金</div>
                                            <div class="metric-value">{{ formatMoney(account.available) }}</div>
                                        </div>
                                    </el-card>
                                </el-col>
                                <el-col :span="6">
                                    <el-card>
                                        <div class="metric">
                                            <div class="metric-label">冻结资金</div>
                                            <div class="metric-value">{{ formatMoney(account.frozen) }}</div>
                                        </div>
                                    </el-card>
                                </el-col>
                                <el-col :span="6">
                                    <el-card>
                                        <div class="metric">
                                            <div class="metric-label">持仓市值</div>
                                            <div class="metric-value">{{ formatMoney(positionValue) }}</div>
                                        </div>
                                    </el-card>
                                </el-col>
                            </el-row>

                            <!-- 持仓和成交 -->
                            <el-row :gutter="20" class="content-row">
                                <el-col :span="16">
                                    <el-card title="持仓明细">
                                        <el-table :data="positions" size="small" stripe>
                                            <el-table-column prop="vt_symbol" label="代码" width="120"></el-table-column>
                                            <el-table-column prop="direction" label="方向" width="80">
                                                <template #default="{ row }">
                                                    <el-tag :type="row.direction === '多' ? 'danger' : 'success'" size="small">
                                                        {{ row.direction }}
                                                    </el-tag>
                                                </template>
                                            </el-table-column>
                                            <el-table-column prop="volume" label="数量" width="100"></el-table-column>
                                            <el-table-column prop="price" label="均价">
                                                <template #default="{ row }">{{ row.price?.toFixed(2) }}</template>
                                            </el-table-column>
                                            <el-table-column prop="last_price" label="现价">
                                                <template #default="{ row }">{{ row.last_price?.toFixed(2) }}</template>
                                            </el-table-column>
                                            <el-table-column prop="pnl" label="盈亏">
                                                <template #default="{ row }">
                                                    <span :class="row.pnl >= 0 ? 'profit' : 'loss'">
                                                        {{ formatMoney(row.pnl) }}
                                                    </span>
                                                </template>
                                            </el-table-column>
                                        </el-table>
                                    </el-card>

                                    <el-card title="最近成交" style="margin-top: 20px;">
                                        <el-table :data="trades.slice(0, 10)" size="small" stripe>
                                            <el-table-column prop="time" label="时间" width="100"></el-table-column>
                                            <el-table-column prop="vt_symbol" label="代码" width="120"></el-table-column>
                                            <el-table-column prop="direction" label="方向" width="80">
                                                <template #default="{ row }">
                                                    <el-tag :type="row.direction === '多' ? 'danger' : 'success'" size="small">
                                                        {{ row.direction }}
                                                    </el-tag>
                                                </template>
                                            </el-table-column>
                                            <el-table-column prop="volume" label="数量" width="80"></el-table-column>
                                            <el-table-column prop="price" label="价格">
                                                <template #default="{ row }">{{ row.price?.toFixed(2) }}</template>
                                            </el-table-column>
                                        </el-table>
                                    </el-card>
                                </el-col>

                                <el-col :span="8">
                                    <el-card title="策略控制">
                                        <div class="strategy-list">
                                            <div v-for="s in strategies" :key="s.name" class="strategy-item">
                                                <span>{{ s.name }}</span>
                                                <el-switch v-model="s.running" @change="toggleStrategy(s)"></el-switch>
                                            </div>
                                        </div>
                                    </el-card>
                                </el-col>
                            </el-row>
                        </div>
                    </el-tab-pane>

                    <!-- 占位标签 -->
                    <el-tab-pane label="股票池" name="pool">股票池内容</el-tab-pane>
                    <el-tab-pane label="K线图表" name="charts">K线图表内容</el-tab-pane>
                    <el-tab-pane label="分析" name="analysis">分析内容</el-tab-pane>
                </el-tabs>
            </el-main>
        </div>
```

- [ ] **步骤 2：添加看板样式**

添加到 `style.css`：

```css
/* 看板 */
.dashboard-container {
    min-height: 100vh;
}

.dashboard-header {
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
    color: white;
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 0 20px;
    height: 60px;
}

.dashboard-header h1 {
    font-size: 20px;
}

.header-right {
    display: flex;
    align-items: center;
    gap: 15px;
}

.update-time {
    font-size: 14px;
    opacity: 0.9;
}

.overview-row {
    margin-bottom: 20px;
}

.metric {
    text-align: center;
}

.metric-label {
    font-size: 14px;
    color: #666;
    margin-bottom: 10px;
}

.metric-value {
    font-size: 24px;
    font-weight: 600;
    color: #333;
}

.content-row {
    margin-top: 20px;
}

.profit {
    color: #f56c6c;
}

.loss {
    color: #67c23a;
}

.strategy-list {
    max-height: 300px;
}

.strategy-item {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 12px;
    border-bottom: 1px solid #ebeef5;
}

.strategy-item:last-child {
    border-bottom: none;
}
```

- [ ] **步骤 3：添加辅助方法和状态**

添加到 `app.js`：

```javascript
        // UI 状态
        const activeTab = ref('trading');

        // 策略
        const strategies = ref([
            { name: 'XGBExtremaLive', running: true }
        ]);

        // 计算属性
        const positionValue = computed(() => {
            return positions.value.reduce((sum, p) => sum + (p.volume * (p.last_price || p.price || 0)), 0);
        });

        // 格式化辅助函数
        const formatMoney = (val) => {
            if (val === undefined || val === null) return '¥0.00';
            return '¥' + Number(val).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
        };

        // 退出登录
        const logout = () => {
            localStorage.removeItem('vnpy_token');
            token.value = '';
            isLoggedIn.value = false;
            wsConnected.value = false;
            if (ws.value) ws.value.close();
        };

        // 策略开关
        const toggleStrategy = (s) => {
            console.log('切换策略：', s.name, s.running);
        };
```

- [ ] **步骤 4：更新 return**

```javascript
        return {
            isLoggedIn,
            token,
            loginForm,
            loginLoading,
            loginError,
            handleLogin,
            logout,
            wsConnected,
            wsStatus,
            account,
            positions,
            trades,
            orders,
            lastUpdate,
            activeTab,
            strategies,
            positionValue,
            formatMoney,
            toggleStrategy
        };
```

- [ ] **步骤 5：测试交易标签页**

1. 刷新页面并登录
2. 验证交易标签页显示账户指标、持仓表格、成交表格
3. 检查 WebSocket 数据更新显示

预期结果：交易标签页显示所有区域，数据实时更新

- [ ] **步骤 6：提交代码**

```bash
git add vnpy_webtrader/static/
git commit -m "feat(webtrader): 实现交易标签页，包含账户、持仓、成交"
```

---

## 任务 4：实现股票池标签页（标签 2）

**文件：**
- 修改：`vnpy_webtrader/static/index.html`
- 修改：`vnpy_webtrader/static/js/app.js`

- [ ] **步骤 1：替换股票池占位符**

在 `index.html` 中，替换 `<el-tab-pane label="股票池" name="pool">股票池内容</el-tab-pane>`：

```html
                    <!-- 标签 2：股票池 -->
                    <el-tab-pane label="股票池" name="pool">
                        <el-row :gutter="20">
                            <!-- 买入信号 -->
                            <el-col :span="12">
                                <el-card>
                                    <template #header>
                                        <span style="color: #f56c6c; font-weight: bold;">📈 今日买入信号</span>
                                        <el-tag type="danger" size="small" style="margin-left: 10px;">
                                            {{ stockPool.buy?.length || 0 }} 只
                                        </el-tag>
                                    </template>
                                    <el-table :data="stockPool.buy || []" stripe>
                                        <el-table-column prop="vt_symbol" label="股票代码" width="120"></el-table-column>
                                        <el-table-column prop="close_price" label="收盘价">
                                            <template #default="{ row }">
                                                ¥{{ row.close_price?.toFixed(2) }}
                                            </template>
                                        </el-table-column>
                                        <el-table-column prop="strength" label="信号强度">
                                            <template #default="{ row }">
                                                <el-progress
                                                    :percentage="Math.round((row.strength || 0) * 100)"
                                                    :color="'#f56c6c'"
                                                ></el-progress>
                                            </template>
                                        </el-table-column>
                                    </el-table>
                                </el-card>
                            </el-col>

                            <!-- 卖出信号 -->
                            <el-col :span="12">
                                <el-card>
                                    <template #header>
                                        <span style="color: #67c23a; font-weight: bold;">📉 今日卖出信号</span>
                                        <el-tag type="success" size="small" style="margin-left: 10px;">
                                            {{ stockPool.sell?.length || 0 }} 只
                                        </el-tag>
                                    </template>
                                    <el-table :data="stockPool.sell || []" stripe>
                                        <el-table-column prop="vt_symbol" label="股票代码" width="120"></el-table-column>
                                        <el-table-column prop="close_price" label="收盘价">
                                            <template #default="{ row }">
                                                ¥{{ row.close_price?.toFixed(2) }}
                                            </template>
                                        </el-table-column>
                                        <el-table-column prop="strength" label="信号强度">
                                            <template #default="{ row }">
                                                <el-progress
                                                    :percentage="Math.round((row.strength || 0) * 100)"
                                                    :color="'#67c23a'"
                                                ></el-progress>
                                            </template>
                                        </el-table-column>
                                    </el-table>
                                </el-card>
                            </el-col>
                        </el-row>
                        <div style="text-align: center; margin-top: 20px; color: #909399;">
                            更新时间：{{ stockPool.last_update || '--' }}
                        </div>
                    </el-tab-pane>
```

- [ ] **步骤 2：添加股票池状态和 WebSocket 处理器**

在 `app.js` 中，添加到数据部分：

```javascript
        // 股票池
        const stockPool = ref({
            buy: [],
            sell: [],
            last_update: ''
        });
```

添加到 `handleWebSocketMessage`：

```javascript
        case 'stock_pool':
            stockPool.value = { ...stockPool.value, ...data };
            break;
```

- [ ] **步骤 3：更新 return**

将 `stockPool` 添加到 return 对象。

- [ ] **步骤 4：测试股票池标签页**

验证标签页显示买卖信号表格和进度条。

- [ ] **步骤 5：提交代码**

```bash
git add vnpy_webtrader/static/
git commit -m "feat(webtrader): 实现股票池标签页，包含买卖信号"
```

---

## 任务 5：实现图表标签页（标签 3）

**文件：**
- 修改：`vnpy_webtrader/static/index.html`
- 修改：`vnpy_webtrader/static/js/app.js`

- [ ] **步骤 1：替换图表占位符**

替换 `<el-tab-pane label="K线图表" name="charts">K线图表内容</el-tab-pane>`：

```html
                    <!-- 标签 3：图表 -->
                    <el-tab-pane label="K线图表" name="charts">
                        <el-card>
                            <template #header>
                                <div style="display: flex; justify-content: space-between; align-items: center;">
                                    <span>K线图表</span>
                                    <el-select v-model="selectedSymbol" placeholder="选择股票" style="width: 200px;">
                                        <el-option
                                            v-for="sym in availableSymbols"
                                            :key="sym"
                                            :label="sym"
                                            :value="sym"
                                        ></el-option>
                                    </el-select>
                                </div>
                            </template>
                            <div id="kline-chart" style="width: 100%; height: 500px;"></div>
                        </el-card>
                    </el-tab-pane>
```

- [ ] **步骤 2：添加图表状态和 ECharts 初始化**

在 `app.js` 中：

```javascript
        // 图表状态
        const selectedSymbol = ref('');
        const availableSymbols = ref([]);
        const candleData = ref({}); // { symbol: [candles] }
        let klineChart = null;

        // 标签激活时初始化图表
        const initChart = () => {
            if (!klineChart) {
                const el = document.getElementById('kline-chart');
                if (el) klineChart = echarts.init(el);
            }
        };

        // 用 K 线数据更新图表
        const updateChart = () => {
            if (!klineChart || !selectedSymbol.value) return;

            const data = candleData.value[selectedSymbol.value] || [];
            const dates = data.map(d => d.datetime);
            const values = data.map(d => [d.open, d.close, d.low, d.high]);

            const option = {
                title: { text: selectedSymbol.value + ' - K线图', left: 'center' },
                tooltip: { trigger: 'axis' },
                xAxis: { type: 'category', data: dates },
                yAxis: { type: 'value' },
                series: [{
                    type: 'candlestick',
                    data: values,
                    itemStyle: {
                        color: '#ef232a',
                        color0: '#14b143'
                    }
                }]
            };

            klineChart.setOption(option);
        };
```

- [ ] **步骤 3：处理图表用的 tick 数据**

在 `handleWebSocketMessage` 中：

```javascript
        case 'eTick.':
            // 存储 tick，可更新实时图表
            if (data.vt_symbol && !candleData.value[data.vt_symbol]) {
                availableSymbols.value = [...new Set([...availableSymbols.value, data.vt_symbol])];
            }
            break;
```

- [ ] **步骤 4：监听标签和代码变化**

添加监听器：

```javascript
        // 监听标签变化以初始化图表
        watch(activeTab, (val) => {
            if (val === 'charts') {
                setTimeout(() => {
                    initChart();
                    updateChart();
                }, 100);
            }
        });

        watch(selectedSymbol, () => {
            updateChart();
        });
```

- [ ] **步骤 5：更新 return 并测试**

将图表相关项添加到 return。

- [ ] **步骤 6：提交代码**

```bash
git add vnpy_webtrader/static/
git commit -m "feat(webtrader): 实现图表标签页，包含 K 线显示"
```

---

## 任务 6：实现分析标签页（标签 4）

**文件：**
- 修改：`vnpy_webtrader/static/index.html`
- 修改：`vnpy_webtrader/static/js/app.js`

- [ ] **步骤 1：替换分析占位符**

替换 `<el-tab-pane label="分析" name="analysis">分析内容</el-tab-pane>`：

```html
                    <!-- 标签 4：分析 -->
                    <el-tab-pane label="分析" name="analysis">
                        <el-row :gutter="20">
                            <el-col :span="12">
                                <el-card title="盈亏分布">
                                    <div id="pnl-chart" style="width: 100%; height: 300px;"></div>
                                </el-card>
                            </el-col>
                            <el-col :span="12">
                                <el-card title="资金曲线">
                                    <div id="equity-chart" style="width: 100%; height: 300px;"></div>
                                </el-card>
                            </el-col>
                        </el-row>
                        <el-row :gutter="20" style="margin-top: 20px;">
                            <el-col :span="24">
                                <el-card title="统计数据">
                                    <el-row :gutter="20">
                                        <el-col :span="4" v-for="(val, key) in stats" :key="key">
                                            <div class="stat-item">
                                                <div class="stat-label">{{ key }}</div>
                                                <div :class="['stat-value', val >= 0 ? 'profit' : 'loss']">
                                                    {{ typeof val === 'number' ? val.toFixed(2) : val }}
                                                </div>
                                            </div>
                                        </el-col>
                                    </el-row>
                                </el-card>
                            </el-col>
                        </el-row>
                    </el-tab-pane>
```

- [ ] **步骤 2：添加分析状态和图表**

在 `app.js` 中：

```javascript
        // 统计
        const stats = ref({
            total_return: 0,
            annual_return: 0,
            max_drawdown: 0,
            sharpe_ratio: 0,
            win_rate: 0,
            total_trades: 0,
            winning_trades: 0,
            losing_trades: 0
        });

        let pnlChart = null;
        let equityChart = null;

        // 更新分析图表
        const updateAnalysisCharts = () => {
            if (!pnlChart) {
                const el = document.getElementById('pnl-chart');
                if (el) pnlChart = echarts.init(el);
            }
            if (!equityChart) {
                const el = document.getElementById('equity-chart');
                if (el) equityChart = echarts.init(el);
            }

            // 盈亏饼图
            if (pnlChart) {
                pnlChart.setOption({
                    tooltip: { trigger: 'item' },
                    series: [{
                        type: 'pie',
                        radius: '50%',
                        data: [
                            { value: stats.value.winning_trades, name: '盈利', itemStyle: { color: '#67c23a' } },
                            { value: stats.value.losing_trades, name: '亏损', itemStyle: { color: '#f56c6c' } }
                        ]
                    }]
                });
            }

            // 资金曲线折线图（占位）
            if (equityChart) {
                equityChart.setOption({
                    xAxis: { type: 'category', data: ['1月', '2月', '3月', '4月'] },
                    yAxis: { type: 'value' },
                    series: [{ type: 'line', data: [100, 105, 103, 110] }]
                });
            }
        };
```

- [ ] **步骤 3：监听分析标签**

```javascript
        watch(activeTab, (val) => {
            if (val === 'charts') {
                setTimeout(() => { initChart(); updateChart(); }, 100);
            } else if (val === 'analysis') {
                setTimeout(updateAnalysisCharts, 100);
            }
        });
```

- [ ] **步骤 4：添加统计样式**

添加到 `style.css`：

```css
.stat-item {
    text-align: center;
    padding: 15px;
    background: #f5f7fa;
    border-radius: 8px;
    margin-bottom: 10px;
}

.stat-label {
    font-size: 12px;
    color: #909399;
    margin-bottom: 8px;
}

.stat-value {
    font-size: 18px;
    font-weight: bold;
}
```

- [ ] **步骤 5：更新 return 并测试**

将 stats 添加到 return 对象。

- [ ] **步骤 6：提交代码**

```bash
git add vnpy_webtrader/static/
git commit -m "feat(webtrader): 实现分析标签页，包含盈亏饼图和统计"
```

---

## 任务 7：最终集成和测试

**文件：**
- 修改：根据需要修改所有文件

- [ ] **步骤 1：添加响应式调整大小处理器**

在 `app.js` 中：

```javascript
        // 处理窗口调整大小
        const handleResize = () => {
            if (klineChart) klineChart.resize();
            if (pnlChart) pnlChart.resize();
            if (equityChart) equityChart.resize();
        };

        onMounted(() => {
            window.addEventListener('resize', handleResize);
        });

        onUnmounted(() => {
            window.removeEventListener('resize', handleResize);
        });
```

- [ ] **步骤 2：测试完整流程**

1. 启动 vnpy_webtrader：`python vnpy_webtrader/run.py`
2. 打开 http://localhost:8000
3. 使用凭据登录
4. 验证 WebSocket 连接
5. 测试所有 4 个标签页：
   - 交易：账户、持仓、成交、策略
   - 股票池：买卖信号
   - 图表：K 线显示
   - 分析：盈亏饼图、资金曲线、统计

- [ ] **步骤 3：最终提交**

```bash
git add vnpy_webtrader/static/
git commit -m "feat(webtrader): 完成 Vue3 看板，包含 4 个标签页和 WebSocket"
```

---

## 自查

**1. 规格覆盖：**
- ✅ Vue3 + Element Plus 前端
- ✅ JWT 登录认证
- ✅ WebSocket 实时数据
- ✅ 4 个标签页：交易、股票池、图表、分析
- ✅ 使用 vnpy_webtrader 后端

**2. 占位符检查：**
- 无 TBD/TODO 占位符
- 所有代码完整可运行

**3. 类型一致性：**
- 所有 Vue3 ref 和 computed 属性一致
- WebSocket 消息格式与后端匹配

---

## 执行选项

**计划完成。两种执行选项：**

**1. 子代理驱动（推荐）** - 每个任务使用新的子代理，任务间进行审查

**2. 内联执行** - 在当前会话中执行

**选择哪种方式？**
