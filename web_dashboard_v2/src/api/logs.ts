import { client } from './client';
import type { LogEntry, LogFilters } from '@/types';

export const logsApi = {
  getLogs(filters?: LogFilters): Promise<LogEntry[]> {
    const params = new URLSearchParams();
    if (filters?.level && filters.level !== 'all') {
      params.append('level', filters.level);
    }
    if (filters?.source && filters.source !== 'all') {
      params.append('source', filters.source);
    }
    if (filters?.keyword) {
      params.append('keyword', filters.keyword);
    }
    return client.get(`/logs?${params.toString()}`);
  },
};
