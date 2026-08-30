const { test, expect } = require('@playwright/test');
const { setupAuthenticatedAdmin } = require('./helpers');

test.describe('Admin Portal E2E Tests', () => {

  test('1. Unauthenticated visit to /admin renders login card', async ({ page }) => {
    await page.goto('/admin');
    await page.waitForLoadState('networkidle');

    // Login container should be visible, app shell hidden
    const loginView = page.locator('#view-login');
    await expect(loginView).toBeVisible();

    const appView = page.locator('#view-app');
    await expect(appView).toBeHidden();

    // Verify form elements exist
    await expect(page.locator('#admin-email')).toBeVisible();
    await expect(page.locator('#admin-password')).toBeVisible();
    await expect(page.locator('#btn-admin-login')).toBeVisible();
  });

  test('2. Invalid login displays error banner', async ({ page }) => {
    await page.goto('/admin');
    await page.waitForLoadState('networkidle');

    await page.fill('#admin-email', 'invalid_admin@bursar.co.ke');
    await page.fill('#admin-password', 'WrongPassword123!');
    await page.click('#btn-admin-login');

    const errBanner = page.locator('#login-error-banner');
    await expect(errBanner).toBeVisible();
  });

  test('3. Authenticated admin enters SPA and sees overview dashboard', async ({ page }) => {
    const admin = await setupAuthenticatedAdmin(page, { role: 'superadmin' });

    // App layout should now be visible
    const appView = page.locator('#view-app');
    await expect(appView).toBeVisible();

    // Verify admin email & role displayed in sidebar
    await expect(page.locator('#current-admin-email')).toHaveText(admin.email);
    await expect(page.locator('#current-admin-role')).toHaveText('superadmin');

    // Verify session countdown chip is active
    await expect(page.locator('#session-timer-chip')).toBeVisible();

    // Overview pane should be active by default
    await expect(page.locator('#pane-overview')).toHaveClass(/active/);
    await expect(page.locator('#topbar-page-title')).toHaveText('Executive Overview');
  });

  test('4. SPA Hash Router navigates across all view panes', async ({ page }) => {
    await setupAuthenticatedAdmin(page, { role: 'superadmin' });

    // Navigate to Users 360
    await page.click('a[data-route="users"]');
    await expect(page.locator('#topbar-page-title')).toHaveText('User 360 Explorer');
    await expect(page.locator('#pane-users')).toHaveClass(/active/);

    // Navigate to Finances
    await page.click('a[data-route="finances"]');
    await expect(page.locator('#topbar-page-title')).toHaveText('Finances & Wallets');
    await expect(page.locator('#pane-finances')).toHaveClass(/active/);

    // Navigate to Deposits
    await page.click('a[data-route="deposits"]');
    await expect(page.locator('#topbar-page-title')).toHaveText('STK Push Deposits');
    await expect(page.locator('#pane-deposits')).toHaveClass(/active/);

    // Navigate to Payouts
    await page.click('a[data-route="payouts"]');
    await expect(page.locator('#topbar-page-title')).toHaveText('B2C Disbursements');
    await expect(page.locator('#pane-payouts')).toHaveClass(/active/);

    // Navigate to Audit Logs
    await page.click('a[data-route="audit"]');
    await expect(page.locator('#topbar-page-title')).toHaveText('Audit Logs');
    await expect(page.locator('#pane-audit')).toHaveClass(/active/);

    // Navigate to System Health
    await page.click('a[data-route="system"]');
    await expect(page.locator('#topbar-page-title')).toHaveText('System Health & Config');
    await expect(page.locator('#pane-system')).toHaveClass(/active/);
  });

  test('5. Dark and light theme toggle switches data-theme attribute', async ({ page }) => {
    await setupAuthenticatedAdmin(page, { role: 'superadmin' });

    const html = page.locator('html');
    await expect(html).toHaveAttribute('data-theme', 'dark');

    // Click theme toggle
    await page.click('#btn-theme-toggle');
    await expect(html).toHaveAttribute('data-theme', 'light');

    // Click again to toggle back
    await page.click('#btn-theme-toggle');
    await expect(html).toHaveAttribute('data-theme', 'dark');
  });

  test('6. RBAC Guards enforce role-based visibility for Auditor role', async ({ page }) => {
    // Log in as Auditor (strictly read-only role)
    await setupAuthenticatedAdmin(page, { role: 'auditor' });

    const appView = page.locator('#view-app');
    await expect(appView).toBeVisible();

    // FinOps quick actions should be hidden
    const btnBatch = page.locator('#btn-qa-trigger-batch');
    await expect(btnBatch).toBeHidden();

    const btnAdjust = page.locator('#btn-qa-adjust-balance');
    await expect(btnAdjust).toBeHidden();
  });

});
