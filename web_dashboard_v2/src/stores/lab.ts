import { ref, watch } from 'vue';
import { defineStore } from 'pinia';
import { labApi } from '@/api';
import type { KlineData } from '@/types';
import type { DataCoverage, Signal } from '@/api/lab';

const STORAGE_KEY_PROJECT = 'lab_last_project';
const STORAGE_KEY_INDEX = 'lab_last_index';
const STORAGE_KEY_DATA_SOURCE = 'lab_last_data_source';

export const useLabStore = defineStore('lab', () => {
  // ============ 项目状态 ============
  const currentProject = ref('');
  const currentIndex = ref('');
  const currentDataSource = ref('');
  const projects = ref<string[]>([]);

  // Default options
  const availableIndices = ['csi300', 'zz500', 'all_a'];
  const availableDataSources = ['xt', 'rq'];

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
  const maxAnalysisDays = ref(60);
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
        // Save to localStorage
        localStorage.setItem(STORAGE_KEY_PROJECT, projectName);
        if (indexCode) {
          currentIndex.value = indexCode;
          localStorage.setItem(STORAGE_KEY_INDEX, indexCode);
        }
        if (dataSource) {
          currentDataSource.value = dataSource;
          localStorage.setItem(STORAGE_KEY_DATA_SOURCE, dataSource);
        }
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

  async function loadSignals() {
    signalsLoading.value = true;
    try {
      // First get available signal names
      const signalNames = await labApi.getSignals();
      if (signalNames.length === 0) {
        signals.value = [];
        return;
      }
      // Load the first signal
      const firstSignal = signalNames[0];
      if (!firstSignal) {
        signals.value = [];
        return;
      }
      signals.value = await labApi.loadSignal(firstSignal);
      // Calculate returns for all signals
      await calculateAllSignalsReturns(analysisDays.value);
      // Auto select first signal
      if (signals.value.length > 0) {
        selectSignal(signals.value[0]);
      }
    } catch (error) {
      console.error('加载信号失败:', error);
      signals.value = [];
    } finally {
      signalsLoading.value = false;
    }
  }

  // Track pending select to prevent rapid clicking
  let pendingSelectSymbol: string | null = null;

  async function selectSignal(signal: Signal) {
    // Prevent selecting the same signal repeatedly
    if (pendingSelectSymbol === signal.vt_symbol) return;
    pendingSelectSymbol = signal.vt_symbol;

    selectedSignal.value = signal;
    selectedStock.value = signal.vt_symbol;
    // Load kline and calculate max days
    try {
      const data = await labApi.getKline(signal.vt_symbol, period.value, 100);
      klineData.value = data;
      // Calculate max days from signal date to last kline
      if (data.length > 0) {
        const signalDate = new Date(signal.datetime);
        const lastKlineDate = new Date(data[data.length - 1].datetime);
        // Calculate difference in days
        const diffTime = lastKlineDate.getTime() - signalDate.getTime();
        const diffDays = Math.ceil(diffTime / (1000 * 60 * 60 * 24));
        maxAnalysisDays.value = Math.max(1, diffDays);
        // Adjust analysisDays if needed
        if (analysisDays.value > maxAnalysisDays.value) {
          analysisDays.value = maxAnalysisDays.value;
        }
      }
    } catch (error) {
      console.error('加载K线失败:', error);
      klineData.value = [];
    } finally {
      pendingSelectSymbol = null;
    }
  }

  // Watch analysisDays changes and recalculate all signals
  watch(analysisDays, (newDays) => {
    if (signals.value.length > 0) {
      calculateAllSignalsReturns(newDays);
    }
  });

  // Calculate returns for all signals with the given days
  async function calculateAllSignalsReturns(days: number) {
    signalsLoading.value = true;
    try {
      // Group signals by vt_symbol to load kline data efficiently
      const signalsBySymbol = new Map<string, Signal[]>();
      for (const signal of signals.value) {
        if (!signalsBySymbol.has(signal.vt_symbol)) {
          signalsBySymbol.set(signal.vt_symbol, []);
        }
        signalsBySymbol.get(signal.vt_symbol)!.push(signal);
      }

      // Process each symbol
      for (const [vtSymbol, symbolSignals] of signalsBySymbol) {
        const kline = await labApi.getKline(vtSymbol, period.value, 100);

        // Calculate returns for each signal of this symbol
        for (const signal of symbolSignals) {
          calculateSignalReturnWithData(signal, days, kline);
        }
      }
    } catch (error) {
      console.error('计算信号收益失败:', error);
    } finally {
      signalsLoading.value = false;
    }
  }

  function calculateSignalReturnWithData(signal: Signal, days: number, klineData: KlineData[]) {
    const signalDate = new Date(signal.datetime);
    const entryData = klineData.find(
      (k) => new Date(k.datetime).toDateString() === signalDate.toDateString()
    );

    if (!entryData) {
      signal.entry_price = undefined;
      signal.exit_price = undefined;
      signal.return = undefined;
      signal.max_drawdown = undefined;
      return;
    }

    const entryIndex = klineData.indexOf(entryData);
    const exitIndex = Math.min(entryIndex + days, klineData.length - 1);
    const exitData = klineData[exitIndex];

    if (!exitData) {
      signal.entry_price = undefined;
      signal.exit_price = undefined;
      signal.return = undefined;
      signal.max_drawdown = undefined;
      return;
    }

    const entryPrice = entryData.close;
    const exitPrice = exitData.close;
    const returnPct = ((exitPrice - entryPrice) / entryPrice) * 100;

    let maxDrawdown = 0;
    let maxPrice = entryPrice;
    for (let i = entryIndex; i <= exitIndex; i++) {
      const price = klineData[i]?.close;
      if (price === undefined) continue;
      if (price > maxPrice) {
        maxPrice = price;
      }
      const drawdown = ((maxPrice - price) / maxPrice) * 100;
      if (drawdown > maxDrawdown) {
        maxDrawdown = drawdown;
      }
    }

    signal.entry_price = entryPrice;
    signal.exit_price = exitPrice;
    signal.return = returnPct;
    signal.max_drawdown = maxDrawdown;

    // Update analysis result if this is the selected signal
    if (selectedSignal.value === signal) {
      analysisResult.value = {
        entryPrice,
        exitPrice,
        return: returnPct,
        maxDrawdown,
      };
    }
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

  // Track the latest kline request to handle race conditions
  let latestKlineRequest: string | null = null;

  async function loadKline(vtSymbol: string, days?: number) {
    const requestId = `${vtSymbol}-${Date.now()}`;
    latestKlineRequest = requestId;
    klineLoading.value = true;
    selectedStock.value = vtSymbol;
    try {
      const data = await labApi.getKline(vtSymbol, period.value, days || 100);
      // Only update if this is still the latest request
      if (latestKlineRequest === requestId) {
        klineData.value = data;
      }
    } catch (error) {
      console.error('加载K线失败:', error);
      if (latestKlineRequest === requestId) {
        klineData.value = [];
      }
    } finally {
      if (latestKlineRequest === requestId) {
        klineLoading.value = false;
      }
    }
  }

  function calculateSignalReturn(signal: Signal, days: number) {
    const signalDate = new Date(signal.datetime);
    const entryData = klineData.value.find(
      (k) => new Date(k.datetime).toDateString() === signalDate.toDateString()
    );

    if (!entryData) {
      analysisResult.value = null;
      // Store undefined return to signal
      signal.return = undefined;
      return;
    }

    const entryIndex = klineData.value.indexOf(entryData);
    const exitIndex = Math.min(entryIndex + days, klineData.value.length - 1);
    const exitData = klineData.value[exitIndex];

    if (!exitData) {
      analysisResult.value = null;
      signal.return = undefined;
      return;
    }

    const entryPrice = entryData.close;
    const exitPrice = exitData.close;
    const returnPct = ((exitPrice - entryPrice) / entryPrice) * 100;

    let maxDrawdown = 0;
    let maxPrice = entryPrice;
    for (let i = entryIndex; i <= exitIndex; i++) {
      const price = klineData.value[i]?.close;
      if (price === undefined) continue;
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

    // Store return to signal for list display
    signal.return = returnPct;
  }

  function setPeriod(newPeriod: '1d' | '1m') {
    period.value = newPeriod;
    if (selectedStock.value) {
      loadKline(selectedStock.value);
    }
  }

  async function switchIndex(indexCode: string) {
    if (indexCode === currentIndex.value) return;
    currentIndex.value = indexCode;
    localStorage.setItem(STORAGE_KEY_INDEX, indexCode);
    // Reload with new index
    if (currentProject.value) {
      await switchProject(currentProject.value, indexCode, currentDataSource.value);
    }
  }

  async function switchDataSource(dataSource: string) {
    if (dataSource === currentDataSource.value) return;
    currentDataSource.value = dataSource;
    localStorage.setItem(STORAGE_KEY_DATA_SOURCE, dataSource);
    // Reload with new data source
    if (currentProject.value) {
      await switchProject(currentProject.value, currentIndex.value, dataSource);
    }
  }

  async function init() {
    // Load project list first
    await loadProjects();

    // Restore saved values from localStorage
    const savedProject = localStorage.getItem(STORAGE_KEY_PROJECT);
    const savedIndex = localStorage.getItem(STORAGE_KEY_INDEX);
    const savedDataSource = localStorage.getItem(STORAGE_KEY_DATA_SOURCE);

    // Determine which project to use
    let targetProject = '';
    if (savedProject && projects.value.includes(savedProject)) {
      targetProject = savedProject;
    } else if (projects.value.length > 0) {
      targetProject = projects.value[0];
    }

    // Determine which index to use
    if (savedIndex && availableIndices.includes(savedIndex)) {
      currentIndex.value = savedIndex;
    } else {
      currentIndex.value = availableIndices[0];
    }

    // Determine which data source to use
    if (savedDataSource && availableDataSources.includes(savedDataSource)) {
      currentDataSource.value = savedDataSource;
    } else {
      currentDataSource.value = availableDataSources[0];
    }

    if (targetProject) {
      // Switch to the target project with restored index and data source
      await switchProject(targetProject, currentIndex.value, currentDataSource.value);
    } else {
      // No projects available, just load coverage
      await loadCoverage();
    }
  }

  return {
    currentProject,
    currentIndex,
    currentDataSource,
    projects,
    availableIndices,
    availableDataSources,
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
    maxAnalysisDays,
    analysisResult,
    loadProjects,
    switchProject,
    switchIndex,
    switchDataSource,
    loadCoverage,
    loadSignals,
    selectSignal,
    removeSignal,
    loadKline,
    calculateAllSignalsReturns,
    setPeriod,
    init,
  };
});
