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

  test('Should support topbar drawer toggle and sidebar flat tab navigation for notifications', async ({ page }) => {
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

    // 1. Verify topbar notification bell button opens slide-over drawer
    const bellBtn = page.locator('#nav-notifications-btn');
    await expect(bellBtn).toBeVisible();

    await bellBtn.click();
    await page.waitForTimeout(300);

    const drawer = page.locator('#notifications-drawer');
    await expect(drawer).toBeVisible();

    // Close notification drawer via close button
    await page.click('#close-notifications-btn');
    await page.waitForTimeout(300);
    await expect(drawer).not.toBeVisible();

    // 2. Verify left sidebar notifications button acts like standard sidebar buttons (switches main view to flat tab)
    const sidebarNotifBtn = page.locator('#sidebar-notifications-btn');
    await expect(sidebarNotifBtn).toBeVisible();

    await sidebarNotifBtn.click();
    await page.waitForTimeout(300);

    const viewNotif = page.locator('#view-notifications');
    await expect(viewNotif).toBeVisible();
    await expect(sidebarNotifBtn).toHaveClass(/active/);

    expect(pageErrors).toHaveLength(0);
  });
});
