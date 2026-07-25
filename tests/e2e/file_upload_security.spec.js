const { test, expect } = require('@playwright/test');
const fs = require('fs');
const path = require('path');

test.describe('Bursar 2.0 Rigorous File Upload Security E2E Tests (H-06)', () => {
  const tmpDir = path.join(__dirname, 'tmp_uploads');

  test.beforeAll(() => {
    if (!fs.existsSync(tmpDir)) {
      fs.mkdirSync(tmpDir, { recursive: true });
    }
  });

  test.afterAll(() => {
    if (fs.existsSync(tmpDir)) {
      fs.rmSync(tmpDir, { recursive: true, force: true });
    }
  });

  // Helper to create a valid 1x1 PNG file
  function createValidPngBuffer() {
    return Buffer.from(
      'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==',
      'base64'
    );
  }

  test('1. Valid PNG avatar upload via browser UI updates avatar preview cleanly', async ({ page }) => {
    await page.goto('/#signup');
    const randomDigits = Math.floor(100000 + Math.random() * 900000);
    const testPhoneNumber = `254700${randomDigits}`;

    await page.fill('#auth-phone', testPhoneNumber);
    await page.fill('#auth-password', 'Str0ng!P@ssw0rd');
    const confirmInput = page.locator('#auth-confirm-password');
    if (await confirmInput.count() > 0) {
      await confirmInput.fill('Str0ng!P@ssw0rd');
    }
    await page.click('#auth-submit-btn');

    await page.waitForURL('**/dashboard');
    await page.waitForLoadState('networkidle');

    // Navigate to Profile tab
    await page.click('[data-tab="profile"]');
    await page.waitForLoadState('networkidle');

    // Create valid PNG temporary file
    const pngPath = path.join(tmpDir, 'valid_avatar.png');
    fs.writeFileSync(pngPath, createValidPngBuffer());

    // Upload via file input #avatar-input
    const avatarInput = page.locator('#avatar-input');
    await avatarInput.setInputFiles(pngPath);

    await page.waitForTimeout(1500);

    // Verify avatar URL updated in profile avatar preview
    const avatarImg = page.locator('#profile-avatar-img');
    await expect(avatarImg).toBeVisible();
    const src = await avatarImg.getAttribute('src');
    expect(src).toContain('/uploads/avatars/');
  });

  test('2. Disguised HTML script payload with .png extension is rejected by server (400)', async ({ page }) => {
    await page.goto('/#signup');
    const randomDigits = Math.floor(100000 + Math.random() * 900000);
    const testPhoneNumber = `254700${randomDigits}`;

    await page.fill('#auth-phone', testPhoneNumber);
    await page.fill('#auth-password', 'Str0ng!P@ssw0rd');
    const confirmInput = page.locator('#auth-confirm-password');
    if (await confirmInput.count() > 0) {
      await confirmInput.fill('Str0ng!P@ssw0rd');
    }
    await page.click('#auth-submit-btn');
    await page.waitForURL('**/dashboard');

    const fakePngBuffer = Buffer.from("<script>alert('XSS Attack')</script>");
    const cookies = await page.context().cookies();
    const csrfCookie = cookies.find(c => c.name === 'csrf_token');

    const res = await page.request.post('/api/profile/avatar', {
      headers: {
        'X-CSRF-Token': csrfCookie ? csrfCookie.value : ''
      },
      multipart: {
        file: {
          name: 'malicious.png',
          mimeType: 'image/png',
          buffer: fakePngBuffer
        }
      }
    });

    expect(res.status()).toBe(400);
    const body = await res.json();
    expect(body.detail).toContain('Invalid or unsupported image file format.');
  });

  test('3. SVG XML file upload is strictly rejected (400)', async ({ page }) => {
    await page.goto('/#signup');
    const randomDigits = Math.floor(100000 + Math.random() * 900000);
    const testPhoneNumber = `254700${randomDigits}`;

    await page.fill('#auth-phone', testPhoneNumber);
    await page.fill('#auth-password', 'Str0ng!P@ssw0rd');
    const confirmInput = page.locator('#auth-confirm-password');
    if (await confirmInput.count() > 0) {
      await confirmInput.fill('Str0ng!P@ssw0rd');
    }
    await page.click('#auth-submit-btn');
    await page.waitForURL('**/dashboard');

    const svgBuffer = Buffer.from('<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>');
    const cookies = await page.context().cookies();
    const csrfCookie = cookies.find(c => c.name === 'csrf_token');

    const res = await page.request.post('/api/profile/avatar', {
      headers: {
        'X-CSRF-Token': csrfCookie ? csrfCookie.value : ''
      },
      multipart: {
        file: {
          name: 'vector.svg',
          mimeType: 'image/svg+xml',
          buffer: svgBuffer
        }
      }
    });

    expect(res.status()).toBe(400);
  });

  test('4. Polyglot PNG file (PNG + trailing script) is re-encoded into clean image (200)', async ({ page }) => {
    await page.goto('/#signup');
    const randomDigits = Math.floor(100000 + Math.random() * 900000);
    const testPhoneNumber = `254700${randomDigits}`;

    await page.fill('#auth-phone', testPhoneNumber);
    await page.fill('#auth-password', 'Str0ng!P@ssw0rd');
    const confirmInput = page.locator('#auth-confirm-password');
    if (await confirmInput.count() > 0) {
      await confirmInput.fill('Str0ng!P@ssw0rd');
    }
    await page.click('#auth-submit-btn');
    await page.waitForURL('**/dashboard');

    const polyglotBuffer = Buffer.concat([
      createValidPngBuffer(),
      Buffer.from("<script>alert('polyglot')</script>")
    ]);

    const cookies = await page.context().cookies();
    const csrfCookie = cookies.find(c => c.name === 'csrf_token');

    const res = await page.request.post('/api/profile/avatar', {
      headers: {
        'X-CSRF-Token': csrfCookie ? csrfCookie.value : ''
      },
      multipart: {
        file: {
          name: 'polyglot.png',
          mimeType: 'image/png',
          buffer: polyglotBuffer
        }
      }
    });

    expect(res.status()).toBe(200);
    const body = await res.json();
    expect(body.avatar_url).toContain('/uploads/avatars/');

    const imgRes = await page.request.get(body.avatar_url);
    expect(imgRes.status()).toBe(200);
    const imgBuffer = await imgRes.body();
    expect(imgBuffer.toString('utf-8')).not.toContain('<script>');
  });

  test('5. Oversized avatar payload (>2MB) is rejected (400)', async ({ page }) => {
    await page.goto('/#signup');
    const randomDigits = Math.floor(100000 + Math.random() * 900000);
    const testPhoneNumber = `254700${randomDigits}`;

    await page.fill('#auth-phone', testPhoneNumber);
    await page.fill('#auth-password', 'Str0ng!P@ssw0rd');
    const confirmInput = page.locator('#auth-confirm-password');
    if (await confirmInput.count() > 0) {
      await confirmInput.fill('Str0ng!P@ssw0rd');
    }
    await page.click('#auth-submit-btn');
    await page.waitForURL('**/dashboard');

    const hugeBuffer = Buffer.alloc(2 * 1024 * 1024 + 100);
    const cookies = await page.context().cookies();
    const csrfCookie = cookies.find(c => c.name === 'csrf_token');

    const res = await page.request.post('/api/profile/avatar', {
      headers: {
        'X-CSRF-Token': csrfCookie ? csrfCookie.value : ''
      },
      multipart: {
        file: {
          name: 'huge.png',
          mimeType: 'image/png',
          buffer: hugeBuffer
        }
      }
    });

    expect(res.status()).toBe(400);
    const body = await res.json();
    expect(body.detail).toContain('exceeds the 2MB limit');
  });

});
