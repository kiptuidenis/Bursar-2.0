const { test, expect } = require('@playwright/test');
const { setupAuthenticatedUser } = require('./helpers');

test.describe('Profile Mobile Responsive Layout E2E Tests', () => {

  test('Desktop view: New password and confirm password are side-by-side', async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 800 });
    await setupAuthenticatedUser(page);

    await page.click('[data-tab="profile"]');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(500);

    const pwdNew = page.locator('#pwd-new');
    const pwdConfirm = page.locator('#pwd-confirm');

    await expect(pwdNew).toBeVisible();
    await expect(pwdConfirm).toBeVisible();

    const boxNew = await pwdNew.boundingBox();
    const boxConfirm = await pwdConfirm.boundingBox();

    expect(boxNew).not.toBeNull();
    expect(boxConfirm).not.toBeNull();

    // On desktop, Y coordinates are aligned on the same horizontal line
    expect(Math.abs(boxNew.y - boxConfirm.y)).toBeLessThan(10);
    // Confirm password is to the right of new password
    expect(boxConfirm.x).toBeGreaterThan(boxNew.x);
  });

  test('Mobile view (<=768px): New password field is stacked vertically ABOVE confirm password', async ({ page }) => {
    // iPhone SE / standard mobile viewport
    await page.setViewportSize({ width: 375, height: 667 });
    await setupAuthenticatedUser(page);

    // Open sidebar on mobile if needed or navigate directly
    await page.evaluate(() => switchTab('profile'));
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(500);

    const pwdNew = page.locator('#pwd-new');
    const pwdConfirm = page.locator('#pwd-confirm');

    await expect(pwdNew).toBeVisible();
    await expect(pwdConfirm).toBeVisible();

    const boxNew = await pwdNew.boundingBox();
    const boxConfirm = await pwdConfirm.boundingBox();

    expect(boxNew).not.toBeNull();
    expect(boxConfirm).not.toBeNull();

    // On mobile, New Password must be stacked ABOVE Confirm Password
    expect(boxConfirm.y).toBeGreaterThan(boxNew.y + boxNew.height);
  });

  test('Mobile view (<=768px): First name field is stacked vertically ABOVE last name', async ({ page }) => {
    await page.setViewportSize({ width: 375, height: 667 });
    await setupAuthenticatedUser(page);

    await page.evaluate(() => switchTab('profile'));
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(500);

    const firstName = page.locator('#profile-first-name');
    const lastName = page.locator('#profile-last-name');

    await expect(firstName).toBeVisible();
    await expect(lastName).toBeVisible();

    const boxFirst = await firstName.boundingBox();
    const boxLast = await lastName.boundingBox();

    expect(boxFirst).not.toBeNull();
    expect(boxLast).not.toBeNull();

    // First name must be stacked ABOVE Last Name on mobile
    expect(boxLast.y).toBeGreaterThan(boxFirst.y + boxFirst.height);
  });
});
