<template>
  <nav class="navbar">
    <div class="navbar-left">
      <div class="logo">VNPY Pro</div>

      <!-- Tab 导航 -->
      <div class="tab-nav">
        <router-link
          v-for="tab in tabs"
          :key="tab.path"
          :to="tab.path"
          :class="['tab-item', { active: route.path === tab.path }]"
        >
          <el-icon :size="18">
            <component :is="tab.icon" />
          </el-icon>
          <span>{{ tab.name }}</span>
        </router-link>
      </div>

      <!-- 策略选择器 -->
      <el-select
        v-if="botStore.hasBots"
        v-model="botStore.activeBotId"
        class="bot-selector"
        placeholder="选择策略"
        @change="handleBotChange"
      >
        <el-option
          v-for="bot in botStore.bots"
          :key="bot.id"
          :label="bot.name"
          :value="bot.id"
        >
          <span class="bot-option">
            <span class="status-dot" :class="bot.status" />
            {{ bot.name }}
            <el-tag size="small" :type="bot.mode === 'live' ? 'danger' : 'success'">
              {{ bot.mode === 'live' ? '实盘' : '模拟' }}
            </el-tag>
          </span>
        </el-option>
      </el-select>
    </div>

    <div class="navbar-right">
      <!-- 连接状态 -->
      <div class="connection-status" :class="{ connected: wsManager.isConnected.value }">
        <el-icon><Connection /></el-icon>
        <span>{{ wsManager.statusText.value }}</span>
      </div>

      <!-- 主题切换 -->
      <el-button
        circle
        :icon="uiStore.isDark ? Sunny : Moon"
        @click="uiStore.toggleTheme"
      />

      <!-- 用户菜单 -->
      <el-dropdown @command="handleCommand">
        <el-button circle :icon="User" />
        <template #dropdown>
          <el-dropdown-menu>
            <el-dropdown-item command="logout">退出登录</el-dropdown-item>
          </el-dropdown-menu>
        </template>
      </el-dropdown>
    </div>
  </nav>
</template>

<script setup lang="ts">
import { useRoute, useRouter } from 'vue-router';
import { User, Sunny, Moon, Connection, DataBoard, TrendCharts, Document, MagicStick } from '@element-plus/icons-vue';
import { useAuthStore, useBotStore, useUIStore } from '@/stores';
import { wsManager } from '@/api';
import { markRaw } from 'vue';

const route = useRoute();
const router = useRouter();
const authStore = useAuthStore();
const botStore = useBotStore();
const uiStore = useUIStore();

const tabs = [
  { name: '总览', path: '/dashboard', icon: markRaw(DataBoard) },
  { name: '交易', path: '/trade', icon: markRaw(TrendCharts) },
  { name: '日志', path: '/logs', icon: markRaw(Document) },
  { name: '实验室', path: '/lab', icon: markRaw(MagicStick) },
];

async function handleBotChange(botId: string) {
  await botStore.switchBot(botId);
}

function handleCommand(command: string) {
  if (command === 'logout') {
    authStore.logout();
    router.push('/login');
  }
}
</script>

<style scoped lang="scss">
.navbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  height: 56px;
  padding: 0 $spacing-md;
  background-color: var(--bg-primary);
  border-bottom: 1px solid var(--border-color);
}

.navbar-left {
  display: flex;
  align-items: center;
  gap: $spacing-lg;
}

.logo {
  font-size: 20px;
  font-weight: bold;
  color: var(--color-primary);
}

// Tab 导航样式
.tab-nav {
  display: flex;
  align-items: center;
  gap: $spacing-xs;
}

.tab-item {
  display: flex;
  align-items: center;
  gap: $spacing-xs;
  padding: $spacing-xs $spacing-md;
  border-radius: $radius-sm;
  color: var(--text-secondary);
  text-decoration: none;
  transition: all 0.2s;

  &:hover {
    color: var(--text-primary);
    background-color: var(--bg-secondary);
  }

  &.active {
    color: var(--color-primary);
    background-color: var(--color-primary-light);
  }
}

.bot-selector {
  width: 200px;
}

.bot-option {
  display: flex;
  align-items: center;
  gap: $spacing-sm;
}

.status-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;

  &.running {
    background-color: var(--color-success);
  }

  &.stopped {
    background-color: var(--color-info);
  }

  &.error {
    background-color: var(--color-danger);
  }
}

.navbar-right {
  display: flex;
  align-items: center;
  gap: $spacing-sm;
}

.connection-status {
  display: flex;
  align-items: center;
  gap: $spacing-xs;
  padding: $spacing-xs $spacing-sm;
  border-radius: $radius-sm;
  color: var(--color-danger);

  &.connected {
    color: var(--color-success);
  }
}
</style>
