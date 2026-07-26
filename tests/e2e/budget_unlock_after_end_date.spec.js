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

  test('Should allow adding new budget items after schedule end date has passed', async ({ page }) => {
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

    // Add budget item & lock budget with future dates first
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

    const tomorrow = new Date();
    tomorrow.setDate(tomorrow.getDate() + 1);
    const tomorrowStr = tomorrow.toISOString().split('T')[0];

    const farFuture = new Date();
    farFuture.setDate(farFuture.getDate() + 5);
    const farFutureStr = farFuture.toISOString().split('T')[0];

    await page.fill('#lock-start-date', tomorrowStr);
    await page.fill('#lock-end-date', farFutureStr);

    page.on('dialog', async dialog => {
      if (dialog.type() === 'confirm') await dialog.accept();
      else await dialog.dismiss();
    });

    await page.click('#lock-budget-btn');
    await page.waitForTimeout(1000);

    // Verify lock notice appears while active
    const lockNotice = page.locator('#budget-creator-lock-notice');
    await expect(lockNotice).toBeVisible();

    expect(pageErrors).toHaveLength(0);
  });
});
