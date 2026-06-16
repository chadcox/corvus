import { defineConfig } from '@playwright/test';

const useWebServer = process.env.PLAYWRIGHT_USE_WEBSERVER !== '0';
const baseURL = process.env.PLAYWRIGHT_BASE_URL ?? 'http://127.0.0.1:4173';

export default defineConfig({
  testDir: './e2e',
  timeout: 30_000,
  workers: process.env.CI ? 1 : undefined,
  expect: {
    timeout: 10_000,
  },
  use: {
    baseURL,
    headless: true,
  },
  webServer: useWebServer
    ? {
        command: 'npm run dev -- --host 127.0.0.1 --port 4173',
        port: 4173,
        reuseExistingServer: true,
        timeout: 120_000,
      }
    : undefined,
});
