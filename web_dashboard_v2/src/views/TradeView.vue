<template>
  <div class="trade-view">
    <!-- 左侧：股票列表 -->
    <div class="stock-list-panel">
      <el-input
        v-model="stockSearch"
        placeholder="搜索股票..."
        clearable
        size="small"
        prefix-icon="Search"
      />
      <div class="stock-list">
        <div
          v-for="stock in filteredStocks"
          :key="stock.vt_symbol"
          :class="['stock-item', { active: selectedStock?.vt_symbol === stock.vt_symbol }]"
          @click="selectStock(stock)"
        >
          <div class="stock-name">{{ stock.name }}</div>
          <div class="stock-code">{{ stock.symbol }}</div>
          <div
            class="stock-change"
            :class="{ up: getStockChange(stock) > 0, down: getStockChange(stock) < 0 }"
          >
            {{ formatStockChange(stock) }}
          </div>
        </div>
        <el-empty v-if="filteredStocks.length === 0" description="暂无数据" :image-size="60" />
      </div>
    </div>

    <!-- 中间：K线图 -->
    <div class="chart-panel">
      <el-card shadow="never" class="chart-card">
        <template #header>
          <div class="card-header">
            <span>{{ selectedStock ? `${selectedStock.name} (${selectedStock.symbol})` : 'K 线图' }}</span>
            <el-select v-model="marketStore.period" size="small" @change="handlePeriodChange">
              <el-option
                v-for="p in KLINE_PERIODS"
                :key="p.value"
                :label="p.label"
                :value="p.value"
              />
            </el-select>
          </div>
        </template>
        <div class="chart-placeholder">
          <div v-if="selectedStock" class="chart-content">
            <!-- TODO: 集成 ECharts K线图 -->
            <el-empty description="K 线图组件待实现">
              <template #description>
                <div class="chart-info">
                  <p>当前合约: {{ selectedStock.vt_symbol }}</p>
                  <p>周期: {{ marketStore.period }}</p>
                  <p>最新价: {{ currentTick?.last_price ?? '-' }}</p>
                </div>
              </template>
            </el-empty>
          </div>
          <el-empty v-else description="请选择股票查看K线图" />
        </div>
      </el-card>
    </div>

    <!-- 右侧：交易面板 -->
    <div class="trading-panel">
      <el-card shadow="never" class="trade-card">
        <template #header>
          <span>交易面板</span>
        </template>

        <!-- 当前股票信息 -->
        <div v-if="selectedStock" class="stock-info">
          <div class="info-row">
            <span class="info-label">当前股票:</span>
            <span class="info-value">{{ selectedStock.name }}</span>
          </div>
          <div class="info-row">
            <span class="info-label">代码:</span>
            <span class="info-value">{{ selectedStock.symbol }}</span>
          </div>
          <div class="info-row">
            <span class="info-label">最新价:</span>
            <span class="info-value price">{{ currentTick?.last_price ?? '-' }}</span>
          </div>
          <div class="info-row">
            <span class="info-label">涨跌幅:</span>
            <span
              class="info-value"
              :class="{ up: getStockChange(selectedStock) > 0, down: getStockChange(selectedStock) < 0 }"
            >
              {{ formatStockChange(selectedStock) }}
            </span>
          </div>
        </div>
        <el-empty v-else description="请选择股票" :image-size="80" />

        <el-divider v-if="selectedStock" />

        <!-- 下单表单 -->
        <el-form v-if="selectedStock" :model="orderForm" label-width="60px" size="small">
          <el-form-item label="操作">
            <el-radio-group v-model="orderForm.direction" class="direction-group">
              <el-radio-button value="BUY">买入</el-radio-button>
              <el-radio-button value="SELL">卖出</el-radio-button>
            </el-radio-group>
          </el-form-item>

          <el-form-item label="类型">
            <el-radio-group v-model="orderForm.type">
              <el-radio-button value="LIMIT">限价</el-radio-button>
              <el-radio-button value="MARKET">市价</el-radio-button>
            </el-radio-group>
          </el-form-item>

          <el-form-item v-if="orderForm.type === 'LIMIT'" label="价格">
            <el-input-number
              v-model="orderForm.price"
              :precision="2"
              :min="0"
              :step="selectedStock.pricetick || 0.01"
              style="width: 100%"
            />
          </el-form-item>

          <el-form-item label="数量">
            <el-input-number
              v-model="orderForm.volume"
              :min="selectedStock.min_volume || 1"
              :step="selectedStock.min_volume || 1"
              style="width: 100%"
            />
          </el-form-item>

          <el-form-item>
            <el-button
              size="default"
              style="width: 100%"
              :type="orderForm.direction === 'BUY' ? 'danger' : 'success'"
              @click="handleSubmit"
            >
              {{ orderForm.direction === 'BUY' ? '买入' : '卖出' }}
            </el-button>
          </el-form-item>
        </el-form>
      </el-card>

      <!-- 当前挂单 -->
      <el-card shadow="never" class="orders-card" style="margin-top: $spacing-md;">
        <template #header>
          <span>当前挂单</span>
        </template>
        <el-table :data="tradingStore.orders" size="small" :max-height="200">
          <el-table-column prop="vt_symbol" label="代码" width="80" show-overflow-tooltip />
          <el-table-column prop="direction" label="方向" width="60">
            <template #default="{ row }">
              <el-tag :type="row.direction === 'BUY' ? 'danger' : 'success'" size="small">
                {{ row.direction === 'BUY' ? '买' : '卖' }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="price" label="价格" width="80" />
          <el-table-column prop="volume" label="数量" width="60" />
          <el-table-column label="操作" width="60">
            <template #default="{ row }">
              <el-button type="danger" size="small" @click="handleCancel(row.vt_orderid)">
                撤
              </el-button>
            </template>
          </el-table-column>
        </el-table>
      </el-card>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, reactive, onMounted } from 'vue';
import { ElMessage } from 'element-plus';
import { useTradingStore, useMarketStore, useAuthStore } from '@/stores';
import { tradingApi } from '@/api';
import { KLINE_PERIODS } from '@/constants';
import type { Contract } from '@/stores/market';

const tradingStore = useTradingStore();
const marketStore = useMarketStore();
const authStore = useAuthStore();

const stockSearch = ref('');

// 过滤后的股票列表
const filteredStocks = computed(() => {
  if (!stockSearch.value) {
    return marketStore.contracts;
  }
  const keyword = stockSearch.value.toLowerCase();
  return marketStore.contracts.filter(
    (c) =>
      c.name.toLowerCase().includes(keyword) ||
      c.symbol.toLowerCase().includes(keyword) ||
      c.vt_symbol.toLowerCase().includes(keyword)
  );
});

const selectedStock = computed(() =>
  marketStore.selectedSymbol
    ? marketStore.contracts.find((c) => c.vt_symbol === marketStore.selectedSymbol)
    : null
);

const currentTick = computed(() =>
  selectedStock.value ? marketStore.ticks[selectedStock.value.vt_symbol] : null
);

const orderForm = reactive({
  direction: 'BUY' as 'BUY' | 'SELL',
  type: 'LIMIT' as 'LIMIT' | 'MARKET',
  price: 0,
  volume: 1,
});

// 获取股票涨跌幅（模拟数据）
function getStockChange(stock: Contract): number {
  const tick = marketStore.ticks[stock.vt_symbol];
  if (!tick) return 0;
  // 模拟计算涨跌幅
  return ((tick.last_price - tick.bid_price_1) / tick.bid_price_1) * 100;
}

function formatStockChange(stock: Contract): string {
  const change = getStockChange(stock);
  const sign = change > 0 ? '+' : '';
  return `${sign}${change.toFixed(2)}%`;
}

function selectStock(stock: Contract) {
  marketStore.setSelectedSymbol(stock.vt_symbol);
  // 设置默认价格
  const tick = marketStore.ticks[stock.vt_symbol];
  if (tick) {
    orderForm.price = tick.last_price;
  }
}

async function handlePeriodChange(period: string) {
  if (marketStore.selectedSymbol) {
    await marketStore.fetchKline(marketStore.selectedSymbol, period as typeof marketStore.period);
  }
}

async function handleSubmit() {
  if (!selectedStock.value) {
    ElMessage.warning('请先选择股票');
    return;
  }

  try {
    await tradingApi.sendOrder({
      symbol: selectedStock.value.symbol,
      exchange: selectedStock.value.exchange,
      direction: orderForm.direction,
      type: orderForm.type,
      volume: orderForm.volume,
      price: orderForm.price,
    });
    ElMessage.success('下单成功');
  } catch {
    ElMessage.error('下单失败');
  }
}

async function handleCancel(vtOrderid: string) {
  try {
    await tradingApi.cancelOrder(vtOrderid);
    ElMessage.success('撤单成功');
  } catch {
    ElMessage.error('撤单失败');
  }
}

onMounted(() => {
  // 只有在登录状态下才请求数据
  if (authStore.isLoggedIn) {
    marketStore.fetchContracts();
  }
});
</script>

<style scoped lang="scss">
.trade-view {
  display: flex;
  gap: $spacing-md;
  height: 100%;
  overflow: hidden;
}

// 左侧股票列表
.stock-list-panel {
  width: 200px;
  display: flex;
  flex-direction: column;
  background-color: var(--bg-primary);
  border-radius: $radius-md;
  border: 1px solid var(--border-color);
  padding: $spacing-sm;
}

.stock-list {
  flex: 1;
  overflow-y: auto;
  margin-top: $spacing-sm;
}

.stock-item {
  display: flex;
  flex-direction: column;
  padding: $spacing-sm;
  border-radius: $radius-sm;
  cursor: pointer;
  transition: all 0.2s;
  border-bottom: 1px solid var(--border-color-light);

  &:hover {
    background-color: var(--bg-secondary);
  }

  &.active {
    background-color: var(--color-primary-light);
  }

  &:last-child {
    border-bottom: none;
  }
}

.stock-name {
  font-size: 14px;
  font-weight: 500;
  color: var(--text-primary);
}

.stock-code {
  font-size: 12px;
  color: var(--text-secondary);
}

.stock-change {
  font-size: 12px;
  font-weight: 600;

  &.up {
    color: var(--color-danger);
  }

  &.down {
    color: var(--color-success);
  }
}

// 中间K线图
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

.chart-placeholder {
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
}

.chart-content {
  width: 100%;
  height: 100%;
}

.chart-info {
  text-align: left;
  color: var(--text-secondary);

  p {
    margin: $spacing-xs 0;
  }
}

// 右侧交易面板
.trading-panel {
  width: 280px;
  display: flex;
  flex-direction: column;
}

.trade-card {
  flex: 1;
}

.stock-info {
  margin-bottom: $spacing-md;
}

.info-row {
  display: flex;
  justify-content: space-between;
  padding: $spacing-xs 0;
}

.info-label {
  color: var(--text-secondary);
  font-size: 13px;
}

.info-value {
  font-weight: 500;

  &.price {
    font-size: 16px;
    color: var(--color-primary);
  }

  &.up {
    color: var(--color-danger);
  }

  &.down {
    color: var(--color-success);
  }
}

.direction-group {
  width: 100%;

  :deep(.el-radio-button) {
    flex: 1;
  }
}

.orders-card {
  flex-shrink: 0;
}

// 响应式
@media (max-width: 1200px) {
  .trade-view {
    flex-direction: column;
  }

  .stock-list-panel {
    width: 100%;
    height: 200px;
    flex-direction: row;

    .el-input {
      width: 200px;
    }

    .stock-list {
      flex: 1;
      margin-top: 0;
      margin-left: $spacing-sm;
      display: flex;
      gap: $spacing-sm;
      overflow-x: auto;
      overflow-y: hidden;
    }

    .stock-item {
      min-width: 150px;
      border-bottom: none;
      border-right: 1px solid var(--border-color-light);
    }
  }

  .trading-panel {
    width: 100%;
    flex-direction: row;
    gap: $spacing-md;

    .trade-card,
    .orders-card {
      flex: 1;
      margin-top: 0 !important;
    }
  }
}
</style>
