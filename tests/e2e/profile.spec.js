const { test, expect } = require('@playwright/test');
const { setupAuthenticatedUser, dismissDisclaimerIfVisible } = require('./helpers');

test.describe('Bursar 2.0 Profile & Security Settings E2E Tests', () => {
  let pageErrors = [];

  test.beforeEach(({ page }) => {
    pageErrors = [];
    page.on('pageerror', (exception) => {
      console.error('Browser console TypeError/Exception:', exception.message);
      pageErrors.push(exception.message);
    });
    page.on('console', msg => {
      console.log(`[Browser Console Log] [${msg.type()}]: ${msg.text()}`);
    });
  });

  test('Should navigate to Profile Settings, update details, toggle theme, and logout', async ({ page }) => {
    const dialogMessages = [];
    page.on('dialog', async dialog => {
      const msg = dialog.message();
      await dialog.accept();
      dialogMessages.push(msg);
    });

    // 1. Authenticated session
    const randomDigits = Math.floor(10000000 + Math.random() * 90000000);
    const testPhoneNumber = `2547${randomDigits}`;
    const testEmail = `user_${testPhoneNumber}@example.com`;
    const testPassword = 'Str0ng!P@ssw0rd';

    await setupAuthenticatedUser(page, { phoneNumber: testPhoneNumber, email: testEmail, password: testPassword });

    // 2. Click sidebar profile settings tab
    await page.click('[data-tab="profile"]');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(500);
    await expect(page.locator('#view-profile')).toHaveClass(/active/);

    // 3. Fill profile info details
    await page.fill('#profile-first-name', 'Jane');
    await page.fill('#profile-last-name', 'Doe');
    await page.fill('#profile-email', testEmail);
    await page.fill('#profile-bio', 'Doing E2E tests for Bursar 2.0');

    await page.click('#profile-info-form button[type="submit"]');
    await expect.poll(() => dialogMessages).toContain('Profile details saved successfully!');

    // Reload page and confirm details are retrieved
    await page.reload({ waitUntil: 'networkidle' });
    await page.waitForLoadState('networkidle');
    
    await page.click('[data-tab="profile"]');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(500);
    
    await expect(page.locator('#profile-first-name')).toHaveValue('Jane');
    await expect(page.locator('#profile-last-name')).toHaveValue('Doe');
    await expect(page.locator('#profile-email')).toHaveValue(testEmail);
    await expect(page.locator('#profile-bio')).toHaveValue('Doing E2E tests for Bursar 2.0');

    // 5. Test Password PIN change
    await page.fill('#pwd-current', 'Str0ng!P@ssw0rd');
    await page.fill('#pwd-new', 'New!Str0ngP@ssw0rd');
    await page.fill('#pwd-confirm', 'New!Str0ngP@ssw0rd');
    
    await page.click('#profile-password-form button[type="submit"]');
    await expect.poll(() => dialogMessages).toContain('Password updated successfully!');

    // Logout and verify we can log back in using the new password PIN
    const logoutBtn = page.locator('#sidebar-logout-btn, #logout-btn');
    await logoutBtn.first().click({ force: true });
    await page.waitForURL(url => !url.toString().includes('dashboard'));
    await page.waitForLoadState('networkidle');
    await dismissDisclaimerIfVisible(page);
    await page.click('#nav-login-btn');
    await page.fill('#auth-phone', testPhoneNumber);
    await page.fill('#auth-password', 'New!Str0ngP@ssw0rd');
    await page.click('#auth-submit-btn');
    await page.waitForURL('**/dashboard');
    
    expect(pageErrors).toHaveLength(0);
  });

  test('Should display active sessions and support multi-device session revocation', async ({ browser, page }) => {
    const dialogMessages = [];
    page.on('dialog', async dialog => {
      const msg = dialog.message();
      await dialog.accept();
      dialogMessages.push(msg);
    });

    // 1. Context A - Register and login
    const randomDigits = Math.floor(10000000 + Math.random() * 90000000);
    const testPhoneNumber = `2547${randomDigits}`;
    const testEmail = `user_${testPhoneNumber}@example.com`;
    const testPassword = 'Str0ng!P@ssw0rd2026!';

    await setupAuthenticatedUser(page, { phoneNumber: testPhoneNumber, email: testEmail, password: testPassword });

    // 2. Context B - Login from another context (simulating a second device)
    const contextB = await browser.newContext({ userAgent: 'Mozilla/5.0 (iPhone; CPU iPhone OS 16_5) Safari/605.1.15' });
    const pageB = await contextB.newPage();
    await setupAuthenticatedUser(pageB, { phoneNumber: testPhoneNumber, email: testEmail, password: testPassword });

    // 3. On Context A, visit Profile and check sessions list
    await page.click('[data-tab="profile"]');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(500);
    await expect(page.locator('#active-sessions-body')).toBeVisible();

    // Verify there are two sessions
    const rows = page.locator('#active-sessions-body tr');
    await expect(rows).toHaveCount(2);

    // Find the Revoke button of the other session (iPhone) and click it
    const revokeBtn = page.locator('#active-sessions-body button.revoke-session-btn').first();
    await revokeBtn.click();
    
    // We expect both a confirm dialog and an alert dialog to have been accepted.
    await expect.poll(() => dialogMessages).toContain('Session revoked successfully.');
    
    // Verify the row count decreased to 1
    await expect(page.locator('#active-sessions-body tr')).toHaveCount(1);

    // Check that Context B (Device B) is revoked. Verify if pageB is kicked out on reload
    await pageB.reload();
    await pageB.waitForURL(url => !url.toString().includes('dashboard'));
    expect(pageB.url()).not.toContain('/dashboard');

    await contextB.close();
  });

  test('Should handle danger zone account deactivation', async ({ page }) => {
    const dialogMessages = [];
    page.on('dialog', async dialog => {
      const msg = dialog.message();
      await dialog.accept();
      dialogMessages.push(msg);
    });

    // 1. Setup authenticated session
    const randomDigits = Math.floor(10000000 + Math.random() * 90000000);
    const testPhoneNumber = `2547${randomDigits}`;
    const testEmail = `user_${testPhoneNumber}@example.com`;
    const testPassword = 'Str0ng!P@ssw0rd';

    await setupAuthenticatedUser(page, { phoneNumber: testPhoneNumber, email: testEmail, password: testPassword });

    // 2. Go to Profile Settings
    await page.click('[data-tab="profile"]');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(500);
    await page.click('#open-deactivate-modal-btn');
    await expect(page.locator('#deactivate-modal')).toHaveClass(/active/);

    // 3. Attempt with wrong phrase or wrong PIN
    await page.fill('#deactivate-confirm-phrase', 'DELET');
    await page.fill('#deactivate-password', 'Str0ng!P@ssw0rd');
    await page.fill('#deactivate-otp', '123456');
    await page.click('#deactivate-form button[type="submit"]');
    await expect(page.locator('#deactivate-error')).toBeVisible();
    await expect(page.locator('#deactivate-error')).toContainText('Please type the confirmation phrase exactly: DELETE');
    
    // Clear captured messages
    dialogMessages.length = 0;

    // Fetch latest OTP code from test backend
    const otpRes = await page.evaluate(async (email) => {
      const res = await fetch(`/api/test/latest-otp?email=${encodeURIComponent(email)}&purpose=account_deactivation`);
      return await res.json();
    }, testEmail);
    const validOtp = otpRes.otp_code;

    // 4. Successful deactivation with correct phrase, password, and OTP
    await page.fill('#deactivate-confirm-phrase', 'DELETE');
    await page.fill('#deactivate-password', 'Str0ng!P@ssw0rd');
    await page.fill('#deactivate-otp', validOtp);
    await page.click('#deactivate-form button[type="submit"]');
    await page.waitForSelector('#nav-login-btn');
    expect(page.url()).not.toContain('/dashboard');

    // Verify cannot log back in
    await dismissDisclaimerIfVisible(page);
    await page.click('#nav-login-btn');
    await page.fill('#auth-phone', testPhoneNumber);
    await page.fill('#auth-password', 'Str0ng!P@ssw0rd');
    await page.click('#auth-submit-btn');
    await expect(page.locator('#auth-error-msg')).toBeVisible();
  });
});
