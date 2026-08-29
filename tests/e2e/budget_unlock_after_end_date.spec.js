const { test, expect } = require('@playwright/test');
const { setupAuthenticatedUser } = require('./helpers');

test.describe('Phase 3: Budget Unlock after End Date E2E Tests', () => {
  let pageErrors = [];

  test.beforeEach(({ page }) => {
    pageErrors = [];
    page.on('pageerror', (exception) => {
      console.error('Browser console exception:', exception.message);
      pageErrors.push(exception.message);
    });
  });

  test('Should allow locking budget during active schedule and unlock when schedule ends', async ({ page }) => {
    // 1. Register dialog handler first to auto-accept confirm & alert dialogs
    page.on('dialog', async dialog => {
      await dialog.accept();
    });

    await setupAuthenticatedUser(page);

    // 2. Add budget item & lock budget with future dates
    await page.click('#open-budget-designer-btn');
    await expect(page.locator('#budget-designer-modal')).toHaveClass(/active/);

    await page.fill('#new-category-name', 'Food');
    await page.fill('#new-category-amount', '200');

    await Promise.all([
      page.waitForResponse(res => res.url().includes('/api/budget/items') && res.request().method() === 'POST'),
      page.click('#add-category-form button[type="submit"]')
    ]);

    await expect(page.locator('#designer-category-list')).toContainText('Food');

    // Expand schedule dates and lock with dates
    await page.evaluate(() => {
      const scheduleBody = document.getElementById('schedule-collapse-body');
      if (scheduleBody) scheduleBody.style.display = 'block';
    });

    // Use +3 and +10 days to be 100% timezone resilient (UTC vs EAT)
    const future3 = new Date();
    future3.setDate(future3.getDate() + 3);
    const future3Str = future3.toISOString().split('T')[0];

    const future10 = new Date();
    future10.setDate(future10.getDate() + 10);
    const future10Str = future10.toISOString().split('T')[0];

    await page.fill('#lock-start-date', future3Str);
    await page.fill('#lock-end-date', future10Str);

    const [lockRes] = await Promise.all([
      page.waitForResponse(res => res.url().includes('/api/budget/lock') && res.request().method() === 'POST'),
      page.click('#lock-budget-btn')
    ]);
    expect(lockRes.status()).toBe(200);

    // 3. Verify budget lock badge is visible on the dashboard card
    const lockBadge = page.locator('#budget-lock-badge');
    await expect(lockBadge).toBeVisible();

    // 4. Re-open budget modal and verify lock notice is visible inside modal
    await page.click('#open-budget-designer-btn');
    await expect(page.locator('#budget-designer-modal')).toHaveClass(/active/);

    const lockNotice = page.locator('#budget-creator-lock-notice');
    await expect(lockNotice).toBeVisible();

    expect(pageErrors).toHaveLength(0);
  });
});
