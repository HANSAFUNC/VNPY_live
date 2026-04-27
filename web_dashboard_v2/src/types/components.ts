export interface MetricCardProps {
  label: string;
  value: string | number;
  prefix?: string;
  suffix?: string;
  trend?: 'up' | 'down' | 'neutral';
  color?: string;
}

export interface WidgetProps {
  id: string;
  title: string;
  removable?: boolean;
  collapsible?: boolean;
}

export interface ChartProps {
  symbol: string;
  data: number[][];
  loading?: boolean;
}

export type LogLevelColor = 'info' | 'success' | 'warning' | 'danger';
