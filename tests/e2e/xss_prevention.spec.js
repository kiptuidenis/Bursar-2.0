const { test, expect } = require('@playwright/test');
const { setupAuthenticatedUser } = require('./helpers');

test.describe('XSS Prevention E2E Tests (SEC-004)', () => {

    test('verifies DOM sanitization escapes XSS script payloads and control characters', async ({ page }) => {
        await setupAuthenticatedUser(page);

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
