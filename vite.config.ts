/**
 * Owns Vite build base path ('./' for GitLab Pages subpaths) and Vitest runner config.
 * Does not contain application runtime code.
 */
import { defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';

export default defineConfig({
  base: './',
  plugins: [react()],
  test: {
    environment: 'node',
    include: ['src/**/*.test.ts'],
  },
});
