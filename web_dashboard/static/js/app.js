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

        // 当日盈亏（简化计算）
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
                case 'account':
                    // 更新账户数据
                    if (data) {
                        account.value = { ...account.value, ...data };
                    }
                    lastUpdate.value = new Date().toLocaleTimeString();
                    break;

                case 'position':
                    // 更新持仓数据
                    if (data) {
                        const idx = positions.value.findIndex(p => p.vt_symbol === data.vt_symbol);
                        if (idx >= 0) {
                            positions.value[idx] = data;
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

        // ==================== Watchers ====================

        // ==================== 生命周期 ====================

        onMounted(() => {
            connectWebSocket();

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
        });

        // ==================== 返回 ====================
        return {
            // 数据
            account,
            positions,
            trades,
            strategies,
            lastUpdate,
            wsStatus,
            dailyPnl,
            positionValue,
            pnlClass,

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
