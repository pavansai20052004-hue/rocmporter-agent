import { expect, test } from '@playwright/test'

async function stubOllamaStatus(page) {
  const checkedAt = new Date('2026-07-01T06:00:00.000Z').toISOString()
  await page.route('**/api/health', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ status: 'ok' }),
    })
  })
  await page.route('**/api/ollama/status**', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        host: 'http://127.0.0.1:11434',
        reachable: false,
        checkedAt,
        version: null,
        responseTimeMs: null,
        preferredModel: {
          requestedName: 'qwen2.5-coder:latest',
          resolvedName: null,
          available: false,
          loaded: false,
        },
        modelCount: 0,
        loadedModelCount: 0,
        models: [],
        runningModels: [],
        summary: 'Playwright stub: Ollama is unavailable for offline UI smoke testing.',
        error: 'stubbed',
      }),
    })
  })
  await page.route('**/api/ollama/models', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: '[]',
    })
  })
}

test('home screen renders without runtime errors', async ({ page }) => {
  await stubOllamaStatus(page)
  const messages = []
  page.on('console', (message) => {
    if (['error', 'warning'].includes(message.type())) {
      const text = message.text()
      if (!text.includes('Failed to load resource: the server responded with a status of 502')) {
        messages.push(`${message.type()}: ${text}`)
      }
    }
  })
  page.on('pageerror', (error) => messages.push(`pageerror: ${error.message}`))

  const response = await page.goto('/', { waitUntil: 'networkidle' })

  expect(response?.status()).toBe(200)
  await expect(page.getByRole('heading', { name: 'ROCmPorter Agent' })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Analyze Repository' })).toBeVisible()
  await expect(page.getByRole('button', { name: 'extension-cpp' })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Export Report' })).toBeDisabled()
  await expect(page.getByText('Benchmark Proof')).toBeVisible()
  await expect(page.getByRole('heading', { name: '3 export-ready review artifacts' })).toBeVisible()
  await expect(page.getByText('submission-proof-v2')).toBeVisible()
  await expect(page.getByText('Patch Model')).toBeVisible()
  await expect(page.getByText('No cloud LLM API')).toBeVisible()
  await expect(page.getByText('Patch Workspace')).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Export-gated review artifact' })).toBeVisible()
  expect(messages).toEqual([])
})

test('sample scan demo flow loads report, patch, export, and review states', async ({ page }) => {
  await stubOllamaStatus(page)
  const messages = []
  page.on('console', (message) => {
    if (['error', 'warning'].includes(message.type())) {
      const text = message.text()
      if (!text.includes('Failed to load resource: the server responded with a status of 502')) {
        messages.push(`${message.type()}: ${text}`)
      }
    }
  })
  page.on('pageerror', (error) => messages.push(`pageerror: ${error.message}`))

  await page.goto('/', { waitUntil: 'networkidle' })

  await page.getByRole('button', { name: 'Load Sample Scan' }).click()
  await expect(page.getByRole('heading', { name: 'extension-cpp' })).toBeVisible()
  await expect(page.getByText('Executive Summary')).toBeVisible()
  await expect(page.getByText(/scores 54\/100 for ROCm portability/)).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Build configuration is tied to CUDA or NVCC' })).toBeVisible()

  await page.getByRole('button', { name: 'Generate Patch' }).first().click()
  await expect(page.getByText('sample_patch_setup_py_rocm', { exact: true })).toBeVisible()
  await expect(page.getByText('apply gate blocked')).toBeVisible()

  await page.getByRole('button', { name: 'Export With Patch' }).click()
  await expect(page.getByText('Sample bundle paths are illustrative')).toBeVisible()
  await expect(page.getByText('Zip Bundle')).toBeVisible()

  await page.getByRole('button', { name: 'Build GitHub Review' }).click()
  await expect(page.getByText('Sample review: conservative ROCm build-path aid generated')).toBeVisible()
  const reviewResult = page.locator('.github-review-result')
  await expect(reviewResult.getByText('Export Ready', { exact: true })).toBeVisible()
  await expect(reviewResult.getByText('Apply Ready', { exact: true })).toBeVisible()
  await expect(reviewResult.getByText('Review artifact: export is ready')).toBeVisible()

  expect(messages).toEqual([])
})
