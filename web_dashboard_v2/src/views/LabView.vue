<template>
  <div class="lab-view">
    <!-- top: signal list -->
    <div class="top-section">
      <el-card shadow="never" class="signal-card">
        <template #header>
          <div class="card-header">
            <div class="header-left">
              <span class="header-title">信号列表</span>
              <el-select
                v-model="labStore.currentProject"
                placeholder="选择项目"
                size="small"
                style="width: 120px"
                @change="handleProjectChange"
              >
                <el-option
                  v-for="project in labStore.projects"
                  :key="project"
                  :label="project"
                  :value="project"
                />
              </el-select>
              <el-select
                v-model="labStore.currentIndex"
                placeholder="选择指数"
                size="small"
                style="width: 120px"
                @change="handleIndexChange"
              >
                <el-option label="沪深300" value="csi300" />
                <el-option label="中证500" value="zz500" />
                <el-option label="全A股" value="all_a" />
              </el-select>
              <el-select
                v-model="labStore.currentDataSource"
                placeholder="数据源"
                size="small"
                style="width: 100px"
                @change="handleDataSourceChange"
              >
                <el-option label="迅投" value="xt" />
                <el-option label="米筐" value="rq" />
              </el-select>
              <el-radio-group v-model="activeSignalTab" size="small">
                <el-radio-button value="buy">
                  买入
                  <el-tag size="small" type="danger" class="count-tag">
                    {{ labStore.signals.filter(s => s.signal === 1).length }}
                  </el-tag>
                </el-radio-button>
                <el-radio-button value="sell">
                  卖出
                  <el-tag size="small" type="success" class="count-tag">
                    {{ labStore.signals.filter(s => s.signal === -1).length }}
                  </el-tag>
                </el-radio-button>
              </el-radio-group>
            </div>
            <div class="header-controls">
              <el-form-item label="持有天数" size="small" class="days-input">
                <el-select
                  v-model="labStore.analysisDays"
                  size="small"
                  style="width: 80px"
                >
                  <el-option
                    v-for="day in dayOptions"
                    :key="day"
                    :label="day + '天'"
                    :value="day"
                  />
                </el-select>
              </el-form-item>
              <el-input
                v-model="stockSearch"
                placeholder="搜索信号..."
                clearable
                size="small"
                prefix-icon="Search"
                style="width: 180px"
                @keyup.enter="handleSearchStock"
              />
              <el-button size="small" type="primary" @click="handleSearchStock" :disabled="!stockSearch">
                查看K线
              </el-button>
              <el-button size="small" @click="labStore.loadSignals()">
                刷新
              </el-button>
            </div>
          </div>
        </template>

        <div v-loading="labStore.signalsLoading" class="signal-table-wrapper">
          <!-- 表头 -->
          <div class="signal-table-header">
            <div class="header-cell name-col">名称</div>
            <div class="header-cell code-col">代码</div>
            <div class="header-cell time-col">时间</div>
            <div class="header-cell entry-col">入场价</div>
            <div class="header-cell exit-col">出场价</div>
            <div
              class="header-cell return-col sortable"
              :class="{ active: sortByReturn }"
              @click="toggleSortByReturn"
            >
              总收益率
              <span class="sort-icon">
                <el-icon v-if="sortByReturn === 'desc'"><ArrowDown /></el-icon>
                <el-icon v-else-if="sortByReturn === 'asc'"><ArrowUp /></el-icon>
                <el-icon v-else class="sort-default"><Sort /></el-icon>
              </span>
            </div>
            <div class="header-cell dd-col">最大回撤</div>
          </div>
          <!-- 信号列表 -->
          <div class="signal-table-body">
            <div
              v-for="(signal, index) in filteredSignals"
              :key="`${signal.vt_symbol}-${signal.datetime}-${index}`"
              :class="['signal-row', { active: labStore.selectedSignal === signal }]"
              @click="labStore.selectSignal(signal)"
            >
              <div class="cell name-col">{{ signal.vt_symbol.split('.')[0] }}</div>
              <div class="cell code-col">{{ signal.vt_symbol }}</div>
              <div class="cell time-col">{{ signal.datetime.slice(0, 10) }}</div>
              <div class="cell entry-col">{{ signal.entry_price?.toFixed(2) ?? '--' }}</div>
              <div class="cell exit-col">{{ signal.exit_price?.toFixed(2) ?? '--' }}</div>
              <div
                v-if="signal.return !== undefined"
                class="cell return-col"
                :class="{ profit: signal.return > 0, loss: signal.return < 0 }"
              >
                {{ signal.return > 0 ? '+' : '' }}{{ signal.return.toFixed(2) }}%
              </div>
              <div v-else class="cell return-col">--</div>
              <div
                v-if="signal.max_drawdown !== undefined"
                class="cell dd-col loss"
              >
                {{ signal.max_drawdown.toFixed(2) }}%
              </div>
              <div v-else class="cell dd-col">--</div>
            </div>
            <el-empty v-if="filteredSignals.length === 0 && !labStore.signalsLoading" description="暂无信号" :image-size="60" />
          </div>
        </div>
      </el-card>
    </div>

    <!-- bottom: chart + analysis -->
    <div class="bottom-section">
      <!-- left: K-line chart -->
      <div class="chart-panel">
        <el-card shadow="never" class="chart-card">
          <template #header>
            <div class="card-header">
              <span>{{ labStore.selectedStock ? `K线 - ${labStore.selectedStock}` : 'K线图' }}</span>
              <div class="header-controls">
                <el-radio-group v-model="labStore.period" size="small" @change="handlePeriodChange">
                  <el-radio-button value="1d">日线</el-radio-button>
                  <el-radio-button value="1m">分钟</el-radio-button>
                </el-radio-group>
              </div>
            </div>
          </template>
          <div v-loading="labStore.klineLoading" class="chart-container">
            <div v-if="labStore.selectedStock" ref="chartRef" class="chart-dom" />
            <el-empty v-else description="请选择信号或搜索股票查看K线图" />
          </div>
        </el-card>
      </div>

      <!-- right: project info -->
      <div class="analysis-panel">
        <el-card shadow="never" class="info-card">
          <template #header>
            <span>项目信息</span>
          </template>
          <div class="info-row">
            <span class="info-label">项目:</span>
            <span class="info-value">{{ labStore.currentProject }}</span>
          </div>
          <div class="info-row">
            <span class="info-label">指数:</span>
            <span class="info-value">{{ labStore.currentIndex }}</span>
          </div>
          <div class="info-row">
            <span class="info-label">数据源:</span>
            <span class="info-value">{{ labStore.currentDataSource }}</span>
          </div>
          <template v-if="labStore.coverage">
            <el-divider />
            <div class="info-row">
              <span class="info-label">标的数:</span>
              <span class="info-value">{{ labStore.coverage.total_symbols }}</span>
            </div>
            <div class="info-row">
              <span class="info-label">日线文件:</span>
              <span class="info-value">{{ labStore.coverage.daily_files }}</span>
            </div>
            <div class="info-row">
              <span class="info-label">分钟文件:</span>
              <span class="info-value">{{ labStore.coverage.minute_files }}</span>
            </div>
          </template>
        </el-card>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted, onBeforeUnmount, nextTick } from 'vue';
import * as echarts from 'echarts';
import { ArrowDown, ArrowUp, Sort } from '@element-plus/icons-vue';
import { useLabStore, useAuthStore } from '@/stores';

const labStore = useLabStore();
const authStore = useAuthStore();

const stockSearch = ref('');
const chartRef = ref<HTMLElement | null>(null);
let chartInstance: echarts.ECharts | null = null;

// signal tab: 'buy' | 'sell'
const activeSignalTab = ref<'buy' | 'sell'>('buy');

// sort by return: null | 'asc' | 'desc'
const sortByReturn = ref<'asc' | 'desc' | null>(null);

// toggle sort by return
function toggleSortByReturn() {
  if (sortByReturn.value === null) {
    sortByReturn.value = 'desc';
  } else if (sortByReturn.value === 'desc') {
    sortByReturn.value = 'asc';
  } else {
    sortByReturn.value = null;
  }
}

// Generate day options based on maxAnalysisDays
const dayOptions = computed(() => {
  const max = labStore.maxAnalysisDays;
  const options = [];
  // Common day intervals: 1, 3, 5, 10, 20, 30, 60
  const commonDays = [1, 3, 5, 10, 20, 30, 60];
  for (const day of commonDays) {
    if (day <= max) {
      options.push(day);
    }
  }
  // Add max if not already in list
  if (!options.includes(max)) {
    options.push(max);
  }
  return options.sort((a, b) => a - b);
});

// watch tab change, auto select first signal in new tab
watch(activeSignalTab, (newTab) => {
  // Clear selection if current signal doesn't match new tab
  if (labStore.selectedSignal) {
    const isBuySignal = labStore.selectedSignal.signal === 1;
    if ((newTab === 'buy' && !isBuySignal) || (newTab === 'sell' && isBuySignal)) {
      labStore.selectedSignal = null;
      labStore.selectedStock = '';
    }
  }
  // Auto select first signal in the new tab
  const signals = newTab === 'buy'
    ? labStore.signals.filter(s => s.signal === 1)
    : labStore.signals.filter(s => s.signal === -1);
  if (signals.length > 0) {
    labStore.selectSignal(signals[0]);
  }
});

// filtered signal list by tab, search and sort
const filteredSignals = computed(() => {
  // first filter by signal type (buy/sell)
  let signals = labStore.signals;
  if (activeSignalTab.value === 'buy') {
    signals = signals.filter(s => s.signal === 1);
  } else {
    signals = signals.filter(s => s.signal === -1);
  }

  // then filter by search keyword
  if (stockSearch.value) {
    const keyword = stockSearch.value.toLowerCase();
    signals = signals.filter(
      (s) =>
        s.vt_symbol.toLowerCase().includes(keyword) ||
        s.datetime.includes(keyword)
    );
  }

  // sort by return if specified
  if (sortByReturn.value) {
    signals = [...signals].sort((a, b) => {
      const aReturn = a.return ?? -Infinity;
      const bReturn = b.return ?? -Infinity;
      return sortByReturn.value === 'desc' ? bReturn - aReturn : aReturn - bReturn;
    });
  }

  return signals;
});

// search stock and load kline
function handleSearchStock() {
  if (!stockSearch.value) return;
  labStore.loadKline(stockSearch.value);
}

function handlePeriodChange(val: '1d' | '1m') {
  labStore.setPeriod(val);
}

async function handleProjectChange(projectName: string) {
  await labStore.switchProject(projectName, labStore.currentIndex, labStore.currentDataSource);
}

async function handleIndexChange(indexCode: string) {
  await labStore.switchIndex(indexCode);
}

async function handleDataSourceChange(dataSource: string) {
  await labStore.switchDataSource(dataSource);
}

// ============ ECharts K-line chart ============

function buildChartOption(data: typeof labStore.klineData) {
  const dates = data.map((d) => d.datetime);
  const ohlc = data.map((d) => [d.open, d.close, d.low, d.high]);
  const volumes = data.map((d) => d.volume);

  // signal mark points
  const markPoints: { coord: [string, number]; itemStyle: { color: string }; symbol: string; symbolSize: number }[] = [];
  if (labStore.selectedSignal) {
    const sig = labStore.selectedSignal;
    const idx = dates.findIndex((dt) => dt.startsWith(sig.datetime.slice(0, 10)));
    if (idx >= 0 && data[idx] && dates[idx]) {
      markPoints.push({
        coord: [dates[idx]!, data[idx]!.low * 0.99],
        itemStyle: { color: sig.signal === 1 ? '#f56c6c' : '#67c23a' },
        symbol: sig.signal === 1 ? 'triangle' : 'pin',
        symbolSize: 16,
      });
    }
  }

  return {
    animation: false,
    grid: [
      { left: 60, right: 20, top: 20, height: '60%' },
      { left: 60, right: 20, top: '76%', height: '16%' },
    ],
    xAxis: [
      {
        type: 'category',
        data: dates,
        boundaryGap: true,
        axisLine: { lineStyle: { color: '#666' } },
        axisLabel: { fontSize: 10 },
        min: 'dataMin',
        max: 'dataMax',
      },
      {
        type: 'category',
        gridIndex: 1,
        data: dates,
        boundaryGap: true,
        axisLabel: { show: false },
        axisTick: { show: false },
        axisLine: { lineStyle: { color: '#666' } },
      },
    ],
    yAxis: [
      {
        scale: true,
        splitLine: { lineStyle: { color: 'rgba(255,255,255,0.1)' } },
        axisLine: { lineStyle: { color: '#666' } },
        axisLabel: { fontSize: 10 },
      },
      {
        scale: true,
        gridIndex: 1,
        splitNumber: 2,
        axisLabel: { show: false },
        axisTick: { show: false },
        splitLine: { show: false },
        axisLine: { lineStyle: { color: '#666' } },
      },
    ],
    dataZoom: [
      {
        type: 'inside',
        xAxisIndex: [0, 1],
        start: Math.max(0, 100 - Math.min(100, (60 / (dates.length || 1)) * 100)),
        end: 100,
      },
    ],
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'cross' },
    },
    series: [
      {
        name: 'K线',
        type: 'candlestick',
        data: ohlc,
        itemStyle: {
          color: '#f56c6c',
          color0: '#67c23a',
          borderColor: '#f56c6c',
          borderColor0: '#67c23a',
        },
        markPoint: markPoints.length > 0 ? { data: markPoints } : undefined,
      },
      {
        name: '成交量',
        type: 'bar',
        xAxisIndex: 1,
        yAxisIndex: 1,
        data: volumes,
        itemStyle: {
          color: (params: { dataIndex: number }) => {
            const d = data[params.dataIndex];
            return (d?.close ?? 0) >= (d?.open ?? 0) ? '#f56c6c' : '#67c23a';
          },
        },
      },
    ],
  };
}

let renderPending = false;

function renderChart() {
  if (!chartRef.value) return;
  if (renderPending) return;

  renderPending = true;
  requestAnimationFrame(() => {
    renderPending = false;
    if (!chartRef.value) return;

    // Dispose old instance if exists to prevent memory leaks
    if (chartInstance) {
      try {
        chartInstance.dispose();
      } catch (e) {
        // Ignore dispose errors
      }
    }

    // Create new instance
    try {
      chartInstance = echarts.init(chartRef.value);
    } catch (e) {
      console.error('Failed to init chart:', e);
      return;
    }

    if (labStore.klineData.length === 0) {
      chartInstance.clear();
      return;
    }

    const option = buildChartOption(labStore.klineData);
    try {
      chartInstance.setOption(option, true);
    } catch (e) {
      console.error('Failed to set chart option:', e);
    }
  });
}

function handleResize() {
  chartInstance?.resize();
}

// watch kline data changes, redraw chart with debounce
let chartUpdateTimeout: ReturnType<typeof setTimeout> | null = null;
watch(
  () => [labStore.klineData, labStore.selectedSignal],
  () => {
    if (chartUpdateTimeout) {
      clearTimeout(chartUpdateTimeout);
    }
    chartUpdateTimeout = setTimeout(() => {
      nextTick(renderChart);
    }, 100);
  },
  { deep: true }
);

// watch selectedStock changes, ensure chart container is ready
watch(
  () => labStore.selectedStock,
  () => {
    if (chartUpdateTimeout) {
      clearTimeout(chartUpdateTimeout);
    }
    chartUpdateTimeout = setTimeout(() => {
      nextTick(renderChart);
    }, 100);
  }
);

onMounted(() => {
  if (authStore.isLoggedIn) {
    labStore.init();
  }
  window.addEventListener('resize', handleResize);
});

onBeforeUnmount(() => {
  window.removeEventListener('resize', handleResize);
  if (chartUpdateTimeout) {
    clearTimeout(chartUpdateTimeout);
  }
  chartInstance?.dispose();
  chartInstance = null;
});
</script>

<style scoped lang="scss">
.lab-view {
  display: flex;
  flex-direction: column;
  gap: $spacing-md;
  height: 100%;
  overflow: hidden;
}

// top section: signal list
.top-section {
  flex-shrink: 0;
  height: 350px;
}

.signal-card {
  height: 100%;

  :deep(.el-card__body) {
    height: calc(100% - 55px);
    padding: $spacing-sm;
  }
}

.card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.header-left {
  display: flex;
  align-items: center;
  gap: $spacing-md;
}

.header-title {
  font-weight: 500;
}

.count-tag {
  margin-left: 4px;
  font-size: 11px;
  padding: 0 6px;
  height: 18px;
  line-height: 16px;
}

.header-controls {
  display: flex;
  align-items: center;
  gap: $spacing-sm;
}

// 信号表格样式
.signal-table-wrapper {
  height: 100%;
  display: flex;
  flex-direction: column;
}

.signal-table-header {
  display: flex;
  padding: $spacing-xs $spacing-md;
  background-color: var(--bg-secondary);
  border-bottom: 1px solid var(--border-color);
  font-weight: 500;
  font-size: 13px;
  color: var(--text-secondary);
  flex-shrink: 0;
}

.signal-table-body {
  flex: 1;
  overflow-y: auto;
}

.signal-row {
  display: flex;
  padding: $spacing-xs $spacing-md;
  border-bottom: 1px solid var(--border-color);
  cursor: pointer;
  transition: all 0.2s;
  font-size: 13px;

  &:hover {
    background-color: var(--bg-secondary);
  }

  &.active {
    background-color: var(--el-color-primary-light-9);
    border-left: 3px solid var(--el-color-primary);
  }
}

.header-cell,
.cell {
  padding: $spacing-xs $spacing-sm;
}

.name-col {
  width: 80px;
  flex-shrink: 0;
}

.code-col {
  width: 120px;
  flex-shrink: 0;
}

.time-col {
  width: 90px;
  flex-shrink: 0;
}

.entry-col,
.exit-col {
  width: 80px;
  flex-shrink: 0;
  text-align: right;
}

.return-col {
  width: 90px;
  flex-shrink: 0;
  text-align: right;
  font-weight: 500;
}

.dd-col {
  width: 80px;
  flex-shrink: 0;
  text-align: right;
}

.cell.return-col {
  &.profit {
    color: #f56c6c;
  }

  &.loss {
    color: #67c23a;
  }
}

.cell.dd-col {
  &.loss {
    color: #67c23a;
  }
}

// 排序样式
.sortable {
  cursor: pointer;
  user-select: none;
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 4px;

  &:hover {
    color: var(--el-color-primary);
  }

  &.active {
    color: var(--el-color-primary);
  }
}

.sort-icon {
  font-size: 12px;
  display: flex;
  align-items: center;

  .sort-default {
    opacity: 0.3;
  }
}

// 持有天数输入框
.days-input {
  margin-bottom: 0;
  margin-right: $spacing-sm;

  :deep(.el-form-item__label) {
    font-size: 13px;
    padding-right: 8px;
  }
}

// bottom section: chart + analysis
.bottom-section {
  flex: 1;
  display: flex;
  gap: $spacing-md;
  min-height: 0;
}

// left: K-line chart
.chart-panel {
  flex: 1;
  min-width: 0;
}

.chart-card {
  height: 100%;

  :deep(.el-card__body) {
    height: calc(100% - 55px);
    padding: 0;
  }
}

.chart-container {
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
}

.chart-dom {
  width: 100%;
  height: 100%;
}

// right: analysis panel
.analysis-panel {
  width: 280px;
  display: flex;
  flex-direction: column;
  gap: $spacing-md;
}

.info-card {
  flex-shrink: 0;
}

.info-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: $spacing-xs 0;
}

.info-label {
  color: var(--text-secondary);
  font-size: 13px;
}

.info-value {
  font-weight: 500;
  font-size: 13px;
}

.profit {
  color: #f56c6c;
}

.loss {
  color: #67c23a;
}

// responsive
@media (max-width: 1200px) {
  .bottom-section {
    flex-direction: column;
  }

  .analysis-panel {
    width: 100%;
    flex-direction: row;

    .info-card {
      flex: 1;
    }
  }
}
</style>
