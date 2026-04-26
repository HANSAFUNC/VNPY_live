<template>
  <div class="draggable-grid">
    <grid-layout
      v-model:layout="layout"
      :col-num="12"
      :row-height="30"
      :is-draggable="true"
      :is-resizable="true"
      :responsive="true"
      :breakpoints="RESPONSIVE_BREAKPOINTS"
      :cols="COLS_CONFIG"
      @layout-updated="handleLayoutUpdated"
    >
      <grid-item
        v-for="item in layout"
        :key="item.i"
        :x="item.x"
        :y="item.y"
        :w="item.w"
        :h="item.h"
        :i="item.i"
        :static="item.static"
      >
        <slot :name="item.i" :item="item">
          <div class="grid-item-placeholder">
            {{ item.i }}
          </div>
        </slot>
      </grid-item>
    </grid-layout>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import { GridLayout, GridItem } from 'vue-grid-layout';
import { useUIStore } from '@/stores';
import { RESPONSIVE_BREAKPOINTS, COLS_CONFIG } from '@/constants';
import type { GridItem as GridItemType } from '@/types';

const uiStore = useUIStore();

const layout = computed({
  get: () => uiStore.layout,
  set: (value: GridItemType[]) => {
    uiStore.updateLayout(value);
  },
});

function handleLayoutUpdated(newLayout: GridItemType[]) {
  uiStore.updateLayout(newLayout);
}
</script>

<style scoped lang="scss">
.draggable-grid {
  height: 100%;
}

:deep(.vue-grid-layout) {
  background-color: var(--bg-secondary);
}

:deep(.vue-grid-item) {
  background-color: var(--bg-primary);
  border-radius: $radius-md;
  box-shadow: $shadow-sm;
  overflow: hidden;
}

.grid-item-placeholder {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 100%;
  color: var(--text-tertiary);
}
</style>
