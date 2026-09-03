// 按钮 enable 矩阵纯函数(三源对称版):snapshot / 关联文件 / Working Copy 三源共用同一条载入判据
//   canLoad[kind] = 源存在 && (parse 失败逃生 || 编辑区 ≠ 源)
// 写出侧(Write Copy / Save / Save As)各源判据不同,原样保留;snapshot 无写出(scan 只读记录)。
// 基准(对比锚)不再参与任何按钮判据——载入与对比彻底解耦。monaco 无关,纯 dict 判定。
import { describe, it, expect } from 'vitest'
import {
  dictsEqual, computeButtonStates, normalizeSaveAsName, resolveAssocFile, resolveAnchorKind,
} from '../src/components/paramsEditorState'

const A = { bo: { total_window: 10, m: 'high' } }
const B = { bo: { total_window: 42, m: 'high' } }

describe('dictsEqual', () => {
  it('嵌套相等(键序无关)', () => {
    expect(dictsEqual({ x: { a: 1, b: 2 } }, { x: { b: 2, a: 1 } })).toBe(true)
  })
  it('值不同 / 键缺失 → false', () => {
    expect(dictsEqual(A, B)).toBe(false)
    expect(dictsEqual({ x: { a: 1 } }, { x: { a: 1, b: 2 } })).toBe(false)
  })
  it('数组顺序敏感', () => {
    expect(dictsEqual({ v: [1, 2] }, { v: [2, 1] })).toBe(false)
    expect(dictsEqual({ v: [1, 2] }, { v: [1, 2] })).toBe(true)
  })
})

describe('computeButtonStates', () => {
  const base = { parseOk: true, editorDict: A, snapDict: A, assocDict: A, wcDict: null }
  it('全一致(无 WC):三源载入全灰;Write Copy(空转创建,决策3)与 SaveAs 可点', () => {
    expect(computeButtonStates(base)).toEqual({
      canLoad: { snapshot: false, assoc: false, wc: false },
      canWriteCopy: true, canSave: false, canSaveAs: true,
    })
  })
  it('编辑区偏离全部源(无 WC):snapshot/关联文件载入亮,WC 灰(不存在);WriteCopy/Save 亮', () => {
    expect(computeButtonStates({ ...base, editorDict: B })).toEqual({
      canLoad: { snapshot: true, assoc: true, wc: false },
      canWriteCopy: true, canSave: true, canSaveAs: true,
    })
  })
  it('parse 失败:写出侧全灰;已存在的源载入全亮(逃生门)', () => {
    expect(computeButtonStates({ ...base, parseOk: false, editorDict: null, wcDict: B })).toEqual({
      canLoad: { snapshot: true, assoc: true, wc: true },
      canWriteCopy: false, canSave: false, canSaveAs: false,
    })
  })
  it('三源载入判据同构:编辑区≠源才亮 / ==源灰 / 源缺失灰 / parse 失败逃生亮', () => {
    const cases = [['snapshot', 'snapDict'], ['assoc', 'assocDict'], ['wc', 'wcDict']] as const
    for (const [kind, field] of cases) {
      const withSrc = { ...base, [field]: A }
      expect(computeButtonStates({ ...withSrc, editorDict: A }).canLoad[kind]).toBe(false)
      expect(computeButtonStates({ ...withSrc, editorDict: B }).canLoad[kind]).toBe(true)
      expect(computeButtonStates({ ...base, [field]: null }).canLoad[kind]).toBe(false)
      expect(computeButtonStates({ ...withSrc, parseOk: false, editorDict: null }).canLoad[kind]).toBe(true)
    }
  })
  it('canWriteCopy 三分支:无 WC 可点/编辑区==副本 灰/编辑区≠副本 亮', () => {
    expect(computeButtonStates(base).canWriteCopy).toBe(true)                       // 无 WC(空转创建)
    expect(computeButtonStates({ ...base, wcDict: A }).canWriteCopy).toBe(false)    // ==副本,无写入意义
    expect(computeButtonStates({ ...base, wcDict: B }).canWriteCopy).toBe(true)     // ≠副本
  })
  it('编辑区==副本但异于关联文件:Write Copy 灰,Save 亮,载入关联文件亮', () => {
    const s = computeButtonStates({ ...base, wcDict: A, assocDict: B })
    expect(s.canWriteCopy).toBe(false)
    expect(s.canSave).toBe(true)
    expect(s.canLoad.assoc).toBe(true)
    expect(s.canLoad.wc).toBe(false)
  })
  it('assocDict 未拉到(null):Save 灰', () => {
    expect(computeButtonStates({ ...base, assocDict: null }).canSave).toBe(false)
  })
  it('snapDict null(异常防御):snapshot 载入灰,不影响其它两源', () => {
    const s = computeButtonStates({ ...base, snapDict: null, editorDict: B, wcDict: A })
    expect(s.canLoad.snapshot).toBe(false)
    expect(s.canLoad.assoc).toBe(true)
    expect(s.canLoad.wc).toBe(true)
  })
  it('载入 WC 后(编辑区==WC):WriteCopy 与 WC 载入均灰,snapshot 载入仍亮', () => {
    const after = computeButtonStates({ ...base, editorDict: B, wcDict: B })
    expect(after.canWriteCopy).toBe(false)
    expect(after.canLoad.wc).toBe(false)
    expect(after.canLoad.snapshot).toBe(true)   // 编辑区(=WC) ≠ snapshot,可回 snapshot/可对比
  })
})

describe('resolveAnchorKind', () => {
  it('无记忆(null) → off(默认不对比,沿用原 diff 开关默认关)', () => {
    expect(resolveAnchorKind(null, true)).toBe('off')
  })
  it('合法值原样恢复', () => {
    expect(resolveAnchorKind('off', false)).toBe('off')
    expect(resolveAnchorKind('snapshot', false)).toBe('snapshot')
    expect(resolveAnchorKind('assoc', false)).toBe('assoc')
    expect(resolveAnchorKind('wc', true)).toBe('wc')
  })
  it('记忆为 wc 但当前无 WC → 回退 snapshot(不静默留在挂不上的基准)', () => {
    expect(resolveAnchorKind('wc', false)).toBe('snapshot')
  })
  it('非法值(手改 localStorage / 旧版本残留) → off', () => {
    expect(resolveAnchorKind('1', true)).toBe('off')
    expect(resolveAnchorKind('anchor', true)).toBe('off')
    expect(resolveAnchorKind('', true)).toBe('off')
  })
})

describe('normalizeSaveAsName', () => {
  it('补 .yaml 后缀', () => { expect(normalizeSaveAsName('exp_wide')).toBe('exp_wide.yaml') })
  it('已带 .yaml 保留', () => { expect(normalizeSaveAsName('exp-1.yaml')).toBe('exp-1.yaml') })
  it('非法字符/路径穿越 → null', () => {
    expect(normalizeSaveAsName('../evil')).toBeNull()
    expect(normalizeSaveAsName('a/b')).toBeNull()
    expect(normalizeSaveAsName('x.yml')).toBeNull()
    expect(normalizeSaveAsName('')).toBeNull()
  })
})

describe('resolveAssocFile', () => {
  const list = ['params.yaml', 'p2.yaml', 'exp_wide.yaml']
  it('persisted ∈ fileList → 用 persisted', () => {
    expect(resolveAssocFile(list, 'p2.yaml')).toBe('p2.yaml')
  })
  it('persisted ∉ fileList(文件被删/改名) → 回退 params.yaml', () => {
    expect(resolveAssocFile(list, 'gone.yaml')).toBe('params.yaml')
  })
  it('persisted 为 null(无记忆) → 回退 params.yaml', () => {
    expect(resolveAssocFile(list, null)).toBe('params.yaml')
  })
  it('自定义 fallback 生效', () => {
    expect(resolveAssocFile(list, 'gone.yaml', 'params.yaml')).toBe('params.yaml')
    expect(resolveAssocFile(list, null, 'p2.yaml')).toBe('p2.yaml')
  })
})
