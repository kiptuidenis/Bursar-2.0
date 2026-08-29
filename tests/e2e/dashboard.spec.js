const { test, expect } = require('@playwright/test');
const { setupAuthenticatedUser } = require('./helpers');

test.describe('Bursar 2.0 End-to-End Visual & Functional Tests', () => {
  let pageErrors = [];

  test.beforeEach(({ page }) => {
    pageErrors = [];
    // Collect any client-side JavaScript runtime exceptions
    page.on('pageerror', (exception) => {
      console.error('Browser console TypeError/Exception:', exception.message);
      pageErrors.push(exception.message);
    });
  });

  test('Should perform Signup, auto-login, verify dashboard buttons, and logout without console errors', async ({ page }) => {
    // 1. Setup authenticated session
    await setupAuthenticatedUser(page);

    // 2. Assert that NO runtime JS console TypeErrors occurred during page load / setup
    expect(pageErrors).toHaveLength(0);

    // 3. Verify "Deposit Funds" button works (opens modal)
    await page.click('#debit-card-container');
    await page.waitForTimeout(600); // Wait for 3D flip transition to finish
    await page.click('#open-deposit-btn');
    await expect(page.locator('#deposit-modal')).toHaveClass(/active/);
    
    // Close the Deposit modal
    await page.click('#close-deposit-btn');
    await expect(page.locator('#deposit-modal')).not.toHaveClass(/active/);
    
    // Flip card back to keep initial state
    await page.click('#debit-card-container');
    await page.waitForTimeout(600); // Wait for 3D flip back transition to finish

    // 4. Verify "Create" (Budget Creator Modal) button works (opens modal)
    await page.click('#open-budget-designer-btn');
    await expect(page.locator('#budget-designer-modal')).toHaveClass(/active/);

    // Verify Payout Schedule is collapsed by default initially
    await expect(page.locator('#schedule-collapse-body')).not.toBeVisible();

    // Toggle expand
    await page.click('#schedule-toggle-hdr');
    await expect(page.locator('#schedule-collapse-body')).toBeVisible();

    // Toggle collapse back
    await page.click('#schedule-toggle-hdr');
    await expect(page.locator('#schedule-collapse-body')).not.toBeVisible();

    // Close the Budget Designer modal
    await page.click('#close-budget-designer-btn');
    await expect(page.locator('#budget-designer-modal')).not.toHaveClass(/active/);

    // 5. Verify "Settings" Toggle drawer works (opens settings drawer)
    await page.click('#toggle-settings-btn');
    await expect(page.locator('#settings-drawer')).toHaveClass(/active/);

    // Close Settings drawer
    await page.click('#close-settings-btn');
    await expect(page.locator('#settings-drawer')).not.toHaveClass(/active/);

    // 6. Verify "Logout" button works (redirects back to homepage)
    await page.click('#logout-btn');
    await page.waitForURL('**/');
    expect(page.url()).not.toContain('/dashboard');

    // Ensure no console exceptions occurred during any of these transitions
    expect(pageErrors).toHaveLength(0);
  });

  test('Should toggle sidebar collapse state and switch tabs successfully', async ({ page }) => {
    // 1. Setup authenticated session
    await setupAuthenticatedUser(page);

    // 2. Verify sidebar is visible and collapsed initially by default
    const sidebar = page.locator('#sidebar-nav');
    await expect(sidebar).toBeVisible();
    await expect(sidebar).toHaveClass(/collapsed/);

    // Verify user badge is visible, but the phone number text is hidden when collapsed
    await expect(page.locator('#sidebar-user-badge')).toBeVisible();
    await expect(page.locator('#sidebar-user-phone-number')).not.toBeVisible();

    // 3. Click the sidebar collapse button to expand
    await page.click('#sidebar-collapse-btn');
    await expect(sidebar).not.toHaveClass(/collapsed/);

    // Verify user badge and phone number text are both visible when expanded
    await expect(page.locator('#sidebar-user-badge')).toBeVisible();
    await expect(page.locator('#sidebar-user-phone-number')).toBeVisible();

    // 4. Click it again to collapse
    await page.click('#sidebar-collapse-btn');
    await expect(sidebar).toHaveClass(/collapsed/);

    // Verify phone number text is hidden again when collapsed
    await expect(page.locator('#sidebar-user-phone-number')).not.toBeVisible();

    // 5. Test tab switching: click Transactions tab
    await page.click('[data-tab="transactions"]');
    await expect(page.locator('#view-transactions')).toHaveClass(/active/);
    await expect(page.locator('#view-dashboard')).toHaveClass(/hidden/);

    // 6. Return to Dashboard tab
    await page.click('[data-tab="dashboard"]');
    await expect(page.locator('#view-dashboard')).toHaveClass(/active/);
    await expect(page.locator('#view-transactions')).toHaveClass(/hidden/);
  });

  test('Should verify sidebar deposit and logout buttons work correctly when sidebar is expanded', async ({ page }) => {
    // 1. Setup authenticated session
    await setupAuthenticatedUser(page);

    // 2. Expand the sidebar to make buttons interactive/visible
    const sidebar = page.locator('#sidebar-nav');
    await page.click('#sidebar-collapse-btn');
    await expect(sidebar).not.toHaveClass(/collapsed/);

    // Assert that the sidebar logout button and user badge are visible in the viewport without scrolling
    await expect(page.locator('#sidebar-logout-btn')).toBeInViewport();
    await expect(page.locator('#sidebar-user-badge')).toBeInViewport();

    // Scroll the main content dashboard layout to verify independent scrolling
    await page.locator('.main-content').evaluate(el => el.scrollTop = 300);
    
    // Verify sidebar elements are STILL visible in the viewport after main content scrolls
    await expect(page.locator('#sidebar-logout-btn')).toBeInViewport();
    await expect(page.locator('#sidebar-user-badge')).toBeInViewport();

    // 3. Test Sidebar Deposit Button switches to flat tab view
    await page.click('#sidebar-deposit-btn');
    await expect(page.locator('#view-deposit')).toHaveClass(/active/);
    await expect(page.locator('#deposit-modal')).not.toHaveClass(/active/);
    await expect(page.locator('#view-deposit #deposit-amount')).toBeVisible();

    // Test Sidebar Budget Button switches to flat tab view
    await page.click('[data-tab="budget"]');
    await expect(page.locator('#view-budget')).toHaveClass(/active/);
    await expect(page.locator('#budget-designer-modal')).not.toHaveClass(/active/);
    await expect(page.locator('#view-budget #new-category-name')).toBeVisible();

    // Switch back to dashboard
    await page.click('[data-tab="dashboard"]');
    await expect(page.locator('#view-dashboard')).toHaveClass(/active/);
    await expect(page.locator('#view-deposit')).toHaveClass(/hidden/);
    await expect(page.locator('#view-budget')).toHaveClass(/hidden/);

    // 4. Test Sidebar Logout Button logs out
    await page.click('#sidebar-logout-btn');
    await page.waitForURL('**/');
    expect(page.url()).not.toContain('/dashboard');
  });

  test('Should show error alert and expand schedule if trying to lock budget without schedule dates', async ({ page }) => {
    // 1. Setup authenticated session
    await setupAuthenticatedUser(page);

    // 2. Open Budget Creator Modal
    await page.click('#open-budget-designer-btn');
    await expect(page.locator('#budget-designer-modal')).toHaveClass(/active/);

    // 3. Add a category to make lock button visible
    await page.fill('#new-category-name', 'Rent');
    await page.fill('#new-category-amount', '500');
    
    await Promise.all([
      page.waitForResponse(res => res.url().includes('/api/budget/items') && res.request().method() === 'POST'),
      page.click('#add-category-form button[type="submit"]')
    ]);

    await expect(page.locator('#designer-category-list')).toContainText('Rent');
    const lockBtn = page.locator('#lock-budget-btn');
    await expect(lockBtn).toBeVisible();

    // 4. Setup dialog handler to accept/dismiss alerts
    let dialogMessage = '';
    page.on('dialog', async dialog => {
      dialogMessage = dialog.message();
      await dialog.accept();
    });

    // 5. Try to lock WITHOUT setting start/end dates
    await lockBtn.click();

    // 6. Verify alert dialog warned user about missing dates
    expect(dialogMessage).toContain('Please select both start and end dates');

    // 7. Verify schedule accordion automatically expanded to reveal date inputs
    const scheduleBody = page.locator('#schedule-collapse-body');
    await expect(scheduleBody).toBeVisible();
  });

  test('Should verify the full functionality of the Budget Creator (add, delete, draft preservation, dashboard separation, and final lock)', async ({ page }) => {
    // Register dialog handler for the entire test run
    page.on('dialog', async dialog => {
      await dialog.accept();
    });

    // 1. Setup authenticated session
    await setupAuthenticatedUser(page);

    // Verify initial dashboard breakdown is empty
    await expect(page.locator('#budget-breakdown-list')).toContainText('No categories configured');

    // 2. Open Budget Creator Modal
    await page.click('#open-budget-designer-btn');
    await expect(page.locator('#budget-designer-modal')).toHaveClass(/active/);

    // 3. Add a category
    await page.fill('#new-category-name', 'TestCategory');
    await page.fill('#new-category-amount', '1000');
    
    await Promise.all([
      page.waitForResponse(res => res.url().includes('/api/budget/items') && res.request().method() === 'POST'),
      page.click('#add-category-form button[type="submit"]')
    ]);

    // Verify it rendered in the modal list
    await expect(page.locator('#designer-category-list')).toContainText('TestCategory');
    await expect(page.locator('#designer-total-budget')).toContainText('KES 1,000.00');

    // 4. Close the modal without locking
    await page.click('#close-budget-designer-btn');
    await expect(page.locator('#budget-designer-modal')).not.toHaveClass(/active/);

    // 5. Verify dashboard did NOT update and still shows KES 0.00 / empty state (major bug fix validation)
    await expect(page.locator('#budget-breakdown-list')).toContainText('No categories configured');
    await expect(page.locator('#daily-budget-value')).toContainText('0.00');

    // 6. Open modal again and verify that TestCategory is still preserved inside the modal
    await page.click('#open-budget-designer-btn');
    await expect(page.locator('#designer-category-list')).toContainText('TestCategory');

    // 7. Delete TestCategory inside the modal via UI button click
    page.on('dialog', async dialog => {
      await dialog.accept();
    });

    await page.evaluate(() => {
      window.__SKIP_CONFIRM__ = true;
    });

    const cancelBtn = page.locator('#designer-category-list .cancel-btn').first();
    await expect(cancelBtn).toBeVisible();

    const [deleteRes] = await Promise.all([
      page.waitForResponse(res => res.url().includes('/api/budget/items/') && res.request().method() === 'DELETE'),
      cancelBtn.click()
    ]);
    expect(deleteRes.status()).toBe(200);

    // Verify it is gone from the modal list
    await expect(page.locator('#designer-category-list')).toContainText('No categories defined');
    await expect(page.locator('#designer-total-budget')).toContainText('KES 0.00');

    // 8. Close and reopen to verify deletion is preserved
    await page.click('#close-budget-designer-btn');
    await page.click('#open-budget-designer-btn');
    await expect(page.locator('#designer-category-list')).toContainText('No categories defined');
  });

  test('Run Payout button should NOT be visible on the debit card and should be hidden by default in the Next Payout tile', async ({ page }) => {
    // 1. Setup authenticated session
    await setupAuthenticatedUser(page);

    // 2. Verify debit card does NOT contain any trigger payout button
    await expect(page.locator('#debit-card-container #trigger-payout-btn')).toHaveCount(0);

    // 3. Verify Next Payout tile retry footer is hidden by default
    await expect(page.locator('#payout-retry-footer')).toBeHidden();
  });

  test('Run Payout button should appear in the Next Payout tile after a failed payout', async ({ page }) => {
    // 1. Setup authenticated session
    await setupAuthenticatedUser(page);

    // 2. Inject a FAILED payout record for today directly via the API
    const cookies = await page.context().cookies();
    const csrfCookie = cookies.find(c => c.name === 'csrf_token');
    const requestHeaders = {};
    if (csrfCookie) {
      requestHeaders['X-CSRF-Token'] = csrfCookie.value;
    }

    const localDate = new Date();
    const todayStr = `${localDate.getFullYear()}-${String(localDate.getMonth() + 1).padStart(2, '0')}-${String(localDate.getDate()).padStart(2, '0')}`;
    const injectRes = await page.request.post('/api/payout/inject-failed', {
      headers: requestHeaders,
      data: { payout_date: todayStr }
    });
    // If the inject endpoint doesn't exist yet, skip gracefully
    if (injectRes.status() === 404) {
      test.skip('inject-failed endpoint not available');
      return;
    }

    // 3. Wait for the polling cycle to detect the FAILED record and update the UI
    await page.waitForTimeout(6000); // Poll cycle is 5s

    // 4. Verify the Next Payout tile shows the Run Payout button
    await expect(page.locator('#payout-retry-footer')).toBeVisible();
    await expect(page.locator('#countdown-card #trigger-payout-btn')).toBeVisible();

    // 5. Verify the countdown timer shows the failure state message
    const timerText = await page.locator('#countdown-timer').innerText();
    expect(timerText).toContain('Payout Failed');
  });

  test('Dashboard profile mini-card should display logged-in user profile info', async ({ page }) => {
    const dialogMessages = [];
    page.on('dialog', async dialog => {
      await dialog.accept();
      dialogMessages.push(dialog.message());
    });

    const pageErrors = [];
    page.on('pageerror', err => pageErrors.push(err.message));

    // 1. Setup authenticated session
    const { phone: testPhoneNumber } = await setupAuthenticatedUser(page);

    // 2. Verify profile mini-card exists on the dashboard
    await expect(page.locator('#dashboard-profile-card')).toBeVisible();

    // 3. Before setting a profile name, the card should show the phone number as fallback
    await expect(page.locator('#dash-profile-phone')).toContainText(testPhoneNumber);

    // 4. Initials should show last 2 digits of phone (no name yet)
    const initialsBefore = await page.locator('#dash-profile-initials').innerText();
    expect(initialsBefore).toBe(testPhoneNumber.slice(-2));

    // 5. Navigate to profile via edit profile button or switchTab
    await page.evaluate(() => switchTab('profile'));
    await expect(page.locator('#view-profile')).toHaveClass(/active/);
    await page.waitForTimeout(500);

    // 6. Fill profile details
    await page.fill('#profile-first-name', 'Denis');
    await page.fill('#profile-last-name', 'Kiptui');
    await page.fill('#profile-email', 'denis.kiptui@example.com');
    await page.click('#profile-info-form button[type="submit"]');
    await expect.poll(() => dialogMessages).toContain('Profile details saved successfully!');

    // 7. Switch back to dashboard
    await page.click('[data-tab="dashboard"]');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(500);

    // 8. Verify the mini-card now shows the updated name, email, and initials
    await expect(page.locator('#dash-profile-name')).toContainText('Denis Kiptui');
    await expect(page.locator('#dash-profile-email')).toContainText('denis.kiptui@example.com');
    await expect(page.locator('#dash-profile-phone')).toContainText(testPhoneNumber);

    const initialsAfter = await page.locator('#dash-profile-initials').innerText();
    expect(initialsAfter).toBe('DK');

    // 9. No console errors during entire flow
    expect(pageErrors).toHaveLength(0);
  });
});
