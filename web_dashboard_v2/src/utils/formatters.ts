/**
 * 格式化金额
 */
export function formatMoney(value: number | undefined | null): string {
  if (value === undefined || value === null) return '¥0.00';
  return '¥' + Number(value).toLocaleString('zh-CN', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
}

/**
 * 格式化数字
 */
export function formatNumber(value: number | undefined | null, decimals = 2): string {
  if (value === undefined || value === null) return '0';
  return Number(value).toLocaleString('zh-CN', {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  });
}

/**
 * 格式化百分比
 */
export function formatPercent(value: number | undefined | null, decimals = 2): string {
  if (value === undefined || value === null) return '0.00%';
  return value.toFixed(decimals) + '%';
}

/**
 * 格式化涨跌幅颜色类名
 */
export function getPnlClass(value: number): string {
  return value >= 0 ? 'profit' : 'loss';
}

/**
 * 格式化涨跌幅显示
 */
export function formatPnl(value: number | undefined | null, decimals = 2): string {
  if (value === undefined || value === null) return '0.00%';
  const prefix = value >= 0 ? '+' : '';
  return prefix + value.toFixed(decimals) + '%';
}

/**
 * 格式化时间
 */
export function formatTime(date: Date | string | number): string {
  const d = new Date(date);
  return d.toLocaleTimeString('zh-CN', {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  });
}

/**
 * 格式化日期时间
 */
export function formatDateTime(date: Date | string | number): string {
  const d = new Date(date);
  return d.toLocaleString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  });
}

/**
 * 格式化日期
 */
export function formatDate(date: Date | string | number): string {
  const d = new Date(date);
  return d.toLocaleDateString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  });
}
