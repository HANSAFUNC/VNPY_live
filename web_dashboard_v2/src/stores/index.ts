import { createPinia } from 'pinia';
import piniaPluginPersistedstate from 'pinia-plugin-persistedstate';

export const pinia = createPinia();
pinia.use(piniaPluginPersistedstate);

export * from './auth';
export * from './bot';
export * from './trading';
export * from './market';
export * from './logs';
// TODO: Task 10 中启用
// export * from './ui';
