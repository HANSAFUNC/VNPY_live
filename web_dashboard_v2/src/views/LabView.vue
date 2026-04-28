<template>
  <div class="lab-view">
    <!-- left: stock search + signal list -->
    <div class="signal-panel">
      <el-input
        v-model="stockSearch"
        placeholder="搜索信号..."
        clearable
        size="small"
        prefix-icon="Search"
        @keyup.enter="handleSearchStock"
      />
      <div class="signal-actions">
        <el-button size="small" type="primary" @click="handleSearchStock" :disabled="!stockSearch">
          查看K线
        </el-button>
        <el-button size="small" @click="labStore.loadSignals()">
          刷新信号
        </el-button>
      </div>

      <el-divider />

      <div class="signal-list-header">
        <span>信号列表</span>
        <el-tag size="small" type="info">{{ labStore.signals.length }}</el-tag>
      </div>
      <div v-loading="labStore.signalsLoading" class="signal-list">
        <div
          v-for="(signal, index) in filteredSignals"
          :key="`${signal.vt_symbol}-${signal.datetime}-${index}`"
          :class="['signal-item', { active: labStore.selectedSignal === signal }]"
          @click="labStore.selectSignal(signal)"
        >
          <div class="signal-header">
            <span class="signal-symbol">{{ signal.vt_symbol }}</span>
            <el-tag
              :type="signal.signal === 1 ? 'danger' : 'success'"
              size="small"
            >
              {{ signal.signal === 1 ? '买入' : '卖出' }}
            </el-tag>
          </div>
          <div class="signal-time">{{ signal.datetime }}</div>
        </div>
        <el-empty v-if="filteredSignals.length === 0 && !labStore.signalsLoading" description="暂无信号" :image-size="60" />
      </div>
    </div>

    <!-- center: K-line chart -->
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

    <!-- right: signal analysis -->
    <div class="analysis-panel">
      <!-- project info -->
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

      <!-- signal analysis -->
      <el-card shadow="never" class="analysis-card">
        <template #header>
          <span>信号分析</span>
        </template>

        <template v-if="labStore.selectedSignal">
          <div class="info-row">
            <span class="info-label">股票:</span>
            <span class="info-value">{{ labStore.selectedSignal.vt_symbol }}</span>
          </div>
          <div class="info-row">
            <span class="info-label">时间:</span>
            <span class="info-value">{{ labStore.selectedSignal.datetime }}</span>
          </div>
          <div class="info-row">
            <span class="info-label">方向:</span>
            <el-tag
              :type="labStore.selectedSignal.signal === 1 ? 'danger' : 'success'"
              size="small"
            >
              {{ labStore.selectedSignal.signal === 1 ? '买入' : '卖出' }}
            </el-tag>
          </div>

          <el-divider />

          <el-form label-width="70px" size="small">
            <el-form-item label="持有天数">
              <el-input-number
                v-model="labStore.analysisDays"
                :min="1"
                :max="60"
                :step="1"
                style="width: 100%"
              />
            </el-form-item>
            <el-form-item>
              <el-button
                type="primary"
                style="width: 100%"
                @click="handleAnalyze"
                :disabled="labStore.klineData.length === 0"
              >
                计算收益
              </el-button>
            </el-form-item>
          </el-form>

          <template v-if="labStore.analysisResult">
            <el-divider />
            <div class="info-row">
              <span class="info-label">入场价:</span>
              <span class="info-value">{{ labStore.analysisResult.entryPrice.toFixed(2) }}</span>
            </div>
            <div class="info-row">
              <span class="info-label">出场价:</span>
              <span class="info-value">{{ labStore.analysisResult.exitPrice.toFixed(2) }}</span>
            </div>
            <div class="info-row">
              <span class="info-label">收益率:</span>
              <span
                class="info-value"
                :class="{ profit: labStore.analysisResult.return > 0, loss: labStore.analysisResult.return < 0 }"
              >
                {{ labStore.analysisResult.return > 0 ? '+' : '' }}{{ labStore.analysisResult.return.toFixed(2) }}%
              </span>
            </div>
            <div class="info-row">
              <span class="info-label">最大回撤:</span>
              <span class="info-value loss">{{ labStore.analysisResult.maxDrawdown.toFixed(2) }}%</span>
            </div>
          </template>
        </template>
        <el-empty v-else description="请选择信号" :image-size="80" />
      </el-card>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted, onBeforeUnmount, nextTick } from 'vue';
import * as echarts from 'echarts';
import { useLabStore, useAuthStore } from '@/stores';

const labStore = useLabStore();
const authStore = useAuthStore();

const stockSearch = ref('');
const chartRef = ref<HTMLElement | null>(null);
let chartInstance: echarts.ECharts | null = null;

// filtered signal list
const filteredSignals = computed(() => {
  if (!stockSearch.value) return labStore.signals;
  const keyword = stockSearch.value.toLowerCase();
  return labStore.signals.filter(
    (s) =>
      s.vt_symbol.toLowerCase().includes(keyword) ||
      s.datetime.includes(keyword)
  );
});

// search stock and load kline
function handleSearchStock() {
  if (!stockSearch.value) return;
  labStore.loadKline(stockSearch.value);
}

function handlePeriodChange(val: '1d' | '1m') {
  labStore.setPeriod(val);
}

function handleAnalyze() {
  if (!labStore.selectedSignal) return;
  labStore.calculateSignalReturn(labStore.selectedSignal, labStore.analysisDays);
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
    if (idx >= 0) {
      markPoints.push({
        coord: [dates[idx], data[idx].low * 0.99],
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
            return d.close >= d.open ? '#f56c6c' : '#67c23a';
          },
        },
      },
    ],
  };
}

function renderChart() {
  if (!chartRef.value) return;

  if (!chartInstance) {
    chartInstance = echarts.init(chartRef.value);
  }

  if (labStore.klineData.length === 0) {
    chartInstance.clear();
    return;
  }

  const option = buildChartOption(labStore.klineData);
  chartInstance.setOption(option, true);
}

function handleResize() {
  chartInstance?.resize();
}

// watch kline data changes, redraw chart
watch(
  () => [labStore.klineData, labStore.selectedSignal],
  () => {
    nextTick(renderChart);
  },
  { deep: true }
);

// watch selectedStock changes, ensure chart container is ready
watch(
  () => labStore.selectedStock,
  () => {
    nextTick(renderChart);
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
  chartInstance?.dispose();
  chartInstance = null;
});
</script>

<style scoped lang="scss">
.lab-view {
  display: flex;
  gap: $spacing-md;
  height: 100%;
  overflow: hidden;
}

// left signal panel
.signal-panel {
  width: 240px;
  display: flex;
  flex-direction: column;
  background-color: var(--bg-primary);
  border-radius: $radius-md;
  border: 1px solid var(--border-color);
  padding: $spacing-sm;
}

.signal-actions {
  display: flex;
  gap: $spacing-xs;
  margin-top: $spacing-sm;
}

.signal-list-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-size: 13px;
  font-weight: 500;
  color: var(--text-secondary);
  margin-bottom: $spacing-xs;
}

.signal-list {
  flex: 1;
  overflow-y: auto;
}

.signal-item {
  padding: $spacing-sm;
  border-radius: $radius-sm;
  cursor: pointer;
  transition: all 0.2s;
  border-bottom: 1px solid var(--border-light);

  &:hover {
    background-color: var(--bg-secondary);
  }

  &.active {
    background-color: var(--bg-tertiary);
  }

  &:last-child {
    border-bottom: none;
  }
}

.signal-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.signal-symbol {
  font-size: 13px;
  font-weight: 500;
  color: var(--text-primary);
}

.signal-time {
  font-size: 11px;
  color: var(--text-tertiary);
  margin-top: 2px;
}

// center K-line chart
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

.card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.header-controls {
  display: flex;
  align-items: center;
  gap: $spacing-sm;
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

// right analysis panel
.analysis-panel {
  width: 260px;
  display: flex;
  flex-direction: column;
  gap: $spacing-md;
}

.info-card,
.analysis-card {
  flex-shrink: 0;
}

.analysis-card {
  flex: 1;
  overflow-y: auto;
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

// responsive
@media (max-width: 1200px) {
  .lab-view {
    flex-direction: column;
  }

  .signal-panel {
    width: 100%;
    max-height: 200px;
  }

  .analysis-panel {
    width: 100%;
    flex-direction: row;

    .info-card,
    .analysis-card {
      flex: 1;
    }
  }
}
</style>
