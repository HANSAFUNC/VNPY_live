export interface LoginRequest {
  username: string;
  password: string;
}

export interface LoginResponse {
  access_token: string;
  token_type: string;
}

export interface OrderRequest {
  symbol: string;
  exchange: string;
  direction: 'BUY' | 'SELL';
  type: 'LIMIT' | 'MARKET';
  volume: number;
  price?: number;
  offset?: 'OPEN' | 'CLOSE';
  reference?: string;
}

export interface WebSocketMessage<T = unknown> {
  topic: string;
  data: T;
}

export interface ApiResponse<T> {
  code: number;
  message: string;
  data: T;
}

export interface LogFilters {
  level: 'all' | 'DEBUG' | 'INFO' | 'WARNING' | 'ERROR' | 'CRITICAL';
  source: 'all' | 'system' | 'trade' | 'strategy';
  keyword: string;
}
