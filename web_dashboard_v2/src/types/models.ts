export interface AccountData {
  accountid: string;
  balance: number;
  available: number;
  frozen: number;
}

export interface PositionData {
  vt_symbol: string;
  symbol: string;
  exchange: string;
  direction: 'LONG' | 'SHORT';
  volume: number;
  price: number;
  pnl: number;
  pnl_ratio: number;
  last_price: number;
  name?: string;
  order_id?: string;
  total_cost?: number;
  start_time?: string;
}

export interface TradeData {
  vt_tradeid: string;
  vt_orderid: string;
  vt_symbol: string;
  direction: 'LONG' | 'SHORT';
  offset: 'OPEN' | 'CLOSE';
  price: number;
  volume: number;
  trade_time: string;
  name?: string;
  open_price?: number;
  close_price?: number;
  pnl_ratio?: number;
  start_time?: string;
  end_time?: string;
  close_reason?: string;
}

export interface OrderData {
  vt_orderid: string;
  vt_symbol: string;
  direction: 'BUY' | 'SELL';
  type: 'LIMIT' | 'MARKET';
  price: number;
  volume: number;
  traded: number;
  status: 'SUBMITTING' | 'NOTTRADED' | 'PARTTRADED' | 'ALLTRADED' | 'CANCELLED' | 'REJECTED';
  order_time: string;
}

export interface TickData {
  vt_symbol: string;
  symbol: string;
  exchange: string;
  last_price: number;
  volume: number;
  bid_price_1: number;
  bid_volume_1: number;
  ask_price_1: number;
  ask_volume_1: number;
  datetime: string;
}

export interface KlineData {
  datetime: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

export interface LogEntry {
  id: number;
  time: string;
  level: 'DEBUG' | 'INFO' | 'WARNING' | 'ERROR' | 'CRITICAL';
  source: 'system' | 'trade' | 'strategy';
  message: string;
}

export interface TradingStats {
  total_return: number;
  annual_return: number;
  max_drawdown: number;
  sharpe_ratio: number;
  win_rate: number;
  total_trades: number;
  winning_trades: number;
  losing_trades: number;
}

export interface BotInfo {
  id: string;
  name: string;
  status: 'running' | 'stopped' | 'error';
  mode: 'live' | 'paper';
  rpcUrl: string;
  wsUrl: string;
  lastPing: number;
}

export interface GridItem {
  i: string;
  x: number;
  y: number;
  w: number;
  h: number;
  static?: boolean;
}

export type Period = '1m' | '5m' | '15m' | '1h' | '1d';

export interface ServerConfig {
  id: string;
  name: string;
  url: string;
  wsUrl: string;
  lastUsed: number;
  isDefault?: boolean;
}
