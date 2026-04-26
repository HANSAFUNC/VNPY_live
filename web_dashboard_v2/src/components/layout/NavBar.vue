<template>
  <nav class="navbar">
    <div class="navbar-left">
      <div class="logo">VNPY Pro</div>

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
import { useRouter } from 'vue-router';
import { User, Sunny, Moon, Connection } from '@element-plus/icons-vue';
import { useAuthStore, useBotStore, useUIStore } from '@/stores';
import { wsManager } from '@/api';

const router = useRouter();
const authStore = useAuthStore();
const botStore = useBotStore();
const uiStore = useUIStore();

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
