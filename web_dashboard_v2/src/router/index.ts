import { createRouter, createWebHistory } from 'vue-router';
import { useAuthStore } from '@/stores';

// 路由配置
declare module 'vue-router' {
  interface RouteMeta {
    requiresAuth?: boolean;
    title?: string;
  }
}

const routes = [
  {
    path: '/login',
    name: 'Login',
    component: () => import('@/views/LoginView.vue'),
    meta: { requiresAuth: false, title: '登录' },
  },
  {
    path: '/',
    name: 'Layout',
    component: () => import('@/layouts/AppLayout.vue'),
    meta: { requiresAuth: true },
    children: [
      {
        path: '',
        redirect: '/dashboard',
      },
      {
        path: 'dashboard',
        name: 'Dashboard',
        component: () => import('@/views/DashboardView.vue'),
        meta: { requiresAuth: true, title: '总览' },
      },
      {
        path: 'trade',
        name: 'Trade',
        component: () => import('@/views/TradeView.vue'),
        meta: { requiresAuth: true, title: '交易' },
      },
      {
        path: 'logs',
        name: 'Logs',
        component: () => import('@/views/LogsView.vue'),
        meta: { requiresAuth: true, title: '日志' },
      },
      {
        path: 'lab',
        name: 'Lab',
        component: () => import('@/views/LabView.vue'),
        meta: { requiresAuth: true, title: '实验室' },
      },
    ],
  },
  {
    path: '/:pathMatch(.*)*',
    redirect: '/',
  },
];

const router = createRouter({
  history: createWebHistory(),
  routes,
});

// 全局前置守卫
router.beforeEach((to, _from, next) => {
  const authStore = useAuthStore();

  // 设置页面标题
  if (to.meta.title) {
    document.title = `${to.meta.title} - VNPY Pro`;
  }

  // 检查是否需要认证
  const requiresAuth = to.meta.requiresAuth !== false;

  if (requiresAuth && !authStore.isLoggedIn) {
    // 需要认证但未登录，跳转到登录页
    next({
      path: '/login',
      query: { redirect: to.fullPath },
    });
  } else if (to.path === '/login' && authStore.isLoggedIn) {
    // 已登录但访问登录页，跳转到首页
    next('/dashboard');
  } else {
    next();
  }
});

export default router;
