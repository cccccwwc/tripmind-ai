import { defineConfig } from 'vitest/config'
import vue from '@vitejs/plugin-vue'
import { resolve } from 'path'

// https://vite.dev/config/
export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      '@': resolve(__dirname, 'src')
    }
  },
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true
      }
    }
  },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./src/tests/setup.ts'],
    clearMocks: true,
    // 地图相关测试必须显式使用测试配置，不能依赖开发者本机的 .env。
    // 这样本地与 GitHub Actions 都会进入相同的 JS 地图分支。
    env: {
      VITE_AMAP_WEB_JS_KEY: 'test-amap-key',
      VITE_AMAP_SECURITY_JS_CODE: 'test-security-code'
    }
  }
})
