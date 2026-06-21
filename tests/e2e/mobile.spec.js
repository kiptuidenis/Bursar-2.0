const { test, expect } = require('@playwright/test');

test.describe('Bursar 2.0 Mobile Responsiveness & Form Validation E2E Tests', () => {
  // Use a standard mobile device viewport (iPhone 12/X dimensions)
  test.use({ viewport: { width: 375, height: 812 }, hasTouch: true });

  let pageErrors = [];

  test.beforeEach(({ page }) => {
    pageErrors = [];
    page.on('pageerror', (exception) => {
      console.error('Browser console TypeError/Exception:', exception.message);
      pageErrors.push(exception.message);
    });
  });

  test('Should validate mobile input attributes on auth and dashboard forms', async ({ page }) => {
    // 1. Visit landing/login page
    await page.goto('/#login');

    // 2. Assert auth phone number keyboard type attributes
    const authPhoneInput = page.locator('#auth-phone');
    await expect(authPhoneInput).toHaveAttribute('type', 'tel');
    await expect(authPhoneInput).toHaveAttribute('inputmode', 'tel');
    await expect(authPhoneInput).toHaveAttribute('autocomplete', 'tel');

    // 3. Assert auth password autocomplete attributes
    const authPasswordInput = page.locator('#auth-password');
    await expect(authPasswordInput).toHaveAttribute('autocomplete', 'current-password');

    // 4. Signup to check dashboard mobile forms
    await page.goto('/#signup');
    const randomDigits = Math.floor(100000 + Math.random() * 900000);
    const testPhoneNumber = `254700${randomDigits}`;
    await page.fill('#auth-phone', testPhoneNumber);
    await page.fill('#auth-password', '123456');
    await page.click('#auth-submit-btn');
    await page.waitForURL('**/dashboard');
    await page.waitForLoadState('networkidle');

    // 5. Open Deposit Modal and assert amount keyboard attributes
    await page.click('#open-deposit-btn');
    await expect(page.locator('#deposit-modal')).toHaveClass(/active/);
    const depositAmtInput = page.locator('#deposit-amount');
    await expect(depositAmtInput).toHaveAttribute('type', 'number');
    await expect(depositAmtInput).toHaveAttribute('inputmode', 'decimal');
    await page.click('#close-deposit-btn');

    // 6. Open Settings Drawer and assert inputs
    await page.click('#toggle-settings-btn');
    await expect(page.locator('#settings-drawer')).toHaveClass(/active/);
    const budgetInput = page.locator('#settings-budget');
    await expect(budgetInput).toHaveAttribute('type', 'number');
    await expect(budgetInput).toHaveAttribute('inputmode', 'decimal');
    const targetPhoneInput = page.locator('#settings-phone');
    await expect(targetPhoneInput).toHaveAttribute('type', 'tel');
    await expect(targetPhoneInput).toHaveAttribute('inputmode', 'tel');
    await expect(targetPhoneInput).toHaveAttribute('autocomplete', 'tel');
    await page.click('#close-settings-btn');

    // 7. Go to Profile Settings and verify attributes
    await page.click('#sidebar-toggle-btn');
    await page.click('[data-tab="profile"]');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(500);

    const firstNameInput = page.locator('#profile-first-name');
    await expect(firstNameInput).toHaveAttribute('type', 'text');
    await expect(firstNameInput).toHaveAttribute('autocomplete', 'given-name');

    const lastNameInput = page.locator('#profile-last-name');
    await expect(lastNameInput).toHaveAttribute('type', 'text');
    await expect(lastNameInput).toHaveAttribute('autocomplete', 'family-name');

    const emailInput = page.locator('#profile-email');
    await expect(emailInput).toHaveAttribute('type', 'email');
    await expect(emailInput).toHaveAttribute('inputmode', 'email');
    await expect(emailInput).toHaveAttribute('autocomplete', 'email');

    const currentPwdInput = page.locator('#pwd-current');
    await expect(currentPwdInput).toHaveAttribute('type', 'password');
    await expect(currentPwdInput).toHaveAttribute('autocomplete', 'current-password');

    const newPwdInput = page.locator('#pwd-new');
    await expect(newPwdInput).toHaveAttribute('type', 'password');
    await expect(newPwdInput).toHaveAttribute('autocomplete', 'new-password');

    const confirmPwdInput = page.locator('#pwd-confirm');
    await expect(confirmPwdInput).toHaveAttribute('type', 'password');
    await expect(confirmPwdInput).toHaveAttribute('autocomplete', 'new-password');

    expect(pageErrors).toHaveLength(0);
  });

  test('Should toggle sidebar drawer menu navigation on mobile and backdrop overlay clicks', async ({ page }) => {
    // 1. Signup & auto-login
    await page.goto('/#signup');
    const randomDigits = Math.floor(100000 + Math.random() * 900000);
    const testPhoneNumber = `254700${randomDigits}`;
    await page.fill('#auth-phone', testPhoneNumber);
    await page.fill('#auth-password', '123456');
    await page.click('#auth-submit-btn');
    await page.waitForURL('**/dashboard');
    await page.waitForLoadState('networkidle');

    const sidebar = page.locator('#sidebar-nav');
    const toggleBtn = page.locator('#sidebar-toggle-btn');
    const backdrop = page.locator('#sidebar-backdrop');

    // 2. Under mobile viewport, hamburger button is visible
    await expect(toggleBtn).toBeVisible();
    // Sidebar menu is sliding left (out of view)
    await expect(sidebar).not.toHaveClass(/active/);

    // 3. Click menu toggle button to slide it in
    await toggleBtn.click();
    await expect(sidebar).toHaveClass(/active/);
    await expect(backdrop).toHaveClass(/active/);

    // 4. Click backdrop overlay to slide it out/dismiss it
    await backdrop.click();
    await expect(sidebar).not.toHaveClass(/active/);
    await expect(backdrop).not.toHaveClass(/active/);
  });

  test('Should ensure active sessions revocation buttons remain visible on mobile screens', async ({ browser, page }) => {
    const dialogMessages = [];
    page.on('dialog', async dialog => {
      dialogMessages.push(dialog.message());
      await dialog.accept();
    });

    // 1. Context A - Register and login
    await page.goto('/#signup');
    const randomDigits = Math.floor(100000 + Math.random() * 900000);
    const testPhoneNumber = `254700${randomDigits}`;
    await page.fill('#auth-phone', testPhoneNumber);
    await page.fill('#auth-password', '123456');
    await page.click('#auth-submit-btn');
    await page.waitForURL('**/dashboard');
    await page.waitForLoadState('networkidle');

    // 2. Context B - Login from another context (simulating a second device)
    const contextB = await browser.newContext({ userAgent: 'Mozilla/5.0 (iPhone; CPU iPhone OS 16_5) Safari/605.1.15' });
    const pageB = await contextB.newPage();
    await pageB.goto('/#login');
    await pageB.fill('#auth-phone', testPhoneNumber);
    await pageB.fill('#auth-password', '123456');
    await pageB.click('#auth-submit-btn');
    await pageB.waitForURL('**/dashboard');
    await pageB.waitForLoadState('networkidle');

    // 3. Navigate to Profile Settings on Context A (Mobile)
    await page.click('#sidebar-toggle-btn');
    await page.click('[data-tab="profile"]');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(500);

    // 4. Assert active sessions table is visible
    const sessionsTableBody = page.locator('#active-sessions-body');
    await expect(sessionsTableBody).toBeVisible();

    // 5. Ensure that the active sessions revocation buttons are VISIBLE and not hidden by mobile media queries
    const revokeBtn = page.locator('#active-sessions-body button.revoke-session-btn').first();
    await expect(revokeBtn).toBeVisible();
    await expect(revokeBtn).toBeEnabled();

    // 6. Perform click to verify revocation works cleanly on mobile
    await revokeBtn.click();
    await expect.poll(() => dialogMessages).toContain('Session revoked successfully.');
    
    // Verify rows count decreased
    await expect(page.locator('#active-sessions-body tr')).toHaveCount(1);

    await contextB.close();
  });
});
