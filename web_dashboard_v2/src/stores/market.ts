import { ref } from 'vue';
import { defineStore } from 'pinia';
import type { TickData, KlineData } from '@/types';

export const useMarketStore = defineStore('market', () => {
  const ticks = ref<Record<string, TickData>>({});
  const klines = ref<Record<string, KlineData[]>>({});

  function clearData() {
    ticks.value = {};
    klines.value = {};
  }

  async function fetchContracts() {
    // TODO: 在 Task 8 中实现
  }

  return {
    ticks,
    klines,
    clearData,
    fetchContracts,
  };
});
