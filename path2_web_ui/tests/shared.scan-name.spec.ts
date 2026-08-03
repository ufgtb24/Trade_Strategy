import { describe, it, expect } from 'vitest'
import { validateScanName } from '../src/shared/scanName'

describe('validateScanName', () => {
  it('空串/纯空格合法(= 默认时间戳命名)', () => {
    expect(validateScanName('')).toBeNull()
    expect(validateScanName('   ')).toBeNull()
  })
  it('合法:中文/字母/数字/下划线/连字符', () => {
    expect(validateScanName('tb深度28-38')).toBeNull()
    expect(validateScanName('exp_1')).toBeNull()
    expect(validateScanName('20260729T153147')).toBeNull()   // 默认时间戳名也满足
  })
  it('非法:含 / . 空格 等(防路径穿越)', () => {
    expect(validateScanName('bad/name')).not.toBeNull()
    expect(validateScanName('a.b')).not.toBeNull()
    expect(validateScanName('a b')).not.toBeNull()
  })
})
