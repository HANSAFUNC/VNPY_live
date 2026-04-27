import { ref, computed } from 'vue';
import { defineStore } from 'pinia';
import { authApi, wsManager, setApiBaseUrl } from '@/api';
import { setToken, clearToken, getToken } from '@/utils/storage';
import { saveServer, generateWsUrl } from '@/utils/servers';
import type { LoginRequest, ServerConfig } from '@/types';

const STORAGE_KEY = 'vnpy_current_server';

export const useAuthStore = defineStore(
  'auth',
  () => {
    // State
    const token = ref<string | null>(getToken());
    const isLoggedIn = computed(() => !!token.value);
    const currentServer = ref<ServerConfig | null>(null);

    // 从 localStorage 恢复当前服务器
    function loadCurrentServer(): void {
      try {
        const data = localStorage.getItem(STORAGE_KEY);
        if (data) {
          currentServer.value = JSON.parse(data);
        }
      } catch {
        currentServer.value = null;
      }
    }

    // 保存当前服务器到 localStorage
    function saveCurrentServer(server: ServerConfig): void {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(server));
      currentServer.value = server;
    }

    // 应用服务器配置到 API 和 WebSocket
    function applyServerConfig(server: ServerConfig): void {
      setApiBaseUrl(server.url);
      wsManager.setUrl(server.wsUrl);
    }

    // Actions
    async function login(
      credentials: LoginRequest,
      serverUrl: string
    ): Promise<void> {
      // 1. 设置 API 地址
      setApiBaseUrl(serverUrl);

      // 2. 调用登录 API
      const response = await authApi.login(credentials);
      token.value = response.access_token;
      setToken(response.access_token);

      // 3. 生成并保存服务器配置
      const serverConfig: ServerConfig = saveServer({
        name: serverUrl,
        url: serverUrl,
        wsUrl: generateWsUrl(serverUrl),
      });

      // 4. 设为当前服务器并保存
      saveCurrentServer(serverConfig);

      // 5. 应用 WebSocket URL
      wsManager.setUrl(serverConfig.wsUrl);

      // 6. 连接 WebSocket
      wsManager.connect();
    }

    function logout(): void {
      token.value = null;
      currentServer.value = null;
      clearToken();
      localStorage.removeItem(STORAGE_KEY);
      wsManager.disconnect();
    }

    // 初始化：恢复服务器配置并连接
    function initialize(): void {
      loadCurrentServer();
      if (currentServer.value && token.value) {
        applyServerConfig(currentServer.value);
        // 延迟连接，让页面先加载完成
        setTimeout(() => {
          wsManager.connect();
        }, 100);
      }
    }

    // 清除当前服务器配置（用于切换服务器）
    function clearServerConfig(): void {
      currentServer.value = null;
      localStorage.removeItem(STORAGE_KEY);
      wsManager.disconnect();
    }

    // 切换服务器
    async function switchServer(server: ServerConfig): Promise<void> {
      // 断开当前连接
      wsManager.disconnect();

      // 应用新配置
      applyServerConfig(server);
      saveCurrentServer(server);

      // 如果已登录，重新连接
      if (token.value) {
        wsManager.connect();
      }
    }

    return {
      token,
      isLoggedIn,
      currentServer,
      login,
      logout,
      initialize,
      switchServer,
      clearServerConfig,
    };
  },
  {
    persist: {
      pick: ['token'],
    },
  }
);
