import { ref, computed } from 'vue';
import { defineStore } from 'pinia';
import { wsManager } from '@/api';
import { useTradingStore } from './trading';
import { useMarketStore } from './market';
import { useLogsStore } from './logs';
import type { BotInfo } from '@/types';

export const useBotStore = defineStore(
  'bot',
  () => {
    // State
    const activeBotId = ref<string | null>(null);
    const bots = ref<BotInfo[]>([]);
    const isLoading = ref(false);
    const error = ref<string | null>(null);

    // Getters
    const activeBot = computed(() =>
      bots.value.find((b) => b.id === activeBotId.value)
    );

    const hasBots = computed(() => bots.value.length > 0);

    // Actions
    function setBots(newBots: BotInfo[]) {
      bots.value = newBots;
      // 如果没有激活的策略且列表不为空，默认选择第一个
      const first = newBots[0];
      if (!activeBotId.value && first) {
        activeBotId.value = first.id;
      }
    }

    async function switchBot(botId: string) {
      if (botId === activeBotId.value) return;

      isLoading.value = true;
      error.value = null;

      try {
        // 1. 断开当前 WebSocket
        wsManager.disconnect();

        // 2. 更新激活的策略
        activeBotId.value = botId;

        // 3. 清空相关 store 的数据
        const tradingStore = useTradingStore();
        const marketStore = useMarketStore();
        const logsStore = useLogsStore();

        tradingStore.clearData();
        marketStore.clearData();
        logsStore.clearLogs();

        // 4. 重新连接 WebSocket
        wsManager.connect();

        // 5. 获取新策略的数据
        await Promise.all([
          tradingStore.fetchAllData(),
          marketStore.fetchContracts(),
        ]);
      } catch (e) {
        error.value = e instanceof Error ? e.message : '切换策略失败';
        console.error('Failed to switch bot:', e);
      } finally {
        isLoading.value = false;
      }
    }

    function updateBotStatus(botId: string, status: BotInfo['status']) {
      const bot = bots.value.find((b) => b.id === botId);
      if (bot) {
        bot.status = status;
      }
    }

    return {
      activeBotId,
      bots,
      isLoading,
      error,
      activeBot,
      hasBots,
      setBots,
      switchBot,
      updateBotStatus,
    };
  },
  {
    persist: {
      pick: ['activeBotId'],
    },
  }
);
