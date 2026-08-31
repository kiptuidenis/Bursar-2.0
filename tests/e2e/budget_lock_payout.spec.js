const { test, expect } = require('@playwright/test');
const { setupEmailOnlyUser } = require('./helpers');

test.describe('Budget Lock Payout Phone Configuration Flow', () => {

  test('Email user deposits from custom phone, configures payout phone during budget lock', async ({ page }) => {
    test.setTimeout(60000);
    page.on('dialog', async dialog => await dialog.accept());

    await setupEmailOnlyUser(page);

    // 1. Flip debit card and deposit KES 5000 using custom payer phone
    await page.click('#debit-card-container');
    await page.waitForTimeout(600);
    await page.click('#open-deposit-btn');
    await expect(page.locator('#deposit-modal')).toHaveClass(/active/);

    const payerPhone = '0799887766';
    await page.locator('#deposit-phone').fill(payerPhone);
    await page.locator('#deposit-amount').fill('5000');
    await page.locator('#deposit-form button[type="submit"]').click();

    const pollingOverlay = page.locator('#deposit-polling-overlay');
    await expect(pollingOverlay).toHaveClass(/active/);
    await expect(pollingOverlay).not.toHaveClass(/active/, { timeout: 30000 });

    // Verify balance is credited
    await expect(page.locator('#wallet-balance')).toHaveText('5,000.00');

    // 2. Open Budget Designer Modal
    await page.click('#open-budget-designer-btn');
    const budgetModal = page.locator('#budget-designer-modal');
    await expect(budgetModal).toHaveClass(/active/);

    // 3. Add a budget allocation item
    await page.locator('#new-category-name').fill('Lunch & Travel');
    await page.locator('#new-category-amount').fill('500');
    await page.locator('#add-category-form button[type="submit"]').click();
    await page.waitForTimeout(500);

    // 4. Advance to Step 2 (Payout Schedule)
    await page.click('#budget-wizard-next-1');
    await page.waitForTimeout(400);
    await expect(page.locator('#budget-wizard-step-title')).toContainText('Step 2 of 3');

    // Fill start and end dates
    const today = new Date();
    const tomorrow = new Date(today);
    tomorrow.setDate(tomorrow.getDate() + 1);
    const nextWeek = new Date(today);
    nextWeek.setDate(nextWeek.getDate() + 7);

    const formatYMD = (d) => d.toISOString().split('T')[0];
    await page.locator('#lock-start-date').fill(formatYMD(tomorrow));
    await page.locator('#lock-end-date').fill(formatYMD(nextWeek));

    // 5. Advance to Step 3 (Payout Destination)
    await page.click('#budget-wizard-next-2');
    await page.waitForTimeout(400);
    await expect(page.locator('#budget-wizard-step-title')).toContainText('Step 3 of 3');

    // Fill in Target M-Pesa Payout Number
    const targetPayoutPhone = '0712345678';
    await page.locator('#budget-lock-payout-phone').fill(targetPayoutPhone);

    // 6. Click Lock & Finalize Budget
    await page.locator('#lock-budget-btn').click();
    await page.waitForTimeout(1000);

    // Verify modal closes and lock notice is reflected
    await expect(page.locator('#budget-designer-modal')).not.toHaveClass(/active/);

    // 7. Wait for dashboard data to refresh, then verify payout phone is reflected on profile card
    await expect(page.locator('#dash-profile-phone')).toHaveText('254712345678', { timeout: 10000 });
  });

});
