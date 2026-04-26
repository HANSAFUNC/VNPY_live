<template>
  <div class="dashboard-view">
    <DraggableGrid>
      <template #account-summary>
        <AccountSummaryWidget />
      </template>
      <template #positions>
        <PositionWidget />
      </template>
      <template #trade-history>
        <TradeHistoryWidget />
      </template>
      <template #signals>
        <SignalWidget />
      </template>
      <template #stats>
        <StatWidget />
      </template>
    </DraggableGrid>
  </div>
</template>

<script setup lang="ts">
import { onMounted } from 'vue';
import DraggableGrid from '@/components/layout/DraggableGrid.vue';
import AccountSummaryWidget from '@/widgets/AccountSummaryWidget.vue';
import PositionWidget from '@/widgets/PositionWidget.vue';
import TradeHistoryWidget from '@/widgets/TradeHistoryWidget.vue';
import SignalWidget from '@/widgets/SignalWidget.vue';
import StatWidget from '@/widgets/StatWidget.vue';
import { useTradingStore } from '@/stores';

const tradingStore = useTradingStore();

onMounted(() => {
  tradingStore.fetchAllData();
});
</script>

<style scoped lang="scss">
.dashboard-view {
  height: 100%;
}
</style>
