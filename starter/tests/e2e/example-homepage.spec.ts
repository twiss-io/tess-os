/**
 * Example E2E Test — Homepage
 *
 * This is a reference test showing the CORRECT pattern for E2E tests.
 * Every test must have explicit success criteria:
 *   - URL verification
 *   - Element visibility
 *   - Content/data verification
 *   - Error state coverage
 *
 * NOTE: These tests are SKIPPED by default because they depend on
 * project-specific routes/content. When you add pages to your project:
 * 1. Remove the .skip from the describe block
 * 2. Update selectors and assertions to match your actual pages
 * 3. Run: pnpm test:e2e
 */

import { test, expect } from '@playwright/test';

// SKIPPED — Remove .skip when your project has actual pages to test
test.describe.skip('Homepage (example — customize for your project)', () => {
  test.describe('happy path', () => {
    test('should load with correct title and navigation', async ({ page }) => {
      await page.goto('/');

      // URL verification
      await expect(page).toHaveURL('/');

      // Element visibility — key UI elements present
      await expect(page.locator('h1')).toBeVisible();

      // Content verification — update these to match YOUR project
      await expect(page).toHaveTitle(/My Project/);
      await expect(page.locator('h1')).toContainText('Welcome');
    });

    test('should navigate to about page from nav link', async ({ page }) => {
      await page.goto('/');
      await page.click('a[href="/about"]');

      // URL changed correctly
      await expect(page).toHaveURL('/about');

      // About page content loaded
      await expect(page.locator('h1')).toContainText('About');
    });
  });

  test.describe('error handling', () => {
    test('should show 404 page for unknown routes', async ({ page }) => {
      const response = await page.goto('/this-page-does-not-exist');

      // Correct status code
      expect(response?.status()).toBe(404);

      // Error page visible with helpful message
      await expect(page.locator('h1')).toContainText('Not Found');
      await expect(page.locator('a[href="/"]')).toBeVisible();
    });
  });

  test.describe('responsive behavior', () => {
    test('should show mobile menu on small screens', async ({ page }) => {
      await page.setViewportSize({ width: 375, height: 667 });
      await page.goto('/');

      // Desktop nav hidden
      await expect(page.locator('nav.desktop-nav')).not.toBeVisible();

      // Mobile menu button visible
      await expect(page.locator('button.menu-toggle')).toBeVisible();
    });
  });
});
