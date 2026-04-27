import { ref, computed } from 'vue';
import { defineStore } from 'pinia';
import { logsApi } from '@/api';
import type { LogEntry, LogFilters } from '@/types';

export const useLogsStore = defineStore('logs', () => {
  // State
  const logs = ref<LogEntry[]>([]);
  const filters = ref<LogFilters>({
    level: 'all',
    source: 'all',
    keyword: '',
  });

  // Getters
  const filteredLogs = computed(() => {
    return logs.value.filter((log) => {
      if (filters.value.level !== 'all' && log.level !== filters.value.level) {
        return false;
      }
      if (filters.value.source !== 'all' && log.source !== filters.value.source) {
        return false;
      }
      if (filters.value.keyword && !log.message.includes(filters.value.keyword)) {
        return false;
      }
      return true;
    });
  });

  const logCount = computed(() => filteredLogs.value.length);

  // Actions
  function clearLogs() {
    logs.value = [];
  }

  async function fetchLogs() {
    logs.value = await logsApi.getLogs(filters.value);
  }

  function addLog(log: LogEntry) {
    logs.value.unshift(log);
    if (logs.value.length > 1000) {
      logs.value = logs.value.slice(0, 1000);
    }
  }

  function setFilters(newFilters: Partial<LogFilters>) {
    Object.assign(filters.value, newFilters);
  }

  function clearFilters() {
    filters.value = {
      level: 'all',
      source: 'all',
      keyword: '',
    };
  }

  return {
    logs,
    filters,
    filteredLogs,
    logCount,
    clearLogs,
    fetchLogs,
    addLog,
    setFilters,
    clearFilters,
  };
});
