const { test, expect } = require('@playwright/test');

test.describe('Bursar 2.0 Mobile Layout E2E Tests (Phase 1)', () => {
  let pageErrors = [];

  test.beforeEach(({ page }) => {
    pageErrors = [];
    page.on('pageerror', (exception) => {
      pageErrors.push(exception.message);
    });
  });

  test.use({ viewport: { width: 375, height: 667 } }); // Target standard mobile size (iPhone SE)

  test('Should support responsive sidebar toggling and stacked profile settings grid', async ({ page }) => {
    // 1. Visit landing page, sign up to create a session and auto-login
    await page.goto('/');
    await page.click('#nav-signup-btn');
    await page.waitForTimeout(500); // Wait for modal slide/scale animations to settle
    
    const randomDigits = Math.floor(100000 + Math.random() * 900000);
    const testPhoneNumber = `254700${randomDigits}`;
    
    await page.fill('#auth-phone', testPhoneNumber);
    await page.fill('#auth-password', 'Str0ng!P@ssw0rd');
    const confirmInput = page.locator('#auth-confirm-password');
    if (await confirmInput.count() > 0) {
      await confirmInput.fill('Str0ng!P@ssw0rd');
    }
    await page.click('#auth-submit-btn', { force: true });
    
    await page.waitForURL('**/dashboard');
    await page.waitForLoadState('networkidle');

    // 2. Verify sidebar toggle button (hamburger menu) is visible on mobile
    const toggleBtn = page.locator('#sidebar-toggle-btn');
    await expect(toggleBtn).toBeVisible();

    // 3. Verify sidebar navigation drawer is off-screen initially
    const sidebar = page.locator('#sidebar-nav');
    // On mobile, sidebar uses transform: translateX(-100%)
    const sidebarBox = await sidebar.boundingBox();
    expect(sidebarBox.x).toBeLessThan(0); // Positioned offscreen left

    // 4. Click hamburger menu to open drawer
    await toggleBtn.click();
    await expect(sidebar).toHaveClass(/active/);
    await page.waitForTimeout(600); // Wait for transition animation to fully settle
    
    // Drawer should slide in to x=0
    const activeSidebarBox = await sidebar.boundingBox();
    expect(Math.abs(activeSidebarBox.x)).toBeLessThan(8);

    // 5. Dismiss sidebar drawer by clicking the backdrop overlay
    const backdrop = page.locator('#sidebar-backdrop');
    await expect(backdrop).toHaveClass(/active/);
    await backdrop.click();
    await page.waitForTimeout(400); // Wait for transition animation
    
    await expect(sidebar).not.toHaveClass(/active/);
    const closedSidebarBox = await sidebar.boundingBox();
    expect(closedSidebarBox.x).toBeLessThan(0);

    // 6. Navigate to Profile settings via mobile sidebar menu
    await toggleBtn.click();
    await page.click('#sidebar-nav [data-tab="profile"]');
    await expect(page.locator('#view-profile')).toHaveClass(/active/);

    // 7. Verify the profile page grid columns stack vertically
    const profileLeft = page.locator('.profile-left-col');
    const profileRight = page.locator('.profile-right-col');
    
    await expect(profileLeft).toBeVisible();
    await expect(profileRight).toBeVisible();

    const leftBox = await profileLeft.boundingBox();
    const rightBox = await profileRight.boundingBox();

    // If they stack vertically, the top coordinate of the right column should be below the bottom coordinate of the left column
    const leftBottom = leftBox.y + leftBox.height;
    expect(rightBox.y).toBeGreaterThanOrEqual(leftBottom);

    expect(pageErrors).toHaveLength(0);
  });

  test('Should verify mobile input types and keyboard configurations (Phase 2)', async ({ page }) => {
    // 1. Visit landing page
    await page.goto('/');
    
    // 2. Click signup to open form overlay
    await page.click('#nav-signup-btn');
    await page.waitForTimeout(500);

    // 3. Verify mobile configurations of registration form fields
    const phoneInput = page.locator('#auth-phone');
    const pwdInput = page.locator('#auth-password');

    await expect(phoneInput).toHaveAttribute('type', 'text');
    await expect(pwdInput).toHaveAttribute('type', 'password');

    // 4. Log in
    const randomDigits = Math.floor(100000 + Math.random() * 900000);
    const testPhoneNumber = `254700${randomDigits}`;
    await phoneInput.fill(testPhoneNumber);
    await pwdInput.fill('ComplexP@ssw0rd99!');
    if (await page.locator('#auth-confirm-password').isVisible()) {
      await page.fill('#auth-confirm-password', 'ComplexP@ssw0rd99!');
    }
    await page.click('#auth-submit-btn', { force: true });
    
    await page.waitForURL('**/dashboard');
    await page.waitForLoadState('networkidle');

    // 5. Verify email field on Profile Tab
    const toggleBtn = page.locator('#sidebar-toggle-btn');
    await toggleBtn.click();
    await page.click('#sidebar-nav [data-tab="profile"]');
    await expect(page.locator('#view-profile')).toHaveClass(/active/);

    const emailInput = page.locator('#profile-email');
    await expect(emailInput).toHaveAttribute('autocomplete', 'email');

    // 6. Verify settings drawer inputs
    await page.click('#toggle-settings-btn');
    await expect(page.locator('#settings-drawer')).toHaveClass(/active/);

    const settingsBudget = page.locator('#settings-budget');
    const settingsPhone = page.locator('#settings-phone');

    await expect(settingsBudget).toHaveAttribute('inputmode', 'decimal');
    await expect(settingsPhone).toHaveAttribute('type', 'tel');
    await expect(settingsPhone).toHaveAttribute('inputmode', 'tel');

    expect(pageErrors).toHaveLength(0);
  });

  test('Should verify mobile table-to-card layout rendering (Phase 3)', async ({ page }) => {
    // 1. Visit page and log in
    await page.goto('/');
    await page.click('#nav-signup-btn');
    await page.waitForTimeout(500);

    const randomDigits = Math.floor(100000 + Math.random() * 900000);
    const testPhoneNumber = `254700${randomDigits}`;
    await page.fill('#auth-phone', testPhoneNumber);
    await page.fill('#auth-password', 'Str0ng!P@ssw0rd');
    const confirmInput = page.locator('#auth-confirm-password');
    if (await confirmInput.count() > 0) {
      await confirmInput.fill('Str0ng!P@ssw0rd');
    }
    await page.click('#auth-submit-btn', { force: true });
    
    await page.waitForURL('**/dashboard');
    await page.waitForLoadState('networkidle');

    // 2. Add a session by navigating to profile settings
    const toggleBtn = page.locator('#sidebar-toggle-btn');
    await toggleBtn.click();
    await page.click('#sidebar-nav [data-tab="profile"]');
    await expect(page.locator('#view-profile')).toHaveClass(/active/);

    // 3. Verify Active Sessions table has stacked display (flex/block) on mobile viewports
    const firstCell = page.locator('#active-sessions-body td').first();
    await expect(firstCell).toBeVisible();

    const displayStyle = await firstCell.evaluate(el => window.getComputedStyle(el).display);
    expect(displayStyle).toBe('flex'); // Stacked flex block layout on mobile

    const dataLabel = await firstCell.getAttribute('data-label');
    expect(dataLabel).toBe('Device');

    // 4. Verify transaction history table cells also use flex block layout on mobile
    await toggleBtn.click();
    await page.click('#sidebar-nav [data-tab="transactions"]');
    await expect(page.locator('#view-transactions')).toHaveClass(/active/);

    const transactionCell = page.locator('#payout-history-body td').first();
    await expect(transactionCell).toBeVisible();

    const txDisplay = await transactionCell.evaluate(el => window.getComputedStyle(el).display);
    expect(txDisplay).toBe('flex');

    expect(pageErrors).toHaveLength(0);
  });

  test('Should verify mobile quick deposit presets autofill (Phase 4)', async ({ page }) => {
    // 1. Visit page and log in
    await page.goto('/');
    await page.click('#nav-signup-btn');
    await page.waitForTimeout(500);

    const randomDigits = Math.floor(100000 + Math.random() * 900000);
    const testPhoneNumber = `254700${randomDigits}`;
    await page.fill('#auth-phone', testPhoneNumber);
    await page.fill('#auth-password', 'Str0ng!P@ssw0rd');
    const confirmInput = page.locator('#auth-confirm-password');
    if (await confirmInput.count() > 0) {
      await confirmInput.fill('Str0ng!P@ssw0rd');
    }
    await page.click('#auth-submit-btn', { force: true });
    
    await page.waitForURL('**/dashboard');
    await page.waitForLoadState('networkidle');

    // 2. Open Deposit Modal
    await page.click('#debit-card-container');
    await page.waitForTimeout(600); // Wait for 3D flip transition to finish
    await page.click('#open-deposit-btn');
    await expect(page.locator('#deposit-modal')).toHaveClass(/active/);


    // 3. Verify presets are visible
    const preset1k = page.locator('.quick-amt-btn[data-amount="1000"]');
    const preset2k = page.locator('.quick-amt-btn[data-amount="2000"]');
    const depositInput = page.locator('#deposit-amount');

    await expect(preset1k).toBeVisible();
    await expect(preset2k).toBeVisible();
    await expect(depositInput).toHaveValue('');

    // 4. Click +1k preset and check auto-fill
    await preset1k.click();
    await expect(depositInput).toHaveValue('1000');

    // 5. Click +2k preset and check auto-fill updates to 2000
    await preset2k.click();
    await expect(depositInput).toHaveValue('2000');

    expect(pageErrors).toHaveLength(0);
  });
});
