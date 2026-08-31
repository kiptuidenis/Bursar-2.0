const { test, expect } = require('@playwright/test');
const { setupEmailOnlyUser, setupAuthenticatedUser } = require('./helpers');

test.describe('Deposit Phone Prompt Feature', () => {

  test('Email-only user deposits with custom phone number without altering profile', async ({ page }) => {
    test.setTimeout(60000);
    page.on('dialog', async dialog => await dialog.accept());

    await setupEmailOnlyUser(page);

    // Random test phone
    const randomSuffix = Math.floor(10000000 + Math.random() * 90000000);
    const testPhone = `07${randomSuffix}`;

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

    // Wait for polling modal to dismiss (simulation polling cycle)
    await expect(pollingOverlay).not.toHaveClass(/active/, { timeout: 30000 });

    // Verify balance updated on dashboard
    await expect(page.locator('#wallet-balance')).toHaveText('2,000.00');

    // Verify profile phone remains unlinked ("—")
    await expect(page.locator('#dash-profile-phone')).toHaveText('—');
  });

  test('Phone-registered user can deposit using a different phone without altering original profile', async ({ page }) => {
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

    // Edit to pay from a different phone number
    await phoneInput.fill('0711998877');
    await page.locator('#deposit-amount').fill('1500');
    await page.locator('#deposit-form button[type="submit"]').click();

    const pollingOverlay = page.locator('#deposit-polling-overlay');
    await expect(pollingOverlay).toHaveClass(/active/);
    await expect(pollingOverlay).not.toHaveClass(/active/, { timeout: 30000 });

    // Verify profile retains original phone number
    await expect(page.locator('#dash-profile-phone')).toHaveText(userPhone);
  });

});
