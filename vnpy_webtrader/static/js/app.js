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
