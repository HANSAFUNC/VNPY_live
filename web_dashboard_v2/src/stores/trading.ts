import { ref } from 'vue';
import { defineStore } from 'pinia';
import type { AccountData, PositionData, OrderData, TradeData } from '@/types';

export const useTradingStore = defineStore('trading', () => {
  const account = ref<AccountData | null>(null);
  const positions = ref<PositionData[]>([]);
  const orders = ref<OrderData[]>([]);
  const trades = ref<TradeData[]>([]);

  function clearData() {
    account.value = null;
    positions.value = [];
    orders.value = [];
    trades.value = [];
  }

  async function fetchAllData() {
    // TODO: 在 Task 7 中实现
  }

  return {
    account,
    positions,
    orders,
    trades,
    clearData,
    fetchAllData,
  };
});
