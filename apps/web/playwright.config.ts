import { defineConfig } from '@playwright/test'

const python = process.platform === 'win32' ? '".venv\\Scripts\\python.exe"' : 'python'

export default defineConfig({
  testDir: './e2e',
  timeout: 30_000,
  expect: { timeout: 5_000 },
  fullyParallel: false,
  workers: 1,
  reporter: [['list'], ['html', { open: 'never' }]],
  use: {
    baseURL: 'http://127.0.0.1:5173',
    viewport: { width: 1440, height: 960 },
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
  },
  webServer: [
    {
      command: `${python} -m file_curator --host 127.0.0.1 --port 8000`,
      cwd: '../api',
      url: 'http://127.0.0.1:8000/health/ready',
      reuseExistingServer: true,
      env: {
        FILE_CURATOR_CONFIG_DIR: './e2e-data',
        FILE_CURATOR_DATABASE_URL: 'sqlite:///./e2e-data/file-curator.db',
        FILE_CURATOR_SERVE_UI: 'false',
      },
    },
    {
      command: 'npm run dev -- --host 127.0.0.1',
      cwd: '.',
      url: 'http://127.0.0.1:5173',
      reuseExistingServer: true,
    },
  ],
})
