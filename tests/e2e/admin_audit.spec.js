const { test, expect } = require('@playwright/test');
const { setupAuthenticatedAdmin } = require('./helpers');

test.describe('Admin Portal Sub-Phase 3.7: Compliance Audit Logs & Security Forensics E2E Tests', () => {

  test('1. Auditor can navigate to Audit Logs pane and view compliance audit trail', async ({ page }) => {
    await setupAuthenticatedAdmin(page, { role: 'auditor' });

    // Navigate to Audit Logs
    await page.click('a[data-route="audit"]');
    await page.waitForTimeout(400);

    const auditPane = page.locator('#pane-audit');
    await expect(auditPane).toHaveClass(/active/);

    // Verify table and export button render
    const table = page.locator('#audit-table');
    await expect(table).toBeVisible();

    const exportBtn = page.locator('#btn-export-audit-csv');
    await expect(exportBtn).toBeVisible();

    const rows = page.locator('#audit-table-body tr');
    await expect(rows.first()).toBeVisible();
  });

  test('2. Search input filters audit logs dynamically', async ({ page }) => {
    await setupAuthenticatedAdmin(page, { role: 'auditor' });

    await page.click('a[data-route="audit"]');
    await page.waitForTimeout(400);

    // Search for login or session events
    const searchInput = page.locator('#audit-search-input');
    await searchInput.fill('ADMIN_LOGIN');
    await page.waitForTimeout(500);

    const rows = page.locator('#audit-table-body tr');
    await expect(rows.first()).toBeVisible();
    await expect(rows.first()).toContainText('ADMIN_LOGIN');
  });

  test('3. Action dropdown filters audit logs by action type', async ({ page }) => {
    const admin = await setupAuthenticatedAdmin(page, { role: 'auditor' });

    await page.request.post('/api/test/seed-audit-log', {
      data: {
        admin_id: 1,
        action: 'ADMIN_FINANCIAL_ADJUSTMENT',
        reason: 'Filter verification financial adjustment'
      }
    });

    await page.click('a[data-route="audit"]');
    await page.waitForTimeout(400);

    // Filter by Financial Adjustment
    const actionSelect = page.locator('#audit-action-filter');
    await actionSelect.selectOption('ADMIN_FINANCIAL_ADJUSTMENT');
    await page.waitForTimeout(500);

    const rows = page.locator('#audit-table-body tr');
    await expect(rows.first()).toBeVisible();
    await expect(rows.first()).toContainText('ADMIN_FINANCIAL_ADJUSTMENT');
  });

  test('4. Admin can inspect state transformation payload in inspector modal', async ({ page }) => {
    await setupAuthenticatedAdmin(page, { role: 'superadmin' });

    await page.click('a[data-route="audit"]');
    await page.waitForTimeout(400);

    // Click "Inspect" on first row
    const inspectBtn = page.locator('.btn-inspect-audit').first();
    await expect(inspectBtn).toBeVisible();
    await inspectBtn.click();
    await page.waitForTimeout(300);

    // Verify Inspector modal opens
    const modal = page.locator('#modal-audit-payload');
    await expect(modal).toBeVisible();

    const beforePre = page.locator('#audit-before-state');
    await expect(beforePre).toBeVisible();

    const afterPre = page.locator('#audit-after-state');
    await expect(afterPre).toBeVisible();

    // Close modal
    await page.click('button[data-modal="modal-audit-payload"]');
    await page.waitForTimeout(300);
    await expect(modal).toBeHidden();
  });

  test('5. Export CSV triggers file download endpoint', async ({ page }) => {
    await setupAuthenticatedAdmin(page, { role: 'auditor' });

    await page.click('a[data-route="audit"]');
    await page.waitForTimeout(400);

    // Verify download response
    const downloadPromise = page.waitForEvent('download');
    await page.click('#btn-export-audit-csv');
    const download = await downloadPromise;

    expect(download.suggestedFilename()).toBe('bursar_admin_audit_logs.csv');
  });

});
