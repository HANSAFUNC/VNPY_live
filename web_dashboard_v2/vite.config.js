import { defineConfig } from 'vite';
import vue from '@vitejs/plugin-vue';
import { resolve } from 'path';
export default defineConfig({
    plugins: [vue()],
    resolve: {
        alias: {
            '@': resolve(__dirname, 'src'),
        },
    },
    css: {
        preprocessorOptions: {
            scss: {
                additionalData: `@use "@/assets/styles/variables" as *;`,
            },
        },
    },
    build: {
        outDir: 'dist',
        rollupOptions: {
            output: {
                manualChunks: {
                    'element-plus': ['element-plus', '@element-plus/icons-vue'],
                    echarts: ['echarts', 'vue-echarts'],
                    'vue-grid-layout': ['vue-grid-layout'],
                },
            },
        },
    },
    server: {
        port: 3000,
        proxy: {
            // WebSocket 代理
            '/ws': {
                target: 'ws://localhost:8000',
                changeOrigin: true,
                ws: true,
            },
            // API 代理 - 直接转发 /api/* 到后端
            '/api': {
                target: 'http://localhost:8000',
                changeOrigin: true,
                configure: (proxy) => {
                    proxy.on('proxyReq', (proxyReq, req) => {
                        // 转发 Authorization 头
                        const auth = req.headers.authorization;
                        if (auth) {
                            proxyReq.setHeader('Authorization', auth);
                        }
                    });
                },
            },
        },
    },
});
