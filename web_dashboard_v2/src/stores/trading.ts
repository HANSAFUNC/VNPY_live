import { ref, computed } from 'vue';
import { defineStore } from 'pinia';
import { tradingApi, wsManager } from '@/api';
import type {
  AccountData,
  PositionData,
  OrderData,
  TradeData,
  TradingStats,
} from '@/types';

export const useTradingStore = defineStore('trading', () => {
  // State
  const account = ref<AccountData | null>(null);
  const positions = ref<PositionData[]>([]);
  const orders = ref<OrderData[]>([]);
  const trades = ref<TradeData[]>([]);
  const stats = ref<TradingStats>({
    total_return: 0,
    annual_return: 0,
    max_drawdown: 0,
    sharpe_ratio: 0,
    win_rate: 0,
    total_trades: 0,
    winning_trades: 0,
    losing_trades: 0,
  });

  // Getters
  const positionValue = computed(() =>
    positions.value.reduce(
      (sum, p) => sum + p.volume * (p.last_price ?? p.price ?? 0),
      0
    )
  );

  const dailyPnl = computed(() =>
    positions.value.reduce((sum, p) => sum + (p.pnl ?? 0), 0)
  );

  const positionCount = computed(() => positions.value.length);
  const orderCount = computed(() => orders.value.length);
  const tradeCount = computed(() => trades.value.length);

  // Actions
  function clearData() {
    account.value = null;
    positions.value = [];
    orders.value = [];
    trades.value = [];
    stats.value = {
      total_return: 0,
      annual_return: 0,
      max_drawdown: 0,
      sharpe_ratio: 0,
      win_rate: 0,
      total_trades: 0,
      winning_trades: 0,
      losing_trades: 0,
    };
  }

  async function fetchAllData() {
    await Promise.all([
      fetchAccount(),
      fetchPositions(),
      fetchOrders(),
      fetchTrades(),
    ]);
  }

  async function fetchAccount() {
    const accounts = await tradingApi.getAccounts();
    account.value = accounts[0] ?? null;
  }

  async function fetchPositions() {
    positions.value = await tradingApi.getPositions();
  }

  async function fetchOrders() {
    orders.value = await tradingApi.getOrders();
  }

  async function fetchTrades() {
    trades.value = await tradingApi.getTrades();
  }

  // WebSocket handlers
  function handleAccountUpdate(data: Partial<AccountData>) {
    if (account.value) {
      Object.assign(account.value, data);
    }
  }

  function handlePositionUpdate(data: PositionData) {
    const index = positions.value.findIndex((p) => p.vt_symbol === data.vt_symbol);
    if (index >= 0) {
      positions.value[index] = { ...positions.value[index], ...data };
    } else {
      positions.value.push(data);
    }
  }

  function handleTradeUpdate(data: TradeData) {
    trades.value.unshift(data);
    if (trades.value.length > 100) {
      trades.value = trades.value.slice(0, 100);
    }
  }

  function handleOrderUpdate(data: OrderData) {
    const index = orders.value.findIndex((o) => o.vt_orderid === data.vt_orderid);
    if (index >= 0) {
      orders.value[index] = { ...orders.value[index], ...data };
    } else {
      orders.value.push(data);
    }
  }

  // Setup WebSocket listeners
  function setupWebSocketListeners() {
    wsManager.on<Partial<AccountData>>('eAccount.', handleAccountUpdate);
    wsManager.on<PositionData>('ePosition.', handlePositionUpdate);
    wsManager.on<TradeData>('eTrade.', handleTradeUpdate);
    wsManager.on<OrderData>('eOrder.', handleOrderUpdate);
  }

  return {
    account,
    positions,
    orders,
    trades,
    stats,
    positionValue,
    dailyPnl,
    positionCount,
    orderCount,
    tradeCount,
    clearData,
    fetchAllData,
    fetchAccount,
    fetchPositions,
    fetchOrders,
    fetchTrades,
    setupWebSocketListeners,
  };
});
