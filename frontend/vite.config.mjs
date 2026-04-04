// frontend/vite.config.mjs
import { defineConfig } from 'vite';

export default defineConfig({
  base: '/static/editor/',
  build: {
    outDir: '../app/static/editor',
    emptyOutDir: false,
    cssCodeSplit: true,
    rollupOptions: {
      input: {
        board_new: './board_new.js',
        board_edit: './board_edit.js',
        board_view: './board_view.js',
        board_new_tiptap: './board_new_tiptap.js',
        board_edit_tiptap: './board_edit_tiptap.js',
      },
      output: {
        entryFileNames: '[name].js',
        chunkFileNames: 'assets/[name]-[hash].js',
        assetFileNames: (assetInfo) => {
          return assetInfo.name;
        },
      },
    },
  },
});

