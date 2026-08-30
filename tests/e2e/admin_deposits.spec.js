const { test, expect } = require('@playwright/test');
const { setupAuthenticatedAdmin } = require('./helpers');

/**
 * Seed customer user and STK deposit transactions for E2E testing.
 * Calls /api/test/seed-deposit directly without setting customer session cookies.
 */
async function seedDepositScenario(page, { status = 'PENDING', amount = 3500, receipt = null } = {}) {
  const randomDigits = Math.floor(10000000 + Math.random() * 90000000);
  const phone = `2547${randomDigits}`;
  const email = `dep_${phone}@bursar.co.ke`;
  const checkoutId = `ws_CO_TEST_${Date.now()}_${randomDigits.toString().slice(0, 4)}`;

  const depRes = await page.request.post('/api/test/seed-deposit', {
    data: {
      phone_number: phone,
      email: email,
      checkout_request_id: checkoutId,
      amount: amount,
      status: status,
      mpesa_receipt: receipt
    }
  });
  const depData = await depRes.json();
  const userId = depData.user_id;

  return { userId, phone, email, checkoutId, amount, status, receipt };
}

test.describe('Admin Portal Sub-Phase 3.5: M-Pesa STK Push Deposits & Manual Reconciliation E2E Tests', () => {

  test('1. Admin can navigate to Deposits pane, view total collected volume and transactions table', async ({ page }) => {
    await setupAuthenticatedAdmin(page, { role: 'finops' });
    const scenario = await seedDepositScenario(page, { status: 'COMPLETED', amount: 5000, receipt: 'QWE123TEST' });

    // Navigate to Deposits
    await page.click('a[data-route="deposits"]');
    await page.waitForTimeout(400);

    const depositsPane = page.locator('#pane-deposits');
    await expect(depositsPane).toHaveClass(/active/);

    // Verify Total Collected volume stat
    const totalVolume = page.locator('#deposits-total-volume');
    await expect(totalVolume).toBeVisible();
    await expect(totalVolume).toContainText('KES');

    // Verify table renders
    const table = page.locator('#deposits-table');
    await expect(table).toBeVisible();

    const rows = page.locator('#deposits-table-body tr');
    await expect(rows.first()).toBeVisible();
  });

  test('2. Search input filters deposit records dynamically', async ({ page }) => {
    await setupAuthenticatedAdmin(page, { role: 'finops' });
    const scenario = await seedDepositScenario(page, { status: 'COMPLETED', amount: 4500, receipt: 'SRCH_REC_8899' });

    await page.click('a[data-route="deposits"]');
    await page.waitForTimeout(400);

    // Search by unique M-Pesa receipt
    const searchInput = page.locator('#deposits-search-input');
    await searchInput.fill('SRCH_REC_8899');
    await page.waitForTimeout(500);

    const rows = page.locator('#deposits-table-body tr');
    await expect(rows.first()).toContainText('SRCH_REC_8899');
    await expect(rows.first()).toContainText('4,500');
  });

  test('3. Status dropdown filters deposit records by status', async ({ page }) => {
    await setupAuthenticatedAdmin(page, { role: 'finops' });
    const pendingScenario = await seedDepositScenario(page, { status: 'PENDING', amount: 1500 });

    await page.click('a[data-route="deposits"]');
    await page.waitForTimeout(400);

    // Filter by PENDING
    const statusSelect = page.locator('#deposits-status-filter');
    await statusSelect.selectOption('PENDING');
    await page.waitForTimeout(500);

    const rows = page.locator('#deposits-table-body tr');
    await expect(rows.first()).toBeVisible();
    await expect(rows.first()).toContainText('PENDING');
  });

  test('4. FinOps admin can manually settle a stuck PENDING deposit with M-Pesa receipt', async ({ page }) => {
    await setupAuthenticatedAdmin(page, { role: 'finops' });
    const scenario = await seedDepositScenario(page, { status: 'PENDING', amount: 6000 });

    await page.click('a[data-route="deposits"]');
    await page.waitForTimeout(400);

    // Search for specific pending deposit
    await page.fill('#deposits-search-input', scenario.checkoutId);
    await page.waitForTimeout(500);

    // Click "Settle" button
    const settleBtn = page.locator('.btn-deposit-settle').first();
    await expect(settleBtn).toBeVisible();
    await settleBtn.click();
    await page.waitForTimeout(300);

    // Verify Manual Settle modal opens
    const modal = page.locator('#modal-manual-settle-deposit');
    await expect(modal).toBeVisible();

    // Fill form
    const generatedReceipt = `MAN_SETTLE_${Date.now().toString().slice(-6)}`;
    await page.fill('#settle-mpesa-receipt', generatedReceipt);
    await page.fill('#settle-reason', 'Verified customer payment in Safaricom MPesa statement');

    // Submit and wait for modal to disappear and ledger table to refresh
    await page.locator('#btn-submit-settle-deposit').click();
    await expect(modal).toBeHidden({ timeout: 10000 });

    const toast = page.locator('.toast');
    await expect(toast.first()).toBeVisible({ timeout: 5000 });

    await page.waitForTimeout(500);
    const rows = page.locator('#deposits-table-body tr');
    await expect(rows.first()).toContainText('COMPLETED');
    await expect(rows.first()).toContainText(generatedReceipt);
  });

  test('5. Auditor role cannot see Manual Settle or Requery mutation buttons', async ({ page }) => {
    await setupAuthenticatedAdmin(page, { role: 'auditor' });
    await seedDepositScenario(page, { status: 'PENDING', amount: 2000 });

    await page.click('a[data-route="deposits"]');
    await page.waitForTimeout(400);

    // Verify deposits table visible
    await expect(page.locator('#deposits-table')).toBeVisible();

    // Settle & Requery buttons container (rbac-finops) should be hidden for auditor
    const rbacButtons = page.locator('.rbac-finops');
    await expect(rbacButtons.first()).toBeHidden();
    await expect(page.locator('.btn-deposit-settle:visible')).toHaveCount(0);
  });

});
