const { test, expect } = require('@playwright/test');
const { setupAuthenticatedUser } = require('./helpers');

test.describe('Phase 2: Next Payout Tile Status E2E Tests', () => {
  let pageErrors = [];

  test.beforeEach(({ page }) => {
    pageErrors = [];
    page.on('pageerror', (exception) => {
      console.error('Browser console exception:', exception.message);
      pageErrors.push(exception.message);
    });
  });

  test('Should display "No Budget Set" when budget is unlocked', async ({ page }) => {
    await setupAuthenticatedUser(page);

    // Default tile state should say "No Budget Set"
    const timerLabel = page.locator('#countdown-timer');
    await expect(timerLabel).toContainText('No Budget Set');
  });

  test('Should NOT display "Payout is due" when time passes without a failed 3rd-party API attempt', async ({ page }) => {
    await setupAuthenticatedUser(page);

    // Add budget item & lock budget
    await page.click('#open-budget-designer-btn');
    await page.waitForTimeout(300);
    await page.fill('#new-category-name', 'Food');
    await page.fill('#new-category-amount', '200');
    await page.click('#add-category-form button[type="submit"]');
    await page.waitForTimeout(500);

    // Advance to Step 2 (Payout Schedule)
    await page.click('#budget-wizard-next-1');
    await page.waitForTimeout(300);
    
    const tomorrow = new Date();
    tomorrow.setDate(tomorrow.getDate() + 1);
    const tomorrowStr = tomorrow.toISOString().split('T')[0];

    const farFuture = new Date();
    farFuture.setDate(farFuture.getDate() + 5);
    const farFutureStr = farFuture.toISOString().split('T')[0];

    await page.fill('#lock-start-date', tomorrowStr);
    await page.fill('#lock-end-date', farFutureStr);

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
