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
  await page.getByRole('button', { name: '专家模式' }).click()
  await expect(page.getByText('处理关卡')).toBeVisible()
  await expect(page.getByText('实时检查')).toBeVisible()
  await expect(page.getByRole('button', { name: '添加规则' })).toBeVisible()
  await expect(page.getByText('冻结计划并确认前，真实文件保持不变。')).toBeVisible()
  const undersizedText = await page.locator('body').evaluate(body => [...body.querySelectorAll('*')].filter(element => {
    const style = getComputedStyle(element)
    const rect = element.getBoundingClientRect()
    return style.display !== 'none' && style.visibility !== 'hidden' && rect.width > 0 && rect.height > 0 && element.childNodes.length === 1 && element.firstChild?.nodeType === 3 && element.textContent?.trim() && Number.parseFloat(style.fontSize) < 12
  }).length)
  expect(undersizedText).toBe(0)
  for (const [navigation,heading] of [
    ['数据源','数据源'],['文件浏览器','文件浏览器'],['垃圾规则','垃圾规则'],
    ['审核中心','审核中心'],['虚拟预览','虚拟预览'],['执行','执行'],
    ['历史记录','历史与恢复'],['设置','设置'],
  ] as const) {
    await page.getByRole('button', { name: navigation }).click()
    await expect(page.getByRole('heading', { name: heading })).toBeVisible()
  }
})

test('desktop breakpoints do not overflow', async ({ page }) => {
  for (const width of [1024,1280,1440,1920]) {
    await page.setViewportSize({ width, height: 960 })
    await page.goto('/')
    await expect(page.getByText('API connected')).toBeVisible()
    const overflow = await page.locator('html').evaluate(element => element.scrollWidth > element.clientWidth)
    expect(overflow, `horizontal overflow at ${width}px`).toBe(false)
  }
})

test('template selection opens the five-step builder and expert stage', async ({ page }) => {
  await page.goto('/')
  await expect(page.getByText('API connected')).toBeVisible()
  await page.getByRole('button', { name: 'Pipeline' }).click()
  await page.getByRole('button', {
    name: 'Archive by year and month Extract dates and archive within the source. 2 rules',
  }).click()

  await expect(page.getByRole('heading', { name: '1. What to process' })).toBeVisible()
  await page.getByRole('button', { name: 'Expert' }).click()
  await expect(page.getByRole('heading', { name: 'Extract information' })).toBeVisible()
  await expect(page.getByRole('button', { name: '1 Extract all dates Extract all dates On' })).toBeVisible()
})

test('workflow delegates junk packs and keeps filename cleanup forms', async ({ page }) => {
  await page.goto('/')
  await expect(page.getByText('API connected')).toBeVisible()
  await page.getByRole('button', { name: 'Pipeline' }).click()
  await page.getByRole('button', { name: 'Build manually' }).click()

  await page.getByRole('button', { name: /2\. What to recognize/ }).first().click()
  await page.locator('.business-feature').filter({ hasText: 'Detect junk files' }).locator('.switch-control').click()
  await expect(page.getByPlaceholder('Search rule packs')).toBeVisible()
  await expect(page.getByText('BT advertisements and junk')).toBeVisible()
  await expect(page.getByLabel('Additional junk keywords')).toHaveCount(0)

  await page.getByRole('button', { name: /3\. How to rename/ }).first().click()
  await page.locator('.business-feature').filter({ hasText: 'Clean file names' }).locator('.switch-control').click()
  await expect(page.getByLabel('Keywords to remove from file name')).toBeVisible()

  await page.getByRole('button', { name: 'Expert' }).click()
  await page.getByRole('button', { name: 'Detect and quarantine BT advertisements' }).click()
  await expect(page.getByText('Reusable junk rule packs')).toBeVisible()
  await expect(page.getByText('Manage junk rules from the Junk rules navigation page.')).toBeVisible()
  await expect(page.getByLabel('Additional junk keywords')).toHaveCount(0)

  await page.getByRole('button', { name: 'Remove advertisement words' }).click()
  await expect(page.getByLabel('Keywords to remove from file name')).toBeVisible()
  await expect(page.getByLabel('Prefixes to remove')).toBeVisible()
  await expect(page.getByLabel('Suffixes to remove')).toBeVisible()

  await expect(page.getByText('Developer options (JSON)')).toBeVisible()
  await page.getByRole('button', { name: 'Standard' }).click()
  await expect(page.getByText('Developer options (JSON)')).toHaveCount(0)
})

test('junk rule library versions independent rules and applies a snapshot', async ({ page, request }) => {
  const packName = `E2E reusable advertisements ${Date.now()}`
  const workflow = await (await request.post('/api/workflows', {
    data: { name: `E2E junk rules ${Date.now()}`, processors: [] },
  })).json()

  await page.goto('/')
  await expect(page.getByText('API connected')).toBeVisible()
  await page.getByRole('button', { name: 'Junk rules' }).click()
  await page.getByRole('button', { name: 'New rule pack' }).click()
  await page.getByLabel('Rule pack name').fill(packName)
  await page.getByLabel('Rule name').fill('Quarantine tracker advertisement')
  await page.getByLabel('Action').selectOption('quarantine')
  await page.getByLabel('Evidence score').fill('65')
  const keywords = page.getByLabel('File name keywords')
  await keywords.fill('tracker.example')
  await keywords.press('Enter')
  await page.getByRole('button', { name: 'Add rule' }).click()
  await page.getByLabel('Rule name').fill('Review sample files')
  await page.getByLabel('Action').selectOption('review')
  const sampleKeywords = page.getByLabel('File name keywords')
  await sampleKeywords.fill('sample')
  await sampleKeywords.press('Enter')
  await page.getByRole('button', { name: 'Save new version' }).click()
  await expect(page.getByText('Junk rule pack saved')).toBeVisible()

  const packs = await (await request.get('/api/junk-rule-packs')).json()
  const pack = packs.find((item: {name:string}) => item.name === packName)
  expect(pack.rules).toHaveLength(2)
  expect(pack.rules[0]).toMatchObject({action:'quarantine',filename_contains:['tracker.example']})
  expect(pack.rules[1]).toMatchObject({action:'review',filename_contains:['sample']})

  await page.getByLabel('Target workflow').selectOption(workflow.id)
  await page.getByRole('button', { name: 'Apply selected version' }).click()
  await expect(page.getByText('Junk rule pack applied to workflow')).toBeVisible()

  await expect.poll(async () => {
    const response = await request.get(`/api/workflow-templates/${workflow.id}/export?format=json`)
    const template = await response.json()
    const actions = template.stages.flatMap((stage: {rules:{actions:{options:Record<string,unknown>}[]}[]}) => stage.rules.flatMap(rule => rule.actions))
    const options = actions.find((action: {options:Record<string,unknown>}) => action.options.processor_id === 'detect_junk')?.options
    return options
  }).toMatchObject({ rule_pack_refs: [{id:pack.id,version:'1'}] })
})
