/**
 * 安全获取 localStorage
 */
export function getItem<T>(key: string, defaultValue: T): T {
  try {
    const item = localStorage.getItem(key);
    return item ? JSON.parse(item) as T : defaultValue;
  } catch {
    return defaultValue;
  }
}

/**
 * 安全设置 localStorage
 */
export function setItem<T>(key: string, value: T): void {
  try {
    localStorage.setItem(key, JSON.stringify(value));
  } catch (e) {
    console.error('Storage setItem failed:', e);
  }
}

/**
 * 移除 localStorage
 */
export function removeItem(key: string): void {
  try {
    localStorage.removeItem(key);
  } catch (e) {
    console.error('Storage removeItem failed:', e);
  }
}

/**
 * 获取 Token
 */
export function getToken(): string | null {
  try {
    return localStorage.getItem('vnpy_token');
  } catch {
    return null;
  }
}

/**
 * 设置 Token
 */
export function setToken(token: string): void {
  try {
    localStorage.setItem('vnpy_token', token);
  } catch (e) {
    console.error('Storage setToken failed:', e);
  }
}

/**
 * 清除 Token
 */
export function clearToken(): void {
  try {
    localStorage.removeItem('vnpy_token');
  } catch (e) {
    console.error('Storage clearToken failed:', e);
  }
}
