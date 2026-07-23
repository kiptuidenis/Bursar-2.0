const { test, expect } = require('@playwright/test');

test.describe('Bursar 2.0 Production Fintech Account Lockout & CSS Prohibition E2E Tests', () => {

  test('Should lock account after 5 failed PIN logins and enforce cursor: not-allowed prohibition styling', async ({ page }) => {
    // 1. Intercept /api/auth/login to mock 5th failure lockout response
    await page.route('**/api/auth/login', async route => {
      await route.fulfill({
        status: 429,
        contentType: 'application/json',
        headers: { 'Retry-After': '900' },
        body: JSON.stringify({ detail: 'Account locked due to 5 failed login attempts. Please try again in 15 minutes.' })
      });
    });

    // 2. Visit landing page & open login modal
    await page.goto('/');
    await page.waitForLoadState('networkidle');
    await page.click('#nav-login-btn');

    // 3. Fill login credentials & click submit
    await page.fill('#auth-phone', '254755999888');
    await page.fill('#auth-password', '000000');
    await page.click('#auth-submit-btn');

    await page.waitForTimeout(500);

    // 4. Assert error message visibility and content
    const errorMsgLocator = page.locator('#auth-error-msg');
    await expect(errorMsgLocator).toBeVisible();

    const errorText = await errorMsgLocator.innerText();
    expect(errorText.toLowerCase()).toContain('account locked');

    // 5. Assert submit button is disabled
    const submitBtn = page.locator('#auth-submit-btn');
    await expect(submitBtn).toBeDisabled();

    // 6. CRITICAL CSS PROHIBITION CURSOR ASSERTION
    // Verify computed CSS cursor is 'not-allowed'
    const computedCursor = await submitBtn.evaluate(el => window.getComputedStyle(el).cursor);
    expect(computedCursor).toBe('not-allowed');
  });

});
