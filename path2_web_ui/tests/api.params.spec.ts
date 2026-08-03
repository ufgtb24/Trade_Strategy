// Task 8:params_override / params_diff / params/apply 前端 wire 层测试。
// 目录约定跟随既有 api.*.spec.ts(如 api.getTimeDiagnose-anchor-kind.spec.ts),不用 brief 字面
// src/__tests__ 路径 —— vitest.config include 只扫 tests/**/*.spec.ts。
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { getPreview, getParamsDiff, listParamFiles, readParamFile, saveParamFile, deleteParamFile, getDiagnose } from '../src/api'

const okJson = (body: any) =>
  Promise.resolve({ ok: true, json: () => Promise.resolve(body), text: () => Promise.resolve('') } as any)

describe('params api 扩展', () => {
  beforeEach(() => { vi.stubGlobal('fetch', vi.fn(() => okJson({}))) })
  afterEach(() => { vi.unstubAllGlobals() })

  it('getPreview 带 paramsOverride 时 query 含 JSON 序列化的 params_override', async () => {
    await getPreview('bbb', 'ACRS', '2025-01-01', '2025-06-01', 20, { bo: { total_window: 42 } })
    const url = (fetch as any).mock.calls[0][0] as string
    expect(url).toContain('params_override=')
    expect(decodeURIComponent(url)).toContain('"total_window":42')
  })

  it('getPreview 不带 override 时 query 无 params_override(现状不回归)', async () => {
    await getPreview('bbb', 'ACRS', '2025-01-01', '2025-06-01', 20)
    expect((fetch as any).mock.calls[0][0]).not.toContain('params_override')
  })

  it('getDiagnose 支持尾参 override', async () => {
    await getDiagnose('bbb', 'ACRS', '2025-01-01', '2025-06-01', { bo: { total_window: 42 } })
    expect((fetch as any).mock.calls[0][0]).toContain('params_override=')
  })

  it('getParamsDiff 命中 /params_diff', async () => {
    await getParamsDiff('bbb', '20260720T000000')
    expect((fetch as any).mock.calls[0][0]).toContain('/params_diff?pattern_id=bbb&scan_ts=20260720T000000')
  })

  it('listParamFiles GET /params/files 并解包 files', async () => {
    vi.stubGlobal('fetch', vi.fn(() => okJson({ files: ['params.yaml', 'exp.yaml'] })))
    const files = await listParamFiles('bbb')
    expect((fetch as any).mock.calls[0][0]).toContain('/params/files?pattern_id=bbb')
    expect(files).toEqual(['params.yaml', 'exp.yaml'])
  })

  it('readParamFile GET /params/file 并解包 params', async () => {
    vi.stubGlobal('fetch', vi.fn(() => okJson({ params: { bo: { total_window: 40 } } })))
    const d = await readParamFile('bbb', 'exp.yaml')
    expect((fetch as any).mock.calls[0][0]).toContain('/params/file?pattern_id=bbb&name=exp.yaml')
    expect(d).toEqual({ bo: { total_window: 40 } })
  })

  it('saveParamFile POST /params/save 带 name', async () => {
    await saveParamFile('bbb', 'exp.yaml', { bo: { total_window: 42 } })
    const [url, init] = (fetch as any).mock.calls[0]
    expect(url).toContain('/params/save')
    expect(init.method).toBe('POST')
    const body = JSON.parse(init.body)
    expect(body.name).toBe('exp.yaml')
    expect(body.params.bo.total_window).toBe(42)
  })

  it('deleteParamFile DELETE /params/file 带 name', async () => {
    await deleteParamFile('bbb', 'exp.yaml')
    const [url, init] = (fetch as any).mock.calls[0]
    expect(url).toContain('/params/file?pattern_id=bbb&name=exp.yaml')
    expect(init.method).toBe('DELETE')
  })
})
