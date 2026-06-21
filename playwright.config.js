const { defineConfig, devices } = require('@playwright/test');
const fs = require('fs');
const path = require('path');

const hasVenv = fs.existsSync(path.join(__dirname, 'venv'));
const isWin = process.platform === 'win32';
const pythonCmd = hasVenv 
  ? (isWin ? 'venv\\Scripts\\python' : 'venv/bin/python') 
  : 'python';

module.exports = defineConfig({
  testDir: './tests/e2e',
  timeout: 60000, // 60 seconds test execution timeout
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
    command: `${pythonCmd} -m uvicorn app.main:app --port 8000 --app-dir src`,
    url: 'http://localhost:8000/api/diagnostics',
    reuseExistingServer: !process.env.CI,
    timeout: 30000,
    env: {
      DISABLE_SCHEDULER: '1',
      DATABASE_URL: 'bursar_test.db',
    },
  },
});
