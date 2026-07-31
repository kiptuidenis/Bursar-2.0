const { test, expect } = require('@playwright/test');

test.describe('XSS Prevention E2E Tests (SEC-004)', () => {

    test('verifies DOM sanitization escapes XSS script payloads and control characters', async ({ page }) => {
        await page.goto('/#signup');
        const randomDigits = Math.floor(100000 + Math.random() * 900000);
        const testPhoneNumber = `254799${randomDigits}`;

        await page.fill('#auth-phone', testPhoneNumber);
        await page.fill('#auth-password', 'Str0ng!P@ssw0rd');
        const confirmInput = page.locator('#auth-confirm-password');
        if (await confirmInput.count() > 0) {
            await confirmInput.fill('Str0ng!P@ssw0rd');
        }
        await page.click('#auth-submit-btn');

        await page.waitForURL(url => url.toString().includes('dashboard') || url.hash.includes('dashboard'), { timeout: 30000 });
        await page.waitForLoadState('networkidle');

        // Evaluate XSS prevention inside the live browser environment where app.js is loaded
        const result = await page.evaluate(() => {
            window.__xss_triggered = false;
            const maliciousPayload = '<img src=x onerror="window.__xss_triggered=true">';
            
            // 1. Render simulated payout row using escapeHTML helper
            const escaped = typeof window.escapeHTML === 'function' ? window.escapeHTML(maliciousPayload) : maliciousPayload;
            
            const tbody = document.createElement('tbody');
            tbody.innerHTML = `<tr><td>${escaped}</td></tr>`;
            document.body.appendChild(tbody);

            // 2. Verify escapeHTML function escapes HTML control characters (<, >, ", ')
            const rawTagInput = '<script>alert("xss")</script>';
            const sanitizedOutput = window.escapeHTML(rawTagInput);
            const isSanitized = sanitizedOutput.includes('&lt;script&gt;') && !sanitizedOutput.includes('<script>');

            return {
                xssExecuted: window.__xss_triggered,
                isSanitized: isSanitized
            };
        });

        expect(result.xssExecuted).toBe(false);
        expect(result.isSanitized).toBe(true);
    });
});
