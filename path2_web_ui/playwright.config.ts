import { defineConfig } from '@playwright/test'
import { apiBase, baseURL, frontendPort } from './e2e/ports'

export default defineConfig({
  testDir: './e2e',
  timeout: 600_000,
  use: { baseURL, headless: true },
  webServer: {
    command: `npm run dev -- --port ${frontendPort} --strictPort`,
    url: baseURL,
    reuseExistingServer: true,
    timeout: 60_000,
    env: { VITE_API_BASE: apiBase },
  },
})
