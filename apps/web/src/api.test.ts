import { afterEach, describe, expect, it, vi } from 'vitest'
import { api } from './api'

afterEach(() => vi.unstubAllGlobals())

describe('API client', () => {
  it('returns stable backend error codes to the UI', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(
      JSON.stringify({ detail: 'plan.must_be_frozen' }),
      { status: 409, headers: { 'content-type': 'application/json' } },
    )))

    await expect(api.confirmPlan('plan-id')).rejects.toThrow('plan.must_be_frozen')
  })
})
