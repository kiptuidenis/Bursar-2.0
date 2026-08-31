const { test, expect } = require('@playwright/test');
const { setupAuthenticatedUser } = require('./helpers');

test.describe('Settings Form Polling & Input Overwrite Regression Tests (Phase 1)', () => {
  let pageErrors = [];

  test.beforeEach(({ page }) => {
    pageErrors = [];
    page.on('pageerror', (exception) => {
      console.error('Browser console exception:', exception.message);
      pageErrors.push(exception.message);
    });
  });

  test('Settings form inputs should not auto-fill / overwrite deleted values during background polling', async ({ page }) => {
    // 1. Setup authenticated user
    const user = await setupAuthenticatedUser(page);

    // 2. Open Settings Drawer
    await page.click('#toggle-settings-btn');
    const settingsDrawer = page.locator('#settings-drawer');
    await expect(settingsDrawer).toHaveClass(/active/);

    const phoneInput = page.locator('#settings-phone');
    const timeInput = page.locator('#settings-time');

    // Verify initial values
    await expect(phoneInput).toHaveValue(user.phone);

    // 3. Clear/Delete phone and time inputs
    await phoneInput.fill('');
    await timeInput.fill('');

    await expect(phoneInput).toHaveValue('');
    await expect(timeInput).toHaveValue('');

    // 4. Focus on the phone input and wait longer than the 5-second polling interval (wait 7 seconds)
    await phoneInput.focus();
    await page.waitForTimeout(7000);

    // 5. Verify inputs remain empty and have NOT been overwritten by background polling
    await expect(phoneInput).toHaveValue('');
    await expect(timeInput).toHaveValue('');

    // 6. Enter new phone and time
    await phoneInput.fill('254712345678');
    await timeInput.fill('09:30');

    // Wait another 6 seconds
    await page.waitForTimeout(6000);

    // Verify newly entered values were preserved during background polling
    await expect(phoneInput).toHaveValue('254712345678');
    await expect(timeInput).toHaveValue('09:30');

    expect(pageErrors).toHaveLength(0);
  });
});
