const { test, expect } = require('@playwright/test');
const { setupAuthenticatedUser } = require('./helpers');

test.describe('Bursar 2.0 Rigorous CSRF Protection E2E Tests (H-05)', () => {

  test('1. Normal user browser flow attaches X-CSRF-Token header on state-mutating requests', async ({ page }) => {
    // 1. Authenticated session
    await setupAuthenticatedUser(page);

    // 2. Verify csrf_token cookie exists in browser context
    const cookies = await page.context().cookies();
    const csrfCookie = cookies.find(c => c.name === 'csrf_token');
    expect(csrfCookie).toBeDefined();
    expect(csrfCookie.value.length).toBeGreaterThan(20);

    // 3. Intercept next state-mutating request (/api/profile update) and verify X-CSRF-Token header
    let interceptedCsrfHeader = null;
    page.on('request', request => {
      if (request.url().includes('/api/profile') && request.method() === 'POST') {
        interceptedCsrfHeader = request.headers()['x-csrf-token'];
      }
    });

    // Navigate to Profile tab and update info
    await page.click('[data-tab="profile"]');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(500);

    await page.fill('#profile-first-name', 'CSRF');
    await page.fill('#profile-last-name', 'Tester');
    await page.fill('#profile-email', 'csrf.tester@example.com');
    await page.click('#profile-info-form button[type="submit"]');

    await page.waitForTimeout(500);
    expect(interceptedCsrfHeader).toBe(csrfCookie.value);
  });

  test('2. State-mutating request with session cookie but missing X-CSRF-Token header is rejected (403)', async ({ page }) => {
    // 1. Authenticated session
    await setupAuthenticatedUser(page);

    // 2. Execute raw XHR from inside browser page omitting X-CSRF-Token header
    const responseStatus = await page.evaluate(async () => {
      return new Promise((resolve) => {
        const xhr = new XMLHttpRequest();
        xhr.open('POST', '/api/profile');
        xhr.setRequestHeader('Content-Type', 'application/json');
        xhr.onload = () => resolve(xhr.status);
        xhr.onerror = () => resolve(xhr.status);
        xhr.send(JSON.stringify({ first_name: 'Hacker', last_name: 'Attack', email: 'hacker@example.com' }));
      });
    });

    expect(responseStatus).toBe(403);
  });

  test('3. State-mutating request with mismatched / forged X-CSRF-Token header is rejected (403)', async ({ page }) => {
    // 1. Authenticated session
    await setupAuthenticatedUser(page);

    // 2. Execute raw XHR with forged X-CSRF-Token header
    const responseStatus = await page.evaluate(async () => {
      return new Promise((resolve) => {
        const xhr = new XMLHttpRequest();
        xhr.open('POST', '/api/profile');
        xhr.setRequestHeader('Content-Type', 'application/json');
        xhr.setRequestHeader('X-CSRF-Token', 'forged_csrf_token_1234567890_invalid_signature');
        xhr.onload = () => resolve(xhr.status);
        xhr.onerror = () => resolve(xhr.status);
        xhr.send(JSON.stringify({ first_name: 'Hacker', last_name: 'Attack', email: 'hacker@example.com' }));
      });
    });

    expect(responseStatus).toBe(403);
  });

  test('4. CSRF token cookie is cleared on session logout', async ({ page }) => {
    // 1. Authenticated session
    await setupAuthenticatedUser(page);

    // Verify token exists
    let cookies = await page.context().cookies();
    expect(cookies.some(c => c.name === 'csrf_token')).toBe(true);

    // Logout using sidebar button
    const logoutBtn = page.locator('#sidebar-logout-btn');
    await logoutBtn.click({ force: true });

    await page.waitForURL(url => !url.toString().includes('dashboard'));
    await page.waitForLoadState('networkidle');

    // Verify csrf_token cookie is deleted / expired (expires: -1)
    cookies = await page.context().cookies();
    const csrfCookie = cookies.find(c => c.name === 'csrf_token');
    const isCleared = !csrfCookie || csrfCookie.expires === -1 || (csrfCookie.expires && csrfCookie.expires * 1000 < Date.now());
    expect(isCleared).toBe(true);
  });

  test('5. Safe GET requests pass without requiring X-CSRF-Token header', async ({ page }) => {
    await page.goto('/');
    const res = await page.request.get('/api/auth/config');
    expect(res.status()).toBe(200);
  });

});
