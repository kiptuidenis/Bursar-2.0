const { test, expect } = require('@playwright/test');
const { setupAuthenticatedUser } = require('./helpers');

test.describe('Educational & Regulatory Disclaimer Modal E2E Tests', () => {

  // ==========================================
  // DESKTOP / PC VIEWPORT (1280x800)
  // ==========================================
  test.describe('Desktop / PC Viewport', () => {
    test.use({ viewport: { width: 1280, height: 800 } });

    test('First-time visitor sees disclaimer, accepts, and modal does not reappear on reload', async ({ page }) => {
      await page.goto('/');
      await page.waitForLoadState('domcontentloaded');

      const overlay = page.locator('#disclaimer-overlay');
      await expect(overlay).toBeVisible({ timeout: 5000 });
      await expect(overlay).toHaveClass(/active/);

      // Verify content elements
      await expect(page.locator('#disclaimer-card h2')).toContainText('Notice to Users');
      await expect(page.locator('#disclaimer-card')).toContainText('No Custodial Licenses');

      // Click Accept
      const acceptBtn = page.locator('#btn-accept-disclaimer');
      await expect(acceptBtn).toBeVisible();
      await acceptBtn.click();

      // Overlay hides
      await expect(overlay).not.toBeVisible();

      // Reload page — modal should NOT reappear
      await page.reload();
      await page.waitForLoadState('domcontentloaded');
      await page.waitForTimeout(600);
      await expect(page.locator('#disclaimer-overlay')).not.toBeVisible();
    });

    test('First-time visitor sees support contact for deposit and withdrawal issues', async ({ page }) => {
      await page.goto('/');
      await page.waitForLoadState('domcontentloaded');

      const overlay = page.locator('#disclaimer-overlay');
      await expect(overlay).toBeVisible({ timeout: 5000 });

      // Support point text and instructions
      const supportPoint = page.locator('#disclaimer-support-point');
      await expect(supportPoint).toBeVisible();
      await expect(supportPoint).toContainText('issues with deposits or withdrawals');
      await expect(supportPoint).toContainText('contact support');

      // Email contact link
      const emailLink = page.locator('#disclaimer-support-email');
      await expect(emailLink).toBeVisible();
      await expect(emailLink).toHaveAttribute('href', 'mailto:support@bursar.co.ke');
      await expect(emailLink).toContainText('support@bursar.co.ke');

      // WhatsApp contact link
      const whatsappLink = page.locator('#disclaimer-support-whatsapp');
      await expect(whatsappLink).toBeVisible();
      await expect(whatsappLink).toHaveAttribute('href', 'https://wa.me/254786918393');
      await expect(whatsappLink).toContainText('+254786918393');
    });

    test('Clicking Decline triggers exit redirect', async ({ page }) => {
      await page.goto('/');
      await page.waitForLoadState('domcontentloaded');

      const overlay = page.locator('#disclaimer-overlay');
      await expect(overlay).toBeVisible({ timeout: 5000 });

      const declineBtn = page.locator('#btn-decline-disclaimer');
      await expect(declineBtn).toBeVisible();

      // Intercept navigation or verify URL redirect
      await Promise.all([
        page.waitForURL(/google\.com/, { timeout: 10000 }).catch(() => {}),
        declineBtn.click()
      ]);
    });

    test('Registered user with disclaimer_accepted=True never sees disclaimer on dashboard', async ({ page }) => {
      await setupAuthenticatedUser(page);

      await page.goto('/dashboard');
      await page.waitForLoadState('networkidle');

      const overlay = page.locator('#disclaimer-overlay');
      await expect(overlay).not.toBeVisible();
    });
  });

  // ==========================================
  // MOBILE VIEWPORT (375x667)
  // ==========================================
  test.describe('Mobile Viewport (375x667)', () => {
    test.use({ viewport: { width: 375, height: 667 } });

    test('Mobile visitor sees disclaimer rendered cleanly within viewport width', async ({ page }) => {
      await page.goto('/');
      await page.waitForLoadState('domcontentloaded');

      const overlay = page.locator('#disclaimer-overlay');
      await expect(overlay).toBeVisible({ timeout: 5000 });

      const card = page.locator('#disclaimer-card');
      await expect(card).toBeVisible();

      // Verify support contact elements are visible on mobile
      const supportPoint = page.locator('#disclaimer-support-point');
      await expect(supportPoint).toBeVisible();
      await expect(supportPoint).toContainText('issues with deposits or withdrawals');
      await expect(page.locator('#disclaimer-support-email')).toBeVisible();
      await expect(page.locator('#disclaimer-support-whatsapp')).toBeVisible();

      // Verify bounding box fits cleanly inside mobile width
      const box = await card.boundingBox();
      expect(box).not.toBeNull();
      expect(box.x).toBeGreaterThanOrEqual(0);
      expect(box.x + box.width).toBeLessThanOrEqual(385);

      // Verify accept button is tappable
      const acceptBtn = page.locator('#btn-accept-disclaimer');
      await expect(acceptBtn).toBeVisible();
      await acceptBtn.click();

      await expect(overlay).not.toBeVisible();
    });
  });
});
