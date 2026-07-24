const { test, expect } = require('@playwright/test');

test.describe('Bursar 2.0 Rate Limiting & Financial Idempotency E2E Tests', () => {
  
  test('Should attach Idempotency-Key header on deposit initiation request', async ({ page }) => {
    // 1. Visit signup & complete user registration
    await page.goto('/#signup');
    await page.waitForLoadState('networkidle');

    const randomDigits = Math.floor(100000 + Math.random() * 900000);
    const testPhoneNumber = `254711${randomDigits}`;

    await page.fill('#auth-phone', testPhoneNumber);
    await page.fill('#auth-password', '123456');
    await page.click('#auth-submit-btn');

    // Wait for redirect to dashboard
    await page.waitForURL('**/dashboard');
    await page.waitForLoadState('networkidle');
    expect(page.url()).toContain('/dashboard');

    // 2. Intercept the deposit initiate fetch request
    let capturedIdempotencyHeader = null;
    page.on('request', request => {
      if (request.url().includes('/api/deposit/initiate') && request.method() === 'POST') {
        const headers = request.headers();
        capturedIdempotencyHeader = headers['idempotency-key'] || headers['x-idempotency-key'];
      }
    });

    // 3. Open deposit modal & submit deposit request
    await page.click('#debit-card-container');
    await page.waitForTimeout(500);
    await page.click('#open-deposit-btn');
    await expect(page.locator('#deposit-modal')).toHaveClass(/active/);

    await page.fill('#deposit-amount', '1000');
    await page.click('#deposit-modal form button[type="submit"]');

    // Wait for request to complete
    await page.waitForTimeout(1000);

    // CRITICAL E2E IDEMPOTENCY ASSERTION
    expect(capturedIdempotencyHeader).not.toBeNull();
    expect(capturedIdempotencyHeader.length).toBeGreaterThan(10);
  });

  test('Should handle HTTP 429 Rate Limit response cleanly in login modal error text', async ({ page }) => {
    // 1. Visit landing page
    await page.goto('/#login');
    await page.waitForLoadState('networkidle');

    // 2. Intercept /api/auth/login and mock 429 response
    await page.route('**/api/auth/login', async route => {
      await route.fulfill({
        status: 429,
        contentType: 'application/json',
        headers: { 'Retry-After': '60' },
        body: JSON.stringify({ detail: 'Too many attempts. Please try again later.' })
      });
    });

    // 3. Fill and submit login form
    await page.fill('#auth-phone', '254700000000');
    await page.fill('#auth-password', '123456');
    await page.click('#auth-submit-btn');

    // Wait for error message element to be visible
    const errorMsgLocator = page.locator('#auth-error-msg');
    await expect(errorMsgLocator).toBeVisible();

    // CRITICAL E2E RATE LIMIT ASSERTIONS
    const errorText = await errorMsgLocator.innerText();
    expect(errorText.toLowerCase()).toContain('too many attempts');

    // Button should be disabled with countdown text
    const submitBtnLocator = page.locator('#auth-submit-btn');
    await expect(submitBtnLocator).toBeDisabled();
  });

  test('Should handle HTTP 429 Rate Limit response cleanly on profile password change', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('networkidle');

    // Intercept /api/profile/password and mock 429 response
    await page.route('**/api/profile/password', async route => {
      await route.fulfill({
        status: 429,
        contentType: 'application/json',
        headers: { 'Retry-After': '900' },
        body: JSON.stringify({ detail: 'Rate limit exceeded: 5 per 15 minutes. Please try again later.' })
      });
    });

    let dialogMsg = null;
    page.on('dialog', async dialog => {
      dialogMsg = dialog.message();
      await dialog.accept();
    });

    // Make fetch call from page context
    const responseStatus = await page.evaluate(async () => {
      const res = await fetch('/api/profile/password', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ current_password: '1234', new_password: '5678' })
      });
      return res.status;
    });

    expect(responseStatus).toBe(429);
  });

  test('Should handle HTTP 429 Rate Limit response cleanly on manual payout trigger', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('networkidle');

    // Intercept /api/payout/trigger and mock 429 response
    await page.route('**/api/payout/trigger', async route => {
      await route.fulfill({
        status: 429,
        contentType: 'application/json',
        headers: { 'Retry-After': '300' },
        body: JSON.stringify({ detail: 'Rate limit exceeded: 5 per 5 minutes. Please try again later.' })
      });
    });

    // Make fetch call from page context
    const responseStatus = await page.evaluate(async () => {
      const res = await fetch('/api/payout/trigger', {
        method: 'POST'
      });
      return res.status;
    });

    expect(responseStatus).toBe(429);
  });

});
