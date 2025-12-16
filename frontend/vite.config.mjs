// frontend/vite.config.mjs
import { defineConfig } from 'vite';

export default defineConfig({
  build: {
    outDir: '../app/static/editor',
    emptyOutDir: false,
    cssCodeSplit: true,
    rollupOptions: {
      input: {
        board_new: './board_new.js',
        board_edit: './board_edit.js',
        board_view: './board_view.js', // 🔥 상세 페이지용 엔트리 추가
      },
      output: {
        entryFileNames: '[name].js',
        assetFileNames: (assetInfo) => {
          return assetInfo.name;
        },
      },
    },
  },
});

