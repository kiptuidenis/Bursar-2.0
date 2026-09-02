const { test, expect } = require('@playwright/test');
const { setupEmailOnlyUser, setupAuthenticatedUser, getFutureDates } = require('./helpers');

test.describe('Budget Creation 3-Step Sliding Wizard', () => {

  test('Email user completes full 3-step wizard with sliding transitions and locks budget', async ({ page }) => {
    test.setTimeout(90000);
    page.on('dialog', async dialog => await dialog.accept());

    await setupEmailOnlyUser(page);

    // Wait for dashboard to be fully authenticated and loaded
    await expect(page.locator('#debit-card-container')).toBeVisible({ timeout: 10000 });

    // 1. Fund balance via deposit — flip card then open modal
    await page.click('#debit-card-container');
    await page.waitForTimeout(700);
    await page.click('#open-deposit-btn');
    await expect(page.locator('#deposit-modal')).toHaveClass(/active/, { timeout: 8000 });

    await page.locator('#deposit-phone').fill('0799112233');
    await page.locator('#deposit-amount').fill('6000');
    await page.locator('#deposit-form button[type="submit"]').click();

    const pollingOverlay = page.locator('#deposit-polling-overlay');
    await expect(pollingOverlay).toHaveClass(/active/, { timeout: 10000 });
    await expect(pollingOverlay).not.toHaveClass(/active/, { timeout: 30000 });
    await expect(page.locator('#wallet-balance')).toHaveText('6,000.00', { timeout: 10000 });

    // 2. Open Budget Designer Modal
    await page.locator('#open-budget-designer-btn').click();
    const budgetModal = page.locator('#budget-designer-modal');
    await expect(budgetModal).toHaveClass(/active/, { timeout: 8000 });

    // Verify initial state is Step 1 (Allocations)
    await expect(page.locator('#budget-wizard-step-title')).toContainText('Step 1 of 3');

    // Add a category item
    await page.locator('#new-category-name').fill('Meals & Snacks');
    await page.locator('#new-category-amount').fill('600');
    await page.locator('#add-category-form button[type="submit"]').click();
    await page.waitForTimeout(500);

    // 3. Advance to Step 2 (Payout Schedule)
    await page.locator('#budget-wizard-next-1').click();
    await page.waitForTimeout(400);
    await expect(page.locator('#budget-wizard-step-title')).toContainText('Step 2 of 3');

    // Fill start and end dates
    const dates1 = getFutureDates();
    await page.locator('#lock-start-date').fill(dates1.tomorrow);
    await page.locator('#lock-end-date').fill(dates1.nextWeek);

    // 4. Advance to Step 3 (Payout Destination)
    await page.locator('#budget-wizard-next-2').click();
    await page.waitForTimeout(400);
    await expect(page.locator('#budget-wizard-step-title')).toContainText('Step 3 of 3');

    // Enter target payout phone number
    await page.locator('#budget-lock-payout-phone').fill('0712345678');

    // 5. Lock and Finalize Budget
    await page.locator('#lock-budget-btn').click();

    // Modal closes
    await expect(budgetModal).not.toHaveClass(/active/, { timeout: 10000 });

    // Payout phone reflected on dashboard profile card
    await expect(page.locator('#dash-profile-phone')).toHaveText('254712345678', { timeout: 15000 });
  });

  test('Saved phone user reviews and confirms pre-filled number in Step 3', async ({ page }) => {
    test.setTimeout(90000);
    page.on('dialog', async dialog => await dialog.accept());

    const userPhone = '254799554433';
    await setupAuthenticatedUser(page, { phoneNumber: userPhone, balance: 5000 });

    // Wait for dashboard to be fully loaded
    await expect(page.locator('#open-budget-designer-btn')).toBeVisible({ timeout: 10000 });

    // Open Budget Designer Modal
    await page.locator('#open-budget-designer-btn').click();
    const budgetModal = page.locator('#budget-designer-modal');
    await expect(budgetModal).toHaveClass(/active/, { timeout: 8000 });

    // Step 1: Add a category
    await page.locator('#new-category-name').fill('Transport');
    await page.locator('#new-category-amount').fill('400');
    await page.locator('#add-category-form button[type="submit"]').click();
    await page.waitForTimeout(500);

    // Advance to Step 2
    await page.locator('#budget-wizard-next-1').click();
    await page.waitForTimeout(400);

    const dates2 = getFutureDates();
    await page.locator('#lock-start-date').fill(dates2.tomorrow);
    await page.locator('#lock-end-date').fill(dates2.nextWeek);

    // Advance to Step 3
    await page.locator('#budget-wizard-next-2').click();
    await page.waitForTimeout(400);
    await expect(page.locator('#budget-wizard-step-title')).toContainText('Step 3 of 3');

    // Step 3 shows pre-filled number
    const payoutInput = page.locator('#budget-lock-payout-phone');
    await expect(payoutInput).toHaveValue(userPhone, { timeout: 5000 });

    // Click Lock & Finalize Budget
    await page.locator('#lock-budget-btn').click();

    await expect(budgetModal).not.toHaveClass(/active/, { timeout: 10000 });
    await expect(page.locator('#dash-profile-phone')).toHaveText(userPhone, { timeout: 15000 });
  });

  test('Saved phone user modifying payout line in Step 3 triggers Step-Up Modal and verifies password and OTP', async ({ page }) => {
    test.setTimeout(90000);
    page.on('dialog', async dialog => await dialog.accept());

    const initialPhone = '254711998877';
    const newPayoutPhone = '254722334455';
    const userPassword = 'Str0ng!P@ssw0rd2026!';
    const user = await setupAuthenticatedUser(page, { phoneNumber: initialPhone, password: userPassword, balance: 5000 });

    await expect(page.locator('#open-budget-designer-btn')).toBeVisible({ timeout: 10000 });
    await page.locator('#open-budget-designer-btn').click();
    const budgetModal = page.locator('#budget-designer-modal');
    await expect(budgetModal).toHaveClass(/active/, { timeout: 8000 });

    // Step 1: Add a category
    await page.locator('#new-category-name').fill('Food');
    await page.locator('#new-category-amount').fill('300');
    await page.locator('#add-category-form button[type="submit"]').click();
    await page.waitForTimeout(500);

    // Advance to Step 2
    await page.locator('#budget-wizard-next-1').click();
    await page.waitForTimeout(400);

    const dates3 = getFutureDates();
    await page.locator('#lock-start-date').fill(dates3.tomorrow);
    await page.locator('#lock-end-date').fill(dates3.nextWeek);

    // Advance to Step 3
    await page.locator('#budget-wizard-next-2').click();
    await page.waitForTimeout(400);
    await expect(page.locator('#budget-wizard-step-title')).toContainText('Step 3 of 3');

    // Change payout phone to a new number
    const payoutInput = page.locator('#budget-lock-payout-phone');
    await payoutInput.fill(newPayoutPhone);

    // Click Lock Budget -> Step-Up Modal triggers
    await page.locator('#lock-budget-btn').click();
    const stepupModal = page.locator('#stepup-payout-modal');
    await expect(stepupModal).toHaveClass(/active/, { timeout: 8000 });

    // Try submitting with wrong password
    await page.locator('#stepup-payout-password').fill('WrongPassword!');
    await page.locator('#stepup-payout-otp').fill('123456');
    await page.locator('#stepup-payout-form button[type="submit"]').click();

    // Verify error message displayed
    const errorEl = page.locator('#stepup-payout-error');
    await expect(errorEl).toBeVisible({ timeout: 5000 });
    await expect(errorEl).toContainText('Invalid');

    // Fetch the real mock OTP code generated by the backend
    const otpRes = await page.evaluate(async (email) => {
      const res = await fetch(`/api/test/latest-otp?email=${encodeURIComponent(email)}&purpose=payout_stepup`);
      return await res.json();
    }, user.email);
    const validOtp = otpRes.otp_code;

    // Fill correct password and valid OTP
    await page.locator('#stepup-payout-password').fill(userPassword);
    await page.locator('#stepup-payout-otp').fill(validOtp);
    await page.locator('#stepup-payout-form button[type="submit"]').click();

    // Verify both modals close and payout phone updates on dashboard
    await expect(stepupModal).not.toHaveClass(/active/, { timeout: 10000 });
    await expect(budgetModal).not.toHaveClass(/active/, { timeout: 10000 });
    await expect(page.locator('#dash-profile-phone')).toHaveText(newPayoutPhone, { timeout: 15000 });
  });

  test('Wizard navigation supports sliding backwards and validates missing data', async ({ page }) => {
    test.setTimeout(90000);
    let lastDialogMessage = '';
    page.on('dialog', async dialog => {
      lastDialogMessage = dialog.message();
      await dialog.accept();
    });

    await setupEmailOnlyUser(page);

    // Wait for dashboard to be fully loaded
    await expect(page.locator('#open-budget-designer-btn')).toBeVisible({ timeout: 10000 });

    await page.locator('#open-budget-designer-btn').click();
    await expect(page.locator('#budget-designer-modal')).toHaveClass(/active/, { timeout: 8000 });

    // Attempting Next with 0 categories should fire alert with 'category'
    await page.locator('#budget-wizard-next-1').click();
    await page.waitForTimeout(300);
    expect(lastDialogMessage).toContain('category');

    // Add category
    await page.locator('#new-category-name').fill('Utilities');
    await page.locator('#new-category-amount').fill('300');
    await page.locator('#add-category-form button[type="submit"]').click();
    await page.waitForTimeout(500);

    // Move to Step 2
    await page.locator('#budget-wizard-next-1').click();
    await page.waitForTimeout(400);
    await expect(page.locator('#budget-wizard-step-title')).toContainText('Step 2 of 3');

    // Click Back to Step 1
    await page.locator('#budget-wizard-back-2').click();
    await page.waitForTimeout(400);
    await expect(page.locator('#budget-wizard-step-title')).toContainText('Step 1 of 3');

    // Forward to Step 2 again
    await page.locator('#budget-wizard-next-1').click();
    await page.waitForTimeout(400);

    // Attempting Next on Step 2 without dates should fire alert with 'dates'
    await page.locator('#budget-wizard-next-2').click();
    await page.waitForTimeout(300);
    expect(lastDialogMessage).toContain('dates');
  });

  test('Wizard slide transitions align precisely without horizontal overflow or bleed', async ({ page }) => {
    test.setTimeout(60000);
    page.on('dialog', async dialog => await dialog.accept());

    await setupEmailOnlyUser(page);

    await expect(page.locator('#open-budget-designer-btn')).toBeVisible({ timeout: 10000 });
    await page.locator('#open-budget-designer-btn').click();
    const modal = page.locator('#budget-designer-modal');
    await expect(modal).toHaveClass(/active/, { timeout: 8000 });

    const container = page.locator('#budget-wizard-container');
    const tile1 = page.locator('#budget-wizard-tile-1');
    const tile2 = page.locator('#budget-wizard-tile-2');
    const tile3 = page.locator('#budget-wizard-tile-3');

    // Add a category to allow moving to step 2
    await page.locator('#new-category-name').fill('Food');
    await page.locator('#new-category-amount').fill('200');
    await page.locator('#add-category-form button[type="submit"]').click();
    await page.waitForTimeout(400);

    // --- STEP 1 CHECKS ---
    let cBox = await container.boundingBox();
    let t1Box = await tile1.boundingBox();
    let t2Box = await tile2.boundingBox();
    let t3Box = await tile3.boundingBox();

    // Tile 1 aligned with container
    expect(Math.abs(t1Box.x - cBox.x)).toBeLessThanOrEqual(5);
    expect(Math.abs(t1Box.width - cBox.width)).toBeLessThanOrEqual(5);
    // Tile 2 is to the right
    expect(t2Box.x).toBeGreaterThanOrEqual(cBox.x + cBox.width - 5);

    // --- MOVE TO STEP 2 ---
    await page.locator('#budget-wizard-next-1').click();
    await page.locator('#budget-wizard-track').evaluate(async (el) => {
      await Promise.all(el.getAnimations().map(a => a.finished));
    });
    await page.waitForTimeout(100);

    cBox = await container.boundingBox();
    t1Box = await tile1.boundingBox();
    t2Box = await tile2.boundingBox();
    t3Box = await tile3.boundingBox();

    // Tile 1 must be completely to the left (no bleed on left)
    expect(t1Box.x + t1Box.width).toBeLessThanOrEqual(cBox.x + 5);

    // Tile 2 must be precisely aligned with the container window
    expect(Math.abs(t2Box.x - cBox.x)).toBeLessThanOrEqual(5);
    expect(Math.abs(t2Box.width - cBox.width)).toBeLessThanOrEqual(5);

    // Tile 2 buttons must be within container bounds
    const backBtn2Box = await page.locator('#budget-wizard-back-2').boundingBox();
    const nextBtn2Box = await page.locator('#budget-wizard-next-2').boundingBox();
    expect(backBtn2Box.x).toBeGreaterThanOrEqual(cBox.x - 2);
    expect(nextBtn2Box.x + nextBtn2Box.width).toBeLessThanOrEqual(cBox.x + cBox.width + 5);

    // Tile 3 is to the right
    expect(t3Box.x).toBeGreaterThanOrEqual(cBox.x + cBox.width - 5);

    // Fill dates to allow moving to Step 3
    await page.locator('#lock-start-date').fill('2026-09-01');
    await page.locator('#lock-end-date').fill('2026-09-07');

    // --- MOVE TO STEP 3 ---
    await page.locator('#budget-wizard-next-2').click();
    await page.locator('#budget-wizard-track').evaluate(async (el) => {
      await Promise.all(el.getAnimations().map(a => a.finished));
    });
    await page.waitForTimeout(100);

    cBox = await container.boundingBox();
    t2Box = await tile2.boundingBox();
    t3Box = await tile3.boundingBox();

    // Tile 2 must be completely to the left
    expect(t2Box.x + t2Box.width).toBeLessThanOrEqual(cBox.x + 5);

    // Tile 3 must be precisely aligned with the container window
    expect(Math.abs(t3Box.x - cBox.x)).toBeLessThanOrEqual(5);
    expect(Math.abs(t3Box.width - cBox.width)).toBeLessThanOrEqual(5);

    // Tile 3 buttons must be within container bounds
    const backBtn3Box = await page.locator('#budget-wizard-back-3').boundingBox();
    const lockBtnBox = await page.locator('#lock-budget-btn').boundingBox();
    expect(backBtn3Box.x).toBeGreaterThanOrEqual(cBox.x - 2);
    expect(lockBtnBox.x + lockBtnBox.width).toBeLessThanOrEqual(cBox.x + cBox.width + 5);
  });

  test('Should not persist draft budget items to server if user cancels wizard before locking', async ({ page }) => {
    await setupAuthenticatedUser(page);

    // 1. Open Budget Designer Modal
    await page.locator('#open-budget-designer-btn').click();
    const budgetModal = page.locator('#budget-designer-modal');
    await expect(budgetModal).toHaveClass(/active/, { timeout: 8000 });

    // 2. Add draft categories
    await page.locator('#new-category-name').fill('Draft Groceries');
    await page.locator('#new-category-amount').fill('450');
    await page.locator('#add-category-form button[type="submit"]').click();

    // Verify row appears in modal table
    await expect(page.locator('#designer-category-list')).toContainText('Draft Groceries');
    await expect(page.locator('#designer-total-budget')).toContainText('450');

    // 3. Close modal without locking
    await page.locator('#close-budget-designer-btn').click();
    await expect(budgetModal).not.toHaveClass(/active/);

    // 4. Verify server items endpoint returned 0 items
    const serverItems = await page.evaluate(async () => {
      const res = await fetch('/api/budget/items');
      return await res.json();
    });
    expect(serverItems).toHaveLength(0);

    // 5. Verify main dashboard Daily Budget card shows no configured categories
    await expect(page.locator('#budget-breakdown-list')).toContainText('No categories configured');
  });

});
