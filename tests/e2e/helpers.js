/**
 * Setup authenticated user & admin sessions for Playwright E2E tests.
 * Uses fast test-only session endpoints to eliminate flaky/slow manual UI login.
 *
 * IMPORTANT: We use page.evaluate(fetch(...)) so the BROWSER itself receives
 * the Set-Cookie header directly — Playwright's page.request API has an
 * isolated cookie jar that does NOT reliably sync to the browser context.
 */

async function setupAuthenticatedUser(page, options = {}) {
  const randomDigits = Math.floor(10000000 + Math.random() * 90000000);
  const phone = options.phoneNumber || `2547${randomDigits}`;
  const email = options.email || `test_${phone}@bursar.co.ke`;
  const password = options.password || 'Str0ng!P@ssw0rd2026!';
  const balance = options.balance !== undefined ? options.balance : 0;

  // Navigate to a page on the same origin first so fetch() has the right context
  await page.goto('/admin');

  // Execute the session setup inside the browser so Set-Cookie is received directly
  await page.evaluate(async (payload) => {
    await fetch('/api/test/setup-session', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
      credentials: 'include'
    });
  }, { phone_number: phone, email, password, balance });

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

  // Navigate to /admin first to establish the origin for in-browser fetch
  await page.goto('/admin');
  await page.waitForLoadState('domcontentloaded');

  // Execute session setup INSIDE the browser so the Set-Cookie header
  // lands directly in the browser's cookie jar (not Playwright's API context)
  await page.evaluate(async (payload) => {
    await fetch('/api/test/setup-admin-session', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
      credentials: 'include'
    });
  }, { email, password, role });

  // Reload — now the browser has the admin_session_token cookie,
  // so checkAuthSession() will succeed and unhide #view-app
  await page.reload();
  await page.waitForLoadState('networkidle');
  await page.locator('#view-app').waitFor({ state: 'visible', timeout: 10000 });
  return { email, password, role };
}

async function setupEmailOnlyUser(page, options = {}) {
  const randomId = Math.floor(100000 + Math.random() * 900000);
  const email = options.email || `emailonly_${randomId}@bursar.co.ke`;
  const password = options.password || 'Str0ng!P@ssw0rd2026!';
  const balance = options.balance !== undefined ? options.balance : 0;

  await page.goto('/admin');
  await page.evaluate(async (payload) => {
    await fetch('/api/test/setup-session', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
      credentials: 'include'
    });
  }, { email_only: true, email, password, balance });

  await page.goto('/dashboard');
  await page.waitForLoadState('networkidle');
  return { email, password };
}

function getFutureDates() {
  const nowUtc = new Date();
  const eatOffsetMs = 3 * 60 * 60 * 1000;
  const nowEat = new Date(nowUtc.getTime() + (nowUtc.getTimezoneOffset() * 60 * 1000) + eatOffsetMs);

  const tomorrow = new Date(nowEat);
  tomorrow.setDate(tomorrow.getDate() + 1);

  const nextWeek = new Date(nowEat);
  nextWeek.setDate(nextWeek.getDate() + 7);

  const formatYMD = (d) => {
    const year = d.getFullYear();
    const month = String(d.getMonth() + 1).padStart(2, '0');
    const day = String(d.getDate()).padStart(2, '0');
    return `${year}-${month}-${day}`;
  };

  return {
    tomorrow: formatYMD(tomorrow),
    nextWeek: formatYMD(nextWeek)
  };
}

module.exports = {
  setupAuthenticatedUser,
  setupAuthenticatedAdmin,
  setupEmailOnlyUser,
  getFutureDates
};

