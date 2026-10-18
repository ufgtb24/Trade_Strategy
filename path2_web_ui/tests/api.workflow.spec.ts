// 看图工作流的取数出错时:只显示状态码和后端说明(detail),不把请求地址带进错误文字——
// K 线请求的地址里有图窗终点(决策日之后 H 根),显示到图上就能推出决策日。
import { describe, it, expect, vi, afterEach } from 'vitest'
import { getWorkflowOhlc, getWorkflowState, loadWorkflowList, recordChartView } from '../src/api'

const fail = (status: number, body: string) =>
  Promise.resolve({ ok: false, status, text: () => Promise.resolve(body) } as any)

describe('workflow api 错误文字', () => {
  afterEach(() => { vi.unstubAllGlobals() })

  it('K 线取不到:错误里只有状态码与说明,没有请求的起止日期', async () => {
    vi.stubGlobal('fetch', vi.fn(() => fail(404, '{"detail":"pkl not found: AAA"}')))
    const err = await getWorkflowOhlc('AAA', '2025-01-02', '2025-08-27').catch(e => e)
    expect(err.message).toBe('404:pkl not found: AAA')
    expect(err.message).not.toContain('2025-08-27')
  })

  it('打开清单 403 / 503:把后端的中文说明显示出来;正文不是 JSON 就原样', async () => {
    vi.stubGlobal('fetch', vi.fn(() => fail(403, '{"detail":"这份清单的图窗早于本轮看图下界 2025-01-01，不能打开"}')))
    expect((await loadWorkflowList('r1').catch(e => e)).message)
      .toBe('403:这份清单的图窗早于本轮看图下界 2025-01-01，不能打开')
    vi.stubGlobal('fetch', vi.fn(() => fail(503, 'Service Unavailable')))
    expect((await loadWorkflowList('r1').catch(e => e)).message).toBe('503:Service Unavailable')
  })

  it('状态根接口:GET /workflow/state 原样返回;出错时带状态码与说明', async () => {
    const body = { path: '/tmp/s', from_env: true, env_var: 'CHART_WORKFLOW_STATE_ROOT', ok: true,
                   message: null }
    const f = vi.fn(() => Promise.resolve({ ok: true, json: () => Promise.resolve(body) } as any))
    vi.stubGlobal('fetch', f)
    expect(await getWorkflowState()).toEqual(body)
    expect(String((f.mock.calls[0] as any)[0])).toMatch(/\/workflow\/state$/)
    vi.stubGlobal('fetch', vi.fn(() => fail(500, '{"detail":"x"}')))
    expect((await getWorkflowState().catch(e => e)).message).toBe('500:x')
  })

  it('单张图事件:POST /workflow/views,reveal 带买点;出错带状态码与说明', async () => {
    const f = vi.fn((..._a: any[]) => Promise.resolve({ ok: true, json: () => Promise.resolve({ ok: true }) } as any))
    vi.stubGlobal('fetch', f)
    await recordChartView('r1', 'AAA@2025-03-12', 'zoom')
    await recordChartView('r1', 'AAA@2025-03-12', 'reveal', [{ date: '2025-03-13', primary: true }])
    expect(String(f.mock.calls[0][0])).toMatch(/\/workflow\/views$/)
    expect(JSON.parse(f.mock.calls[0][1].body)).toEqual({ list_id: 'r1', item_id: 'AAA@2025-03-12', event: 'zoom' })
    expect(JSON.parse(f.mock.calls[1][1].body).buy_points).toEqual([{ date: '2025-03-13', primary: true }])
    vi.stubGlobal('fetch', vi.fn(() => fail(503, '{"detail":"状态根不可用"}')))
    expect((await recordChartView('r1', 'x', 'zoom').catch(e => e)).message).toBe('503:状态根不可用')
  })
})
