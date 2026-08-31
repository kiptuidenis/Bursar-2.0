const { test, expect } = require('@playwright/test');
const { setupAuthenticatedUser } = require('./helpers');

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

    // 1. Authenticated session
    await setupAuthenticatedUser(page);

    // 2. Open Budget Designer Modal
    await page.click('#open-budget-designer-btn');
    await page.waitForTimeout(300);

    // Add a dummy category so total budget > 0 and lock controls appear
    await page.fill('#new-category-name', 'Groceries');
    await page.fill('#new-category-amount', '300');
    await page.click('#add-category-form button[type="submit"]');
    await page.waitForTimeout(500);

    // Advance to Step 2 (Payout Schedule)
    await page.click('#budget-wizard-next-1');
    await page.waitForTimeout(300);

    // 3. Test Today / Past Start Date validation (start_date must be > today)
    const todayStr = new Date().toISOString().split('T')[0];

    const farFuture = new Date();
    farFuture.setDate(farFuture.getDate() + 10);
    const farFutureStr = farFuture.toISOString().split('T')[0];

    // Try today's date as start date -> should be rejected because start_date must be strictly > today
    await page.fill('#lock-start-date', todayStr);
    await page.fill('#lock-end-date', farFutureStr);
    await page.click('#budget-wizard-next-2');
    await page.waitForTimeout(300);
    await page.click('#lock-budget-btn');
    await page.waitForTimeout(500);

    // Verify alert message for non-future date was captured
    expect(dialogMessages.some(m => m.toLowerCase().includes('future') || m.toLowerCase().includes('past'))).toBe(true);

    // 4. Test Matching Start and End Date validation
    // Use a date 5 days in future so it passes start_date > today check in all timezones (UTC vs EAT)
    const futureDate = new Date();
    futureDate.setDate(futureDate.getDate() + 5);
    const futureDateStr = futureDate.toISOString().split('T')[0];

    // Navigate back to Step 2 (Payout Schedule) to change dates
    await page.click('#budget-wizard-back-3');
    await page.waitForTimeout(300);

    await page.fill('#lock-start-date', futureDateStr);
    await page.fill('#lock-end-date', futureDateStr);
    await page.click('#budget-wizard-next-2');
    await page.waitForTimeout(300);
    await page.click('#lock-budget-btn');
    await page.waitForTimeout(500);

    expect(dialogMessages.some(m => /after start date|same/.test(m.toLowerCase()))).toBe(true);

    expect(pageErrors).toHaveLength(0);
  });
});
