import { ref, computed } from 'vue';
import type { WebSocketMessage } from '@/types';
import { getToken } from '@/utils/storage';

export type MessageHandler<T = unknown> = (data: T) => void;

class WebSocketManager {
  private ws: WebSocket | null = null;
  private reconnectTimer: number | null = null;
  private handlers: Map<string, MessageHandler[]> = new Map();
  private reconnectCount = 0;
  private maxReconnectCount = 5;
  private intentionalClose = false;
  private wsUrl: string | null = null;

  public readonly isConnected = ref(false);
  public readonly statusText = computed(() =>
    this.isConnected.value ? '已连接' : '未连接'
  );

  /**
   * 设置 WebSocket URL
   */
  setUrl(url: string): void {
    this.wsUrl = url;
  }

  /**
   * 获取当前 WebSocket URL
   */
  getUrl(): string | null {
    return this.wsUrl;
  }

  connect(): void {
    // 防止重复连接
    if (this.ws) {
      this.ws.close();
      this.ws = null;
    }

    // 检查 URL 是否已设置
    if (!this.wsUrl) {
      console.error('WebSocket URL not set');
      return;
    }

    this.intentionalClose = false;

    const token = getToken();
    if (!token) return;

    const url = `${this.wsUrl}?token=${token}`;

    this.ws = new WebSocket(url);

    this.ws.onopen = () => {
      console.log('WebSocket connected');
      this.isConnected.value = true;
      this.reconnectCount = 0;
    };

    this.ws.onmessage = (event: MessageEvent) => {
      try {
        const message: WebSocketMessage = JSON.parse(event.data as string);
        this.handleMessage(message);
      } catch (e) {
        console.error('Failed to parse WebSocket message:', e);
      }
    };

    this.ws.onclose = () => {
      console.log('WebSocket closed');
      this.isConnected.value = false;
      if (!this.intentionalClose) {
        this.scheduleReconnect();
      }
    };

    this.ws.onerror = (error) => {
      console.error('WebSocket error:', error);
    };
  }

  disconnect(): void {
    this.intentionalClose = true;
    if (this.reconnectTimer !== null) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
    if (this.ws) {
      this.ws.close();
      this.ws = null;
    }
    this.isConnected.value = false;
  }

  private scheduleReconnect(): void {
    if (this.reconnectCount >= this.maxReconnectCount) {
      console.error('Max reconnection attempts reached');
      return;
    }

    const delay = Math.min(1000 * Math.pow(2, this.reconnectCount), 30000);
    this.reconnectCount++;

    this.reconnectTimer = window.setTimeout(() => {
      console.log(`Reconnecting... attempt ${this.reconnectCount}`);
      this.connect();
    }, delay);
  }

  on<T>(topic: string, handler: MessageHandler<T>): void {
    if (!this.handlers.has(topic)) {
      this.handlers.set(topic, []);
    }
    this.handlers.get(topic)!.push(handler as MessageHandler);
  }

  off<T>(topic: string, handler: MessageHandler<T>): void {
    const handlers = this.handlers.get(topic);
    if (handlers) {
      const index = handlers.indexOf(handler as MessageHandler);
      if (index > -1) {
        handlers.splice(index, 1);
      }
    }
  }

  private handleMessage(message: WebSocketMessage): void {
    const handlers = this.handlers.get(message.topic) ?? [];
    handlers.forEach((handler) => {
      try {
        handler(message.data);
      } catch (e) {
        console.error('Message handler error:', e);
      }
    });
  }
}

export const wsManager = new WebSocketManager();
