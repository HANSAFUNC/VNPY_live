<template>
  <el-card class="stat-widget" shadow="never">
    <template #header>
      <div class="card-header">
        <span>交易统计</span>
      </div>
    </template>

    <div class="stat-grid">
      <div class="stat-item">
        <div class="stat-value">{{ stats.total_trades }}</div>
        <div class="stat-label">总交易次数</div>
      </div>
      <div class="stat-item">
        <div class="stat-value" :class="getPnlClass(stats.total_return)">
          {{ formatPnl(stats.total_return) }}
        </div>
        <div class="stat-label">总收益率</div>
      </div>
      <div class="stat-item">
        <div class="stat-value">{{ formatPercent(stats.win_rate) }}</div>
        <div class="stat-label">胜率</div>
      </div>
      <div class="stat-item">
        <div class="stat-value">{{ stats.winning_trades }}</div>
        <div class="stat-label">盈利次数</div>
      </div>
      <div class="stat-item">
        <div class="stat-value">{{ stats.losing_trades }}</div>
        <div class="stat-label">亏损次数</div>
      </div>
      <div class="stat-item">
        <div class="stat-value" :class="getPnlClass(stats.sharpe_ratio)">
          {{ stats.sharpe_ratio.toFixed(2) }}
        </div>
        <div class="stat-label">夏普比率</div>
      </div>
    </div>
  </el-card>
</template>

<script setup lang="ts">
import { storeToRefs } from 'pinia';
import { useTradingStore } from '@/stores';
import { formatPercent, formatPnl, getPnlClass } from '@/utils/formatters';

const tradingStore = useTradingStore();
const { stats } = storeToRefs(tradingStore);
</script>

<style scoped lang="scss">
.stat-widget {
  height: 100%;
}

.card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.stat-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: $spacing-md;
  padding: $spacing-sm;
}

.stat-item {
  text-align: center;
  padding: $spacing-md;
  background-color: var(--bg-secondary);
  border-radius: $radius-md;
}

.stat-value {
  font-size: 24px;
  font-weight: 600;
  color: var(--text-primary);
  margin-bottom: $spacing-xs;
}

.stat-label {
  font-size: 12px;
  color: var(--text-tertiary);
}
</style>
