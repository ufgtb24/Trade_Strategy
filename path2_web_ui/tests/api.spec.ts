import { describe, it, expect, vi, beforeEach } from 'vitest'
import * as api from '../src/api'
import { PATTERN } from './fixtures'
import { getPreview } from '../src/api'

describe('api', () => {
  beforeEach(() => { vi.restoreAllMocks() })

  it('getPatterns GETs /patterns', async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => [PATTERN] })
    vi.stubGlobal('fetch', fetchMock)
    const out = await api.getPatterns()
    expect(out[0].pattern_id).toBe('bottom_breakout_burst')
    expect(fetchMock.mock.calls[0][0]).toContain('/patterns')
  })

  it('startScan POSTs body and returns scan_id', async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => ({ scan_id: 'S1' }) })
    vi.stubGlobal('fetch', fetchMock)
    const id = await api.startScan({ pattern_ids: ['p'], start_date: 'a', end_date: 'b', workers: 4, ticker_regex: null, label_horizon: 20 })
    expect(id).toBe('S1')
    const [, opts] = fetchMock.mock.calls[0]
    expect(opts.method).toBe('POST')
    expect(JSON.parse(opts.body).workers).toBe(4)
  })

  it('throws on non-ok response', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: false, status: 500, text: async () => 'boom' }))
    await expect(api.getPatterns()).rejects.toThrow(/500/)
  })

  it('streamScan wires EventSource and parses events', async () => {
    const handlers: Record<string, (e: any) => void> = {}
    class FakeES {
      url: string
      onmessage: ((e: any) => void) | null = null
      onerror: ((e: any) => void) | null = null
      constructor(url: string) { this.url = url; handlers.es = (e) => this.onmessage?.(e) }
      close() {}
    }
    vi.stubGlobal('EventSource', FakeES as any)
    const got: any[] = []
    const es = api.streamScan('S1', (e) => got.push(e), () => {})
    handlers.es({ data: JSON.stringify({ scanned: 1, total: 10, hits: 0, errors: 0 }) })
    handlers.es({ data: JSON.stringify({ type: 'done', hits: 2, errors: 0, total: 10 }) })
    expect(got[0].scanned).toBe(1)
    expect(got[1].type).toBe('done')
    expect((es as any).url).toContain('/scan/S1/stream')
  })
})

describe('getNodesDiagnose', () => {
  it('builds GET URL with scope=nodes + src_node/dst_node and parses JSON', async () => {
    const fakeResp = {
      scope: 'nodes',
      payload: { edge_id: 'burst_to_tb', total_pair: 3, ok_pair: 1,
                miss_reasons: { gap_out: 2 }, example_failed_pairs: [] },
      caveats: [],
    }
    const fetchSpy = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify(fakeResp), { status: 200 })
    )
    const r = await api.getNodesDiagnose('bottom_burst', 'AAPL', '2025-01-01', '2025-12-31', 'burst', 'tb')
    expect(r.scope).toBe('nodes')
    expect(r.payload.edge_id).toBe('burst_to_tb')
    expect(fetchSpy).toHaveBeenCalledOnce()
    const url = fetchSpy.mock.calls[0][0] as string
    expect(url).toContain('/diagnose?pattern_id=bottom_burst&symbol=AAPL')
    expect(url).toContain('scope=nodes')
    expect(url).toContain('src_node=burst')
    expect(url).toContain('dst_node=tb')
  })
})

describe('getPreview', () => {
  it('builds GET URL with query params + parses JSON', async () => {
    const fakeResp = { analysis: { events: [], matches: [] },
                       summary: { events: 0, matches: 0 },
                       pattern_spec: { pattern_id: 'p',
                                       topology: { nodes: [], edges: [] },
                                       event_styles: {} },
                       scan: { scan_ts: '', start_date: '2025-01-01', end_date: '2025-12-31',
                               workers: 0, scanned: 0, hits: 0, errors: 0,
                               dataset_dir: '', params: '' } }
    const fetchSpy = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify(fakeResp), { status: 200 })
    )
    const r = await getPreview('p', 'AAPL', '2025-01-01', '2025-12-31', 20)
    expect(r.analysis.matches).toEqual([])
    expect(fetchSpy).toHaveBeenCalledOnce()
    const url = fetchSpy.mock.calls[0][0] as string
    expect(url).toContain('/preview?pattern_id=p&symbol=AAPL')
    expect(url).toContain('start=2025-01-01')
    expect(url).toContain('end=2025-12-31')
    expect(url).toContain('label_horizon=20')
  })
})
