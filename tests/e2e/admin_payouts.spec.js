const { test, expect } = require('@playwright/test');
const { setupAuthenticatedAdmin } = require('./helpers');

/**
 * Helper to seed a customer and payout transaction directly via test API.
 */
async function seedPayoutScenario(page, { status = 'FAILED', amount = 1200, transactionId = '', error = '' } = {}) {
  const randomDigits = Math.floor(10000000 + Math.random() * 90000000);
  const phone = `2547${randomDigits}`;
  const email = `payout_${phone}@bursar.co.ke`;
  const conversationId = `AG_B2C_${Date.now()}_${randomDigits.toString().slice(0, 4)}`;

  const res = await page.request.post('/api/test/seed-payout', {
    data: {
      phone_number: phone,
      email: email,
      amount: amount,
      status: status,
      conversation_id: conversationId,
      transaction_id: transactionId,
      error_message: error || (status === 'FAILED' ? 'The balance is insufficient for the transaction.' : '')
    }
  });
  const data = await res.json();

  return {
    payoutId: data.payout_id,
    userId: data.user_id,
    phone,
    email,
    conversationId,
    amount,
    status
  };
}

test.describe('Admin Portal Sub-Phase 3.6: M-Pesa B2C Payouts & Retry Pipeline E2E Tests', () => {

  test('1. Admin can navigate to Payouts pane, view total disbursed metric and payouts table', async ({ page }) => {
    await setupAuthenticatedAdmin(page, { role: 'finops' });
    await seedPayoutScenario(page, { status: 'COMPLETED', amount: 3000, transactionId: 'MPESA_TX_8801' });

    // Navigate to Payouts
    await page.click('a[data-route="payouts"]');
    await page.waitForTimeout(400);

    const payoutsPane = page.locator('#pane-payouts');
    await expect(payoutsPane).toHaveClass(/active/);

    // Verify Total Disbursed stat
    const totalDisbursed = page.locator('#payouts-total-disbursed');
    await expect(totalDisbursed).toBeVisible();
    await expect(totalDisbursed).toContainText('KES');

    // Verify table renders
    const table = page.locator('#payouts-table');
    await expect(table).toBeVisible();

    const rows = page.locator('#payouts-table-body tr');
    await expect(rows.first()).toBeVisible();
  });

  test('2. Search input filters payout records dynamically', async ({ page }) => {
    await setupAuthenticatedAdmin(page, { role: 'finops' });
    const scenario = await seedPayoutScenario(page, { status: 'COMPLETED', amount: 2800, transactionId: 'TX_SEARCH_UNIQUE_99' });

    await page.click('a[data-route="payouts"]');
    await page.waitForTimeout(400);

    // Search by unique transaction ID
    const searchInput = page.locator('#payouts-search-input');
    await searchInput.fill('TX_SEARCH_UNIQUE_99');
    await page.waitForTimeout(500);

    const rows = page.locator('#payouts-table-body tr');
    await expect(rows.first()).toContainText('TX_SEARCH_UNIQUE_99');
    await expect(rows.first()).toContainText('2,800');
  });

  test('3. Status dropdown filters payout records by status', async ({ page }) => {
    await setupAuthenticatedAdmin(page, { role: 'finops' });
    await seedPayoutScenario(page, { status: 'FAILED', amount: 1500 });

    await page.click('a[data-route="payouts"]');
    await page.waitForTimeout(400);

    // Filter by FAILED
    const statusSelect = page.locator('#payouts-status-filter');
    await statusSelect.selectOption('FAILED');
    await page.waitForTimeout(500);

    const rows = page.locator('#payouts-table-body tr');
    await expect(rows.first()).toBeVisible();
    await expect(rows.first()).toContainText('FAILED');
  });

  test('4. FinOps admin can retry a FAILED payout via modal', async ({ page }) => {
    await setupAuthenticatedAdmin(page, { role: 'finops' });
    const scenario = await seedPayoutScenario(page, { status: 'FAILED', amount: 2200 });

    await page.click('a[data-route="payouts"]');
    await page.waitForTimeout(400);

    // Search for specific failed payout
    await page.fill('#payouts-search-input', scenario.phone);
    await page.waitForTimeout(500);

    // Click "Retry" button
    const retryBtn = page.locator('.btn-payout-retry').first();
    await expect(retryBtn).toBeVisible();
    await retryBtn.click();
    await page.waitForTimeout(300);

    // Verify Retry modal opens
    const modal = page.locator('#modal-retry-payout');
    await expect(modal).toBeVisible();

    // Fill justification reason
    await page.fill('#retry-payout-reason', 'Retry after resolving platform utility account float balance');

    // Submit
    await page.locator('#btn-submit-retry-payout').click();
    await expect(modal).toBeHidden({ timeout: 10000 });

    const toast = page.locator('.toast');
    await expect(toast.first()).toBeVisible({ timeout: 5000 });
  });

  test('5. FinOps admin can manually reconcile a FAILED payout with external transaction ID', async ({ page }) => {
    await setupAuthenticatedAdmin(page, { role: 'finops' });
    const scenario = await seedPayoutScenario(page, { status: 'FAILED', amount: 3500 });

    await page.click('a[data-route="payouts"]');
    await page.waitForTimeout(400);

    // Search for specific failed payout
    await page.fill('#payouts-search-input', scenario.phone);
    await page.waitForTimeout(500);

    // Click "Reconcile" button
    const settleBtn = page.locator('.btn-payout-settle').first();
    await expect(settleBtn).toBeVisible();
    await settleBtn.click();
    await page.waitForTimeout(300);

    // Verify Reconcile modal opens
    const modal = page.locator('#modal-manual-settle-payout');
    await expect(modal).toBeVisible();

    // Fill form
    const txId = `MAN_TX_REC_${Date.now().toString().slice(-6)}`;
    await page.fill('#settle-payout-tx', txId);
    await page.fill('#settle-payout-reason', 'Manually transferred funds via corporate banking portal');

    // Submit
    await page.locator('#btn-submit-settle-payout').click();
    await expect(modal).toBeHidden({ timeout: 10000 });

    const toast = page.locator('.toast');
    await expect(toast.first()).toBeVisible({ timeout: 5000 });

    await page.waitForTimeout(500);
    const rows = page.locator('#payouts-table-body tr');
    await expect(rows.first()).toContainText('COMPLETED');
    await expect(rows.first()).toContainText(txId);
  });

  test('6. Auditor role cannot see Retry, Reconcile, or Trigger Batch mutation buttons', async ({ page }) => {
    await setupAuthenticatedAdmin(page, { role: 'auditor' });
    await seedPayoutScenario(page, { status: 'FAILED', amount: 1800 });

    await page.click('a[data-route="payouts"]');
    await page.waitForTimeout(400);

    // Verify table visible
    await expect(page.locator('#payouts-table')).toBeVisible();

    // Trigger batch button should be hidden for auditor
    const triggerBatchBtn = page.locator('#btn-open-trigger-batch');
    await expect(triggerBatchBtn).toBeHidden();

    // Mutation buttons container (rbac-finops) should be hidden for auditor
    const rbacButtons = page.locator('.rbac-finops');
    await expect(rbacButtons.first()).toBeHidden();
    await expect(page.locator('.btn-payout-retry:visible')).toHaveCount(0);
    await expect(page.locator('.btn-payout-settle:visible')).toHaveCount(0);
  });

});
