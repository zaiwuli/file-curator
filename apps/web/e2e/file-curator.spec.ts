import { expect, test } from '@playwright/test'
import { mkdir, rm, writeFile } from 'node:fs/promises'
import path from 'node:path'

test('source to execution and rollback workflow', async ({ page, request }, testInfo) => {
  const mediaRoot = path.join(testInfo.outputPath('media'), String(Date.now()))
  await mkdir(mediaRoot, { recursive: true })
  await writeFile(path.join(mediaRoot, 'Example   File.MP4'), 'test-content')

  await page.goto('/')
  await expect(page.getByText('API connected')).toBeVisible()
  await page.getByRole('button', { name: 'Sources' }).click()
  await page.getByRole('button', { name: 'Add source' }).click()
  const sourceName = `E2E library ${Date.now()}`
  const modal = page.locator('form.modal')
  await modal.getByPlaceholder('Media library').fill(sourceName)
  await modal.getByPlaceholder('/volume1/media').fill(mediaRoot)
  await modal.getByRole('button', { name: 'Add source', exact: true }).click()
  await expect(page.getByRole('heading', { name: sourceName })).toBeVisible()

  const sources = await (await request.get('/api/sources')).json()
  const source = sources.find((item: { name: string }) => item.name === sourceName)
  const sourceCard = page.locator('.source-card').filter({ hasText: sourceName })
  await sourceCard.getByRole('button', { name: 'Scan metadata' }).click()
  await expect.poll(async () => {
    const response = await request.get(`/api/files/page?source_id=${source.id}`)
    return (await response.json()).total
  }).toBe(1)

  await page.getByRole('button', { name: 'File browser' }).click()
  await page.getByRole('combobox').selectOption(source.id)
  await expect(page.getByText('Example   File.MP4')).toBeVisible()

  const workflow = await (await request.post('/api/workflows', {
    data: { name: 'E2E rename', processors: [{ id: 'normalize_name', enabled: true, options: {} }] },
  })).json()
  const run = await (await request.post('/api/pipeline-runs', {
    data: { source_id: source.id, workflow_id: workflow.id },
  })).json()
  const plan = await (await request.post('/api/plans', { data: { run_id: run.id } })).json()

  await page.reload()
  await expect(page.getByText('API connected')).toBeVisible()
  await page.getByRole('button', { name: 'Virtual preview' }).click()
  await expect(page.getByText('Example File.mp4', { exact: true })).toBeVisible()
  await page.getByRole('button', { name: 'Freeze', exact: true }).click()
  await page.getByRole('button', { name: 'Confirm', exact: true }).click()

  await page.getByRole('button', { name: 'Execution' }).click()
  await page.getByRole('button', { name: 'Confirm and execute' }).click()
  await expect.poll(async () => {
    const batches = await (await request.get('/api/batches')).json()
    return batches.find((item: { plan_id: string }) => item.plan_id === plan.id)?.status
  }).toBe('completed')
  const completedBatches = await (await request.get('/api/batches')).json()
  const completedBatch = completedBatches.find((item: { plan_id: string }) => item.plan_id === plan.id)

  await page.reload()
  await expect(page.getByText('API connected')).toBeVisible()
  await page.getByRole('button', { name: 'History' }).click()
  const executionHistory = page.locator('.history-panel').filter({ hasText: 'Execution batches' })
  const batchRow = executionHistory.locator('.table-row').filter({ hasText: completedBatch.id.slice(0, 8) })
  await batchRow.getByRole('button', { name: 'Simulate' }).click()
  await batchRow.getByRole('button', { name: 'Roll back' }).click()
  await expect.poll(async () => {
    const batches = await (await request.get('/api/batches')).json()
    return batches.find((item: { plan_id: string }) => item.plan_id === plan.id)?.status
  }).toBe('rolled_back')

  await rm(mediaRoot, { recursive: true, force: true })
})

test('desktop shell has named controls and no horizontal overflow', async ({ page }) => {
  await page.goto('/')
  await expect(page.getByText('API connected')).toBeVisible()
  await expect(page.locator('nav')).toBeVisible()
  await expect(page.locator('main')).toBeVisible()
  const unnamedButtons = await page.locator('button').evaluateAll(buttons => buttons.filter(button => {
    const name = button.getAttribute('aria-label') || button.getAttribute('title') || button.textContent
    return !name?.trim()
  }).length)
  const overflows = await page.locator('body').evaluate(body => body.scrollWidth > body.clientWidth)
  expect(unnamedButtons).toBe(0)
  expect(overflows).toBe(false)
  await page.getByRole('button', { name: 'Switch to Chinese' }).click()
  await expect(page.getByRole('heading', { name: '工作区概览' })).toBeVisible()
  await page.getByRole('button', { name: '处理流程' }).click()
  await expect(page.getByRole('heading', { name: '工作流构建器' })).toBeVisible()
  await expect(page.getByRole('button', { name: '从模板创建' })).toBeVisible()
  await expect(page.getByRole('button', { name: '粘贴 AI 模板' })).toBeVisible()
  await expect(page.getByRole('button', { name: '手动搭建' })).toBeVisible()
  await page.getByRole('button', { name: '手动搭建' }).click()
  await expect(page.getByText('处理关卡')).toBeVisible()
  await expect(page.getByText('实时检查')).toBeVisible()
  await expect(page.getByRole('button', { name: '添加规则' })).toBeVisible()
  await expect(page.getByText('冻结计划并确认前，真实文件保持不变。')).toBeVisible()
})

test('template selection opens its first configured stage', async ({ page }) => {
  await page.goto('/')
  await expect(page.getByText('API connected')).toBeVisible()
  await page.getByRole('button', { name: 'Pipeline' }).click()
  await page.getByRole('button', {
    name: 'Archive by year and month Extract dates and archive within the source. 2 rules',
  }).click()

  await expect(page.getByRole('heading', { name: 'Extract information' })).toBeVisible()
  await expect(page.getByRole('button', { name: '1 Extract all dates Extract all dates On' })).toBeVisible()
})

test('custom junk and filename cleanup fields are available', async ({ page }) => {
  await page.goto('/')
  await expect(page.getByText('API connected')).toBeVisible()
  await page.getByRole('button', { name: 'Pipeline' }).click()
  await page.getByRole('button', { name: 'Build manually' }).click()

  await page.getByRole('button', { name: 'Detect and quarantine BT advertisements' }).click()
  await expect(page.getByLabel('Additional junk keywords')).toBeVisible()
  await expect(page.getByLabel('Additional junk file extensions')).toBeVisible()
  await expect(page.getByLabel('Protected extension whitelist')).toBeVisible()

  await page.getByRole('button', { name: 'Remove advertisement words' }).click()
  await expect(page.getByLabel('Keywords to remove from file name')).toBeVisible()
  await expect(page.getByLabel('Prefixes to remove')).toBeVisible()
  await expect(page.getByLabel('Suffixes to remove')).toBeVisible()
})
