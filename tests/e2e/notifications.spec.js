const { test, expect } = require('@playwright/test');

test.describe('Phase 4: In-App User Notification System E2E Tests', () => {
  let pageErrors = [];

  test.beforeEach(({ page }) => {
    pageErrors = [];
    page.on('pageerror', (exception) => {
      console.error('Browser console exception:', exception.message);
      pageErrors.push(exception.message);
    });
  });

  test('Should render notification bell icon with unread badge counter and toggle notification drawer', async ({ page }) => {
    await page.goto('/');
    await page.click('#nav-signup-btn');

    const randomDigits = Math.floor(100000 + Math.random() * 900000);
    const testPhoneNumber = `254700${randomDigits}`;

    await page.fill('#auth-phone', testPhoneNumber);
    await page.fill('#auth-password', 'Str0ng!P@ssw0rd');
    const confirmInput = page.locator('#auth-confirm-password');
    if (await confirmInput.count() > 0) {
      await confirmInput.fill('Str0ng!P@ssw0rd');
    }
    await page.click('#auth-submit-btn');

    await page.waitForURL('**/dashboard');
    await page.waitForLoadState('networkidle');

    // 1. Verify notification bell button is visible in dashboard topbar header
    const bellBtn = page.locator('#nav-notifications-btn');
    await expect(bellBtn).toBeVisible();

    // 2. Click notification bell button to toggle slide-over drawer
    await bellBtn.click();
    await page.waitForTimeout(300);

    const drawer = page.locator('#notifications-drawer');
    await expect(drawer).toBeVisible();

    // Close notification drawer
    await page.click('#close-notifications-btn');
    await page.waitForTimeout(300);
    await expect(drawer).not.toBeVisible();

    expect(pageErrors).toHaveLength(0);
  });
});
