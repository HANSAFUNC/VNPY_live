import type { ServerConfig } from '@/types';

const STORAGE_KEY = 'vnpy_servers';

/**
 * 获取所有保存的服务器配置
 */
export function getServers(): ServerConfig[] {
  try {
    const data = localStorage.getItem(STORAGE_KEY);
    return data ? JSON.parse(data) : [];
  } catch {
    return [];
  }
}

/**
 * 保存服务器配置
 */
export function saveServer(
  server: Omit<ServerConfig, 'id' | 'lastUsed'> & { id?: string }
): ServerConfig {
  const servers = getServers();
  const now = Date.now();
  const { id: serverId, ...serverData } = server;

  if (serverId) {
    // 更新现有配置
    const index = servers.findIndex((s) => s.id === serverId);
    if (index >= 0) {
      const updated: ServerConfig = { ...servers[index], ...serverData, id: serverId, lastUsed: now };
      servers[index] = updated;
      localStorage.setItem(STORAGE_KEY, JSON.stringify(servers));
      return updated;
    }
  }

  // 添加新配置
  const newServer: ServerConfig = {
    ...serverData,
    id: serverId ?? `server_${now}`,
    lastUsed: now,
  };
  servers.push(newServer);
  localStorage.setItem(STORAGE_KEY, JSON.stringify(servers));
  return newServer;
}

/**
 * 删除服务器配置
 */
export function deleteServer(id: string): void {
  const servers = getServers().filter((s) => s.id !== id);
  localStorage.setItem(STORAGE_KEY, JSON.stringify(servers));
}

/**
 * 获取最近使用的服务器
 */
export function getRecentServers(limit = 5): ServerConfig[] {
  return getServers()
    .sort((a, b) => b.lastUsed - a.lastUsed)
    .slice(0, limit);
}

/**
 * 获取默认服务器
 */
export function getDefaultServer(): ServerConfig | null {
  const servers = getServers();
  return servers.find((s) => s.isDefault) || servers[0] || null;
}

/**
 * 设置默认服务器
 */
export function setDefaultServer(id: string): void {
  const servers = getServers().map((s) => ({
    ...s,
    isDefault: s.id === id,
  }));
  localStorage.setItem(STORAGE_KEY, JSON.stringify(servers));
}

/**
 * 从 URL 生成 WebSocket URL
 */
export function generateWsUrl(httpUrl: string): string {
  return httpUrl.replace(/^http/, 'ws') + '/ws';
}

/**
 * 验证服务器地址格式
 */
export function validateServerUrl(url: string): boolean {
  try {
    const parsed = new URL(url);
    return parsed.protocol === 'http:' || parsed.protocol === 'https:';
  } catch {
    return false;
  }
}
