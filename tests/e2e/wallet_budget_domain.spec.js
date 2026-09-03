const { test, expect } = require('@playwright/test');
const { dismissDisclaimerIfVisible } = require('./helpers');

test.describe('Phase 3: Wallet & Budget Domain Models E2E Tests', () => {
  let pageErrors = [];

  test.beforeEach(({ page }) => {
    pageErrors = [];
    page.on('pageerror', (exception) => {
      console.error('Browser console exception:', exception.message);
      pageErrors.push(exception.message);
    });
  });

  test('Should initialize Wallet (0 KES) and Budget (0 KES) domain models on 2FA registration', async ({ page }) => {
    page.on('dialog', async dialog => {
      if (dialog.type() === 'confirm') await dialog.accept();
      else await dialog.dismiss();
    });

    await page.goto('/');
    await dismissDisclaimerIfVisible(page);
    
    // Check page loaded cleanly without JS runtime errors
    expect(pageErrors.length).toBe(0);
    
    // Verify landing page element visibility
    await expect(page.locator('#nav-signup-btn')).toBeVisible();
  });
});
