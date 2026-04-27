<template>
  <el-card class="position-widget" shadow="never">
    <template #header>
      <div class="card-header">
        <span>当前持仓</span>
        <el-tag size="small">{{ positions.length }} 个品种</el-tag>
      </div>
    </template>

    <el-table
      :data="positions"
      size="small"
      :max-height="300"
      show-overflow-tooltip
    >
      <el-table-column prop="symbol" label="代码" width="100" />
      <el-table-column prop="name" label="名称" width="120" />
      <el-table-column prop="direction" label="方向" width="80">
        <template #default="{ row }">
          <el-tag :type="row.direction === 'LONG' ? 'danger' : 'success'" size="small">
            {{ row.direction === 'LONG' ? '多' : '空' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="volume" label="数量" width="100" align="right" />
      <el-table-column prop="price" label="成本价" width="100" align="right">
        <template #default="{ row }">
          {{ formatNumber(row.price) }}
        </template>
      </el-table-column>
      <el-table-column prop="last_price" label="现价" width="100" align="right">
        <template #default="{ row }">
          {{ formatNumber(row.last_price) }}
        </template>
      </el-table-column>
      <el-table-column prop="pnl" label="盈亏" width="120" align="right">
        <template #default="{ row }">
          <span :class="getPnlClass(row.pnl)">
            {{ formatMoney(row.pnl) }}
          </span>
        </template>
      </el-table-column>
      <el-table-column prop="pnl_ratio" label="盈亏比" width="100" align="right">
        <template #default="{ row }">
          <span :class="getPnlClass(row.pnl_ratio)">
            {{ formatPnl(row.pnl_ratio) }}
          </span>
        </template>
      </el-table-column>
    </el-table>
  </el-card>
</template>

<script setup lang="ts">
import { storeToRefs } from 'pinia';
import { useTradingStore } from '@/stores';
import { formatMoney, formatNumber, formatPnl, getPnlClass } from '@/utils/formatters';

const tradingStore = useTradingStore();
const { positions } = storeToRefs(tradingStore);
</script>

<style scoped lang="scss">
.position-widget {
  height: 100%;
}

.card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
</style>
