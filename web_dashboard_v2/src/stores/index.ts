import { createPinia } from 'pinia';
import piniaPluginPersistedstate from 'pinia-plugin-persistedstate';

export const pinia = createPinia();
pinia.use(piniaPluginPersistedstate);

// 只导出已实现的 auth store
export * from './auth';
// TODO: 后续任务实现后启用
// export * from './bot';
// export * from './trading';
// export * from './market';
// export * from './logs';
// export * from './ui';
