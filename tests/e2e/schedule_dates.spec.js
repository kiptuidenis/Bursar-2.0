const { test, expect } = require('@playwright/test');

test.describe('Phase 1: Scheduling Date Validation E2E Tests', () => {
  let pageErrors = [];

  test.beforeEach(({ page }) => {
    pageErrors = [];
    page.on('pageerror', (exception) => {
      console.error('Browser console exception:', exception.message);
      pageErrors.push(exception.message);
    });
  });

  test('Should reject entering today or past start date and matching start/end dates in budget lock modal', async ({ page }) => {
    const dialogMessages = [];
    page.on('dialog', async dialog => {
      dialogMessages.push(dialog.message());
      if (dialog.type() === 'confirm') {
        await dialog.accept();
      } else {
        await dialog.dismiss();
      }
    });

    // 1. Visit signup page and register a fresh user
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
    expect(page.url()).toContain('/dashboard');

    // 2. Open Budget Designer Modal
    await page.click('#open-budget-designer-btn');
    await page.waitForTimeout(300);

    // Add a dummy category so total budget > 0 and lock controls appear
    await page.fill('#new-category-name', 'Groceries');
    await page.fill('#new-category-amount', '300');
    await page.click('#add-category-form button[type="submit"]');
    await page.waitForTimeout(500);

    // Expand Payout Schedule section
    await page.evaluate(() => {
      const scheduleBody = document.getElementById('schedule-collapse-body');
      if (scheduleBody) scheduleBody.style.display = 'block';
    });
    await page.waitForTimeout(300);

    // 3. Test Today / Past Start Date validation (start_date must be > today, i.e., tomorrow onwards)
    const todayStr = new Date().toISOString().split('T')[0];

    const tomorrow = new Date();
    tomorrow.setDate(tomorrow.getDate() + 1);
    const tomorrowStr = tomorrow.toISOString().split('T')[0];

    const farFuture = new Date();
    farFuture.setDate(farFuture.getDate() + 5);
    const farFutureStr = farFuture.toISOString().split('T')[0];

    // Try today's date as start date -> should be rejected because start_date must be strictly > today
    await page.fill('#lock-start-date', todayStr);
    await page.fill('#lock-end-date', farFutureStr);
    await page.click('#lock-budget-btn');
    await page.waitForTimeout(1000);

    // Verify alert message for non-future date was captured
    expect(dialogMessages.some(m => m.toLowerCase().includes('future') || m.toLowerCase().includes('past'))).toBe(true);

    // 4. Test Matching Start and End Date validation
    await page.fill('#lock-start-date', tomorrowStr);
    await page.fill('#lock-end-date', tomorrowStr);
    await page.click('#lock-budget-btn');
    await page.waitForTimeout(1000);

    expect(dialogMessages.some(m => /after start date|same/.test(m.toLowerCase()))).toBe(true);

    expect(pageErrors).toHaveLength(0);
  });
});
