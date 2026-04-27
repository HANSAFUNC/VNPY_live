<template>
  <div class="trade-view">
    <el-row :gutter="16">
      <el-col :span="16">
        <el-card shadow="never">
          <template #header>
            <div class="card-header">
              <span>K 线图</span>
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
            <el-empty description="K 线图组件待实现" />
          </div>
        </el-card>
      </el-col>
      <el-col :span="8">
        <el-card shadow="never">
          <template #header>
            <span>快速下单</span>
          </template>
          <el-form :model="orderForm" label-width="80px">
            <el-form-item label="合约">
              <el-select v-model="orderForm.symbol" placeholder="选择合约" filterable>
                <el-option
                  v-for="c in marketStore.contracts"
                  :key="c.vt_symbol"
                  :label="c.name"
                  :value="c.vt_symbol"
                />
              </el-select>
            </el-form-item>
            <el-form-item label="方向">
              <el-radio-group v-model="orderForm.direction">
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
              <el-input-number v-model="orderForm.price" :precision="2" :min="0" />
            </el-form-item>
            <el-form-item label="数量">
              <el-input-number v-model="orderForm.volume" :min="1" />
            </el-form-item>
            <el-form-item>
              <el-button type="primary" @click="handleSubmit">下单</el-button>
            </el-form-item>
          </el-form>
        </el-card>

        <el-card shadow="never" style="margin-top: 16px;">
          <template #header>
            <span>当前挂单</span>
          </template>
          <el-table :data="tradingStore.orders" size="small">
            <el-table-column prop="vt_symbol" label="代码" width="100" />
            <el-table-column prop="direction" label="方向" width="80">
              <template #default="{ row }">
                <el-tag :type="row.direction === 'BUY' ? 'danger' : 'success'" size="small">
                  {{ row.direction === 'BUY' ? '买' : '卖' }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="price" label="价格" width="100" />
            <el-table-column prop="volume" label="数量" width="80" />
            <el-table-column label="操作" width="80">
              <template #default="{ row }">
                <el-button type="danger" size="small" @click="handleCancel(row.vt_orderid)">
                  撤单
                </el-button>
              </template>
            </el-table-column>
          </el-table>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup lang="ts">
import { reactive } from 'vue';
import { ElMessage } from 'element-plus';
import { useTradingStore, useMarketStore } from '@/stores';
import { tradingApi } from '@/api';
import { KLINE_PERIODS } from '@/constants';

const tradingStore = useTradingStore();
const marketStore = useMarketStore();

const orderForm = reactive({
  symbol: '',
  direction: 'BUY' as 'BUY' | 'SELL',
  type: 'LIMIT' as 'LIMIT' | 'MARKET',
  price: 0,
  volume: 1,
});

async function handlePeriodChange(period: string) {
  if (marketStore.selectedSymbol) {
    await marketStore.fetchKline(marketStore.selectedSymbol, period as typeof marketStore.period);
  }
}

async function handleSubmit() {
  try {
    await tradingApi.sendOrder({
      symbol: orderForm.symbol.split('.')[0] ?? '',
      exchange: orderForm.symbol.split('.')[1] ?? '',
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
</script>

<style scoped lang="scss">
.trade-view {
  height: 100%;
}

.card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.chart-placeholder {
  height: 400px;
  display: flex;
  align-items: center;
  justify-content: center;
}
</style>
