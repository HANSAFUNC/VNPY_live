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

        // Tab 相关
        const activeTab = ref('trading');
        const selectedSymbol = ref('');
        const availableSymbols = ref([]);

        // 图表数据
        const candles = ref({});
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
        let indicatorChart = null;
        let pnlChart = null;
        let equityChart = null;

        // 当日盈亏（简化计算）
        const dailyPnl = computed(() => {
            // TODO: 从服务器获取实际当日盈亏
            return positions.value.reduce((sum, pos) => sum + pos.pnl, 0);
        });

        // 持仓市值
        const positionValue = computed(() => {
            return positions.value.reduce((sum, pos) => {
                return sum + pos.volume * pos.last_price;
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
                // 自动重连
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
                case 'init':
                case 'update':
                    // 更新看板数据
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

                    // 更新图表和统计数据
                    if (data.chart_data) {
                        candles.value = data.chart_data;
                        availableSymbols.value = Object.keys(data.chart_data);
                        if (!selectedSymbol.value && availableSymbols.value.length > 0) {
                            selectedSymbol.value = availableSymbols.value[0];
                        }
                    }
                    if (data.stats) {
                        stats.value = data.stats;
                    }

                    lastUpdate.value = new Date().toLocaleTimeString();

                    // 如果当前在图表页，更新图表
                    if (activeTab.value === 'charts') {
                        updateKlineChart();
                    } else if (activeTab.value === 'analysis') {
                        updateStatsCharts();
                    }
                    break;

                case 'trade':
                    // 实时成交通知
                    showNotification('成交', `${data.vt_symbol} ${data.direction} ${data.volume}股 @ ${data.price}`);
                    break;

                case 'notification':
                    showNotification('通知', data.message);
                    break;

                default:
                    console.log('Unknown message type:', type);
            }
        };

        // 发送消息
        const sendMessage = (message) => {
            if (ws.value && wsConnected.value) {
                ws.value.send(JSON.stringify(message));
            }
        };

        // 切换策略
        const toggleStrategy = (strategy) => {
            sendMessage({
                type: 'toggle_strategy',
                name: strategy.name,
                running: strategy.running
            });

            ElMessage.success(`${strategy.name} ${strategy.running ? '启动' : '停止'}`);
        };

        // 刷新数据
        const refreshData = () => {
            sendMessage({ type: 'get_data' });
            ElMessage.success('数据已刷新');
        };

        // 显示通知
        const showNotification = (title, message) => {
            ElNotification({
                title: title,
                message: message,
                type: 'info',
                duration: 5000
            });
        };

        // 初始化 K 线图表
        const initCharts = () => {
            if (!klineChart) {
                const el = document.getElementById('kline-chart');
                if (el) klineChart = echarts.init(el);
            }
            if (!indicatorChart) {
                const el = document.getElementById('indicator-chart');
                if (el) indicatorChart = echarts.init(el);
            }
        };

        // 更新 K 线图表
        const updateKlineChart = () => {
            if (!klineChart || !candles.value[selectedSymbol.value]) return;

            const data = candles.value[selectedSymbol.value];
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

            klineChart.setOption(option);
        };

        // 初始化统计图表
        const initStatsCharts = () => {
            if (!pnlChart) {
                const el = document.getElementById('pnl-chart');
                if (el) pnlChart = echarts.init(el);
            }
            if (!equityChart) {
                const el = document.getElementById('equity-chart');
                if (el) equityChart = echarts.init(el);
            }
        };

        // 更新统计图表
        const updateStatsCharts = () => {
            if (!stats.value) return;

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
                            { value: stats.value.winning_trades, name: '盈利', itemStyle: { color: '#67c23a' } },
                            { value: stats.value.losing_trades, name: '亏损', itemStyle: { color: '#f56c6c' } }
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

            if (pnlChart) pnlChart.setOption(pnlOption);
            if (equityChart) equityChart.setOption(equityOption);
        };

        // 格式化金额
        const formatMoney = (value) => {
            if (value === undefined || value === null) return '¥0.00';
            return '¥' + value.toLocaleString('zh-CN', {
                minimumFractionDigits: 2,
                maximumFractionDigits: 2
            });
        };

        // ==================== Watchers ====================

        watch(activeTab, (newVal) => {
            if (newVal === 'charts') {
                setTimeout(() => {
                    initCharts();
                    updateKlineChart();
                }, 100);
            } else if (newVal === 'analysis') {
                setTimeout(() => {
                    initStatsCharts();
                    updateStatsCharts();
                }, 100);
            }
        });

        watch(selectedSymbol, () => {
            if (activeTab.value === 'charts') {
                updateKlineChart();
            }
        });

        // ==================== 生命周期 ====================

        const handleResize = () => {
            if (klineChart) klineChart.resize();
            if (indicatorChart) indicatorChart.resize();
            if (pnlChart) pnlChart.resize();
            if (equityChart) equityChart.resize();
        };

        onMounted(() => {
            connectWebSocket();

            // 监听窗口大小改变
            window.addEventListener('resize', handleResize);

            // 定期发送心跳
            setInterval(() => {
                if (wsConnected.value) {
                    sendMessage({ type: 'ping' });
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
            if (indicatorChart) { indicatorChart.dispose(); indicatorChart = null; }
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
            lastUpdate,
            wsStatus,
            dailyPnl,
            positionValue,
            pnlClass,

            // Tab 相关
            activeTab,
            selectedSymbol,
            availableSymbols,
            stats,

            // 方法
            toggleStrategy,
            refreshData,
            formatMoney
        };
    }
});

// 使用 Element Plus
app.use(ElementPlus);

// 挂载
app.mount('#app');
