import type { GridItem } from '@/types';

// 默认 Dashboard 布局
export const DEFAULT_DASHBOARD_LAYOUT: GridItem[] = [
  { i: 'account-summary', x: 0, y: 0, w: 12, h: 2, static: true },
  { i: 'positions', x: 0, y: 2, w: 7, h: 6 },
  { i: 'signals', x: 7, y: 2, w: 5, h: 3 },
  { i: 'stats', x: 7, y: 5, w: 5, h: 3 },
  { i: 'trade-history', x: 0, y: 8, w: 12, h: 5 },
];

// 响应式断点
export const RESPONSIVE_BREAKPOINTS = {
  lg: 1200,
  md: 992,
  sm: 768,
  xs: 480,
} as const;

// 列数配置
export const COLS_CONFIG = {
  lg: 12,
  md: 10,
  sm: 6,
  xs: 4,
} as const;

// 日志级别
export const LOG_LEVELS = ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'] as const;

// 日志来源
export const LOG_SOURCES = ['system', 'trade', 'strategy'] as const;

// K线周期
export const KLINE_PERIODS = [
  { label: '1分', value: '1m' },
  { label: '5分', value: '5m' },
  { label: '15分', value: '15m' },
  { label: '1时', value: '1h' },
  { label: '日线', value: '1d' },
] as const;

// 存储键名
export const STORAGE_KEYS = {
  TOKEN: 'vnpy_token',
  LAYOUT_PREFIX: 'vnpy_layout_',
  UI_SETTINGS: 'vnpy_ui_settings',
} as const;
