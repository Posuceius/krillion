/**
 * Owns Vite build base path ('./' for GitLab Pages subpaths), manifest code-splitting, and Vitest runner config.
 * Does not contain application runtime code.
 */
import { defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';

export default defineConfig({
  base: './',
  plugins: [react()],
  build: {
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (id.includes('src/data/manifest.ts')) {
            return 'manifest';
          }
          return undefined;
        },
      },
    },
  },
  test: {
    environment: 'node',
    include: ['src/**/*.test.ts'],
  },
});
