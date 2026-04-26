import { ref, computed } from 'vue';
import { defineStore } from 'pinia';
import { useBotStore } from './bot';
import { DEFAULT_DASHBOARD_LAYOUT, STORAGE_KEYS } from '@/constants';
import type { GridItem } from '@/types';
import { getItem, setItem } from '@/utils/storage';

export const useUIStore = defineStore(
  'ui',
  () => {
    // State
    const sidebarCollapsed = ref(false);
    const theme = ref<'light' | 'dark'>('light');
    const layout = ref<GridItem[]>(DEFAULT_DASHBOARD_LAYOUT);
    const activeTab = ref('dashboard');

    // Getters
    const isDark = computed(() => theme.value === 'dark');

    const layoutStorageKey = computed(() => {
      const botStore = useBotStore();
      return `${STORAGE_KEYS.LAYOUT_PREFIX}${botStore.activeBotId ?? 'default'}`;
    });

    // Actions
    function toggleSidebar() {
      sidebarCollapsed.value = !sidebarCollapsed.value;
    }

    function setTheme(newTheme: 'light' | 'dark') {
      theme.value = newTheme;
      document.documentElement.classList.toggle('dark', newTheme === 'dark');
    }

    function toggleTheme() {
      setTheme(theme.value === 'light' ? 'dark' : 'light');
    }

    function updateLayout(newLayout: GridItem[]) {
      layout.value = newLayout;
      setItem(layoutStorageKey.value, newLayout);
    }

    function loadLayout() {
      const saved = getItem<GridItem[]>(layoutStorageKey.value, DEFAULT_DASHBOARD_LAYOUT);
      layout.value = saved;
    }

    function resetLayout() {
      layout.value = DEFAULT_DASHBOARD_LAYOUT;
      setItem(layoutStorageKey.value, DEFAULT_DASHBOARD_LAYOUT);
    }

    function setActiveTab(tab: string) {
      activeTab.value = tab;
    }

    return {
      sidebarCollapsed,
      theme,
      layout,
      activeTab,
      isDark,
      toggleSidebar,
      setTheme,
      toggleTheme,
      updateLayout,
      loadLayout,
      resetLayout,
      setActiveTab,
    };
  },
  {
    persist: {
      pick: ['sidebarCollapsed', 'theme'],
    },
  }
);
