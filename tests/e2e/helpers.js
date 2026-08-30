/**
 * Setup authenticated user session for Playwright E2E tests.
 * Uses fast test-only session endpoint to eliminate flaky/slow manual UI login.
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
      password: password,
      seed_notifications: options.seedNotifications || false
    }
  });

  await page.goto('/dashboard');
  await page.waitForLoadState('networkidle');
  return { phone, email, password };
}

module.exports = {
  setupAuthenticatedUser
};
