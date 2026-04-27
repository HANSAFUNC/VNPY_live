<template>
  <div class="logs-view">
    <el-card shadow="never">
      <template #header>
        <div class="logs-header">
          <div class="logs-filters">
            <el-select v-model="logsStore.filters.level" placeholder="日志级别" clearable @change="handleFilterChange">
              <el-option label="全部" value="all" />
              <el-option label="DEBUG" value="DEBUG" />
              <el-option label="INFO" value="INFO" />
              <el-option label="WARNING" value="WARNING" />
              <el-option label="ERROR" value="ERROR" />
              <el-option label="CRITICAL" value="CRITICAL" />
            </el-select>
            <el-select v-model="logsStore.filters.source" placeholder="来源" clearable @change="handleFilterChange">
              <el-option label="全部" value="all" />
              <el-option label="system" value="system" />
              <el-option label="trade" value="trade" />
              <el-option label="strategy" value="strategy" />
            </el-select>
            <el-input
              v-model="logsStore.filters.keyword"
              placeholder="搜索关键词"
              clearable
              style="width: 200px;"
              @change="handleFilterChange"
            />
          </div>
          <div class="logs-actions">
            <el-button @click="handleRefresh">刷新</el-button>
            <el-button @click="handleClear">清空</el-button>
          </div>
        </div>
      </template>

      <el-table :data="logsStore.filteredLogs" size="small" :max-height="600">
        <el-table-column prop="time" label="时间" width="160" />
        <el-table-column prop="level" label="级别" width="100">
          <template #default="{ row }">
            <el-tag :type="getLogLevelType(row.level)" size="small">
              {{ row.level }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="source" label="来源" width="100" />
        <el-table-column prop="message" label="消息" show-overflow-tooltip />
      </el-table>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { onMounted } from 'vue';
import { useLogsStore } from '@/stores';
import type { LogLevelColor } from '@/types';

const logsStore = useLogsStore();

function getLogLevelType(level: string): LogLevelColor {
  const map: Record<string, LogLevelColor> = {
    DEBUG: 'info',
    INFO: 'success',
    WARNING: 'warning',
    ERROR: 'danger',
    CRITICAL: 'danger',
  };
  return map[level] ?? 'info';
}

async function handleFilterChange() {
  await logsStore.fetchLogs();
}

async function handleRefresh() {
  await logsStore.fetchLogs();
}

function handleClear() {
  logsStore.clearLogs();
}

onMounted(() => {
  logsStore.fetchLogs();
});
</script>

<style scoped lang="scss">
.logs-view {
  height: 100%;
}

.logs-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.logs-filters {
  display: flex;
  gap: $spacing-sm;
}

.logs-actions {
  display: flex;
  gap: $spacing-sm;
}
</style>
