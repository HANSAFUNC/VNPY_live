const { createApp, ref, reactive, computed } = Vue;

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

                // 登录后连接 WebSocket
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

        // 初始化
        checkStoredToken();

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
    }
});

app.use(ElementPlus);
app.mount('#app');
