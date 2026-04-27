<template>
  <el-card class="account-summary-widget" shadow="never">
    <div class="summary-grid">
      <div class="summary-item">
        <div class="label">总资产</div>
        <div class="value">{{ formatMoney(account?.balance) }}</div>
      </div>
      <div class="summary-item">
        <div class="label">可用资金</div>
        <div class="value">{{ formatMoney(account?.available) }}</div>
      </div>
      <div class="summary-item">
        <div class="label">冻结资金</div>
        <div class="value">{{ formatMoney(account?.frozen) }}</div>
      </div>
      <div class="summary-item">
        <div class="label">持仓市值</div>
        <div class="value">{{ formatMoney(tradingStore.positionValue) }}</div>
      </div>
      <div class="summary-item">
        <div class="label">当日盈亏</div>
        <div class="value" :class="getPnlClass(tradingStore.dailyPnl)">
          {{ formatMoney(tradingStore.dailyPnl) }}
        </div>
      </div>
      <div class="summary-item">
        <div class="label">持仓数量</div>
        <div class="value">{{ tradingStore.positionCount }}</div>
      </div>
    </div>
  </el-card>
</template>

<script setup lang="ts">
import { storeToRefs } from 'pinia';
import { useTradingStore } from '@/stores';
import { formatMoney, getPnlClass } from '@/utils/formatters';

const tradingStore = useTradingStore();
const { account } = storeToRefs(tradingStore);
</script>

<style scoped lang="scss">
.account-summary-widget {
  height: 100%;
}

.summary-grid {
  display: grid;
  grid-template-columns: repeat(6, 1fr);
  gap: $spacing-md;
  padding: $spacing-md;
}

.summary-item {
  text-align: center;
}

.label {
  font-size: 12px;
  color: var(--text-tertiary);
  margin-bottom: $spacing-xs;
}

.value {
  font-size: 20px;
  font-weight: 600;
  color: var(--text-primary);
}

@media (max-width: 1200px) {
  .summary-grid {
    grid-template-columns: repeat(3, 1fr);
  }
}

@media (max-width: 768px) {
  .summary-grid {
    grid-template-columns: repeat(2, 1fr);
  }
}
</style>
