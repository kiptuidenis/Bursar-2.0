const { test, expect } = require('@playwright/test');

test.describe('Mobile Alphanumeric Auth & Tab Switching', () => {

  test('Auth modal defaults to text input and switches attributes on tabs', async ({ page }) => {
    test.setTimeout(30000);
    await page.goto('/');

    // Open login modal
    await page.click('a[href="#login"]');
    const authOverlay = page.locator('#auth-overlay');
    await expect(authOverlay).toHaveClass(/active/);

    const authInput = page.locator('#auth-phone');
    const emailLabel = page.locator('#email-label');

    // 1. Verify Log In tab state: inputmode is text, label says Email or Phone Number
    await expect(emailLabel).toHaveText('Email or Phone Number');
    await expect(authInput).toHaveAttribute('type', 'text');
    await expect(authInput).toHaveAttribute('inputmode', 'text');
    await expect(authInput).toHaveAttribute('placeholder', /e\.g\. user@example\.com or 0712345678/);

    // Can type letters and symbols (email format)
    await authInput.fill('customer.test@example.com');
    await expect(authInput).toHaveValue('customer.test@example.com');

    // 2. Switch to Register tab
    await page.click('#tab-signup');
    await expect(emailLabel).toHaveText('Email Address');
    await expect(authInput).toHaveAttribute('type', 'email');
    await expect(authInput).toHaveAttribute('inputmode', 'email');
    await expect(authInput).toHaveAttribute('placeholder', 'e.g. user@example.com');
    await expect(page.locator('#auth-confirm-password-group')).toBeVisible();

    // 3. Switch back to Log In tab
    await page.click('#tab-login');
    await expect(emailLabel).toHaveText('Email or Phone Number');
    await expect(authInput).toHaveAttribute('type', 'text');
    await expect(authInput).toHaveAttribute('inputmode', 'text');
    await expect(page.locator('#auth-confirm-password-group')).toBeHidden();
  });

});
