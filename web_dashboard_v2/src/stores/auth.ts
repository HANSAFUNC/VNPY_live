import { ref, computed } from 'vue';
import { defineStore } from 'pinia';
import { authApi, wsManager } from '@/api';
import { setToken, clearToken, getToken } from '@/utils/storage';
import type { LoginRequest } from '@/types';

export const useAuthStore = defineStore(
  'auth',
  () => {
    // State
    const token = ref<string | null>(getToken());
    const isLoggedIn = computed(() => !!token.value);

    // Actions
    async function login(credentials: LoginRequest): Promise<void> {
      const response = await authApi.login(credentials);
      token.value = response.access_token;
      setToken(response.access_token);
      wsManager.connect();
    }

    function logout(): void {
      token.value = null;
      clearToken();
      wsManager.disconnect();
    }

    return {
      token,
      isLoggedIn,
      login,
      logout,
    };
  },
  {
    persist: {
      pick: ['token'],
    },
  }
);
