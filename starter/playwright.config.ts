/**
 * Playwright E2E Test Configuration
 *
 * IMPORTANT: E2E tests run on TEST PORTS, not dev ports.
 * This prevents conflicts with running dev servers.
 *
 * Test Ports (from CLAUDE.md — NEVER CHANGE):
 *   Website:   4000
 *   API:       4010
 *   Dashboard: 4020
 *
 * Dev Ports (for development — NOT used in tests):
 *   Website:   3000
 *   API:       3001
 *   Dashboard: 3002
 */

import { defineConfig, devices } from '@playwright/test';

export default defineConfig({
  testDir: './tests/e2e',
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: process.env.CI ? 1 : undefined,
  reporter: [
    ['html', { outputFolder: 'playwright-report' }],
    ['list'],
  ],
  outputDir: 'test-results',

  use: {
    /* Base URL for E2E tests — uses TEST port, not dev port */
    baseURL: 'http://localhost:4000',
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
  },

  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
    {
      name: 'firefox',
      use: { ...devices['Desktop Firefox'] },
    },
    {
      name: 'webkit',
      use: { ...devices['Desktop Safari'] },
    },
    {
      name: 'mobile-chrome',
      use: { ...devices['Pixel 5'] },
    },
  ],

  /* Start services on TEST ports before running E2E tests */
  webServer: [
    {
      command: 'pnpm dev:test:website',
      port: 4000,
      reuseExistingServer: !process.env.CI,
      timeout: 30_000,
    },
    {
      command: 'pnpm dev:test:api',
      port: 4010,
      reuseExistingServer: !process.env.CI,
      timeout: 30_000,
    },
    {
      command: 'pnpm dev:test:dashboard',
      port: 4020,
      reuseExistingServer: !process.env.CI,
      timeout: 30_000,
    },
  ],
});
