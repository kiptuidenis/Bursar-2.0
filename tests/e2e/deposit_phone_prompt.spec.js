const { test, expect } = require('@playwright/test');
const { setupEmailOnlyUser, setupAuthenticatedUser } = require('./helpers');

test.describe('Deposit Phone Prompt Feature', () => {

  test('Email-only user is prompted for phone number on deposit and number is auto-persisted', async ({ page }) => {
    test.setTimeout(60000);
    // Auto-accept alert dialogs
    page.on('dialog', async dialog => await dialog.accept());

    await setupEmailOnlyUser(page);

    // Generate a unique random Kenyan phone number to avoid UNIQUE constraint conflicts
    const randomSuffix = Math.floor(10000000 + Math.random() * 90000000);
    const testPhone = `07${randomSuffix}`;
    const normalizedPhone = `2547${randomSuffix}`;

    // Flip debit card to reveal action buttons
    await page.click('#debit-card-container');
    await page.waitForTimeout(600);
    await page.click('#open-deposit-btn');
    await expect(page.locator('#deposit-modal')).toHaveClass(/active/);

    // Verify phone input is present and empty for email-only user
    const phoneInput = page.locator('#deposit-phone');
    await expect(phoneInput).toBeVisible();
    await expect(phoneInput).toHaveValue('');

    // Fill in M-Pesa phone number and deposit amount
    await phoneInput.fill(testPhone);
    await page.locator('#deposit-amount').fill('2000');

    // Submit deposit form
    await page.locator('#deposit-form button[type="submit"]').click();

    // Verify STK push polling modal is triggered
    const pollingOverlay = page.locator('#deposit-polling-overlay');
    await expect(pollingOverlay).toHaveClass(/active/);

    // In simulation mode, polling will complete or transition
    // Wait for polling modal to dismiss and balance to reflect deposit
    await expect(pollingOverlay).not.toHaveClass(/active/, { timeout: 15000 });

    // Wait for dashboard data to refresh, then verify phone number on profile summary
    await expect(page.locator('#dash-profile-phone')).toHaveText(normalizedPhone, { timeout: 10000 });
  });

  test('Phone-registered user has phone pre-populated in deposit modal', async ({ page }) => {
    test.setTimeout(60000);
    const userPhone = '254799112233';
    await setupAuthenticatedUser(page, { phoneNumber: userPhone });

    // Flip debit card to reveal action buttons
    await page.click('#debit-card-container');
    await page.waitForTimeout(600);
    await page.click('#open-deposit-btn');
    await expect(page.locator('#deposit-modal')).toHaveClass(/active/);

    // Verify phone input is pre-filled with user's phone number
    const phoneInput = page.locator('#deposit-phone');
    await expect(phoneInput).toBeVisible();
    await expect(phoneInput).toHaveValue(userPhone);

    // Verify Saved Line badge is shown
    const savedBadge = page.locator('#deposit-phone-status-badge');
    await expect(savedBadge).toBeVisible();
  });

});
