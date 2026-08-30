const { test, expect } = require('@playwright/test');
const { setupAuthenticatedAdmin } = require('./helpers');

test.describe('Admin Portal Sub-Phase 3.8: System Health Diagnostics & Staff Admin Management E2E Tests', () => {

  test('1. Admin can navigate to System pane and inspect live runtime health indicators', async ({ page }) => {
    await setupAuthenticatedAdmin(page, { role: 'finops' });

    // Navigate to System pane
    await page.click('a[data-route="system"]');
    await page.waitForTimeout(400);

    const systemPane = page.locator('#pane-system');
    await expect(systemPane).toHaveClass(/active/);

    // Verify Health status badges
    const dbStatus = page.locator('#health-db-status');
    await expect(dbStatus).toBeVisible();
    await expect(dbStatus).toContainText('Connected');

    const schedulerStatus = page.locator('#health-scheduler-status');
    await expect(schedulerStatus).toBeVisible();
    await expect(schedulerStatus).toContainText('Active');

    const gatewayStatus = page.locator('#health-gateway-status');
    await expect(gatewayStatus).toBeVisible();
  });

  test('2. SuperAdmin can view staff administrators directory table', async ({ page }) => {
    await setupAuthenticatedAdmin(page, { role: 'superadmin' });

    await page.click('a[data-route="system"]');
    await page.waitForTimeout(400);

    // Verify SuperAdmin management card and table
    const superCard = page.locator('#superadmin-management-card');
    await expect(superCard).toBeVisible();

    const table = page.locator('#admins-table');
    await expect(table).toBeVisible();

    const rows = page.locator('#admins-table-body tr');
    await expect(rows.first()).toBeVisible();
  });

  test('3. SuperAdmin can provision a new staff administrator account via modal', async ({ page }) => {
    await setupAuthenticatedAdmin(page, { role: 'superadmin' });

    await page.click('a[data-route="system"]');
    await page.waitForTimeout(400);

    // Click "New Admin" button
    await page.click('#btn-open-create-admin');
    await page.waitForTimeout(300);

    const modal = page.locator('#modal-create-admin');
    await expect(modal).toBeVisible();

    // Fill form
    const uniqueEmail = `finops_${Date.now()}@bursar.co.ke`;
    await page.fill('#create-admin-email', uniqueEmail);
    await page.fill('#create-admin-password', 'Str0ngAdmin!Pass2026');
    await page.selectOption('#create-admin-role', 'finops');
    await page.fill('#create-admin-reason', 'Provisioning new treasury manager');

    // Submit
    await page.locator('#btn-submit-create-admin').click();
    await expect(modal).toBeHidden({ timeout: 10000 });

    const toast = page.locator('.toast');
    await expect(toast.first()).toBeVisible({ timeout: 5000 });

    // Verify row appears in directory table
    await page.waitForTimeout(500);
    const tbody = page.locator('#admins-table-body');
    await expect(tbody).toContainText(uniqueEmail, { timeout: 10000 });
  });

  test('4. SuperAdmin can update an existing staff administrator role via modal', async ({ page }) => {
    await setupAuthenticatedAdmin(page, { role: 'superadmin' });

    // Provision a support admin to modify using SuperAdmin API
    const targetEmail = `support_to_finops_${Date.now()}@bursar.co.ke`;
    await page.request.post('/api/admin/system/admins', {
      data: { email: targetEmail, password: 'Strong!Password2026', role: 'support', reason: 'Initial setup' }
    });

    await page.click('a[data-route="system"]');
    await page.waitForTimeout(400);

    // Locate target row and click "Role" edit button
    const targetRow = page.locator('#admins-table-body tr', { hasText: targetEmail });
    await expect(targetRow).toBeVisible({ timeout: 10000 });

    const editRoleBtn = targetRow.locator('.btn-edit-admin-role');
    await editRoleBtn.click();
    await page.waitForTimeout(300);

    // Verify modal opens
    const modal = page.locator('#modal-update-admin-role');
    await expect(modal).toBeVisible();

    // Change role to Auditor
    await page.selectOption('#edit-admin-role', 'auditor');
    await page.fill('#edit-admin-reason', 'Promotion to internal compliance officer');

    // Submit
    await page.locator('#btn-submit-update-admin-role').click();
    await expect(modal).toBeHidden({ timeout: 10000 });

    const toast = page.locator('.toast');
    await expect(toast.first()).toBeVisible({ timeout: 5000 });

    // Verify updated role badge
    await page.waitForTimeout(500);
    await expect(targetRow).toContainText('auditor');
  });

  test('5. Auditor and other non-superadmin roles do not see staff management controls', async ({ page }) => {
    await setupAuthenticatedAdmin(page, { role: 'auditor' });

    await page.click('a[data-route="system"]');
    await page.waitForTimeout(400);

    // System health cards visible
    await expect(page.locator('#health-db-status')).toBeVisible();

    // SuperAdmin management card should be hidden
    const superCard = page.locator('#superadmin-management-card');
    await expect(superCard).toBeHidden();
  });

});
