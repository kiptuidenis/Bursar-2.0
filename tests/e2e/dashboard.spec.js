const { test, expect } = require('@playwright/test');

test.describe('Bursar 2.0 End-to-End Visual & Functional Tests', () => {
  let pageErrors = [];

  test.beforeEach(({ page }) => {
    pageErrors = [];
    // Collect any client-side JavaScript runtime exceptions
    page.on('pageerror', (exception) => {
      console.error('Browser console TypeError/Exception:', exception.message);
      pageErrors.push(exception.message);
    });
  });

  test('Should perform Signup, auto-login, verify dashboard buttons, and logout without console errors', async ({ page }) => {
    // 1. Visit signup page directly
    await page.goto('/#signup');

    // 2. Generate a random Safaricom phone number to prevent "number already registered" errors
    const randomDigits = Math.floor(100000 + Math.random() * 900000);
    const testPhoneNumber = `254700${randomDigits}`;
    
    // 3. Fill registration details
    await page.fill('#auth-phone', testPhoneNumber);
    await page.fill('#auth-password', '123456');

    // 4. Click Register button (triggers submit, succeeds, auto-submits login, and redirects)
    await page.click('#auth-submit-btn');

    // 5. Wait for the URL to change to the dashboard
    await page.waitForURL('**/dashboard');
    expect(page.url()).toContain('/dashboard');

    // 6. Assert that NO runtime JS console TypeErrors occurred during page load / setup
    expect(pageErrors).toHaveLength(0);

    // 7. Verify "Deposit Funds" button works (opens modal)
    await page.click('#open-deposit-btn');
    await expect(page.locator('#deposit-modal')).toHaveClass(/active/);
    
    // Close the Deposit modal
    await page.click('#close-deposit-btn');
    await expect(page.locator('#deposit-modal')).not.toHaveClass(/active/);

    // 8. Verify "Create" (Budget Creator Modal) button works (opens modal)
    await page.click('#open-budget-designer-btn');
    await expect(page.locator('#budget-designer-modal')).toHaveClass(/active/);

    // Close the Budget Designer modal
    await page.click('#close-budget-designer-btn');
    await expect(page.locator('#budget-designer-modal')).not.toHaveClass(/active/);

    // 9. Verify "Settings" Toggle drawer works (opens settings drawer)
    await page.click('#toggle-settings-btn');
    await expect(page.locator('#settings-drawer')).toHaveClass(/active/);

    // Close Settings drawer
    await page.click('#close-settings-btn');
    await expect(page.locator('#settings-drawer')).not.toHaveClass(/active/);

    // 10. Verify "Logout" button works (redirects back to homepage)
    await page.click('#logout-btn');
    await page.waitForURL('**/');
    expect(page.url()).not.toContain('/dashboard');

    // Ensure no console exceptions occurred during any of these transitions
    expect(pageErrors).toHaveLength(0);
  });

  test('Should toggle sidebar collapse state and switch tabs successfully', async ({ page }) => {
    // 1. Signup & auto-login
    await page.goto('/#signup');
    const randomDigits = Math.floor(100000 + Math.random() * 900000);
    const testPhoneNumber = `254700${randomDigits}`;
    await page.fill('#auth-phone', testPhoneNumber);
    await page.fill('#auth-password', '123456');
    await page.click('#auth-submit-btn');
    await page.waitForURL('**/dashboard');

    // 2. Verify sidebar is visible and not collapsed initially
    const sidebar = page.locator('#sidebar-nav');
    await expect(sidebar).toBeVisible();
    await expect(sidebar).not.toHaveClass(/collapsed/);

    // 3. Click the sidebar collapse button
    await page.click('#sidebar-collapse-btn');
    await expect(sidebar).toHaveClass(/collapsed/);

    // 4. Click it again to expand
    await page.click('#sidebar-collapse-btn');
    await expect(sidebar).not.toHaveClass(/collapsed/);

    // 5. Test tab switching: click Transactions tab
    await page.click('[data-tab="transactions"]');
    await expect(page.locator('#view-transactions')).toHaveClass(/active/);
    await expect(page.locator('#view-dashboard')).toHaveClass(/hidden/);

    // 6. Return to Dashboard tab
    await page.click('[data-tab="dashboard"]');
    await expect(page.locator('#view-dashboard')).toHaveClass(/active/);
    await expect(page.locator('#view-transactions')).toHaveClass(/hidden/);
  });
});
