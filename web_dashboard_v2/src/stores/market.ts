import { ref, computed } from 'vue';
import { defineStore } from 'pinia';
import { marketApi, wsManager } from '@/api';
import type { TickData, KlineData, Period } from '@/types';

export interface Contract {
  vt_symbol: string;
  symbol: string;
  exchange: string;
  name: string;
  size: number;
  pricetick: number;
  min_volume: number;
}

export const useMarketStore = defineStore(
  'market',
  () => {
    // State
    const ticks = ref<Record<string, TickData>>({});
    const klines = ref<Record<string, KlineData[]>>({});
    const contracts = ref<Contract[]>([]);
    const selectedSymbol = ref<string | null>(null);
    const period = ref<Period>('1d');

    // Getters
    const selectedContract = computed(() =>
      contracts.value.find((c) => c.vt_symbol === selectedSymbol.value)
    );

    const selectedKlines = computed(() =>
      selectedSymbol.value ? klines.value[selectedSymbol.value] ?? [] : []
    );

    const currentTick = computed(() =>
      selectedSymbol.value ? ticks.value[selectedSymbol.value] : null
    );

    // Actions
    function clearData() {
      ticks.value = {};
      klines.value = {};
      selectedSymbol.value = null;
    }

    async function fetchContracts() {
      contracts.value = await marketApi.getContracts();
    }

    async function fetchKline(symbol: string, p: Period = period.value) {
      const data = await marketApi.getKline(symbol, p);
      klines.value[symbol] = data;
    }

    async function subscribe(symbol: string) {
      await marketApi.subscribe(symbol);
    }

    function setSelectedSymbol(symbol: string | null) {
      selectedSymbol.value = symbol;
      if (symbol && !klines.value[symbol]) {
        fetchKline(symbol);
      }
    }

    function setPeriod(p: Period) {
      period.value = p;
      if (selectedSymbol.value) {
        fetchKline(selectedSymbol.value, p);
      }
    }

    // WebSocket handlers
    function handleTickUpdate(data: TickData) {
      ticks.value[data.vt_symbol] = data;
    }

    function handleKlineUpdate(data: KlineData & { vt_symbol: string }) {
      const { vt_symbol, ...klineData } = data;
      if (!klines.value[vt_symbol]) {
        klines.value[vt_symbol] = [];
      }
      const candles = klines.value[vt_symbol];
      const lastCandle = candles[candles.length - 1];
      if (lastCandle && lastCandle.datetime === klineData.datetime) {
        candles[candles.length - 1] = klineData;
      } else {
        candles.push(klineData);
        if (candles.length > 500) {
          candles.shift();
        }
      }
    }

    // Setup WebSocket listeners
    function setupWebSocketListeners() {
      wsManager.on<TickData>('eTick.', handleTickUpdate);
      wsManager.on<KlineData & { vt_symbol: string }>('eKline.', handleKlineUpdate);
    }

    return {
      ticks,
      klines,
      contracts,
      selectedSymbol,
      period,
      selectedContract,
      selectedKlines,
      currentTick,
      clearData,
      fetchContracts,
      fetchKline,
      subscribe,
      setSelectedSymbol,
      setPeriod,
      setupWebSocketListeners,
    };
  },
  {
    persist: {
      pick: ['selectedSymbol', 'period'],
    },
  }
);
