const { test, expect } = require('@playwright/test');
const { setupAuthenticatedUser, dismissDisclaimerIfVisible } = require('./helpers');

test.describe('WhatsApp Alternate Support Contact E2E Tests (PC & Mobile)', () => {
  const WHATSAPP_NUMBER = '+254786918393';
  const WHATSAPP_URL = 'https://wa.me/254786918393';
  const SUPPORT_EMAIL = 'support@bursar.co.ke';

  // ==========================================
  // DESKTOP / PC TESTS (1280x800)
  // ==========================================
  test.describe('Desktop / PC Viewport (1280x800)', () => {
    test.use({ viewport: { width: 1280, height: 800 } });

    test('Landing page footer renders WhatsApp support contact on PC', async ({ page }) => {
      await page.goto('/');
      await page.waitForLoadState('domcontentloaded');
      await dismissDisclaimerIfVisible(page);

      const footer = page.locator('#landing-footer');
      await expect(footer).toBeVisible();
      await footer.scrollIntoViewIfNeeded();

      // Check WhatsApp link
      const waLink = footer.locator(`a[href="${WHATSAPP_URL}"]`);
      await expect(waLink).toBeVisible();
      await expect(waLink).toContainText(WHATSAPP_NUMBER);
      await expect(waLink).toHaveAttribute('target', '_blank');
      await expect(waLink).toHaveAttribute('rel', /noopener/);

      // Verify WhatsApp icon is rendered
      const waIcon = waLink.locator('svg, i');
      await expect(waIcon).toBeVisible();

      // Check Email support link
      const emailLink = footer.locator(`a[href="mailto:${SUPPORT_EMAIL}"]`);
      await expect(emailLink).toBeVisible();
      await expect(emailLink).toContainText(SUPPORT_EMAIL);
    });

    test('Dashboard footer renders WhatsApp support contact on PC', async ({ page }) => {
      await setupAuthenticatedUser(page);

      const footer = page.locator('.app-footer');
      await expect(footer).toBeVisible();

      const waLink = page.locator('#footer-whatsapp-link');
      await expect(waLink).toBeVisible();
      await expect(waLink).toHaveAttribute('href', WHATSAPP_URL);
      await expect(waLink).toContainText(WHATSAPP_NUMBER);
      await expect(waLink).toHaveAttribute('target', '_blank');

      // Verify WhatsApp icon is rendered
      const waIcon = waLink.locator('svg, i');
      await expect(waIcon).toBeVisible();

      // Check Email link
      const emailLink = page.locator('#footer-support-link');
      await expect(emailLink).toBeVisible();
      await expect(emailLink).toHaveAttribute('href', `mailto:${SUPPORT_EMAIL}`);
      await expect(emailLink).toContainText(SUPPORT_EMAIL);
    });
  });

  // ==========================================
  // MOBILE TESTS (375x667)
  // ==========================================
  test.describe('Mobile Viewport (375x667)', () => {
    test.use({ viewport: { width: 375, height: 667 } });

    test('Landing page footer renders WhatsApp support contact cleanly on Mobile without overflow', async ({ page }) => {
      await page.goto('/');
      await page.waitForLoadState('domcontentloaded');
      await dismissDisclaimerIfVisible(page);

      const footer = page.locator('#landing-footer');
      await footer.scrollIntoViewIfNeeded();
      await expect(footer).toBeVisible();

      const waLink = footer.locator(`a[href="${WHATSAPP_URL}"]`);
      await expect(waLink).toBeVisible();
      await expect(waLink).toContainText(WHATSAPP_NUMBER);

      // Verify bounding box stays within mobile screen width
      const box = await waLink.boundingBox();
      expect(box).not.toBeNull();
      expect(box.x).toBeGreaterThanOrEqual(0);
      expect(box.x + box.width).toBeLessThanOrEqual(385); // Fits cleanly on screen
    });

    test('Dashboard footer renders WhatsApp support contact cleanly on Mobile', async ({ page }) => {
      await setupAuthenticatedUser(page);

      const footer = page.locator('.app-footer');
      await expect(footer).toBeVisible();

      const waLink = page.locator('#footer-whatsapp-link');
      await expect(waLink).toBeVisible();
      await expect(waLink).toContainText(WHATSAPP_NUMBER);
      await expect(waLink).toHaveAttribute('href', WHATSAPP_URL);

      // Verify bounding box stays within mobile screen width
      const box = await waLink.boundingBox();
      expect(box).not.toBeNull();
      expect(box.x).toBeGreaterThanOrEqual(0);
      expect(box.x + box.width).toBeLessThanOrEqual(385);
    });
  });
});
