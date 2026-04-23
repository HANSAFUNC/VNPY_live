/**
 * VNPY Web Dashboard - Vue3 Application
 */

const { createApp, ref, computed, onMounted, onUnmounted } = Vue;

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
                    lastUpdate.value = new Date().toLocaleTimeString();
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

        // 格式化金额
        const formatMoney = (value) => {
            if (value === undefined || value === null) return '¥0.00';
            return '¥' + value.toLocaleString('zh-CN', {
                minimumFractionDigits: 2,
                maximumFractionDigits: 2
            });
        };

        // ==================== 生命周期 ====================

        onMounted(() => {
            connectWebSocket();

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
