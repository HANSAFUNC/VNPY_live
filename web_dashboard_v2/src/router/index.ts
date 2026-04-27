import { createRouter, createWebHistory } from 'vue-router';
import { useAuthStore } from '@/stores';

declare module 'vue-router' {
  interface RouteMeta {
    public?: boolean;
  }
}

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: '/login',
      name: 'Login',
      component: () => import('@/views/LoginView.vue'),
      meta: { public: true },
    },
    {
      path: '/',
      component: () => import('@/layouts/AppLayout.vue'),
      children: [
        {
          path: '',
          redirect: '/dashboard',
        },
        {
          path: 'dashboard',
          name: 'Dashboard',
          component: () => import('@/views/DashboardView.vue'),
        },
        {
          path: 'trade',
          name: 'Trade',
          component: () => import('@/views/TradeView.vue'),
        },
        {
          path: 'logs',
          name: 'Logs',
          component: () => import('@/views/LogsView.vue'),
        },
      ],
    },
    {
      path: '/:pathMatch(.*)*',
      redirect: '/',
    },
  ],
});

// 路由守卫
router.beforeEach((to, _from, next) => {
  const authStore = useAuthStore();

  if (to.meta.public) {
    next();
    return;
  }

  if (!authStore.isLoggedIn) {
    next('/login');
    return;
  }

  next();
});

export default router;
