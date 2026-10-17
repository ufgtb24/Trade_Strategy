// 看图工作流的取数出错时:只显示状态码和后端说明(detail),不把请求地址带进错误文字——
// K 线请求的地址里有图窗终点(决策日之后 H 根),显示到图上就能推出决策日。
import { describe, it, expect, vi, afterEach } from 'vitest'
import { getWorkflowOhlc, loadWorkflowList } from '../src/api'

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
})
