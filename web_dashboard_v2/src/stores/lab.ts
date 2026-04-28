import { ref } from 'vue';
import { defineStore } from 'pinia';
import { labApi } from '@/api';
import type { KlineData } from '@/types';
import type { DataCoverage, Signal } from '@/api/lab';

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

  async function loadProjects() {
    try {
      projects.value = await labApi.getProjects();
    } catch (error) {
      console.error('加载项目列表失败:', error);
    }
  }

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
        await loadCoverage();
        await loadSignals();
      }
      return result;
    } catch (error) {
      console.error('切换项目失败:', error);
      throw error;
    }
  }

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

  function selectSignal(signal: Signal) {
    selectedSignal.value = signal;
    selectedStock.value = signal.vt_symbol;
    loadKline(signal.vt_symbol);
  }

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

  async function loadKline(vtSymbol: string, days?: number) {
    klineLoading.value = true;
    selectedStock.value = vtSymbol;
    try {
      klineData.value = await labApi.getKline(vtSymbol, period.value, days || 100);
    } catch (error) {
      console.error('加载K线失败:', error);
      klineData.value = [];
    } finally {
      klineLoading.value = false;
    }
  }

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

  function setPeriod(newPeriod: '1d' | '1m') {
    period.value = newPeriod;
    if (selectedStock.value) {
      loadKline(selectedStock.value);
    }
  }

  async function init() {
    await loadProjects();
    await loadCoverage();
    await loadSignals();
  }

  return {
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
