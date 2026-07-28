const { test, expect } = require('@playwright/test');

test.describe('Phase 1: Email-First & Dual Identifier Authentication E2E Specs', () => {

  test('Should register user with email and login successfully', async ({ request, page }) => {
    const testEmail = `e2e_user_${Date.now()}@bursar.test`;
    const testPassword = 'ComplexP@ssw0rd99!';

    // 1. Direct API Registration Test
    const signupRes = await request.post('/api/auth/signup', {
      data: {
        email: testEmail,
        password: testPassword
      }
    });
    const signupText = await signupRes.text();
    expect(signupRes.ok(), `Signup failed with status ${signupRes.status()}: ${signupText}`).toBeTruthy();
    const signupData = JSON.parse(signupText);
    expect(signupData.status).toBe('success');

    // 2. Direct API Login with Email Test
    const loginRes = await request.post('/api/auth/login', {
      data: {
        identifier: testEmail,
        password: testPassword
      }
    });
    expect(loginRes.ok(), `Login failed with status ${loginRes.status()}: ${await loginRes.text()}`).toBeTruthy();

    // 3. Verify /me endpoint returns email and is_email_verified state
    const meRes = await request.get('/api/auth/me');
    expect(meRes.ok()).toBeTruthy();
    const meData = await meRes.json();
    expect(meData.email).toBe(testEmail);
    expect(meData.is_email_verified).toBe(false);
  });

  test('Should allow legacy phone number user registration and login', async ({ request }) => {
    const randomPhone = `2547${Math.floor(10000000 + Math.random() * 90000000)}`;
    const testPassword = 'ComplexP@ssw0rd99!';

    // 1. Register with phone number
    const signupRes = await request.post('/api/auth/signup', {
      data: {
        phone_number: randomPhone,
        password: testPassword
      }
    });
    expect(signupRes.ok(), `Phone signup failed with status ${signupRes.status()}: ${await signupRes.text()}`).toBeTruthy();

    // 2. Login with phone number
    const loginRes = await request.post('/api/auth/login', {
      data: {
        phone_number: randomPhone,
        password: testPassword
      }
    });
    expect(loginRes.ok()).toBeTruthy();

    // 3. Verify /me returns phone_number
    const meRes = await request.get('/api/auth/me');
    expect(meRes.ok()).toBeTruthy();
    const meData = await meRes.json();
    expect(meData.phone_number).toBe(randomPhone);
  });

  test('Should reject invalid email format during signup', async ({ request }) => {
    const signupRes = await request.post('/api/auth/signup', {
      data: {
        email: 'invalid-email-format',
        password: 'StrongPassword123!'
      }
    });
    expect(signupRes.status()).toBe(400);
    const body = await signupRes.json();
    expect(body.detail).toContain('Invalid email address format');
  });

});
