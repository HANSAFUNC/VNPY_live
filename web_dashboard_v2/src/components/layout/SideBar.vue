<template>
  <aside class="sidebar" :class="{ collapsed: uiStore.sidebarCollapsed }">
    <!-- 策略状态面板 -->
    <div class="sidebar-content">
      <div class="section-title">策略状态</div>

      <!-- 买卖信号 -->
      <div class="signals-section">
        <div class="subsection-title">买卖信号</div>
        <div class="signal-list">
          <div v-for="signal in recentSignals" :key="signal.id" class="signal-item">
            <el-tag :type="signal.type === 'buy' ? 'danger' : 'success'" size="small">
              {{ signal.type === 'buy' ? '买' : '卖' }}
            </el-tag>
            <span class="signal-symbol">{{ signal.symbol }}</span>
            <span class="signal-time">{{ signal.time }}</span>
          </div>
          <el-empty v-if="recentSignals.length === 0" description="暂无信号" :image-size="60" />
        </div>
      </div>

      <!-- 统计分析 -->
      <div class="stats-section">
        <div class="subsection-title">统计分析</div>
        <div class="stats-grid">
          <div class="stat-item">
            <div class="stat-label">胜率</div>
            <div class="stat-value" :class="getPnlClass(stats.win_rate)">
              {{ formatPercent(stats.win_rate) }}
            </div>
          </div>
          <div class="stat-item">
            <div class="stat-label">总收益</div>
            <div class="stat-value" :class="getPnlClass(stats.total_return)">
              {{ formatPercent(stats.total_return) }}
            </div>
          </div>
          <div class="stat-item">
            <div class="stat-label">最大回撤</div>
            <div class="stat-value text-danger">
              {{ formatPercent(stats.max_drawdown) }}
            </div>
          </div>
          <div class="stat-item">
            <div class="stat-label">夏普比率</div>
            <div class="stat-value">{{ formatNumber(stats.sharpe_ratio, 2) }}</div>
          </div>
        </div>
      </div>
    </div>

    <!-- 折叠按钮 -->
    <div class="collapse-btn" @click="uiStore.toggleSidebar">
      <el-icon>
        <Fold v-if="!uiStore.sidebarCollapsed" />
        <Expand v-else />
      </el-icon>
    </div>
  </aside>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import { Fold, Expand } from '@element-plus/icons-vue';
import { useUIStore, useTradingStore } from '@/stores';
import { formatPercent, formatNumber, getPnlClass } from '@/utils/formatters';

const uiStore = useUIStore();
const tradingStore = useTradingStore();

const stats = computed(() => tradingStore.stats);

interface Signal {
  id: string;
  type: 'buy' | 'sell';
  symbol: string;
  time: string;
}

const recentSignals = computed<Signal[]>(() => {
  // TODO: 从实际数据源获取信号
  return [];
});
</script>

<style scoped lang="scss">
.sidebar {
  display: flex;
  flex-direction: column;
  width: 240px;
  background-color: var(--bg-primary);
  border-right: 1px solid var(--border-color);
  transition: width 0.3s;

  &.collapsed {
    width: 0;
    overflow: hidden;
  }
}

.sidebar-content {
  flex: 1;
  padding: $spacing-md;
  overflow-y: auto;
}

.section-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
  margin-bottom: $spacing-md;
  padding-bottom: $spacing-sm;
  border-bottom: 1px solid var(--border-color);
}

.subsection-title {
  font-size: 12px;
  color: var(--text-secondary);
  margin-bottom: $spacing-sm;
}

.signals-section {
  margin-bottom: $spacing-lg;
}

.signal-list {
  display: flex;
  flex-direction: column;
  gap: $spacing-xs;
}

.signal-item {
  display: flex;
  align-items: center;
  gap: $spacing-xs;
  padding: $spacing-xs $spacing-sm;
  background-color: var(--bg-secondary);
  border-radius: $radius-sm;
  font-size: 12px;
}

.signal-symbol {
  flex: 1;
  color: var(--text-primary);
}

.signal-time {
  color: var(--text-secondary);
  font-size: 11px;
}

.stats-section {
  margin-bottom: $spacing-lg;
}

.stats-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: $spacing-sm;
}

.stat-item {
  display: flex;
  flex-direction: column;
  padding: $spacing-sm;
  background-color: var(--bg-secondary);
  border-radius: $radius-sm;
}

.stat-label {
  font-size: 11px;
  color: var(--text-secondary);
  margin-bottom: $spacing-xs;
}

.stat-value {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
}

.collapse-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 48px;
  cursor: pointer;
  border-top: 1px solid var(--border-color);
  color: var(--text-secondary);

  &:hover {
    background-color: var(--bg-secondary);
  }
}
</style>
