import { describe, it, expect } from 'vitest'
import {
  resolveAssocFile,
  resolveParamSource,
  restoreSelectedPatterns,
} from '../src/components/paramsEditorState'

describe('restoreSelectedPatterns', () => {
  const all = ['a', 'b', 'c']
  it('null stored → null(调用方走 selectAll)', () => {
    expect(restoreSelectedPatterns(null, all)).toBeNull()
  })
  it('空串 stored → null', () => {
    expect(restoreSelectedPatterns('', all)).toBeNull()
  })
  it('非法 JSON → null', () => {
    expect(restoreSelectedPatterns('not json', all)).toBeNull()
    expect(restoreSelectedPatterns('{bad', all)).toBeNull()
  })
  it('非数组 JSON → null', () => {
    expect(restoreSelectedPatterns('"abc"', all)).toBeNull()
    expect(restoreSelectedPatterns('{"a":1}', all)).toBeNull()
  })
  it('部分 pid 已删 → 剔除后返回剩余', () => {
    expect(restoreSelectedPatterns('["a","x","c"]', all)).toEqual(['a', 'c'])
  })
  it('全部 pid 已删 → null(回全选,不返回空数组)', () => {
    expect(restoreSelectedPatterns('["x","y"]', all)).toBeNull()
  })
  it('显式空数组 → null(避免 Start 按钮灰着打开)', () => {
    expect(restoreSelectedPatterns('[]', all)).toBeNull()
  })
  it('全量合法 → 全量恢复', () => {
    expect(restoreSelectedPatterns('["a","b","c"]', all)).toEqual(['a', 'b', 'c'])
  })
  it('数组含非 string 元素 → 剔除', () => {
    expect(restoreSelectedPatterns('["a", 1, true, "b"]', all)).toEqual(['a', 'b'])
  })
})

describe('resolveParamSource', () => {
  const files = ['params.yaml', 'tuned.yaml']
  it('persisted="wc" + 有 WC → "wc"', () => {
    expect(resolveParamSource('wc', files, true)).toBe('wc')
  })
  it('persisted="wc" + 无 WC → params.yaml(WC 被清)', () => {
    expect(resolveParamSource('wc', files, false)).toBe('params.yaml')
  })
  it('persisted=具名 + 在列表 → 该文件', () => {
    expect(resolveParamSource('tuned.yaml', files, false)).toBe('tuned.yaml')
  })
  it('persisted=具名 + 不在列表(被删/改名) → params.yaml', () => {
    expect(resolveParamSource('gone.yaml', files, false)).toBe('params.yaml')
  })
  it('persisted=null(首次) → params.yaml(用户确认的统一默认)', () => {
    expect(resolveParamSource(null, files, false)).toBe('params.yaml')
  })
  it('persisted=null + 有 WC → 仍 params.yaml(首次统一,放弃 WC 动线)', () => {
    expect(resolveParamSource(null, files, true)).toBe('params.yaml')
  })
  it('persisted=垃圾字符串 → params.yaml', () => {
    expect(resolveParamSource('garbage', files, false)).toBe('params.yaml')
  })
  it('自定义 fallback 受尊重', () => {
    expect(resolveParamSource('gone.yaml', files, false, 'custom.yaml')).toBe('custom.yaml')
  })
})

describe('resolveAssocFile(顺带覆盖)', () => {
  const files = ['params.yaml', 'tuned.yaml']
  it('persisted 在列表 → 用', () => {
    expect(resolveAssocFile(files, 'tuned.yaml')).toBe('tuned.yaml')
  })
  it('persisted 不在列表 → fallback', () => {
    expect(resolveAssocFile(files, 'gone.yaml')).toBe('params.yaml')
  })
  it('persisted=null → fallback', () => {
    expect(resolveAssocFile(files, null)).toBe('params.yaml')
  })
})
