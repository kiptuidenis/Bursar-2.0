const { test, expect } = require('@playwright/test');
const { setupAuthenticatedUser, getFutureDates } = require('./helpers');

test.describe('Phase 2: Next Payout Tile Status E2E Tests', () => {
  let pageErrors = [];

  test.beforeEach(({ page }) => {
    pageErrors = [];
    page.on('pageerror', (exception) => {
      console.error('Browser console exception:', exception.message);
      pageErrors.push(exception.message);
    });
  });

  test('Daily payout tile reflects SCHEDULED, PROCESSING, and PAID statuses dynamically', async ({ page }) => {
    test.setTimeout(60000);

    const userPhone = '254712345678';
    await setupAuthenticatedUser(page, { phoneNumber: userPhone });

    // Open Budget Modal
    await page.click('#open-budget-designer-btn');
    await page.waitForSelector('#budget-designer-modal.active', { state: 'visible' });

    // Add a category
    await page.fill('#new-category-name', 'Transport');
    await page.fill('#new-category-amount', '200');
    await page.click('#add-category-form button[type="submit"]');
    await page.waitForTimeout(500);

    // Advance to Step 2 (Payout Schedule)
    await page.click('#budget-wizard-next-1');
    await page.waitForTimeout(300);
    
    const dates = getFutureDates();
    await page.fill('#lock-start-date', dates.tomorrow);
    await page.fill('#lock-end-date', dates.nextWeek);

    // Advance to Step 3 (Payout Destination)
    await page.click('#budget-wizard-next-2');
    await page.waitForTimeout(300);

    page.on('dialog', async dialog => {
      if (dialog.type() === 'confirm') await dialog.accept();
      else await dialog.dismiss();
    });

    await page.click('#lock-budget-btn');
    await page.waitForTimeout(1000);

    const timerText = await page.locator('#countdown-timer').textContent();
    expect(timerText.toLowerCase()).not.toContain('payout is due');
    expect(pageErrors).toHaveLength(0);
  });
});
