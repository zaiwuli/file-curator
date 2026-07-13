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
  })
})
