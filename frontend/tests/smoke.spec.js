import { expect, test } from '@playwright/test'

// Smoke tests for the current SaaS app (landing → login → scanner shell).
// CI runs without Supabase env, so auth is dormant and protected routes stay
// open — letting us smoke the scanner without a signed-in session.

function collectErrors(page) {
  const messages = []
  page.on('console', (message) => {
    if (message.type() === 'error') {
      const text = message.text()
      // Backend/API is not running during UI smoke tests; ignore network noise.
      if (!text.includes('Failed to load resource')) {
        messages.push(`console error: ${text}`)
      }
    }
  })
  page.on('pageerror', (error) => messages.push(`pageerror: ${error.message}`))
  return messages
}

test('landing page renders hero and CTAs without runtime errors', async ({ page }) => {
  const messages = collectErrors(page)

  const response = await page.goto('/', { waitUntil: 'domcontentloaded' })

  expect(response?.status()).toBe(200)
  await expect(page.getByRole('heading', { level: 1 })).toContainText('CUDA lock-in')
  await expect(page.getByRole('link', { name: /Scan your first repo|Open the scanner/ })).toBeVisible()
  await expect(page.getByRole('link', { name: 'Sign in' })).toBeVisible()
  expect(messages).toEqual([])
})

test('login page shows both OAuth providers', async ({ page }) => {
  const messages = collectErrors(page)

  await page.goto('/login', { waitUntil: 'domcontentloaded' })

  await expect(page.getByRole('heading', { name: 'Welcome back' })).toBeVisible()
  await expect(page.getByRole('button', { name: /Continue with Google/ })).toBeVisible()
  await expect(page.getByRole('button', { name: /Continue with GitHub/ })).toBeVisible()
  expect(messages).toEqual([])
})

test('scanner shell renders repo input and analyze action', async ({ page }) => {
  const messages = collectErrors(page)

  await page.goto('/app', { waitUntil: 'domcontentloaded' })

  await expect(page.getByPlaceholder('https://github.com/org/repo')).toBeVisible()
  await expect(page.getByRole('button', { name: 'Analyze Repository' })).toBeVisible()
  expect(messages).toEqual([])
})

test('unknown routes redirect to the landing page', async ({ page }) => {
  await page.goto('/definitely-not-a-page', { waitUntil: 'domcontentloaded' })
  await expect(page).toHaveURL(/\/$/)
  await expect(page.getByRole('heading', { level: 1 })).toContainText('CUDA lock-in')
})
