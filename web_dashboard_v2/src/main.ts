import { createApp } from 'vue';
import ElementPlus from 'element-plus';
import * as ElementPlusIconsVue from '@element-plus/icons-vue';
import 'element-plus/dist/index.css';

import App from './App.vue';
import router from './router';
import { pinia } from './stores';
import { useAuthStore, useTradingStore, useMarketStore } from './stores';

import '@/assets/styles/global.scss';

const app = createApp(App);

// 注册所有图标
for (const [key, component] of Object.entries(ElementPlusIconsVue)) {
  app.component(key, component);
}

app.use(pinia);
app.use(router);
app.use(ElementPlus);

// 初始化：恢复服务器配置和 WebSocket 连接（如果已登录）
const authStore = useAuthStore();
authStore.initialize();

if (authStore.isLoggedIn && authStore.currentServer) {
  // 确认服务器配置与当前页面一致（避免localhost/IP混乱）
  const currentHost = window.location.hostname;
  const serverHost = new URL(authStore.currentServer.url).hostname;

  // 如果配置是localhost但页面从IP访问，或反过来，提示重新登录
  const isLocalhost = (host: string) => host === 'localhost' || host === '127.0.0.1';

  if (isLocalhost(currentHost) !== isLocalhost(serverHost)) {
    console.warn('服务器配置与当前访问地址不匹配，请重新登录');
    authStore.logout();
    router.push('/login');
  } else {
    // 设置 WebSocket 监听器
    const tradingStore = useTradingStore();
    const marketStore = useMarketStore();
    tradingStore.setupWebSocketListeners();
    marketStore.setupWebSocketListeners();

    // 加载初始数据
    tradingStore.fetchAllData();
    marketStore.fetchContracts();
  }
}

app.mount('#app');
