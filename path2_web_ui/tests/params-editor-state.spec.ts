// 按钮 enable 矩阵纯函数(解耦 spec §3.1):Write Copy=无 WC 可点(空转创建)/有 WC 且编辑区≠副本;
// Reset=偏离锚或 parse 失败(逃生门);Save=异于关联文件;SaveAs=parse OK;
// Load Assoc=异于关联文件(或 parse 失败逃生)——切下拉不载入编辑区,载入走独立 Load 按钮。monaco 无关,纯 dict 判定。
import { describe, it, expect } from 'vitest'
import { dictsEqual, computeButtonStates, normalizeSaveAsName, resolveAssocFile } from '../src/components/paramsEditorState'

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
  const base = { parseOk: true, editorDict: A, assocDict: A, anchorDict: A, wcDict: null }
  it('全一致(无 WC):Write Copy(空转创建,决策3)与 SaveAs 可点', () => {
    expect(computeButtonStates(base)).toEqual(
      { canWriteCopy: true, canReset: false, canSave: false, canSaveAs: true, canLoadWc: false, canLoadAssoc: false })
  })
  it('编辑区偏离全部锚(无 WC):WriteCopy/Reset/Save 均亮', () => {
    expect(computeButtonStates({ ...base, editorDict: B })).toEqual(
      { canWriteCopy: true, canReset: true, canSave: true, canSaveAs: true, canLoadWc: false, canLoadAssoc: true })
  })
  it('parse 失败:Write Copy 灰;Reset 可点(逃生门),有 WC 时载入副本同理', () => {
    expect(computeButtonStates({ ...base, parseOk: false, editorDict: null })).toEqual(
      { canWriteCopy: false, canReset: true, canSave: false, canSaveAs: false, canLoadWc: false, canLoadAssoc: true })
    expect(computeButtonStates({ ...base, parseOk: false, editorDict: null, wcDict: B }).canLoadWc).toBe(true)
  })
  it('canWriteCopy 三分支:无 WC 可点/编辑区==副本 灰/编辑区≠副本 亮', () => {
    expect(computeButtonStates(base).canWriteCopy).toBe(true)                       // 无 WC(空转创建)
    expect(computeButtonStates({ ...base, wcDict: A }).canWriteCopy).toBe(false)    // ==副本,无写入意义
    expect(computeButtonStates({ ...base, wcDict: B }).canWriteCopy).toBe(true)     // ≠副本
  })
  it('编辑区==副本但异于关联文件:Write Copy 灰,Save 亮', () => {
    expect(computeButtonStates({ ...base, wcDict: A, assocDict: B }).canWriteCopy).toBe(false)
    expect(computeButtonStates({ ...base, wcDict: A, assocDict: B }).canSave).toBe(true)
  })
  it('assocDict 未拉到(null):Save 灰', () => {
    expect(computeButtonStates({ ...base, assocDict: null }).canSave).toBe(false)
  })
  it('anchorDict null(异常防御):Reset 灰(parse OK 时)', () => {
    expect(computeButtonStates({ ...base, anchorDict: null }).canReset).toBe(false)
  })
  it('载入副本(D7):编辑区≠WC 才亮;载入后编辑区==WC → WriteCopy/载入均灰', () => {
    expect(computeButtonStates({ ...base, wcDict: B }).canLoadWc).toBe(true)     // 编辑区 A ≠ WC B
    expect(computeButtonStates({ ...base, wcDict: A }).canLoadWc).toBe(false)    // 已一致,无需载入
    const after = computeButtonStates({ ...base, editorDict: B, wcDict: B })
    expect(after.canWriteCopy).toBe(false)
    expect(after.canLoadWc).toBe(false)
    expect(after.canReset).toBe(true)    // 编辑区(=WC) ≠ 锚 A,可回锚/可对比
  })
  it('载入关联文件:编辑区≠关联文件 亮;==关联文件/assocDict null 灰;parse 失败逃生亮', () => {
    expect(computeButtonStates({ ...base, editorDict: B }).canLoadAssoc).toBe(true)    // 编辑区 B ≠ 关联 A
    expect(computeButtonStates(base).canLoadAssoc).toBe(false)                         // 编辑区==关联文件
    expect(computeButtonStates({ ...base, assocDict: null }).canLoadAssoc).toBe(false) // 关联文件未拉到
    expect(computeButtonStates({ ...base, parseOk: false, editorDict: null }).canLoadAssoc).toBe(true) // parse 失败逃生
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
