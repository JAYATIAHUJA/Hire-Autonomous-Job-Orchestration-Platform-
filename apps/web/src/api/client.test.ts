import { afterEach, describe, expect, it, vi } from 'vitest'

import { apiFetch, getBoard, swipeJob } from './client'

const ok = () => new Response(JSON.stringify({}), { status: 200, headers: { 'Content-Type': 'application/json' } })

describe('apiFetch', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('sends the session cookie and the CSRF header on every call', async () => {
    const fetchMock = vi.fn(async () => ok())
    vi.stubGlobal('fetch', fetchMock)

    await apiFetch('/api/applications/board', { headers: { 'Content-Type': 'application/json' } })
    const [, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit]
    const headers = new Headers(init.headers)
    expect(init.credentials).toBe('include')
    expect(headers.get('X-Requested-With')).toBe('hire-web')
    expect(headers.get('Content-Type')).toBe('application/json')
  })

  it('is what the deck and board calls go through', async () => {
    const fetchMock = vi.fn(async () => ok())
    vi.stubGlobal('fetch', fetchMock)

    await getBoard()
    await swipeJob('job-1', 'right').catch(() => undefined)
    for (const call of fetchMock.mock.calls as unknown as [string, RequestInit][]) {
      expect(call[1].credentials).toBe('include')
      expect(new Headers(call[1].headers).get('X-Requested-With')).toBe('hire-web')
    }
    expect(fetchMock).toHaveBeenCalledTimes(2)
  })
})
