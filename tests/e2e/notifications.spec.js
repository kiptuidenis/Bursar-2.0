const { test, expect } = require('@playwright/test');
const { setupAuthenticatedUser } = require('./helpers');

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
    await setupAuthenticatedUser(page);

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
