import { defineConfig } from 'vite';
import vue from '@vitejs/plugin-vue';
import { fileURLToPath, URL } from 'node:url';

export default defineConfig({
  plugins: [vue()],
  clearScreen: false,
  root: './app',
  publicDir: '../public',
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./app', import.meta.url)),
    },
  },
  server: {
    port: 3000,
    strictPort: true,
    watch: {
      ignored: ['**/src-tauri/**', '**/dist/**', '**/tmp/**'],
    },
  },
  build: {
    outDir: '../dist',
    emptyOutDir: true,
  },
});
