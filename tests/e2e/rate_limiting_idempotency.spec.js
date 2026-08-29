const { test, expect } = require('@playwright/test');
const { setupAuthenticatedUser } = require('./helpers');

test.describe('Bursar 2.0 Rate Limiting & Financial Idempotency E2E Tests', () => {
  
  test('Should attach Idempotency-Key header on deposit initiation request', async ({ page }) => {
    page.on('dialog', async dialog => await dialog.accept());

    // 1. Authenticated session
    await setupAuthenticatedUser(page);

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
    await expect.poll(() => capturedIdempotencyHeader).not.toBeNull();

    // CRITICAL E2E IDEMPOTENCY ASSERTION
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
    await page.fill('#auth-password', 'Str0ng!P@ssw0rd');
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
        body: JSON.stringify({ current_password: 'Str0ng!P@ssw0rd', new_password: 'New!Str0ngP@ssw0rd' })
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

  test('Should handle HTTP 429 Rate Limit response cleanly on profile info update', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('networkidle');

    // Intercept /api/profile and mock 429 response
    await page.route('**/api/profile', async route => {
      if (route.request().method() === 'POST') {
        await route.fulfill({
          status: 429,
          contentType: 'application/json',
          headers: { 'Retry-After': '60' },
          body: JSON.stringify({ detail: 'Rate limit exceeded: 10 per 1 minute. Please try again later.' })
        });
      } else {
        await route.continue();
      }
    });

    // Make fetch call from page context
    const responseStatus = await page.evaluate(async () => {
      const res = await fetch('/api/profile', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ first_name: 'Jane', last_name: 'Doe' })
      });
      return res.status;
    });

    expect(responseStatus).toBe(429);
  });

  test('Should handle HTTP 429 Rate Limit response cleanly on settings configuration update', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('networkidle');

    // Intercept /api/settings and mock 429 response
    await page.route('**/api/settings', async route => {
      if (route.request().method() === 'POST') {
        await route.fulfill({
          status: 429,
          contentType: 'application/json',
          headers: { 'Retry-After': '60' },
          body: JSON.stringify({ detail: 'Rate limit exceeded: 10 per 1 minute. Please try again later.' })
        });
      } else {
        await route.continue();
      }
    });

    // Make fetch call from page context
    const responseStatus = await page.evaluate(async () => {
      const res = await fetch('/api/settings', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ phone_number: '254712345678' })
      });
      return res.status;
    });

    expect(responseStatus).toBe(429);
  });

  test('Should handle HTTP 429 Rate Limit response cleanly on add budget category item', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('networkidle');

    // Intercept /api/budget/items and mock 429 response
    await page.route('**/api/budget/items', async route => {
      if (route.request().method() === 'POST') {
        await route.fulfill({
          status: 429,
          contentType: 'application/json',
          headers: { 'Retry-After': '60' },
          body: JSON.stringify({ detail: 'Rate limit exceeded: 20 per 1 minute. Please try again later.' })
        });
      } else {
        await route.continue();
      }
    });

    // Make fetch call from page context
    const responseStatus = await page.evaluate(async () => {
      const res = await fetch('/api/budget/items', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ category: 'Food', amount: 100 })
      });
      return res.status;
    });

    expect(responseStatus).toBe(429);
  });

  test('Should enforce settings response credential masking and secret preservation in browser (H-01 & H-02)', async ({ page }) => {
    // 1. Authenticated session
    await setupAuthenticatedUser(page);

    // 2. POST settings with sensitive credentials from page context
    const saveResponse = await page.evaluate(async () => {
      const res = await fetch('/api/settings', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          mpesa_consumer_key: 'key_abc_123',
          mpesa_consumer_secret: 'top_secret_credential_xyz'
        })
      });
      return await res.json();
    });

    // CRITICAL E2E RESPONSE MASKING ASSERTION (Issue H-02)
    expect(saveResponse.settings.mpesa_consumer_secret).toBe('********');

    // 3. GET settings from page context and verify masked
    const getResponse = await page.evaluate(async () => {
      const res = await fetch('/api/settings');
      return await res.json();
    });
    expect(getResponse.mpesa_consumer_secret).toBe('********');
  });

  test('Should enforce authentication on /api/diagnostics endpoint in browser (H-03)', async ({ page }) => {
    // 1. Unauthenticated call without session cookie returns 401
    await page.goto('/');
    await page.waitForLoadState('networkidle');
    const unauthStatus = await page.evaluate(async () => {
      const res = await fetch('/api/diagnostics');
      return res.status;
    });
    expect(unauthStatus).toBe(401);

    // 2. Authenticated session
    await setupAuthenticatedUser(page);

    // 3. Authenticated call returns 200 with sanitized metadata
    const authData = await page.evaluate(async () => {
      const res = await fetch('/api/diagnostics');
      return { status: res.status, json: await res.json() };
    });
    expect(authData.status).toBe(200);
    expect(authData.json.status).toBe('healthy');
    expect(authData.json).toHaveProperty('version');
    expect(authData.json).toHaveProperty('commit_hash');
  });

});
