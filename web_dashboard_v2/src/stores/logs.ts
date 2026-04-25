import { ref } from 'vue';
import { defineStore } from 'pinia';
import type { LogEntry } from '@/types';

export const useLogsStore = defineStore('logs', () => {
  const logs = ref<LogEntry[]>([]);

  function clearLogs() {
    logs.value = [];
  }

  return {
    logs,
    clearLogs,
  };
});
