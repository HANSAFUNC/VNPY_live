<template>
  <el-card class="trade-history-widget" shadow="never">
    <template #header>
      <div class="card-header">
        <span>成交记录</span>
        <el-tag size="small">{{ trades.length }} 笔</el-tag>
      </div>
    </template>

    <el-table
      :data="trades.slice(0, 50)"
      size="small"
      :max-height="400"
    >
      <el-table-column prop="trade_time" label="时间" width="160">
        <template #default="{ row }">
          {{ formatDateTime(row.trade_time) }}
        </template>
      </el-table-column>
      <el-table-column prop="name" label="名称" width="120" />
      <el-table-column prop="direction" label="方向" width="80">
        <template #default="{ row }">
          <el-tag :type="row.direction === 'LONG' ? 'danger' : 'success'" size="small">
            {{ row.direction === 'LONG' ? '多' : '空' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="offset" label="开平" width="80">
        <template #default="{ row }">
          {{ row.offset === 'OPEN' ? '开' : '平' }}
        </template>
      </el-table-column>
      <el-table-column prop="volume" label="数量" width="80" align="right" />
      <el-table-column prop="price" label="价格" width="100" align="right">
        <template #default="{ row }">
          {{ formatNumber(row.price) }}
        </template>
      </el-table-column>
      <el-table-column prop="vt_tradeid" label="成交编号" width="160" show-overflow-tooltip />
    </el-table>
  </el-card>
</template>

<script setup lang="ts">
import { storeToRefs } from 'pinia';
import { useTradingStore } from '@/stores';
import { formatNumber, formatDateTime } from '@/utils/formatters';

const tradingStore = useTradingStore();
const { trades } = storeToRefs(tradingStore);
</script>

<style scoped lang="scss">
.trade-history-widget {
  height: 100%;
}

.card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
</style>
