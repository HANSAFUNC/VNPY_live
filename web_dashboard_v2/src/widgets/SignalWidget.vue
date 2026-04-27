<template>
  <el-card class="signal-widget" shadow="never">
    <template #header>
      <div class="card-header">
        <span>交易信号</span>
        <el-button-group size="small">
          <el-button @click="clearSignals">清空</el-button>
        </el-button-group>
      </div>
    </template>

    <div class="signal-list">
      <div
        v-for="signal in signals.slice(0, 20)"
        :key="signal.id"
        class="signal-item"
        :class="signal.type"
      >
        <div class="signal-header">
          <span class="symbol">{{ signal.symbol }}</span>
          <el-tag :type="signal.type === 'buy' ? 'danger' : 'success'" size="small">
            {{ signal.type === 'buy' ? '买入' : '卖出' }}
          </el-tag>
        </div>
        <div class="signal-time">{{ formatTime(signal.time) }}</div>
        <div class="signal-info">{{ signal.message }}</div>
      </div>
      <el-empty v-if="signals.length === 0" description="暂无信号" />
    </div>
  </el-card>
</template>

<script setup lang="ts">
import { ref } from 'vue';
import { formatTime } from '@/utils/formatters';

interface Signal {
  id: number;
  symbol: string;
  type: 'buy' | 'sell';
  time: string;
  message: string;
}

const signals = ref<Signal[]>([]);

function clearSignals() {
  signals.value = [];
}

// 模拟信号数据（后续从 WebSocket 接收）
if (signals.value.length === 0) {
  signals.value = [
    { id: 1, symbol: 'IF2412', type: 'buy', time: new Date().toISOString(), message: '突破买入信号' },
    { id: 2, symbol: 'IC2412', type: 'sell', time: new Date(Date.now() - 60000).toISOString(), message: '止损卖出' },
  ];
}
</script>

<style scoped lang="scss">
.signal-widget {
  height: 100%;
}

.card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.signal-list {
  max-height: 300px;
  overflow-y: auto;
}

.signal-item {
  padding: $spacing-sm;
  border-bottom: 1px solid var(--border-light);

  &:last-child {
    border-bottom: none;
  }
}

.signal-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: $spacing-xs;
}

.symbol {
  font-weight: 600;
  color: var(--text-primary);
}

.signal-time {
  font-size: 12px;
  color: var(--text-tertiary);
  margin-bottom: $spacing-xs;
}

.signal-info {
  font-size: 13px;
  color: var(--text-secondary);
}
</style>
