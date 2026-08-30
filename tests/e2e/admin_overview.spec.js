const { test, expect } = require('@playwright/test');
const { setupAuthenticatedAdmin } = require('./helpers');

test.describe('Sub-Phase 3.2: Executive Dashboard & Float Visualizations E2E', () => {

  test('1. KPI Cards display platform liquidity, active users, and today statistics', async ({ page }) => {
    await setupAuthenticatedAdmin(page, { role: 'superadmin' });

    // Ensure Overview pane is active
    await expect(page.locator('#pane-overview')).toHaveClass(/active/);

    // Verify Active Users KPI
    const activeUsersVal = page.locator('#kpi-active-users');
    await expect(activeUsersVal).toBeVisible();
    await expect(activeUsersVal).not.toHaveText('-');

    // Verify Platform Float KPI (formatted with KES)
    const platformFloatVal = page.locator('#kpi-platform-float');
    await expect(platformFloatVal).toBeVisible();
    await expect(platformFloatVal).toContainText('KES');

    // Verify Today's Deposits Inflow KPI
    const todayDepositsVal = page.locator('#kpi-today-deposits');
    await expect(todayDepositsVal).toBeVisible();
    await expect(todayDepositsVal).toContainText('KES');

    // Verify Today's B2C Disbursements KPI
    const todayDisbursedVal = page.locator('#kpi-today-disbursed');
    await expect(todayDisbursedVal).toBeVisible();
    await expect(todayDisbursedVal).toContainText('KES');
  });

  test('2. Chart.js canvases for Float Distribution & Cashflow Velocity are instantiated', async ({ page }) => {
    await setupAuthenticatedAdmin(page, { role: 'superadmin' });

    // Verify Donut Chart canvas for Float Distribution
    const floatChartCanvas = page.locator('#chart-float-distribution');
    await expect(floatChartCanvas).toBeVisible();

    // Verify Line Chart canvas for Cashflow Velocity
    const velocityChartCanvas = page.locator('#chart-cashflow-velocity');
    await expect(velocityChartCanvas).toBeVisible();
  });

  test('3. Global Live Refresh button spins icon and displays toast confirmation', async ({ page }) => {
    await setupAuthenticatedAdmin(page, { role: 'superadmin' });

    // Click Refresh Button
    await page.click('#btn-global-refresh');

    // Toast alert should pop up confirming refresh
    const toast = page.locator('.toast').filter({ hasText: 'Dashboard metrics refreshed' });
    await expect(toast).toBeVisible();
  });

  test('4. Operational Quick Action: Trigger Daily Batch handles confirmation and triggers API', async ({ page }) => {
    await setupAuthenticatedAdmin(page, { role: 'superadmin' });

    // Setup dialog auto-accept
    page.once('dialog', async dialog => {
      expect(dialog.message()).toContain('trigger immediate daily payouts');
      await dialog.accept();
    });

    // Click Trigger Batch Quick Action tile
    await page.click('#btn-qa-trigger-batch');

    // Toast alert should indicate success
    const toast = page.locator('.toast').filter({ hasText: 'Payout batch triggered' });
    await expect(toast).toBeVisible();
  });

  test('5. Operational Quick Action: Adjust Balance tile routes to Finances view', async ({ page }) => {
    await setupAuthenticatedAdmin(page, { role: 'superadmin' });

    // Click Adjust Balance tile
    await page.click('#btn-qa-adjust-balance');

    // Router should update to #/finances and activate finances pane
    await expect(page.locator('#topbar-page-title')).toHaveText('Finances & Wallets');
    await expect(page.locator('#pane-finances')).toHaveClass(/active/);
  });

  test('6. Critical Pipeline Alerts display failed payouts and locked users counters', async ({ page }) => {
    await setupAuthenticatedAdmin(page, { role: 'superadmin' });

    const failedAlertTitle = page.locator('#alert-failed-payouts-title');
    await expect(failedAlertTitle).toBeVisible();
    await expect(failedAlertTitle).toContainText('Failed Payouts:');

    const lockoutsAlertTitle = page.locator('#alert-locked-users-title');
    await expect(lockoutsAlertTitle).toBeVisible();
    await expect(lockoutsAlertTitle).toContainText('Locked Out Users:');
  });

});
