import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import tailwindcss from '@tailwindcss/vite';
import { resolve } from 'node:path';

// Builds to ../static/dist with fixed entry names so Django templates can link them directly:
// app.js/app.css on every page, landing.js (S1), tracker.js (S4), city.js (S12). Shared code goes to chunks/.
export default defineConfig({
  plugins: [react(), tailwindcss()],
  base: '/static/dist/',
  build: {
    outDir: resolve(__dirname, '../static/dist'),
    emptyOutDir: true,
    rollupOptions: {
      input: {
        app: resolve(__dirname, 'src/main.js'),
        landing: resolve(__dirname, 'src/landing.js'),
        tracker: resolve(__dirname, 'src/tracker/main.jsx'),
        city: resolve(__dirname, 'src/city/main.jsx'),
      },
      output: {
        entryFileNames: '[name].js',
        chunkFileNames: 'chunks/[name].js',
        assetFileNames: (info) => (info.names?.[0]?.endsWith('.css') ? 'app.css' : 'assets/[name][extname]'),
      },
    },
  },
});
