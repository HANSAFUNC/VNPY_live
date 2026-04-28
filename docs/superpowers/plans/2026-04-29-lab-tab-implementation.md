# 实验室 Tab 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 Web Dashboard V2 中添加实验室 Tab，提供数据管理、信号管理和 K 线查看功能

**Architecture:** 添加 NavBar 实验室 Tab 入口，创建 LabView.vue 主视图，使用 Pinia 状态管理 (lab.ts)，API 封装 (lab.ts)

**Tech Stack:** Vue 3, TypeScript, Element Plus, ECharts, Pinia

**设计文档:** `docs/superpowers/specs/2026-04-29-lab-tab-design.md`

---

## 文件结构

| 文件 | 操作 | 说明 |
|------|------|------|
| `web_dashboard_v2/src/router/index.ts` | 修改 | 添加实验室路由 |
| `web_dashboard_v2/src/components/layout/NavBar.vue` | 修改 | 添加实验室 Tab |
| `web_dashboard_v2/src/stores/index.ts` | 修改 | 导出 lab store |
| `web_dashboard_v2/src/api/index.ts` | 修改 | 导出 lab API |
| `web_dashboard_v2/src/stores/lab.ts` | 创建 | 实验室状态管理 |
| `web_dashboard_v2/src/api/lab.ts` | 创建 | 实验室 API 封装 |
| `web_dashboard_v2/src/views/LabView.vue` | 创建 | 实验室主视图 |

---

## Task 1: 添加实验室路由

**Files:**
- Modify: `web_dashboard_v2/src/router/index.ts`

- [ ] **Step 1: 添加实验室路由配置**

在路由配置中添加实验室路由：

```typescript
// 在 routes 数组中添加
{
  path: '/lab',
  name: 'lab',
  component: () => import('@/views/LabView.vue'),
  meta: { requiresAuth: true },
}
```

- [ ] **Step 2: Commit**

```bash
git add web_dashboard_v2/src/router/index.ts
git commit -m "feat: add lab route"
```

---

## Task 2: 在 NavBar 添加实验室 Tab

**Files:**
- Modify: `web_dashboard_v2/src/components/layout/NavBar.vue`

- [ ] **Step 1: 添加图标导入**

添加实验室图标：

```typescript
import { User, Sunny, Moon, Connection, DataBoard, TrendCharts, Document, Laboratory } from '@element-plus/icons-vue';
```

- [ ] **Step 2: 添加实验室 Tab**

在 tabs 数组中添加：

```typescript
const tabs = [
  { name: '总览', path: '/dashboard', icon: markRaw(DataBoard) },
  { name: '交易', path: '/trade', icon: markRaw(TrendCharts) },
  { name: '日志', path: '/logs', icon: markRaw(Document) },
  { name: '实验室', path: '/lab', icon: markRaw(Laboratory) },  // 新增
];
```

- [ ] **Step 3: Commit**

```bash
git add web_dashboard_v2/src/components/layout/NavBar.vue
git commit -m "feat: add lab tab in NavBar"
```

---

## Task 3: 创建实验室 API 封装

**Files:**
- Create: `web_dashboard_v2/src/api/lab.ts`

- [ ] **Step 1: 创建 lab.ts API 文件**

```typescript
import { client } from './client';

// 类型定义
export interface Project {
  name: string;
  index_code: string;
  data_source: string;
}

export interface DataCoverage {
  total_symbols: number;
  daily_files: number;
  minute_files: number;
  date_range: {
    start: string | null;
    end: string | null;
  };
  last_update: string | null;
  missing_data: string[];
}

export interface Signal {
  datetime: string;
  vt_symbol: string;
  signal: number; // 1=buy, -1=sell
}

export interface KlineData {
  datetime: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

// 获取项目列表
export async function getProjects(): Promise<string[]> {
  return client.get('/lab/projects') as Promise<string[]>;
}

// 切换项目
export async function switchProject(
  project_name: string,
  index_code?: string,
  data_source?: string
): Promise<{ success: boolean; message: string }> {
  return client.post('/lab/project/switch', {
    project_name,
    index_code,
    data_source,
  }) as Promise<{ success: boolean; message: string }>;
}

// 获取数据覆盖
export async function getCoverage(): Promise<DataCoverage> {
  return client.get('/lab/coverage') as Promise<DataCoverage>;
}

// 获取信号列表
export async function getSignals(): Promise<string[]> {
  return client.get('/lab/signals') as Promise<string[]>;
}

// 加载信号数据
export async function loadSignal(name: string): Promise<Signal[]> {
  const result = await client.get(`/lab/signal/${name}`) as { data: Signal[] } | { error: string };
  if ('error' in result) {
    throw new Error(result.error);
  }
  return result.data;
}

// 删除信号
export async function deleteSignal(name: string): Promise<{ success: boolean }> {
  return client.delete(`/lab/signal/${name}`) as Promise<{ success: boolean }>;
}

// 获取K线数据
export async function getKline(
  vt_symbol: string,
  period: '1d' | '1m' = '1d',
  days: number = 100
): Promise<KlineData[]> {
  return client.get(`/lab/kline/${vt_symbol}`, {
    params: { period, days },
  }) as Promise<KlineData[]>;
}
```

- [ ] **Step 2: 在 api/index.ts 中导出**

```typescript
// 在 web_dashboard_v2/src/api/index.ts 中添加
export * from './lab';
```

- [ ] **Step 3: Commit**

```bash
git add web_dashboard_v2/src/api/lab.ts web_dashboard_v2/src/api/index.ts
git commit -m "feat: add lab API module"
```

---

## Task 4: 创建实验室状态管理

**Files:**
- Create: `web_dashboard_v2/src/stores/lab.ts`

- [ ] **Step 1: 创建 lab.ts store 文件**

```typescript
import { defineStore } from 'pinia';
import { ref, computed } from 'vue';
import * as labApi from '@/api/lab';
import type { DataCoverage, Signal, KlineData } from '@/api/lab';

export const useLabStore = defineStore('lab', () => {
  // ============ 项目状态 ============
  const currentProject = ref('default');
  const currentIndex = ref('csi300');
  const currentDataSource = ref('xt');
  const projects = ref<string[]>([]);

  // ============ 数据覆盖 ============
  const coverage = ref<DataCoverage | null>(null);
  const coverageLoading = ref(false);

  // ============ 信号状态 ============
  const signals = ref<Signal[]>([]);
  const selectedSignal = ref<Signal | null>(null);
  const signalsLoading = ref(false);

  // ============ K线状态 ============
  const klineData = ref<KlineData[]>([]);
  const selectedStock = ref('');
  const period = ref<'1d' | '1m'>('1d');
  const klineLoading = ref(false);

  // ============ 分析状态 ============
  const analysisDays = ref(5);
  const analysisResult = ref<{
    entryPrice: number;
    exitPrice: number;
    return: number;
    maxDrawdown: number;
  } | null>(null);

  // ============ Actions ============

  // 加载项目列表
  async function loadProjects() {
    try {
      projects.value = await labApi.getProjects();
    } catch (error) {
      console.error('加载项目列表失败:', error);
    }
  }

  // 切换项目
  async function switchProject(
    projectName: string,
    indexCode?: string,
    dataSource?: string
  ) {
    try {
      const result = await labApi.switchProject(projectName, indexCode, dataSource);
      if (result.success) {
        currentProject.value = projectName;
        if (indexCode) currentIndex.value = indexCode;
        if (dataSource) currentDataSource.value = dataSource;
        // 重新加载数据
        await loadCoverage();
        await loadSignals();
      }
      return result;
    } catch (error) {
      console.error('切换项目失败:', error);
      throw error;
    }
  }

  // 加载数据覆盖
  async function loadCoverage() {
    coverageLoading.value = true;
    try {
      coverage.value = await labApi.getCoverage();
    } catch (error) {
      console.error('加载数据覆盖失败:', error);
    } finally {
      coverageLoading.value = false;
    }
  }

  // 加载信号
  async function loadSignals(signalName: string = 'signals') {
    signalsLoading.value = true;
    try {
      signals.value = await labApi.loadSignal(signalName);
    } catch (error) {
      console.error('加载信号失败:', error);
      signals.value = [];
    } finally {
      signalsLoading.value = false;
    }
  }

  // 选择信号
  function selectSignal(signal: Signal) {
    selectedSignal.value = signal;
    selectedStock.value = signal.vt_symbol;
    // 自动加载该股票的K线
    loadKline(signal.vt_symbol);
  }

  // 删除信号
  async function removeSignal(name: string) {
    try {
      const result = await labApi.deleteSignal(name);
      if (result.success) {
        await loadSignals();
      }
      return result;
    } catch (error) {
      console.error('删除信号失败:', error);
      throw error;
    }
  }

  // 加载K线
  async function loadKline(vtSymbol: string, days?: number) {
    klineLoading.value = true;
    selectedStock.value = vtSymbol;
    try {
      klineData.value = await labApi.getKline(
        vtSymbol,
        period.value,
        days || 100
      );
    } catch (error) {
      console.error('加载K线失败:', error);
      klineData.value = [];
    } finally {
      klineLoading.value = false;
    }
  }

  // 计算信号收益
  function calculateSignalReturn(signal: Signal, days: number) {
    const signalDate = new Date(signal.datetime);
    const entryData = klineData.value.find(
      (k) => new Date(k.datetime).toDateString() === signalDate.toDateString()
    );

    if (!entryData) {
      analysisResult.value = null;
      return;
    }

    const entryIndex = klineData.value.indexOf(entryData);
    const exitIndex = Math.min(entryIndex + days, klineData.value.length - 1);
    const exitData = klineData.value[exitIndex];

    if (!exitData) {
      analysisResult.value = null;
      return;
    }

    const entryPrice = entryData.close;
    const exitPrice = exitData.close;
    const returnPct = ((exitPrice - entryPrice) / entryPrice) * 100;

    // 计算最大回撤
    let maxDrawdown = 0;
    let maxPrice = entryPrice;
    for (let i = entryIndex; i <= exitIndex; i++) {
      const price = klineData.value[i].close;
      if (price > maxPrice) {
        maxPrice = price;
      }
      const drawdown = ((maxPrice - price) / maxPrice) * 100;
      if (drawdown > maxDrawdown) {
        maxDrawdown = drawdown;
      }
    }

    analysisResult.value = {
      entryPrice,
      exitPrice,
      return: returnPct,
      maxDrawdown,
    };
  }

  // 切换周期
  function setPeriod(newPeriod: '1d' | '1m') {
    period.value = newPeriod;
    if (selectedStock.value) {
      loadKline(selectedStock.value);
    }
  }

  // 初始化
  async function init() {
    await loadProjects();
    await loadCoverage();
    await loadSignals();
  }

  return {
    // 状态
    currentProject,
    currentIndex,
    currentDataSource,
    projects,
    coverage,
    coverageLoading,
    signals,
    selectedSignal,
    signalsLoading,
    klineData,
    selectedStock,
    period,
    klineLoading,
    analysisDays,
    analysisResult,

    // Actions
    loadProjects,
    switchProject,
    loadCoverage,
    loadSignals,
    selectSignal,
    removeSignal,
    loadKline,
    calculateSignalReturn,
    setPeriod,
    init,
  };
});
```

- [ ] **Step 2: 在 stores/index.ts 中导出**

```typescript
// 在 web_dashboard_v2/src/stores/index.ts 中添加
export * from './lab';
```

- [ ] **Step 3: Commit**

```bash
git add web_dashboard_v2/src/stores/lab.ts web_dashboard_v2/src/stores/index.ts
git commit -m "feat: add lab store"
```

---

## Task 5: 创建实验室主视图

**Files:**
- Create: `web_dashboard_v2/src/views/LabView.vue`

- [ ] **Step 1: 创建 LabView.vue 基础结构**

```vue
<template>
  <div class="lab-view">
    <!-- 顶部工具栏 -->
    <div class="toolbar">
      <el-select v-model="labStore.currentProject" @change="handleProjectChange">
        <el-option
          v-for="p in labStore.projects"
          :key="p"
          :label="p"
          :value="p"
        />
      </el-select>

      <div class="coverage-info" v-if="labStore.coverage">
        <el-tag>股票数: {{ labStore.coverage.total_symbols }}</el-tag>
        <el-tag>日期范围: {{ formatDateRange(labStore.coverage.date_range) }}</el-tag>
      </div>

      <el-button @click="labStore.init" :loading="labStore.coverageLoading">
        <el-icon><Refresh /></el-icon>
      </el-button>
    </div>

    <!-- 主内容区 -->
    <div class="main-content">
      <!-- 左侧：导航/股票列表 -->
      <div class="left-panel">
        <el-tabs v-model="activeTab">
          <el-tab-pane label="股票搜索" name="search">
            <el-input
              v-model="stockSearch"
              placeholder="输入股票代码 (如 600519.SSE)"
              @keyup.enter="handleSearch"
            >
              <template #append>
                <el-button @click="handleSearch">搜索</el-button>
              </template>
            </el-input>
          </el-tab-pane>

          <el-tab-pane label="信号列表" name="signals">
            <div class="signal-list" v-loading="labStore.signalsLoading">
              <div
                v-for="signal in labStore.signals"
                :key="`${signal.datetime}-${signal.vt_symbol}`"
                :class="['signal-item', { active: isSelectedSignal(signal) }, signal.signal > 0 ? 'buy' : 'sell']"
                @click="labStore.selectSignal(signal)"
              >
                <span class="date">{{ formatDate(signal.datetime) }}</span>
                <span class="symbol">{{ signal.vt_symbol }}</span>
                <el-tag :type="signal.signal > 0 ? 'success' : 'danger'" size="small">
                  {{ signal.signal > 0 ? '买入' : '卖出' }}
                </el-tag>
              </div>
            </div>
          </el-tab-pane>
        </el-tabs>
      </div>

      <!-- 中间：K线图 -->
      <div class="center-panel">
        <el-card>
          <template #header>
            <div class="chart-header">
              <span>{{ labStore.selectedStock || '请选择股票' }}</span>
              <el-radio-group v-model="labStore.period" @change="handlePeriodChange">
                <el-radio-button value="1d">日线</el-radio-button>
                <el-radio-button value="1m">分钟线</el-radio-button>
              </el-radio-group>
            </div>
          </template>
          <div ref="chartRef" class="kline-chart" v-loading="labStore.klineLoading"></div>
        </el-card>
      </div>

      <!-- 右侧：信号分析 -->
      <div class="right-panel">
        <el-card title="信号分析" v-if="labStore.selectedSignal">
          <template #header>信号详情</template>

          <div class="signal-detail">
            <div class="detail-item">
              <span class="label">日期:</span>
              <span>{{ formatDate(labStore.selectedSignal.datetime) }}</span>
            </div>
            <div class="detail-item">
              <span class="label">股票:</span>
              <span>{{ labStore.selectedSignal.vt_symbol }}</span>
            </div>
            <div class="detail-item">
              <span class="label">信号:</span>
              <el-tag :type="labStore.selectedSignal.signal > 0 ? 'success' : 'danger'">
                {{ labStore.selectedSignal.signal > 0 ? '买入' : '卖出' }}
              </el-tag>
            </div>
          </div>

          <el-divider />

          <div class="analysis-section">
            <div class="days-input">
              <span>N天后:</span>
              <el-input-number v-model="labStore.analysisDays" :min="1" :max="30" />
              <el-button @click="calculateReturn">计算收益</el-button>
            </div>

            <div v-if="labStore.analysisResult" class="analysis-result">
              <div class="result-item">
                <span class="label">买入价:</span>
                <span>{{ labStore.analysisResult.entryPrice.toFixed(2) }}</span>
              </div>
              <div class="result-item">
                <span class="label">N天后价格:</span>
                <span>{{ labStore.analysisResult.exitPrice.toFixed(2) }}</span>
              </div>
              <div class="result-item">
                <span class="label">收益率:</span>
                <span :class="labStore.analysisResult.return > 0 ? 'up' : 'down'">
                  {{ labStore.analysisResult.return.toFixed(2) }}%
                </span>
              </div>
              <div class="result-item">
                <span class="label">最大回撤:</span>
                <span>{{ labStore.analysisResult.maxDrawdown.toFixed(2) }}%</span>
              </div>
            </div>
          </div>
        </el-card>

        <el-empty v-else description="请选择信号查看分析" />
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted, watch, nextTick } from 'vue';
import { Refresh } from '@element-plus/icons-vue';
import { useLabStore } from '@/stores';
import * as echarts from 'echarts';
import type { Signal } from '@/api/lab';

const labStore = useLabStore();
const activeTab = ref('signals');
const stockSearch = ref('');
const chartRef = ref<HTMLDivElement>();
let chart: echarts.ECharts | null = null;

// 初始化
onMounted(async () => {
  await labStore.init();
  initChart();
});

onUnmounted(() => {
  if (chart) {
    chart.dispose();
    chart = null;
  }
});

// 监听K线数据变化，更新图表
watch(() => labStore.klineData, () => {
  updateChart();
}, { deep: true });

// 监听选中信号，标注在图表上
watch(() => labStore.selectedSignal, () => {
  updateChart();
});

function initChart() {
  if (!chartRef.value) return;
  chart = echarts.init(chartRef.value);
  updateChart();
}

function updateChart() {
  if (!chart || labStore.klineData.length === 0) return;

  const data = labStore.klineData.map((k) => [
    k.datetime,
    k.open,
    k.close,
    k.low,
    k.high,
  ]);

  const option: echarts.EChartsOption = {
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'cross' },
    },
    grid: { left: '10%', right: '10%', bottom: '15%' },
    xAxis: {
      type: 'category',
      data: labStore.klineData.map((k) => k.datetime),
      scale: true,
      boundaryGap: false,
      axisLine: { onZero: false },
      splitLine: { show: false },
      min: 'dataMin',
      max: 'dataMax',
    },
    yAxis: {
      scale: true,
      splitArea: { show: true },
    },
    dataZoom: [
      { type: 'inside', start: 50, end: 100 },
      { show: true, type: 'slider', top: '90%' },
    ],
    series: [
      {
        type: 'candlestick',
        data: labStore.klineData.map((k) => [k.open, k.close, k.low, k.high]),
        itemStyle: {
          color: '#ef232a',
          color0: '#14b143',
          borderColor: '#ef232a',
          borderColor0: '#14b143',
        },
      },
    ],
  };

  // 如果有选中信号，添加标注
  if (labStore.selectedSignal) {
    const signalIndex = labStore.klineData.findIndex(
      (k) => new Date(k.datetime).toDateString() ===
        new Date(labStore.selectedSignal!.datetime).toDateString()
    );

    if (signalIndex >= 0) {
      const markPoint = {
        data: [
          {
            coord: [signalIndex, labStore.klineData[signalIndex].close],
            value: labStore.selectedSignal.signal > 0 ? '买' : '卖',
            itemStyle: {
              color: labStore.selectedSignal.signal > 0 ? '#14b143' : '#ef232a',
            },
          },
        ],
      };
      (option.series as any)[0].markPoint = markPoint;
    }
  }

  chart.setOption(option);
}

function handleSearch() {
  if (stockSearch.value) {
    labStore.loadKline(stockSearch.value);
  }
}

function handlePeriodChange() {
  if (labStore.selectedStock) {
    labStore.loadKline(labStore.selectedStock);
  }
}

function handleProjectChange(project: string) {
  labStore.switchProject(project);
}

function calculateReturn() {
  if (labStore.selectedSignal) {
    labStore.calculateSignalReturn(labStore.selectedSignal, labStore.analysisDays);
  }
}

function isSelectedSignal(signal: Signal): boolean {
  return labStore.selectedSignal?.datetime === signal.datetime &&
    labStore.selectedSignal?.vt_symbol === signal.vt_symbol;
}

function formatDate(dateStr: string): string {
  return new Date(dateStr).toLocaleDateString('zh-CN');
}

function formatDateRange(range: { start: string | null; end: string | null }): string {
  if (!range.start || !range.end) return '-';
  return `${formatDate(range.start)} - ${formatDate(range.end)}`;
}
</script>

<style scoped lang="scss">
.lab-view {
  height: 100%;
  display: flex;
  flex-direction: column;
  padding: $spacing-md;
}

.toolbar {
  display: flex;
  align-items: center;
  gap: $spacing-md;
  padding-bottom: $spacing-md;
  border-bottom: 1px solid var(--border-color);

  .coverage-info {
    display: flex;
    gap: $spacing-sm;
  }
}

.main-content {
  flex: 1;
  display: grid;
  grid-template-columns: 280px 1fr 320px;
  gap: $spacing-md;
  margin-top: $spacing-md;
  overflow: hidden;
}

.left-panel {
  overflow: auto;

  .signal-list {
    max-height: 500px;
    overflow: auto;
  }

  .signal-item {
    display: flex;
    align-items: center;
    gap: $spacing-xs;
    padding: $spacing-xs $spacing-sm;
    cursor: pointer;
    border-radius: $radius-sm;
    transition: background-color 0.2s;

    &:hover {
      background-color: var(--bg-secondary);
    }

    &.active {
      background-color: var(--color-primary-light);
    }

    .date {
      font-size: 12px;
      color: var(--text-secondary);
      width: 80px;
    }

    .symbol {
      flex: 1;
      font-weight: 500;
    }
  }
}

.center-panel {
  overflow: auto;

  .chart-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
  }

  .kline-chart {
    height: 400px;
  }
}

.right-panel {
  overflow: auto;

  .signal-detail {
    .detail-item {
      display: flex;
      justify-content: space-between;
      padding: $spacing-xs 0;

      .label {
        color: var(--text-secondary);
      }
    }
  }

  .analysis-section {
    .days-input {
      display: flex;
      align-items: center;
      gap: $spacing-xs;
      margin-bottom: $spacing-md;
    }

    .analysis-result {
      .result-item {
        display: flex;
        justify-content: space-between;
        padding: $spacing-xs 0;

        .label {
          color: var(--text-secondary);
        }

        .up { color: var(--color-success); }
        .down { color: var(--color-danger); }
      }
    }
  }
}
</style>
```

- [ ] **Step 2: Commit**

```bash
git add web_dashboard_v2/src/views/LabView.vue
git commit -m "feat: add LabView.vue"
```

---

## Task 6: 安装 ECharts 依赖

**Files:**
- Modify: `web_dashboard_v2/package.json`

- [ ] **Step 1: 安装 ECharts**

```bash
cd F:/vnpy_live/web_dashboard_v2
npm install echarts
```

- [ ] **Step 2: Commit**

```bash
git add web_dashboard_v2/package.json web_dashboard_v2/package-lock.json
git commit -m "chore: add echarts dependency"
```

---

## Task 7: 测试验证

**Files:**
- None (运行测试)

- [ ] **Step 1: 验证 TypeScript 编译**

```bash
cd F:/vnpy_live/web_dashboard_v2
npx vue-tsc --noEmit
```

- [ ] **Step 2: 验证构建**

```bash
cd F:/vnpy_live/web_dashboard_v2
npm run build
```

- [ ] **Step 3: Commit 最终版本**

```bash
git add -A
git commit -m "feat: complete lab tab implementation

- Add LabView.vue with 3-column layout
- Add lab store with signal analysis
- Add lab API module
- Add lab tab in NavBar
- Integrate ECharts for K-line display"
```

---

## 计划完成

**执行选项：**
1. **Subagent-Driven** - 为每个 Task 分派独立子代理
2. **Inline Execution** - 在当前会话中直接执行

准备开始执行。
