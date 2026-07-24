const { test, expect } = require('@playwright/test');

test.describe('Bursar 2.0 Password Visibility Toggle E2E Tests', () => {

  test('Should toggle login password visibility on landing page modal', async ({ page }) => {
    await page.goto('/#login');
    await page.waitForLoadState('networkidle');

    const pwdInput = page.locator('#auth-password');
    const toggleBtn = page.locator('.btn-toggle-password[data-target="auth-password"]');

    // Initially input type is 'password'
    await expect(pwdInput).toHaveAttribute('type', 'password');

    // Click toggle button to reveal password
    await toggleBtn.click();
    await expect(pwdInput).toHaveAttribute('type', 'text');

    // Click toggle button again to hide password
    await toggleBtn.click();
    await expect(pwdInput).toHaveAttribute('type', 'password');
  });

  test('Should toggle confirm password visibility on signup modal', async ({ page }) => {
    await page.goto('/#signup');
    await page.waitForLoadState('networkidle');

    const confirmInput = page.locator('#auth-confirm-password');
    const toggleBtn = page.locator('.btn-toggle-password[data-target="auth-confirm-password"]');

    // Initially input type is 'password'
    await expect(confirmInput).toHaveAttribute('type', 'password');

    // Click toggle button to reveal confirm password
    await toggleBtn.click();
    await expect(confirmInput).toHaveAttribute('type', 'text');

    // Click toggle button again to hide confirm password
    await toggleBtn.click();
    await expect(confirmInput).toHaveAttribute('type', 'password');
  });

  test('Should toggle current, new, and confirm password visibility on profile settings page', async ({ page }) => {
    // 1. Signup & auto-login
    await page.goto('/#signup');
    const randomDigits = Math.floor(100000 + Math.random() * 900000);
    const testPhoneNumber = `254700${randomDigits}`;
    
    await page.fill('#auth-phone', testPhoneNumber);
    await page.fill('#auth-password', 'Str0ng!P@ssw0rd');
    const confirmInput = page.locator('#auth-confirm-password');
    if (await confirmInput.count() > 0) {
      await confirmInput.fill('Str0ng!P@ssw0rd');
    }
    await page.click('#auth-submit-btn');

    await page.waitForURL('**/dashboard');
    await page.waitForLoadState('networkidle');

    // 2. Navigate to Profile Settings tab
    await page.click('[data-tab="profile"]');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(500);

    // 3. Current Password toggle
    const currentPwdInput = page.locator('#pwd-current');
    const currentToggle = page.locator('.btn-toggle-password[data-target="pwd-current"]');
    await expect(currentPwdInput).toHaveAttribute('type', 'password');
    await currentToggle.click();
    await expect(currentPwdInput).toHaveAttribute('type', 'text');
    await currentToggle.click();
    await expect(currentPwdInput).toHaveAttribute('type', 'password');

    // 4. New Password toggle
    const newPwdInput = page.locator('#pwd-new');
    const newToggle = page.locator('.btn-toggle-password[data-target="pwd-new"]');
    await expect(newPwdInput).toHaveAttribute('type', 'password');
    await newToggle.click();
    await expect(newPwdInput).toHaveAttribute('type', 'text');
    await newToggle.click();
    await expect(newPwdInput).toHaveAttribute('type', 'password');

    // 5. Confirm New Password toggle
    const confirmPwdInput = page.locator('#pwd-confirm');
    const confirmToggle = page.locator('.btn-toggle-password[data-target="pwd-confirm"]');
    await expect(confirmPwdInput).toHaveAttribute('type', 'password');
    await confirmToggle.click();
    await expect(confirmPwdInput).toHaveAttribute('type', 'text');
    await confirmToggle.click();
    await expect(confirmPwdInput).toHaveAttribute('type', 'password');
  });

  test('Should toggle password visibility in account deactivation modal', async ({ page }) => {
    // 1. Signup & auto-login
    await page.goto('/#signup');
    const randomDigits = Math.floor(100000 + Math.random() * 900000);
    const testPhoneNumber = `254700${randomDigits}`;
    
    await page.fill('#auth-phone', testPhoneNumber);
    await page.fill('#auth-password', 'Str0ng!P@ssw0rd');
    const confirmInput = page.locator('#auth-confirm-password');
    if (await confirmInput.count() > 0) {
      await confirmInput.fill('Str0ng!P@ssw0rd');
    }
    await page.click('#auth-submit-btn');

    await page.waitForURL('**/dashboard');
    await page.waitForLoadState('networkidle');

    // 2. Open Profile Settings and Deactivation modal
    await page.click('[data-tab="profile"]');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(500);
    await page.click('#open-deactivate-modal-btn');
    await expect(page.locator('#deactivate-modal')).toHaveClass(/active/);

    // 3. Verify Deactivate Password input toggle
    const deactivatePwdInput = page.locator('#deactivate-password');
    const deactivateToggle = page.locator('.btn-toggle-password[data-target="deactivate-password"]');

    await expect(deactivatePwdInput).toHaveAttribute('type', 'password');
    await deactivateToggle.click();
    await expect(deactivatePwdInput).toHaveAttribute('type', 'text');
    await deactivateToggle.click();
    await expect(deactivatePwdInput).toHaveAttribute('type', 'password');
  });

});
