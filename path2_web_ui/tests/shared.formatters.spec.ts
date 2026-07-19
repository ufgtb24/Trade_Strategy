import { describe, it, expect } from 'vitest'
import { fmt, fmtValue } from '../src/shared/formatters'

describe('fmt · kind-aware', () => {
    it('gap kind 加 gap= 前缀', () => {
        expect(fmt(13, 'gap')).toBe('gap=13')
    })
    it('anchor_delta 显示 Δanchor=', () => {
        expect(fmt(0.234, 'anchor_delta')).toBe('Δanchor=0.234')
    })
    it('strict_clear 显示 strict候选=', () => {
        expect(fmt(2, 'strict_clear')).toBe('strict候选=2')
    })
    it('硬伤 E · window_offset 显示 起点偏移=(Containment/Overlap/Equals)', () => {
        expect(fmt(3, 'window_offset')).toBe('起点偏移=3')
    })
    it('硬伤 E · unknown 兜底显示 ?(_make_measured 未识别的 edge kind)', () => {
        expect(fmt(null, 'unknown')).toBe('?')
    })
    it('未知 kind 直接 String(val)', () => {
        expect(fmt('foo', 'unknown_kind')).toBe('foo')
    })
})

describe('fmtValue · 数组分支(硬伤 D)', () => {
    it('数组展开显示', () => {
        expect(fmtValue([1, 2, 3])).toBe('[1.000, 2.000, 3.000]')
    })
    it('嵌套数组递归', () => {
        expect(fmtValue([[1, 2], [3]])).toBe('[[1.000, 2.000], [3.000]]')
    })
    it('数字 3 位小数', () => {
        expect(fmtValue(1.23456)).toBe('1.235')
    })
    it('字符串原样', () => {
        expect(fmtValue('abc')).toBe('abc')
    })
})
