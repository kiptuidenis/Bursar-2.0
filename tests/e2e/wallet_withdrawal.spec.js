const { test, expect } = require('@playwright/test');
const { setupAuthenticatedUser } = require('./helpers');

test.describe('Wallet Cash Withdrawal E2E Flow', () => {
  test.beforeEach(async ({ page }) => {
    // Auto-accept alert/confirm dialogs
    page.on('dialog', async dialog => {
      await dialog.accept();
    });
  });

  test('Should show Withdraw button when deposit is unlocked and balance >= 10', async ({ page }) => {
    const user = await setupAuthenticatedUser(page);

    // 1. Give user balance of KES 500 via deposit or settings
    await page.evaluate(async () => {
      // Initiate deposit simulation
      const res = await fetch('/api/deposit/initiate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ amount: 500 })
      });
      const data = await res.json();
      if (data.checkout_request_id) {
        await fetch('/api/deposit/simulate-callback', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            checkout_request_id: data.checkout_request_id,
            status: 'SUCCESS'
          })
        });
      }
    });

    await page.reload();
    await page.waitForLoadState('networkidle');

    // 2. Flip Debit Card
    const cardContainer = page.locator('#debit-card-container');
    await cardContainer.click();

    // 3. Verify Withdraw Button is visible on card back
    const withdrawBtn = page.locator('#open-withdraw-btn');
    await expect(withdrawBtn).toBeVisible();

    // 4. Click Withdraw button
    await withdrawBtn.click();

    // 5. Verify Withdrawal Modal appears
    const withdrawModal = page.locator('#withdraw-modal');
    await expect(withdrawModal).toHaveClass(/active/);

    // 6. Test quick chip selection (e.g. 500)
    await page.click('.btn-quick-withdraw[data-amt="500"]');
    await expect(page.locator('#withdraw-amount-input')).toHaveValue('500');

    // 7. Submit form to proceed to 2FA
    const [otpRes] = await Promise.all([
      page.waitForResponse(res => res.url().includes('/api/profile/request-stepup-otp') && res.request().method() === 'POST'),
      page.click('#proceed-withdraw-btn')
    ]);
    expect(otpRes.status()).toBe(200);

    // 8. Verify 2FA Modal opens
    const withdraw2faModal = page.locator('#withdraw-2fa-modal');
    await expect(withdraw2faModal).toHaveClass(/active/);
    await expect(page.locator('#withdraw-confirm-amount')).toHaveText('500');
  });

  test('Should hide Withdraw button when budget schedule is actively locked', async ({ page }) => {
    const user = await setupAuthenticatedUser(page);

    // Give user balance
    await page.evaluate(async () => {
      const res = await fetch('/api/deposit/initiate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ amount: 1000 })
      });
      const data = await res.json();
      if (data.checkout_request_id) {
        await fetch('/api/deposit/simulate-callback', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            checkout_request_id: data.checkout_request_id,
            status: 'SUCCESS'
          })
        });
      }
    });

    // Add budget item & lock schedule
    await page.click('#open-budget-designer-btn');
    await page.fill('#new-category-name', 'Groceries');
    await page.fill('#new-category-amount', '300');
    await page.click('#add-category-form button[type="submit"]');
    await page.waitForTimeout(300);

    await page.click('#budget-wizard-next-1');
    await page.waitForTimeout(300);

    const future3 = new Date();
    future3.setDate(future3.getDate() + 3);
    const future10 = new Date();
    future10.setDate(future10.getDate() + 10);

    await page.fill('#lock-start-date', future3.toISOString().split('T')[0]);
    await page.fill('#lock-end-date', future10.toISOString().split('T')[0]);

    await page.click('#budget-wizard-next-2');
    await page.waitForTimeout(300);

    await page.click('#lock-budget-btn');
    await page.waitForTimeout(500);

    await page.goto('/dashboard');
    await page.waitForLoadState('networkidle');

    // Flip Debit Card
    await page.click('#debit-card-container');

    // Verify Withdraw button is HIDDEN while schedule is locked
    const withdrawBtn = page.locator('#open-withdraw-btn');
    await expect(withdrawBtn).toBeHidden();
  });
});
