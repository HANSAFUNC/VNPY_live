import { createApp } from 'vue';
import ElementPlus from 'element-plus';
import * as ElementPlusIconsVue from '@element-plus/icons-vue';
import 'element-plus/dist/index.css';

import App from './App.vue';
import router from './router';
import { pinia } from './stores';
import { useAuthStore, useTradingStore, useMarketStore } from './stores';
import { wsManager } from './api';

import '@/assets/styles/global.scss';

const app = createApp(App);

// 注册所有图标
for (const [key, component] of Object.entries(ElementPlusIconsVue)) {
  app.component(key, component);
}

app.use(pinia);
app.use(router);
app.use(ElementPlus);

// 初始化 WebSocket 连接（如果已登录）
const authStore = useAuthStore();
if (authStore.isLoggedIn) {
  wsManager.connect();

  // 设置 WebSocket 监听器
  const tradingStore = useTradingStore();
  const marketStore = useMarketStore();
  tradingStore.setupWebSocketListeners();
  marketStore.setupWebSocketListeners();

  // 加载初始数据
  tradingStore.fetchAllData();
  marketStore.fetchContracts();
}

app.mount('#app');
