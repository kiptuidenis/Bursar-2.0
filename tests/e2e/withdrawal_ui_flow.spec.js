const { test, expect } = require('@playwright/test');
const { setupAuthenticatedUser } = require('./helpers');

test.describe('Withdrawal UI Flow', () => {
  test('Should show Get Authorization Code, reveal OTP, and display Confirm Withdrawal', async ({ page }) => {
    // 1. Setup authenticated session with enough balance
    await setupAuthenticatedUser(page, { balance: 1000 });

    // 2. Open Withdrawal Modal (Flip card, click open withdraw)
    await page.click('#debit-card-container');
    await page.waitForTimeout(600); // Wait for flip transition
    await page.click('#open-withdraw-btn');

    // Verify modal is active
    await expect(page.locator('#withdraw-modal')).toHaveClass(/active/);

    // 3. Verify initial button states
    const requestOtpBtn = page.locator('#request-withdraw-otp-btn');
    const confirmBtn = page.locator('#confirm-withdraw-submit-btn');
    const otpGroup = page.locator('#withdraw-otp-group');
    const otpInput = page.locator('#withdraw-otp');
    const errorBox = page.locator('#withdraw-error');

    await expect(requestOtpBtn).toBeVisible();
    await expect(confirmBtn).toBeHidden();
    await expect(otpGroup).toBeHidden();

    // 4. Fill in withdrawal form (amount, password)
    await page.fill('#withdraw-amount', '200');
    await page.fill('#withdraw-password', 'Str0ng!P@ssw0rd2026!');

    // 5. Click "Get Authorization Code"
    // We expect the backend call to succeed (it will mock or send real email in test env)
    // and the UI should transition.
    
    // Intercept the API call to ensure it goes through and we don't proceed too fast
    const requestPromise = page.waitForResponse(response => 
      response.url().includes('/api/profile/request-stepup-otp') && response.status() === 200
    );
    
    await requestOtpBtn.click();
    
    // Verify loading state
    await expect(requestOtpBtn).toBeDisabled();
    await expect(requestOtpBtn).toContainText('Sending Code...');
    
    // Wait for the API response
    await requestPromise;

    // 6. Verify UI transitions after OTP is dispatched
    await expect(requestOtpBtn).toBeHidden(); // Hidden after success
    await expect(otpGroup).toBeVisible(); // OTP input revealed
    await expect(confirmBtn).toBeVisible(); // Confirm button revealed
    await expect(confirmBtn).toBeEnabled();

    // Verify the OTP input has focus
    await expect(otpInput).toBeFocused();

    // 7. Click Confirm Withdrawal without entering OTP
    await confirmBtn.click();
    
    // Verify validation error
    await expect(errorBox).toBeVisible();
    await expect(errorBox).toContainText('Please enter the 6-digit verification code');
  });
});
