<template>
  <div class="dashboard-view">
    <!-- 顶部指标栏 -->
    <div class="metrics-bar">
      <div class="metric-card">
        <div class="metric-label">收益率曲线</div>
        <div class="metric-value chart-placeholder">
          <span :class="getPnlClass(stats.total_return)">
            {{ formatPercent(stats.total_return) }}
          </span>
        </div>
      </div>
      <div class="metric-card">
        <div class="metric-label">当日盈亏</div>
        <div class="metric-value" :class="getPnlClass(dailyPnl)">
          {{ formatMoney(dailyPnl) }}
        </div>
      </div>
      <div class="metric-card">
        <div class="metric-label">总资产</div>
        <div class="metric-value">
          {{ formatMoney(account?.balance ?? 0) }}
        </div>
      </div>
      <div class="metric-card">
        <div class="metric-label">持仓市值</div>
        <div class="metric-value">
          {{ formatMoney(positionValue) }}
        </div>
      </div>
      <div class="metric-card">
        <div class="metric-label">总收益率</div>
        <div class="metric-value" :class="getPnlClass(stats.total_return)">
          {{ formatPercent(stats.total_return) }}
        </div>
      </div>
    </div>

    <!-- 当前持仓表格 -->
    <el-card shadow="never" class="table-card">
      <template #header>
        <div class="card-header">
          <span>当前持仓</span>
          <el-tag size="small">{{ positions.length }} 个</el-tag>
        </div>
      </template>

      <el-table
        :data="positions"
        size="small"
        :max-height="350"
        show-overflow-tooltip
      >
        <el-table-column prop="name" label="名称" width="120" />
        <el-table-column prop="symbol" label="代码" width="100" />
        <el-table-column prop="order_id" label="订单ID" width="120" />
        <el-table-column prop="direction" label="方向" width="80">
          <template #default="{ row }">
            <el-tag :type="row.direction === 'LONG' ? 'danger' : 'success'" size="small">
              {{ row.direction === 'LONG' ? '多' : '空' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="volume" label="持仓量" width="100" align="right" />
        <el-table-column prop="total_cost" label="总筹码" width="120" align="right">
          <template #default="{ row }">
            {{ formatMoney(row.total_cost ?? row.volume * row.price) }}
          </template>
        </el-table-column>
        <el-table-column prop="price" label="开仓价格" width="100" align="right">
          <template #default="{ row }">
            {{ formatNumber(row.price) }}
          </template>
        </el-table-column>
        <el-table-column prop="last_price" label="最新价" width="100" align="right">
          <template #default="{ row }">
            {{ formatNumber(row.last_price) }}
          </template>
        </el-table-column>
        <el-table-column prop="pnl_ratio" label="涨跌幅" width="100" align="right">
          <template #default="{ row }">
            <span :class="getPnlClass(row.pnl_ratio)">
              {{ formatPercent(row.pnl_ratio) }}
            </span>
          </template>
        </el-table-column>
        <el-table-column prop="start_time" label="开始时间" width="160">
          <template #default="{ row }">
            {{ row.start_time ? formatDateTime(row.start_time) : '-' }}
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 历史成交表格 -->
    <el-card shadow="never" class="table-card">
      <template #header>
        <div class="card-header">
          <span>历史成交</span>
          <el-tag size="small">{{ closedTrades.length }} 笔</el-tag>
        </div>
      </template>

      <el-table
        :data="closedTrades"
        size="small"
        :max-height="350"
        show-overflow-tooltip
      >
        <el-table-column prop="name" label="名称" width="120" />
        <el-table-column prop="symbol" label="代码" width="100" />
        <el-table-column prop="vt_orderid" label="订单ID" width="140" />
        <el-table-column prop="direction" label="方向" width="80">
          <template #default="{ row }">
            <el-tag :type="row.direction === 'LONG' ? 'danger' : 'success'" size="small">
              {{ row.direction === 'LONG' ? '多' : '空' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="volume" label="持仓量" width="100" align="right" />
        <el-table-column prop="total_cost" label="总筹码" width="120" align="right">
          <template #default="{ row }">
            {{ formatMoney(row.total_cost ?? row.volume * (row.open_price ?? row.price)) }}
          </template>
        </el-table-column>
        <el-table-column prop="open_price" label="开仓价格" width="100" align="right">
          <template #default="{ row }">
            {{ formatNumber(row.open_price ?? row.price) }}
          </template>
        </el-table-column>
        <el-table-column prop="close_price" label="空仓价格" width="100" align="right">
          <template #default="{ row }">
            {{ formatNumber(row.close_price ?? row.price) }}
          </template>
        </el-table-column>
        <el-table-column prop="pnl_ratio" label="涨跌幅" width="100" align="right">
          <template #default="{ row }">
            <span :class="getPnlClass(row.pnl_ratio)">
              {{ formatPercent(row.pnl_ratio) }}
            </span>
          </template>
        </el-table-column>
        <el-table-column prop="start_time" label="开始时间" width="160">
          <template #default="{ row }">
            {{ row.start_time ? formatDateTime(row.start_time) : '-' }}
          </template>
        </el-table-column>
        <el-table-column prop="end_time" label="结束时间" width="160">
          <template #default="{ row }">
            {{ row.end_time ? formatDateTime(row.end_time) : '-' }}
          </template>
        </el-table-column>
        <el-table-column prop="close_reason" label="结束原因" width="100">
          <template #default="{ row }">
            <el-tag v-if="row.close_reason" size="small" :type="getCloseReasonType(row.close_reason)">
              {{ row.close_reason }}
            </el-tag>
            <span v-else>-</span>
          </template>
        </el-table-column>
      </el-table>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted } from 'vue';
import { storeToRefs } from 'pinia';
import { useTradingStore, useAuthStore } from '@/stores';
import { formatMoney, formatNumber, formatPercent, formatDateTime, getPnlClass } from '@/utils/formatters';
import type { TradeData } from '@/types';

const tradingStore = useTradingStore();
const authStore = useAuthStore();
const { account, positions, trades, stats } = storeToRefs(tradingStore);

const positionValue = computed(() =>
  positions.value.reduce(
    (sum, p) => sum + p.volume * (p.last_price ?? p.price ?? 0),
    0
  )
);

const dailyPnl = computed(() =>
  positions.value.reduce((sum, p) => sum + (p.pnl ?? 0), 0)
);

// 历史成交（已平仓的交易）
const closedTrades = computed<TradeData[]>(() => {
  // 这里需要根据实际业务逻辑判断哪些交易是已平仓的
  // 目前简单展示所有交易
  return trades.value.filter(t => t.offset === 'CLOSE');
});

function getCloseReasonType(reason: string): string {
  const map: Record<string, string> = {
    '止盈': 'success',
    '止损': 'danger',
    '手动': 'info',
  };
  return map[reason] ?? 'info';
}

onMounted(() => {
  // 只有在登录状态下才请求数据
  if (authStore.isLoggedIn) {
    tradingStore.fetchAllData();
  }
});
</script>

<style scoped lang="scss">
.dashboard-view {
  display: flex;
  flex-direction: column;
  gap: $spacing-md;
  height: 100%;
}

// 顶部指标栏
.metrics-bar {
  display: grid;
  grid-template-columns: repeat(5, 1fr);
  gap: $spacing-md;
}

.metric-card {
  display: flex;
  flex-direction: column;
  padding: $spacing-md;
  background-color: var(--bg-primary);
  border-radius: $radius-md;
  border: 1px solid var(--border-color);
}

.metric-label {
  font-size: 12px;
  color: var(--text-secondary);
  margin-bottom: $spacing-xs;
}

.metric-value {
  font-size: 18px;
  font-weight: 600;
  color: var(--text-primary);
}

.chart-placeholder {
  min-height: 28px;
}

// 表格卡片
.table-card {
  flex: 1;

  :deep(.el-card__body) {
    padding: 0;
  }
}

.card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

// 响应式
@media (max-width: 1200px) {
  .metrics-bar {
    grid-template-columns: repeat(3, 1fr);
  }
}

@media (max-width: 768px) {
  .metrics-bar {
    grid-template-columns: repeat(2, 1fr);
  }
}
</style>
