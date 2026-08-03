// WorkingCopyDrawer 的非编辑器逻辑:yaml⇄dict 纯函数(本文件)+ 按钮 enable 矩阵
// (tests/params-editor-state.spec.ts)。monaco 在 jsdom 不可用,不 mount 组件本身。
import { describe, it, expect } from 'vitest'
import { dictToYamlText, yamlTextToDict } from '../src/components/workingCopyYaml'

describe('workingCopyYaml 纯函数', () => {
  it('dict → yaml → dict 往返', () => {
    const d = { bo: { total_window: 42, peak_measure: 'high' } }
    const text = dictToYamlText(d)
    expect(text).toContain('total_window: 42')
    expect(yamlTextToDict(text)).toEqual(d)
  })
  it('非法 yaml → 抛错(保存按钮禁用判据)', () => {
    expect(() => yamlTextToDict('bo: [unclosed')).toThrow()
  })
})
