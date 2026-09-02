const { test, expect } = require('@playwright/test');
const { setupAuthenticatedUser } = require('./helpers');

test.describe('Profile Input Preservation & Email Change OTP Verification E2E Tests', () => {
  let pageErrors = [];

  test.beforeEach(({ page }) => {
    pageErrors = [];
    page.on('pageerror', (exception) => {
      console.error('Browser console exception:', exception.message);
      pageErrors.push(exception.message);
    });
    page.on('console', msg => {
      console.log(`[Browser Console] [${msg.type()}]: ${msg.text()}`);
    });
  });

  test('Should preserve user typed input in profile fields across multiple 5-second background polling cycles', async ({ page }) => {
    const randomDigits = Math.floor(10000000 + Math.random() * 90000000);
    const testPhoneNumber = `2547${randomDigits}`;
    const testEmail = `polluser_${testPhoneNumber}@example.com`;
    const testPassword = 'Str0ng!P@ssw0rd';

    await setupAuthenticatedUser(page, { phoneNumber: testPhoneNumber, email: testEmail, password: testPassword });

    // Navigate to profile tab
    await page.click('[data-tab="profile"]');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(500);

    // Type into profile input fields
    await page.fill('#profile-first-name', 'PreservedFirst');
    await page.fill('#profile-last-name', 'PreservedLast');
    await page.fill('#profile-bio', 'Active typing in progress...');

    // Keep focus on bio input
    await page.focus('#profile-bio');

    // Wait for more than one 5-second polling interval (6.5 seconds)
    await page.waitForTimeout(6500);

    // Assert that the fields have NOT been clobbered by background polling
    await expect(page.locator('#profile-first-name')).toHaveValue('PreservedFirst');
    await expect(page.locator('#profile-last-name')).toHaveValue('PreservedLast');
    await expect(page.locator('#profile-bio')).toHaveValue('Active typing in progress...');

    expect(pageErrors).toHaveLength(0);
  });

  test('Should trigger step-up modal when changing email address and verify OTP', async ({ page }) => {
    const dialogMessages = [];
    page.on('dialog', async dialog => {
      const msg = dialog.message();
      await dialog.accept();
      dialogMessages.push(msg);
    });

    const randomDigits = Math.floor(10000000 + Math.random() * 90000000);
    const testPhoneNumber = `2547${randomDigits}`;
    const initialEmail = `initial_${testPhoneNumber}@example.com`;
    const targetEmail = `updated_${testPhoneNumber}@example.com`;
    const testPassword = 'Str0ng!P@ssw0rd';

    await setupAuthenticatedUser(page, { phoneNumber: testPhoneNumber, email: initialEmail, password: testPassword });

    // Navigate to profile tab
    await page.click('[data-tab="profile"]');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(500);

    // Update first name and change email address
    await page.fill('#profile-first-name', 'Grace');
    await page.fill('#profile-last-name', 'Hopper');
    await page.fill('#profile-email', targetEmail);

    // Click Save Profile and wait for request-stepup-otp response
    const [otpRes] = await Promise.all([
      page.waitForResponse(res => res.url().includes('/api/profile/request-stepup-otp') && res.request().method() === 'POST'),
      page.click('#profile-info-form button[type="submit"]')
    ]);
    expect(otpRes.status()).toBe(200);

    // Step-up verification modal should open for new email
    const stepupModal = page.locator('#stepup-payout-modal');
    await expect(stepupModal).toHaveClass(/active/);
    await expect(page.locator('#stepup-payout-title')).toContainText('Verify New Email Address');

    expect(pageErrors).toHaveLength(0);
  });

  test('Should reject registration attempt when an existing email is submitted', async ({ page }) => {
    const randomDigits = Math.floor(10000000 + Math.random() * 90000000);
    const existingEmail = `existing_${randomDigits}@example.com`;
    const testPassword = 'Str0ng!P@ssw0rd';

    // 1. Create first user
    await setupAuthenticatedUser(page, { phoneNumber: `2547${randomDigits}`, email: existingEmail, password: testPassword });

    // 2. Logout
    const logoutBtn = page.locator('#sidebar-logout-btn, #logout-btn');
    await logoutBtn.first().click({ force: true });
    await page.waitForURL(url => !url.toString().includes('dashboard'));
    await page.waitForLoadState('networkidle');

    // 3. Try to register a new account with the same email
    const loginNavBtn = page.locator('#nav-login-btn, #hero-cta-btn');
    if (await loginNavBtn.count() > 0) {
      await loginNavBtn.first().click();
    }
    await page.click('#tab-signup');
    await page.fill('#auth-phone', existingEmail);
    await page.fill('#auth-password', 'Another!P@ssw0rd1');
    await page.fill('#auth-confirm-password', 'Another!P@ssw0rd1');
    await page.click('#auth-submit-btn');

    // Verify error message is shown
    await expect(page.locator('#auth-error-msg')).toBeVisible();
    await expect(page.locator('#auth-error-msg')).toContainText(/already exists/i);

    expect(pageErrors).toHaveLength(0);
  });

  test('Should allow legacy user without email to link new email with OTP verification', async ({ page }) => {
    const randomDigits = Math.floor(10000000 + Math.random() * 90000000);
    const legacyPhone = `2547${randomDigits}`;
    const newTargetEmail = `linked_legacy_${randomDigits}@example.com`;

    // 1. Setup legacy user with no email
    await setupAuthenticatedUser(page, { phoneNumber: legacyPhone, legacyPhoneOnly: true });

    // 2. Go to Profile Settings
    await page.click('[data-tab="profile"]');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(500);

    // 3. Fill new email address
    await page.fill('#profile-email', newTargetEmail);

    // 4. Click Save Profile and wait for request-stepup-otp response
    const [otpRes] = await Promise.all([
      page.waitForResponse(res => res.url().includes('/api/profile/request-stepup-otp') && res.request().method() === 'POST'),
      page.click('#profile-info-form button[type="submit"]')
    ]);
    expect(otpRes.status()).toBe(200);

    // 5. Verify step-up modal opens with target email linking message
    const modal = page.locator('#stepup-payout-modal');
    await expect(modal).toHaveClass(/active/);
    await expect(page.locator('#stepup-payout-subtitle')).toContainText(newTargetEmail);

    // 6. Fetch OTP code from backend test endpoint
    const mockOtpRes = await page.evaluate(async (email) => {
      const res = await fetch(`/api/test/latest-otp?email=${encodeURIComponent(email)}&purpose=email_change`);
      return await res.json();
    }, newTargetEmail);
    const validOtp = mockOtpRes.otp_code;

    // 7. Submit OTP and verify profile save succeeds
    await page.fill('#stepup-payout-otp', validOtp);
    const [saveRes] = await Promise.all([
      page.waitForResponse(res => res.url().includes('/api/profile') && res.request().method() === 'POST'),
      page.click('#confirm-stepup-payout-btn')
    ]);
    expect(saveRes.status()).toBe(200);

    // 8. Verify modal closes and email is preserved
    await expect(modal).not.toHaveClass(/active/);
    await expect(page.locator('#profile-email')).toHaveValue(newTargetEmail);

    expect(pageErrors).toHaveLength(0);
  });
});
