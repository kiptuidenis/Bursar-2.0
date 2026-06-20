const { defineConfig, devices } = require('@playwright/test');

const isWin = process.platform === 'win32';
const pythonCmd = isWin ? 'venv\\Scripts\\python' : 'venv/bin/python';

module.exports = defineConfig({
  testDir: './tests/e2e',
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: 1,
  reporter: 'list',
  use: {
    baseURL: 'http://localhost:8000',
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
  },
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    }
  ],
  webServer: {
    command: `${pythonCmd} -m uvicorn app.main:app --port 8000`,
    url: 'http://localhost:8000/api/diagnostics',
    reuseExistingServer: !process.env.CI,
    timeout: 30000,
  },
});
