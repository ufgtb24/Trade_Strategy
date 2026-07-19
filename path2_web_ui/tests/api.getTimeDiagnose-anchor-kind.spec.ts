/**
 * v3 · getTimeDiagnose URL 参数 anchorKind 拼接测试。
 *
 * 契约:
 * - 传 anchorKind='gate' → URL 含 '&anchor_kind=gate'
 * - 传 undefined → URL 不含 anchor_kind query
 * - 传空串 '' → URL 不含 anchor_kind query(与后端 handler 空串判据对齐 · 前端主动 skip)
 * - encodeURIComponent 正确
 */
import { describe, it, expect, vi, beforeEach, type MockInstance } from 'vitest'
import { getTimeDiagnose } from '../src/api'

describe('getTimeDiagnose anchorKind query 拼接', () => {
  // 注:brief 原版 `ReturnType<typeof vi.spyOn>` 在此仓库无先例、且对重载函数(fetch)会
  // 塌缩成 `MockInstance<(...args: unknown[]) => unknown>`,与具体 spy 赋值不兼容(vue-tsc 报
  // TS2322)。改用 vitest 导出的 `MockInstance<T>` 泛型、以被 spy 的具体函数类型参数化。
  let fetchSpy: MockInstance<typeof fetch>

  beforeEach(() => {
    fetchSpy = vi.spyOn(globalThis, 'fetch').mockResolvedValue({
      ok: true,
      json: async () => ({ scope: 'time', payload: {}, caveats: [] }),
    } as any)
  })

  it('传 anchorKind="gate" · URL 含 &anchor_kind=gate', async () => {
    await getTimeDiagnose('bo_only', 'AAA', '2024-01-01', '2024-07-01',
                          50, 80, undefined, undefined, 'gate')
    const url = fetchSpy.mock.calls[0][0] as string
    expect(url).toContain('&anchor_kind=gate')
  })

  it('传 anchorKind="trough" · URL 含 &anchor_kind=trough', async () => {
    await getTimeDiagnose('bo_only', 'AAA', '2024-01-01', '2024-07-01',
                          50, 80, undefined, undefined, 'trough')
    const url = fetchSpy.mock.calls[0][0] as string
    expect(url).toContain('&anchor_kind=trough')
  })

  it('不传 anchorKind(undefined)· URL 不含 anchor_kind', async () => {
    await getTimeDiagnose('bo_only', 'AAA', '2024-01-01', '2024-07-01',
                          50, 80, undefined, undefined)
    const url = fetchSpy.mock.calls[0][0] as string
    expect(url).not.toContain('anchor_kind=')
  })

  it('传空串 anchorKind="" · URL 不含 anchor_kind', async () => {
    await getTimeDiagnose('bo_only', 'AAA', '2024-01-01', '2024-07-01',
                          50, 80, undefined, undefined, '')
    const url = fetchSpy.mock.calls[0][0] as string
    expect(url).not.toContain('anchor_kind=')
  })

  it('特殊字符 anchorKind encodeURIComponent 正确(防守 · 目前 anchorKind 词汇纯字母)', async () => {
    await getTimeDiagnose('bo_only', 'AAA', '2024-01-01', '2024-07-01',
                          50, 80, undefined, undefined, 'gate&x=y')
    const url = fetchSpy.mock.calls[0][0] as string
    expect(url).toContain('&anchor_kind=gate%26x%3Dy')
  })
})
