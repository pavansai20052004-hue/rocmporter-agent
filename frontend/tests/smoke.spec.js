import { expect, test } from '@playwright/test'

test('home screen renders without runtime errors', async ({ page }) => {
  const messages = []
  page.on('console', (message) => {
    if (['error', 'warning'].includes(message.type())) {
      messages.push(`${message.type()}: ${message.text()}`)
    }
  })
  page.on('pageerror', (error) => messages.push(`pageerror: ${error.message}`))

  const response = await page.goto('/', { waitUntil: 'networkidle' })

  expect(response?.status()).toBe(200)
  await expect(page.getByRole('heading', { name: 'ROCmPorter Agent' })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Analyze Repository' })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Export Report' })).toBeDisabled()
  await expect(page.getByText('Patch Model')).toBeVisible()
  await expect(page.getByText('Patch Workspace')).toBeVisible()
  expect(messages).toEqual([])
})
