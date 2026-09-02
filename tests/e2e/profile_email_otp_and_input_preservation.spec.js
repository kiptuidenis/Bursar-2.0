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

    // Click Save Profile
    await page.click('#profile-info-form button[type="submit"]');

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
    const registerTabBtn = page.locator('#auth-tab-register, [data-auth-tab="register"]');
    if (await registerTabBtn.count() > 0) {
      await registerTabBtn.first().click();
    }

    await page.fill('#register-email', existingEmail);
    await page.fill('#register-password', 'Another!P@ssw0rd1');
    await page.click('#register-submit-btn, #register-form button[type="submit"]');

    // Verify error message is shown
    await expect(page.locator('#auth-error, .auth-error, #register-error')).toBeVisible();
    await expect(page.locator('#auth-error, .auth-error, #register-error')).toContainText(/already exists/i);

    expect(pageErrors).toHaveLength(0);
  });
});
