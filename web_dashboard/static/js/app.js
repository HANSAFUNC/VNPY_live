const { createApp, ref, reactive, computed, watch, onMounted, onUnmounted } = Vue;

const app = createApp({
    setup() {
        const isLoggedIn = ref(false);
        const token = ref('');
        const loginLoading = ref(false);
        const loginError = ref('');
        // 图标用简单字符代替
        const UserIcon = 'User';
        const LockIcon = 'Lock';

        // 登录表单
        const loginForm = reactive({
            username: 'admin',
            password: 'admin'
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
        const activeTab = ref('positions');

        // 交易模式
        const tradingMode = ref({
            mode: 'paper',
            mode_text: '模拟盘',
            engine: 'unknown'
        });

        // 获取交易模式
        const fetchTradingMode = async () => {
            try {
                const response = await fetch('/trading_mode', {
                    headers: { 'Authorization': `Bearer ${token.value}` }
                });
                if (response.ok) {
                    const data = await response.json();
                    tradingMode.value = data;
                }
            } catch (error) {
                console.error('获取交易模式失败:', error);
            }
        };

        // 获取基础数据
        const fetchData = async () => {
            try {
                // 获取账户
                const accountRes = await fetch('/account', {
                    headers: { 'Authorization': `Bearer ${token.value}` }
                });
                if (accountRes.ok) {
                    const accounts = await accountRes.json();
                    if (accounts.length > 0) {
                        account.value = accounts[0];
                    }
                }

                // 获取持仓
                const posRes = await fetch('/position', {
                    headers: { 'Authorization': `Bearer ${token.value}` }
                });
                if (posRes.ok) {
                    positions.value = await posRes.json();
                }

                // 获取成交
                const tradeRes = await fetch('/trade', {
                    headers: { 'Authorization': `Bearer ${token.value}` }
                });
                if (tradeRes.ok) {
                    trades.value = await tradeRes.json();
                }

                // 获取委托
                const orderRes = await fetch('/order', {
                    headers: { 'Authorization': `Bearer ${token.value}` }
                });
                if (orderRes.ok) {
                    orders.value = await orderRes.json();
                }

                // 更新时间
                lastUpdate.value = new Date().toLocaleString('zh-CN');
            } catch (error) {
                console.error('获取数据失败:', error);
            }
        };

        // 获取K线数据（API模式）
        const fetchKlineData = async (symbol, period = '1d') => {
            if (!symbol) return [];
            try {
                const response = await fetch(`/kline/${symbol}?period=${period}`, {
                    headers: { 'Authorization': `Bearer ${token.value}` }
                });
                if (response.ok) {
                    const data = await response.json();
                    candleData.value[symbol] = data;
                    if (!availableSymbols.value.includes(symbol)) {
                        availableSymbols.value.push(symbol);
                    }
                    updateChart();
                    return data;
                }
            } catch (error) {
                console.error('获取K线数据失败:', error);
            }
            return [];
        };

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

        // 买卖信号
        const signals = ref([]);

        // 图表状态
        const selectedSymbol = ref('');
        const availableSymbols = ref([]);
        const candleData = ref({}); // { symbol: [candles] }
        let klineChart = null;

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

        // 分析图表
        let pnlChart = null;
        let equityChart = null;

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

        // 监听标签变化以初始化图表
        watch(activeTab, (val) => {
            if (val === 'charts') {
                setTimeout(() => { initChart(); updateChart(); }, 100);
            } else if (val === 'analysis') {
                setTimeout(updateAnalysisCharts, 100);
            }
        });

        watch(selectedSymbol, (newVal) => {
            if (newVal) {
                // API 获取历史K线
                fetchKlineData(newVal);
            }
            updateChart();
        });

        // 计算属性
        const positionValue = computed(() => {
            return positions.value.reduce((sum, p) => sum + (p.volume * (p.last_price || p.price || 0)), 0);
        });

        const dailyPnl = computed(() => {
            return positions.value.reduce((sum, p) => sum + (p.pnl || 0), 0);
        });

        const pnlClass = computed(() => {
            return dailyPnl.value >= 0 ? 'profit' : 'loss';
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
                fetchTradingMode(); // 获取交易模式
                fetchData(); // 获取初始数据

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
                fetchTradingMode();
                fetchData();
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
                case 'eKline.':
                    // K线实时推送更新
                    if (data.vt_symbol) {
                        if (!candleData.value[data.vt_symbol]) {
                            candleData.value[data.vt_symbol] = [];
                        }
                        const candles = candleData.value[data.vt_symbol];
                        const lastCandle = candles[candles.length - 1];
                        if (lastCandle && lastCandle.datetime === data.datetime) {
                            candles[candles.length - 1] = data;
                        } else {
                            candles.push(data);
                            if (candles.length > 500) candles.shift();
                        }
                        if (selectedSymbol.value === data.vt_symbol) {
                            updateChart();
                        }
                    }
                    break;
                case 'eSignal.':
                    // 交易信号
                    if (data.signal === 1 || data.signal === 'buy') {
                        stockPool.value.buy.unshift(data);
                    } else if (data.signal === -1 || data.signal === 'sell') {
                        stockPool.value.sell.unshift(data);
                    }
                    signals.value.unshift(data);
                    if (signals.value.length > 50) signals.value = signals.value.slice(0, 50);
                    break;
                case 'eStrategy.':
                    // 策略状态更新
                    if (data.name) {
                        const idx = strategies.value.findIndex(s => s.name === data.name);
                        if (idx >= 0) {
                            strategies.value[idx] = { ...strategies.value[idx], ...data };
                        }
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

        // 处理窗口调整大小
        const handleResize = () => {
            if (klineChart) klineChart.resize();
            if (pnlChart) pnlChart.resize();
            if (equityChart) equityChart.resize();
        };

        onMounted(() => {
            window.addEventListener('resize', handleResize);
            // 登录后定时刷新数据
            if (isLoggedIn.value) {
                setInterval(fetchData, 5000);
            }
        });

        onUnmounted(() => {
            window.removeEventListener('resize', handleResize);
        });

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
            tradingMode,
            account,
            positions,
            trades,
            orders,
            lastUpdate,
            activeTab,
            strategies,
            stockPool,
            signals,
            selectedSymbol,
            availableSymbols,
            stats,
            positionValue,
            dailyPnl,
            pnlClass,
            formatMoney,
            toggleStrategy,
            fetchKlineData
        };
    }
});

app.use(ElementPlus);
app.mount('#app');
