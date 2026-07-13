import { describe, expect, it } from 'vitest'
import { messages } from '../i18n'

describe('localization resources', () => {
  it('keeps navigation keys aligned', () => {
    expect(Object.keys(messages.en.nav)).toEqual(Object.keys(messages['zh-CN'].nav))
  })
  it('ships a safe default workflow label', () => {
    expect(messages.en.nav.preview).toBe('Virtual preview')
  })
})
