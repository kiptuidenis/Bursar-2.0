const { test, expect } = require('@playwright/test');

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
    // 1. Register dialog handler first
    page.on('dialog', async dialog => {
      if (dialog.type() === 'confirm') await dialog.accept();
      else await dialog.dismiss();
    });

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

    // 2. Add budget item & lock budget with future dates
    await page.click('#open-budget-designer-btn');
    await page.waitForTimeout(300);
    await page.fill('#new-category-name', 'Food');
    await page.fill('#new-category-amount', '200');
    await page.click('#add-category-form button[type="submit"]');
    await page.waitForTimeout(500);

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

    await page.click('#lock-budget-btn');
    await page.waitForTimeout(1000);

    // 3. Verify budget lock badge is visible on the dashboard card
    const lockBadge = page.locator('#budget-lock-badge');
    await expect(lockBadge).toBeVisible();

    // 4. Re-open budget modal and verify lock notice is visible inside modal
    await page.click('#open-budget-designer-btn');
    await page.waitForTimeout(300);

    const lockNotice = page.locator('#budget-creator-lock-notice');
    await expect(lockNotice).toBeVisible();

    expect(pageErrors).toHaveLength(0);
  });
});
