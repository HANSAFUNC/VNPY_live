/**
 * VNPY Web Dashboard - Vue3 Application
 */

const { createApp, ref, computed, watch, onMounted, onUnmounted } = Vue;

const app = createApp({
    setup() {
        // ==================== 响应式数据 ====================
        const ws = ref(null);
        const wsConnected = ref(false);
        const lastUpdate = ref('--');
        const reconnectTimer = ref(null);

        // Tab 相关
        const activeTab = ref('trading');
        const selectedSymbol = ref('');
        const availableSymbols = ref([]);

        // 账户数据
        const account = ref({
            balance: 0,
            available: 0,
            frozen: 0
        });

        // 持仓数据
        const positions = ref([]);

        // 成交数据
        const trades = ref([]);

        // 策略数据
        const strategies = ref([
            { name: 'XGBExtremaLive', running: true }
        ]);

        // 信号数据
        const signals = ref([]);

        // 股票池
        const stockPool = ref({
            buy_stocks: [],
            sell_stocks: [],
            last_update: ''
        });

        // 统计数据
        const stats = ref({
            total_return: 0,
            annual_return: 0,
            max_drawdown: 0,
            sharpe_ratio: 0,
            win_rate: 0,
            profit_factor: 0,
            total_trades: 0,
            winning_trades: 0,
            losing_trades: 0,
            avg_profit: 0,
            avg_loss: 0
        });

        // 图表实例
        let klineChart = null;
        let pnlChart = null;
        let equityChart = null;

        // 当日盈亏
        const dailyPnl = computed(() => {
            return positions.value.reduce((sum, pos) => sum + (pos.pnl || 0), 0);
        });

        // 持仓市值
        const positionValue = computed(() => {
            return positions.value.reduce((sum, pos) => {
                return sum + (pos.volume || 0) * (pos.last_price || pos.price || 0);
            }, 0);
        });

        // 盈亏样式类
        const pnlClass = computed(() => {
            return dailyPnl.value >= 0 ? 'profit' : 'loss';
        });

        // WebSocket 状态
        const wsStatus = computed(() => {
            if (wsConnected.value) {
                return { type: 'success', text: '已连接' };
            } else {
                return { type: 'danger', text: '未连接' };
            }
        });

        // ==================== 方法 ====================

        // 连接 WebSocket
        const connectWebSocket = () => {
            const wsUrl = `ws://${window.location.host}/ws`;
            console.log('Connecting to:', wsUrl);

            ws.value = new WebSocket(wsUrl);

            ws.value.onopen = () => {
                console.log('WebSocket connected');
                wsConnected.value = true;
                clearTimeout(reconnectTimer.value);
            };

            ws.value.onmessage = (event) => {
                const message = JSON.parse(event.data);
                handleMessage(message);
            };

            ws.value.onclose = () => {
                console.log('WebSocket disconnected');
                wsConnected.value = false;
                reconnectTimer.value = setTimeout(() => {
                    console.log('Reconnecting...');
                    connectWebSocket();
                }, 5000);
            };

            ws.value.onerror = (error) => {
                console.error('WebSocket error:', error);
            };
        };

        // 处理消息
        const handleMessage = (message) => {
            const { type, data } = message;

            switch (type) {
                case 'account':
                    if (data) {
                        account.value = { ...account.value, ...data };
                    }
                    lastUpdate.value = new Date().toLocaleTimeString();
                    break;

                case 'position':
                    // 更新单个持仓
                    if (data && data.vt_symbol) {
                        const idx = positions.value.findIndex(p => p.vt_symbol === data.vt_symbol);
                        if (idx >= 0) {
                            positions.value[idx] = { ...positions.value[idx], ...data };
                        } else {
                            positions.value.push(data);
                        }
                    }
                    lastUpdate.value = new Date().toLocaleTimeString();
                    break;

                case 'positions':
                    // 全量更新持仓
                    if (Array.isArray(data)) {
                        positions.value = data;
                    }
                    lastUpdate.value = new Date().toLocaleTimeString();
                    break;

                case 'trade':
                    // 新增成交
                    if (data) {
                        trades.value.unshift(data);
                        if (trades.value.length > 100) {
                            trades.value = trades.value.slice(0, 100);
                        }
                    }
                    lastUpdate.value = new Date().toLocaleTimeString();
                    break;

                case 'trades':
                    // 全量更新成交
                    if (Array.isArray(data)) {
                        trades.value = data;
                    }
                    lastUpdate.value = new Date().toLocaleTimeString();
                    break;

                case 'stock_pool':
                    // 更新股票池
                    if (data) {
                        stockPool.value = data;
                    }
                    break;

                case 'init':
                case 'update':
                    // 全量更新
                    if (data.account) {
                        account.value = data.account;
                    }
                    if (data.positions) {
                        positions.value = data.positions;
                    }
                    if (data.trades) {
                        trades.value = data.trades;
                    }
                    if (data.strategies) {
                        strategies.value = data.strategies;
                    }
                    if (data.signals) {
                        signals.value = data.signals;
                    }
                    if (data.stock_pool) {
                        stockPool.value = data.stock_pool;
                    }
                    if (data.stats) {
                        stats.value = data.stats;
                    }
                    lastUpdate.value = new Date().toLocaleTimeString();
                    break;

                default:
                    console.log('Unknown message type:', type);
            }
        };

        // 切换策略
        const toggleStrategy = (strategy) => {
            ElMessage.success(`${strategy.name} ${strategy.running ? '启动' : '停止'}`);
        };

        // 刷新数据
        const refreshData = () => {
            ElMessage.success('数据已刷新');
        };

        // 格式化金额
        const formatMoney = (value) => {
            if (value === undefined || value === null) return '¥0.00';
            return '¥' + Number(value).toLocaleString('zh-CN', {
                minimumFractionDigits: 2,
                maximumFractionDigits: 2
            });
        };

        // 格式化成交量
        const formatVolume = (volume) => {
            if (!volume) return '--';
            if (volume >= 10000) {
                return (volume / 10000).toFixed(2) + '万';
            }
            return volume.toString();
        };

        // 初始化图表
        const initCharts = () => {
            if (!klineChart) {
                const el = document.getElementById('kline-chart');
                if (el) klineChart = echarts.init(el);
            }
            if (!pnlChart) {
                const el = document.getElementById('pnl-chart');
                if (el) pnlChart = echarts.init(el);
            }
            if (!equityChart) {
                const el = document.getElementById('equity-chart');
                if (el) equityChart = echarts.init(el);
            }
        };

        // 更新图表
        const updateCharts = () => {
            initCharts();

            // 盈亏分布饼图
            if (pnlChart) {
                const pnlOption = {
                    tooltip: { trigger: 'item' },
                    legend: { orient: 'vertical', left: 'left' },
                    series: [
                        {
                            name: '交易分布',
                            type: 'pie',
                            radius: '50%',
                            data: [
                                { value: stats.value.winning_trades || 0, name: '盈利', itemStyle: { color: '#67c23a' } },
                                { value: stats.value.losing_trades || 0, name: '亏损', itemStyle: { color: '#f56c6c' } }
                            ]
                        }
                    ]
                };
                pnlChart.setOption(pnlOption);
            }

            // 资金曲线
            if (equityChart) {
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
                equityChart.setOption(equityOption);
            }
        };

        // ==================== Watchers ====================

        watch(activeTab, (newVal) => {
            if (newVal === 'charts' || newVal === 'analysis') {
                setTimeout(() => {
                    initCharts();
                    updateCharts();
                }, 100);
            }
        });

        // ==================== 生命周期 ====================

        const handleResize = () => {
            if (klineChart) klineChart.resize();
            if (pnlChart) pnlChart.resize();
            if (equityChart) equityChart.resize();
        };

        onMounted(() => {
            connectWebSocket();

            // 监听窗口大小改变
            window.addEventListener('resize', handleResize);

            // 定期发送心跳
            setInterval(() => {
                if (wsConnected.value && ws.value) {
                    ws.value.send(JSON.stringify({ type: 'ping' }));
                }
            }, 30000);
        });

        onUnmounted(() => {
            if (ws.value) {
                ws.value.close();
            }
            clearTimeout(reconnectTimer.value);
            window.removeEventListener('resize', handleResize);

            // 销毁图表实例
            if (klineChart) { klineChart.dispose(); klineChart = null; }
            if (pnlChart) { pnlChart.dispose(); pnlChart = null; }
            if (equityChart) { equityChart.dispose(); equityChart = null; }
        });

        // ==================== 返回 ====================
        return {
            // 数据
            account,
            positions,
            trades,
            strategies,
            signals,
            stockPool,
            stats,
            lastUpdate,
            wsStatus,
            dailyPnl,
            positionValue,
            pnlClass,

            // Tab 相关
            activeTab,
            selectedSymbol,
            availableSymbols,

            // 方法
            toggleStrategy,
            refreshData,
            formatMoney,
            formatVolume
        };
    }
});

// 使用 Element Plus
app.use(ElementPlus);

// 挂载
app.mount('#app');
