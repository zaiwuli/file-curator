import { describe, expect, it } from 'vitest'
import { messages, translate } from '../i18n'

describe('localization resources', () => {
  it('keeps navigation keys aligned', () => {
    expect(Object.keys(messages.en.nav)).toEqual(Object.keys(messages['zh-CN'].nav))
  })
  it('ships a safe default workflow label', () => {
    expect(messages.en.nav.preview).toBe('Virtual preview')
  })
  it('translates desktop text and dynamic counts', () => {
    expect(translate('zh-CN', 'Workspace overview')).toBe('工作区概览')
    expect(translate('zh-CN', '12 files')).toBe('12 个文件')
    expect(translate('zh-CN', 'date extractor')).toBe('日期提取')
    expect(translate('zh-CN', 'date extractor options (JSON)')).toBe('日期提取 选项（JSON）')
    expect(translate('zh-CN', 'v1.0 · safe · score 0.8')).toBe('v1.0 · 安全 · 分数 0.8')
    expect(translate('zh-CN', '3 succeeded · 1 failed · 2 skipped')).toBe('成功 3 · 失败 1 · 跳过 2')
    expect(translate('zh-CN', 'Rev 2 → 3')).toBe('修订 2 → 3')
    expect(translate('zh-CN', 'extract_date'.replaceAll('_', ' '))).toBe('提取日期')
    expect(translate('zh-CN', 'Toggle extract_date')).toBe('切换提取日期')
    expect(translate('zh-CN', 'normal')).toBe('常规')
    expect(translate('zh-CN', '· score')).toBe('· 分数')
    expect(translate('zh-CN', 'files')).toBe('个文件')
    expect(translate('zh-CN', 'workflows')).toBe('工作流')
    expect(translate('zh-CN', 'Build an organization workflow')).toBe('创建整理流程')
    expect(translate('zh-CN', 'feature groups selected · no real file changes')).toBe('项功能已选择 · 不会修改真实文件')
  })
})
