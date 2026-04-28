import { client } from './client';
import type { KlineData } from '@/types/models';

// 类型定义
export interface DataCoverage {
  total_symbols: number;
  daily_files: number;
  minute_files: number;
  date_range: {
    start: string | null;
    end: string | null;
  };
  last_update: string | null;
  missing_data: string[];
}

export interface Signal {
  datetime: string;
  vt_symbol: string;
  signal: number; // 1=buy, -1=sell
}

export const labApi = {
  // 获取项目列表
  getProjects(): Promise<string[]> {
    return client.get('/lab/projects');
  },

  // 切换项目
  switchProject(
    project_name: string,
    index_code?: string,
    data_source?: string
  ): Promise<{ success: boolean; message: string }> {
    return client.post('/lab/project/switch', {
      project_name,
      index_code,
      data_source,
    });
  },

  // 获取数据覆盖
  getCoverage(): Promise<DataCoverage> {
    return client.get('/lab/coverage');
  },

  // 获取信号列表
  getSignals(): Promise<string[]> {
    return client.get('/lab/signals');
  },

  // 加载信号数据
  async loadSignal(name: string): Promise<Signal[]> {
    const result = await client.get(`/lab/signal/${name}`);
    if ('error' in result) {
      throw new Error(result.error);
    }
    return result.data;
  },

  // 删除信号
  deleteSignal(name: string): Promise<{ success: boolean }> {
    return client.delete(`/lab/signal/${name}`);
  },

  // 获取K线数据
  getKline(
    vt_symbol: string,
    period: '1d' | '1m' = '1d',
    days: number = 100
  ): Promise<KlineData[]> {
    return client.get(`/lab/kline/${vt_symbol}`, {
      params: { period, days },
    });
  },
};
