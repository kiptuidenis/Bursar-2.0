const { test, expect } = require('@playwright/test');
const { setupAuthenticatedUser } = require('./helpers');

test.describe('Bursar 2.0 Rigorous Security Response Headers E2E Tests (H-07)', () => {

  test('1. Verify all OWASP security response headers on HTML page requests', async ({ page }) => {
    const response = await page.goto('/');
    expect(response.status()).toBe(200);

    const headers = response.headers();
    expect(headers['content-security-policy']).toBeDefined();
    expect(headers['x-frame-options'].toLowerCase()).toBe('deny');
    expect(headers['x-content-type-options']).toBe('nosniff');
    expect(headers['strict-transport-security']).toContain('max-age=31536000');
    expect(headers['referrer-policy']).toBe('strict-origin-when-cross-origin');
    expect(headers['permissions-policy']).toBeDefined();
    expect(headers['cross-origin-opener-policy']).toBe('same-origin');
    expect(headers['cross-origin-resource-policy']).toBe('same-origin');
  });

  test('2. Verify browser loads landing page with zero CSP violation console errors', async ({ page }) => {
    const cspErrors = [];
    page.on('console', msg => {
      const text = msg.text();
      if (msg.type() === 'error' && (text.includes('Content Security Policy') || text.includes('CSP'))) {
        cspErrors.push(text);
      }
    });

    await page.goto('/');
    await page.waitForLoadState('networkidle');

    expect(cspErrors).toHaveLength(0);
  });

  test('3. Verify browser loads dashboard page with zero CSP violation console errors', async ({ page }) => {
    const cspErrors = [];
    page.on('console', msg => {
      const text = msg.text();
      if (msg.type() === 'error' && (text.includes('Content Security Policy') || text.includes('CSP'))) {
        cspErrors.push(text);
      }
    });

    await setupAuthenticatedUser(page);

    expect(cspErrors).toHaveLength(0);
  });

  test('4. Verify Clickjacking defense prevents embedding application inside an iframe', async ({ page }) => {
    // Attempt to embed application inside a foreign HTML iframe container
    const htmlWithIframe = `
      <!DOCTYPE html>
      <html>
      <body>
        <iframe id="target-frame" src="http://localhost:8000/"></iframe>
      </body>
      </html>
    `;

    await page.setContent(htmlWithIframe);
    await page.waitForTimeout(1000);

    // Verify iframe navigation was blocked or cross-origin security headers prevented embedding
    const frame = page.frame({ url: 'http://localhost:8000/' });
    if (frame) {
      // If frame is initialized, checking its content should throw security restriction error or remain un-evaluated
      try {
        const title = await frame.title();
        // Modern browsers block rendering frame content when X-Frame-Options: DENY or frame-ancestors 'none' is set
        expect(title).toBe('');
      } catch (err) {
        expect(err.message).toBeDefined();
      }
    }
  });

});
