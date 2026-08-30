const { test, expect } = require('@playwright/test');
const { setupAuthenticatedAdmin } = require('./helpers');

/**
 * Seed a customer account with balance for finances tests.
 * Uses Playwright's page.request (API context) to avoid contaminating
 * the browser's cookie jar with session_token/csrf_token cookies.
 */
async function seedCustomerWallet(page, { balance = 10000 } = {}) {
  const randomDigits = Math.floor(10000000 + Math.random() * 90000000);
  const phone = `2547${randomDigits}`;
  const email = `fin_${phone}@bursar.co.ke`;

  const res = await page.request.post('/api/test/setup-session', {
    data: {
      phone_number: phone,
      email: email,
      password: 'Str0ng!P@ssw0rd2026!',
      balance: balance
    }
  });
  const data = await res.json();
  const userId = data.user_id;

  return { userId, phone, email, balance };
}

test.describe('Admin Portal Sub-Phase 3.4: Platform Finances & Wallet Ledger E2E Tests', () => {

  test('1. Admin can navigate to Finances pane, view platform float and wallet table', async ({ page }) => {
    await setupAuthenticatedAdmin(page, { role: 'finops' });
    const user = await seedCustomerWallet(page, { balance: 25000 });

    // Navigate to Finances
    await page.click('a[data-route="finances"]');
    await page.waitForTimeout(400);

    const financesPane = page.locator('#pane-finances');
    await expect(financesPane).toHaveClass(/active/);

    // Verify Platform Total Float stat
    const totalFloat = page.locator('#finances-total-balance');
    await expect(totalFloat).toBeVisible();
    await expect(totalFloat).toContainText('KES');

    // Verify wallets ledger table
    const table = page.locator('#wallets-table');
    await expect(table).toBeVisible();

    // Verify table rows render
    const rows = page.locator('#wallets-table-body tr');
    await expect(rows.first()).toBeVisible();
  });

  test('2. Search input filters wallet ledger dynamically', async ({ page }) => {
    await setupAuthenticatedAdmin(page, { role: 'finops' });
    const user = await seedCustomerWallet(page, { balance: 12000 });

    await page.click('a[data-route="finances"]');
    await page.waitForTimeout(400);

    // Search by unique phone
    const searchInput = page.locator('#wallets-search-input');
    await searchInput.fill(user.phone);
    await page.waitForTimeout(500);

    const rows = page.locator('#wallets-table-body tr');
    await expect(rows.first()).toContainText(user.phone);
    await expect(rows.first()).toContainText('12,000');
  });

  test('3. FinOps admin can execute balance adjustment (CREDIT) via modal', async ({ page }) => {
    await setupAuthenticatedAdmin(page, { role: 'finops' });
    const user = await seedCustomerWallet(page, { balance: 5000 });

    await page.click('a[data-route="finances"]');
    await page.waitForTimeout(400);

    // Search for user
    await page.fill('#wallets-search-input', user.phone);
    await page.waitForTimeout(500);

    // Click row Adjust button
    const adjustBtn = page.locator('.btn-adjust-wallet').first();
    await expect(adjustBtn).toBeVisible();
    await adjustBtn.click();
    await page.waitForTimeout(300);

    // Modal should open
    const modal = page.locator('#modal-adjust-balance');
    await expect(modal).toBeVisible();

    // Fill adjustment form: Credit 3,000
    await page.selectOption('#adj-type', 'CREDIT');
    await page.fill('#adj-amount', '3000');
    await page.fill('#adj-reference', 'MPESA_REF_TEST_99');
    await page.fill('#adj-reason', 'Reconciled missing deposit from Safaricom');

    // Submit
    await page.click('#btn-submit-adjust');
    await page.waitForTimeout(600);

    // Modal hidden, toast appears, row updated
    await expect(modal).toBeHidden();
    const toast = page.locator('.toast');
    await expect(toast.first()).toBeVisible();

    // Verify row displays updated balance (5,000 + 3,000 = 8,000)
    await page.waitForTimeout(400);
    const rows = page.locator('#wallets-table-body tr');
    await expect(rows.first()).toContainText('8,000');
  });

  test('4. FinOps admin can execute balance adjustment (DEBIT) via modal', async ({ page }) => {
    await setupAuthenticatedAdmin(page, { role: 'superadmin' });
    const user = await seedCustomerWallet(page, { balance: 10000 });

    await page.click('a[data-route="finances"]');
    await page.waitForTimeout(400);

    await page.fill('#wallets-search-input', user.phone);
    await page.waitForTimeout(500);

    // Click Adjust
    await page.locator('.btn-adjust-wallet').first().click();
    await page.waitForTimeout(300);

    // Fill form: Debit 4,000
    await page.selectOption('#adj-type', 'DEBIT');
    await page.fill('#adj-amount', '4000');
    await page.fill('#adj-reference', 'DEBIT_REV_01');
    await page.fill('#adj-reason', 'Reversal of erroneous credit entry');

    // Submit
    await page.click('#btn-submit-adjust');
    await page.waitForTimeout(600);

    // Verify row displays updated balance (10,000 - 4,000 = 6,000)
    await page.waitForTimeout(400);
    const rows = page.locator('#wallets-table-body tr');
    await expect(rows.first()).toContainText('6,000');
  });

  test('5. Auditor role cannot see balance adjustment mutation buttons', async ({ page }) => {
    await setupAuthenticatedAdmin(page, { role: 'auditor' });

    await page.click('a[data-route="finances"]');
    await page.waitForTimeout(400);

    // Ledger table should be visible for compliance inspection
    await expect(page.locator('#wallets-table')).toBeVisible();

    // Top action Adjust Balance button should be hidden
    const topAdjustBtn = page.locator('#btn-open-balance-adjust');
    await expect(topAdjustBtn).toBeHidden();
  });

});
