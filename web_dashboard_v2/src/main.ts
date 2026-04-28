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

// 初始化认证状态
const authStore = useAuthStore();
authStore.initialize();

// 检查登录状态，如果已登录则设置 WebSocket
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
  }
}

// 添加全局导航守卫，确保需要认证的页面在登录后才能访问
router.beforeEach((to, _from, next) => {
  const authStore = useAuthStore();

  // 如果访问登录页且已登录，跳转到首页
  if (to.path === '/login' && authStore.isLoggedIn) {
    next('/');
    return;
  }

  // 如果需要认证但未登录，跳转到登录页
  if (to.meta.requiresAuth !== false && !authStore.isLoggedIn) {
    next('/login');
    return;
  }

  next();
});

// 延迟挂载应用，确保 Pinia 状态已恢复
// pinia-plugin-persistedstate 会在 pinia 安装后自动恢复状态
setTimeout(() => {
  app.mount('#app');
}, 0);
