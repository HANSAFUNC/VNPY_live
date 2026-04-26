<template>
  <aside class="sidebar" :class="{ collapsed: uiStore.sidebarCollapsed }">
    <el-menu
      :default-active="activeMenu"
      :collapse="uiStore.sidebarCollapsed"
      :collapse-transition="false"
      router
    >
      <el-menu-item index="/dashboard">
        <el-icon><DataBoard /></el-icon>
        <template #title>总览</template>
      </el-menu-item>

      <el-menu-item index="/trade">
        <el-icon><TrendCharts /></el-icon>
        <template #title>交易</template>
      </el-menu-item>

      <el-menu-item index="/logs">
        <el-icon><Document /></el-icon>
        <template #title>日志</template>
      </el-menu-item>
    </el-menu>

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
import { useRoute } from 'vue-router';
import { DataBoard, TrendCharts, Document, Fold, Expand } from '@element-plus/icons-vue';
import { useUIStore } from '@/stores';

const route = useRoute();
const uiStore = useUIStore();

const activeMenu = computed(() => route.path);
</script>

<style scoped lang="scss">
.sidebar {
  display: flex;
  flex-direction: column;
  width: 200px;
  background-color: var(--bg-primary);
  border-right: 1px solid var(--border-color);
  transition: width 0.3s;

  &.collapsed {
    width: 64px;
  }
}

.el-menu {
  flex: 1;
  border-right: none;
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
