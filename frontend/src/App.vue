<template>
  <a-layout class="app-shell">
    <a-layout-header class="site-header">
      <nav class="site-nav" aria-label="主导航">
        <router-link to="/" class="brand" aria-label="TripMind AI 首页">
          <img src="/tripmind-logo.svg" alt="" class="brand-logo" />
          <span>TripMind AI</span>
        </router-link>
        <div class="nav-actions">
          <router-link to="/" class="nav-link">开始规划</router-link>
          <router-link to="/history" class="nav-link">历史行程</router-link>
          <div class="nav-meta">
            <span class="nav-dot"></span>
            <span>多智能体旅行规划</span>
          </div>
        </div>
      </nav>
    </a-layout-header>

    <a-layout-content class="site-content">
      <router-view />
    </a-layout-content>

    <a-layout-footer class="site-footer">
      <span>© 2026 陈稳畅</span>
      <span class="footer-separator">·</span>
      <span>个人实习项目</span>
    </a-layout-footer>
  </a-layout>
</template>

<script setup lang="ts"></script>

<style>
:root {
  color: #1d1d1f;
  background: #f5f5f7;
  font-family: -apple-system, BlinkMacSystemFont, "SF Pro Display", "SF Pro Text", "Helvetica Neue", Arial, "Noto Sans SC", sans-serif;
  font-synthesis: none;
  text-rendering: optimizeLegibility;
  -webkit-font-smoothing: antialiased;
  --apple-blue: #0071e3;
  --apple-blue-hover: #0077ed;
  --apple-text: #1d1d1f;
  --apple-secondary: #6e6e73;
  --apple-surface: #ffffff;
  --apple-background: #f5f5f7;
  --apple-border: rgba(0, 0, 0, 0.08);
}

* {
  box-sizing: border-box;
}

html {
  scroll-behavior: smooth;
}

body {
  min-width: 320px;
  margin: 0;
  background: var(--apple-background);
}

button,
input,
textarea,
select {
  font: inherit;
}

::selection {
  background: rgba(0, 113, 227, 0.18);
}

#app,
.app-shell {
  min-height: 100vh;
}

.app-shell {
  background: var(--apple-background) !important;
}

.site-header {
  position: sticky;
  top: 0;
  z-index: 1000;
  height: 52px !important;
  padding: 0 24px !important;
  border-bottom: 1px solid rgba(0, 0, 0, 0.06);
  background: rgba(250, 250, 252, 0.82) !important;
  line-height: 52px !important;
  backdrop-filter: saturate(180%) blur(20px);
  -webkit-backdrop-filter: saturate(180%) blur(20px);
}

.site-nav {
  display: flex;
  align-items: center;
  justify-content: space-between;
  width: min(100%, 1440px);
  height: 100%;
  margin: 0 auto;
}

.brand {
  display: inline-flex;
  align-items: center;
  gap: 9px;
  color: var(--apple-text);
  font-size: 15px;
  font-weight: 650;
  line-height: 1;
  letter-spacing: -0.02em;
  text-decoration: none;
}

.brand:hover {
  color: var(--apple-text);
}

.brand-logo {
  display: block;
  width: 27px;
  height: 27px;
  border-radius: 8px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.12);
}

.nav-meta {
  display: flex;
  align-items: center;
  gap: 7px;
  color: var(--apple-secondary);
  font-size: 12px;
  line-height: 1;
}

.nav-actions {
  display: flex;
  height: 100%;
  align-items: center;
  gap: 5px;
}

.nav-link {
  display: inline-flex;
  height: 32px;
  padding: 0 12px;
  align-items: center;
  border-radius: 9px;
  color: #515154;
  font-size: 12px;
  font-weight: 600;
  line-height: 1;
  text-decoration: none;
  transition: background .18s ease, color .18s ease;
}

.nav-link:hover,
.nav-link.router-link-exact-active {
  background: #ededf0;
  color: #1d1d1f;
}

.nav-meta { margin-left: 10px; }

.nav-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: #34c759;
  box-shadow: 0 0 0 4px rgba(52, 199, 89, 0.1);
}

.site-content {
  background: transparent !important;
}

.site-footer {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 30px 20px !important;
  border-top: 1px solid rgba(0, 0, 0, 0.06);
  background: #f5f5f7 !important;
  color: #86868b;
  font-size: 12px;
  text-align: center;
}

.footer-separator {
  color: #c7c7cc;
}

.ant-btn {
  font-weight: 500;
  box-shadow: none;
}

.ant-btn-primary {
  background: var(--apple-blue);
}

.ant-btn-primary:not(:disabled):hover {
  background: var(--apple-blue-hover);
}

@media (max-width: 640px) {
  .site-header {
    padding: 0 16px !important;
  }

  .nav-meta {
    display: none;
  }

  .nav-link { padding-inline: 9px; font-size: 11px; }
}
</style>
