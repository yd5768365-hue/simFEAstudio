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
    port: 1420,
    strictPort: true,
    watch: {
      ignored: ['**/src-tauri/**', '**/dist/**', '**/tmp/**'],
    },
  },
  build: {
    outDir: '../dist',
    emptyOutDir: true,
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (id.includes('node_modules/@kitware/vtk.js')) return 'vtk'
          if (id.includes('node_modules/katex')) return 'katex'
          if (id.includes('node_modules/markdown-it')) return 'markdown'
        },
      },
    },
  },
});
