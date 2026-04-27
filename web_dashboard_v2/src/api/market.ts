import { client } from './client';
import type { TickData, KlineData } from '@/types';

export const marketApi = {
  // 订阅行情
  subscribe(vtSymbol: string): Promise<void> {
    return client.post(`/tick/${vtSymbol}`);
  },

  // 获取所有 tick
  getTicks(): Promise<TickData[]> {
    return client.get('/tick');
  },

  // 获取 K 线数据
  getKline(vtSymbol: string, period = '1d'): Promise<KlineData[]> {
    return client.get(`/kline/${vtSymbol}`, { params: { period } });
  },

  // 获取合约列表
  getContracts(): Promise<Array<{
    vt_symbol: string;
    symbol: string;
    exchange: string;
    name: string;
    size: number;
    pricetick: number;
    min_volume: number;
  }>> {
    return client.get('/contract');
  },
};
