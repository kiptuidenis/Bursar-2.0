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

  test('1. Should support topbar drawer toggle and sidebar flat tab navigation for notifications', async ({ page }) => {
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

  test('2. Should mark unread notification as read when clicking directly on notification card', async ({ page }) => {
    await setupAuthenticatedUser(page, { seedNotifications: true });

    // Open notifications drawer
    await page.click('#nav-notifications-btn');
    const drawer = page.locator('#notifications-drawer');
    await expect(drawer).toBeVisible();

    // Verify unread badge is 2
    const navBadge = page.locator('#nav-notifications-badge');
    await expect(navBadge).toBeVisible();
    await expect(navBadge).toHaveText('2');

    // Click directly on first unread notification card
    const firstNotifCard = page.locator('.notification-item.unread').first();
    await expect(firstNotifCard).toBeVisible();
    await firstNotifCard.click();

    // Verify badge decrements to 1
    await expect(navBadge).toHaveText('1');

    expect(pageErrors).toHaveLength(0);
  });

  test('3. Should mark all notifications as read and clear unread badges when clicking Mark all as read button', async ({ page }) => {
    await setupAuthenticatedUser(page, { seedNotifications: true });

    // Open notifications drawer
    await page.click('#nav-notifications-btn');
    const drawer = page.locator('#notifications-drawer');
    await expect(drawer).toBeVisible();

    // Verify unread badge is visible
    const navBadge = page.locator('#nav-notifications-badge');
    await expect(navBadge).toBeVisible();
    await expect(navBadge).toHaveText('2');

    // Click "Mark all as read" button
    const markAllBtn = page.locator('#mark-all-read-btn');
    await expect(markAllBtn).toBeVisible();
    await markAllBtn.click();

    // Verify unread badge is cleared / hidden
    await expect(navBadge).toBeHidden();

    // Verify no unread items remain
    const unreadItems = page.locator('.notification-item.unread');
    await expect(unreadItems).toHaveCount(0);

    expect(pageErrors).toHaveLength(0);
  });

});
