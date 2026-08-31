const { test, expect } = require('@playwright/test');
const { setupAuthenticatedUser } = require('./helpers');

test.describe('Settings Pre-Modal Rate-Limiting E2E Tests', () => {

  test('Settings phone change shows rate limit error on drawer and DOES NOT open Step-Up Modal when rate limit is exceeded', async ({ page }) => {
    test.setTimeout(60000);
    page.on('dialog', async dialog => await dialog.accept());

    const userPhone = '254711223344';
    await setupAuthenticatedUser(page, { phoneNumber: userPhone });

    // Open Settings Drawer via top navigation button
    const toggleSettingsBtn = page.locator('#toggle-settings-btn');
    await toggleSettingsBtn.click();
    const settingsDrawer = page.locator('#settings-drawer');
    await expect(settingsDrawer).toHaveClass(/active/, { timeout: 8000 });

    // Mock/route /api/profile/request-stepup-otp to return 429 Too Many Requests
    await page.route('**/api/profile/request-stepup-otp', async (route) => {
      await route.fulfill({
        status: 429,
        contentType: 'application/json',
        body: JSON.stringify({ detail: 'Too many requests. Please wait a minute before requesting another verification code.' })
      });
    });

    // Change the phone number in settings
    const phoneInput = page.locator('#settings-phone');
    await phoneInput.fill('254799887766');

    // Click Save Configuration
    const saveBtn = page.locator('#save-settings-btn');
    await saveBtn.click();

    // 1. Verify that #settings-error is visible and contains rate limit message
    const errorEl = page.locator('#settings-error');
    await expect(errorEl).toBeVisible({ timeout: 5000 });
    await expect(errorEl).toContainText('Too many requests');

    // 2. Verify that #stepup-payout-modal DID NOT open (no .active class)
    const stepupModal = page.locator('#stepup-payout-modal');
    await expect(stepupModal).not.toHaveClass(/active/);

    // 3. Verify that settings drawer is still active and save button is re-enabled
    await expect(settingsDrawer).toHaveClass(/active/);
    await expect(saveBtn).toBeEnabled();
  });
});
