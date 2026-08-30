const { test, expect } = require('@playwright/test');
const { setupAuthenticatedAdmin } = require('./helpers');

/**
 * Seed a customer user in the database via in-browser fetch.
 * Must be called AFTER page has navigated to any page on the origin.
 */
async function seedUser(page, phone, email) {
  await page.evaluate(async (payload) => {
    await fetch('/api/test/setup-session', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
      credentials: 'include'
    });
  }, { phone_number: phone, email: email, password: 'Str0ng!P@ssw0rd2026!' });
}

test.describe('Admin Portal Sub-Phase 3.3: User 360 & Customer Support Console E2E Tests', () => {

  test('1. Admin can navigate to Users Directory pane and view customer table', async ({ page }) => {
    // 1. Login as Admin first (this navigates to /admin, establishing the origin)
    await setupAuthenticatedAdmin(page, { role: 'superadmin' });

    // 2. Seed a customer user (browser is already on the origin)
    const randomDigits = Math.floor(10000000 + Math.random() * 90000000);
    const phone = `2547${randomDigits}`;
    const email = `test_${phone}@bursar.co.ke`;
    await seedUser(page, phone, email);

    // 3. Navigate to Users view via sidebar
    await page.click('a[data-route="users"]');
    await page.waitForTimeout(500);

    const usersPane = page.locator('#pane-users');
    await expect(usersPane).toHaveClass(/active/);

    // Verify customer directory table exists
    const usersTable = page.locator('#users-table');
    await expect(usersTable).toBeVisible();

    // Verify search input & status filter exist
    await expect(page.locator('#users-search-input')).toBeVisible();
    await expect(page.locator('#users-status-filter')).toBeVisible();

    // Verify table rows render
    const rows = page.locator('#users-table-body tr');
    await expect(rows.first()).toBeVisible();
  });

  test('2. Search input filters customer accounts dynamically', async ({ page }) => {
    await setupAuthenticatedAdmin(page, { role: 'superadmin' });

    const randomDigits = Math.floor(10000000 + Math.random() * 90000000);
    const phone = `2547${randomDigits}`;
    const email = `search_${phone}@bursar.co.ke`;
    await seedUser(page, phone, email);

    await page.click('a[data-route="users"]');
    await page.waitForTimeout(500);

    // Search by user's unique phone number
    const searchInput = page.locator('#users-search-input');
    await searchInput.fill(phone);
    await page.waitForTimeout(500);

    const rows = page.locator('#users-table-body tr');
    await expect(rows.first()).toContainText(phone);
  });

  test('3. Clicking Inspect 360 opens Customer Profile Modal with identity and financial float', async ({ page }) => {
    await setupAuthenticatedAdmin(page, { role: 'superadmin' });

    const randomDigits = Math.floor(10000000 + Math.random() * 90000000);
    const phone = `2547${randomDigits}`;
    const email = `inspect_${phone}@bursar.co.ke`;
    await seedUser(page, phone, email);

    await page.click('a[data-route="users"]');
    await page.waitForTimeout(500);

    // Search for the specific user
    await page.fill('#users-search-input', email);
    await page.waitForTimeout(500);

    // Click "Inspect 360°" button
    const inspectBtn = page.locator('.btn-inspect-user').first();
    await expect(inspectBtn).toBeVisible();
    await inspectBtn.click();
    await page.waitForTimeout(500);

    // Verify User 360 modal opens
    const modal360 = page.locator('#modal-user-360');
    await expect(modal360).toBeVisible();

    // Verify customer dossier content rendered
    await expect(page.locator('#u360-modal-title')).toContainText('Customer 360° Inspection');
    await expect(page.locator('#u360-modal-body')).toContainText(email);
    await expect(page.locator('#u360-modal-body')).toContainText('Financial Float & Savings');

    // Close modal
    await page.click('#modal-user-360 .btn-close-modal');
    await page.waitForTimeout(300);
    await expect(modal360).toBeHidden();
  });

  test('4. Admin can compose and dispatch an in-app notification to customer', async ({ page }) => {
    await setupAuthenticatedAdmin(page, { role: 'support' });

    const randomDigits = Math.floor(10000000 + Math.random() * 90000000);
    const phone = `2547${randomDigits}`;
    const email = `notify_${phone}@bursar.co.ke`;
    await seedUser(page, phone, email);

    await page.click('a[data-route="users"]');
    await page.waitForTimeout(500);

    // Search for user
    await page.fill('#users-search-input', email);
    await page.waitForTimeout(500);

    // Click notify button
    const notifyBtn = page.locator('.btn-notify-user').first();
    await expect(notifyBtn).toBeVisible();
    await notifyBtn.click();
    await page.waitForTimeout(300);

    // Verify Send Notification modal opens
    const notifModal = page.locator('#modal-send-notification');
    await expect(notifModal).toBeVisible();

    // Fill form
    await page.fill('#notif-title', 'Important Account Update');
    await page.selectOption('#notif-type', 'SUCCESS');
    await page.fill('#notif-message', 'Your account has been reviewed and verified by customer support.');
    await page.fill('#notif-reason', 'Verified customer identification documents.');

    // Submit notification
    await page.click('#btn-submit-send-notif');
    await page.waitForTimeout(600);

    // Verify modal closes and toast feedback appears
    await expect(notifModal).toBeHidden();
    const toast = page.locator('.toast');
    await expect(toast.first()).toBeVisible();
  });

  test('5. Status filter dropdown filters directory by account state', async ({ page }) => {
    await setupAuthenticatedAdmin(page, { role: 'superadmin' });

    await page.click('a[data-route="users"]');
    await page.waitForTimeout(500);

    const statusFilter = page.locator('#users-status-filter');
    await expect(statusFilter).toBeVisible();

    // Filter by Active & Verified
    await statusFilter.selectOption('active');
    await page.waitForTimeout(500);

    const rows = page.locator('#users-table-body tr');
    await expect(rows.first()).toBeVisible();
  });

});
