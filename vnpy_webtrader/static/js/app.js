const { createApp, ref, reactive, computed, watch } = Vue;

const app = createApp({
    setup() {
        const isLoggedIn = ref(false);
        const token = ref('');
        const loginLoading = ref(false);
        const loginError = ref('');
        const UserIcon = shallowRef(ElementPlusIconsVue.User);
        const LockIcon = shallowRef(ElementPlusIconsVue.Lock);

        // 登录表单
        const loginForm = reactive({
            username: '',
            password: ''
        });

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

        // UI 状态
        const activeTab = ref('trading');

        // 策略
        const strategies = ref([
            { name: 'XGBExtremaLive', running: true }
        ]);

        // 股票池
        const stockPool = ref({
            buy: [],
            sell: [],
            last_update: ''
        });

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

        // 计算属性
        const positionValue = computed(() => {
            return positions.value.reduce((sum, p) => sum + (p.volume * (p.last_price || p.price || 0)), 0);
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

                localStorage.setItem('vnpy_token', token.value);
                connectWebSocket();

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
                connectWebSocket();
            }
        };

        // 退出登录
        const logout = () => {
            localStorage.removeItem('vnpy_token');
            if (ws.value) {
                ws.value.close();
                ws.value = null;
            }
            token.value = '';
            isLoggedIn.value = false;
            wsConnected.value = false;
            loginForm.username = '';
            loginForm.password = '';
            loginError.value = '';
        };

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
                case 'stock_pool':
                    stockPool.value = { ...stockPool.value, ...data };
                    break;
                case 'eTick.':
                    // 存储 tick，可更新实时图表
                    if (data.vt_symbol && !candleData.value[data.vt_symbol]) {
                        availableSymbols.value = [...new Set([...availableSymbols.value, data.vt_symbol])];
                    }
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

        // 格式化辅助函数
        const formatMoney = (val) => {
            if (val === undefined || val === null) return '¥0.00';
            return '¥' + Number(val).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
        };

        // 策略开关
        const toggleStrategy = (s) => {
            console.log('切换策略：', s.name, s.running);
        };

        // 初始化
        checkStoredToken();

        return {
            isLoggedIn,
            token,
            loginForm,
            loginLoading,
            loginError,
            handleLogin,
            logout,
            UserIcon,
            LockIcon,
            wsConnected,
            wsStatus,
            account,
            positions,
            trades,
            orders,
            lastUpdate,
            activeTab,
            strategies,
            stockPool,
            selectedSymbol,
            availableSymbols,
            positionValue,
            formatMoney,
            toggleStrategy
        };
    }
});

app.use(ElementPlus);
for (const [key, component] of Object.entries(ElementPlusIconsVue)) {
    app.component(key, component);
}
app.mount('#app');
