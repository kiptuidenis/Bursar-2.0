/**
 * Setup authenticated user & admin sessions for Playwright E2E tests.
 * Uses fast test-only session endpoints to eliminate flaky/slow manual UI login.
 */
async function setupAuthenticatedUser(page, options = {}) {
  const randomDigits = Math.floor(10000000 + Math.random() * 90000000);
  const phone = options.phoneNumber || `2547${randomDigits}`;
  const email = options.email || `test_${phone}@bursar.co.ke`;
  const password = options.password || 'Str0ng!P@ssw0rd2026!';

  await page.request.post('/api/test/setup-session', {
    data: {
      phone_number: phone,
      email: email,
      password: password
    }
  });

  await page.goto('/dashboard');
  await page.waitForLoadState('networkidle');
  return { phone, email, password };
}

/**
 * Setup authenticated admin session for Playwright E2E tests.
 */
async function setupAuthenticatedAdmin(page, options = {}) {
  const role = options.role || 'superadmin';
  const email = options.email || `admin_${role}_${Date.now()}@bursar.co.ke`;
  const password = options.password || 'Admin!Pass2026Secure';

  await page.request.post('/api/test/setup-admin-session', {
    data: {
      email: email,
      password: password,
      role: role
    }
  });

  await page.goto('/admin');
  await page.waitForLoadState('networkidle');
  return { email, password, role };
}

module.exports = {
  setupAuthenticatedUser,
  setupAuthenticatedAdmin
};
