import { client } from './client';
import type {
  AccountData,
  PositionData,
  OrderData,
  TradeData,
  OrderRequest,
} from '@/types';

export const tradingApi = {
  // 账户
  getAccounts(): Promise<AccountData[]> {
    return client.get('/account');
  },

  // 持仓
  getPositions(): Promise<PositionData[]> {
    return client.get('/position');
  },

  // 委托
  getOrders(): Promise<OrderData[]> {
    return client.get('/order');
  },

  // 成交
  getTrades(): Promise<TradeData[]> {
    return client.get('/trade');
  },

  // 下单
  sendOrder(data: OrderRequest): Promise<string> {
    return client.post('/order', data);
  },

  // 撤单
  cancelOrder(vtOrderid: string): Promise<void> {
    return client.delete(`/order/${vtOrderid}`);
  },

  // 交易模式
  getTradingMode(): Promise<{ mode: string; mode_text: string; engine: string }> {
    return client.get('/trading_mode');
  },
};
