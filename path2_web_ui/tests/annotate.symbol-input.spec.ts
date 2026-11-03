// 顶栏 symbol 输入的解析:去空白、转大写、对股票列表核一遍
import { describe, it, expect } from 'vitest'
import { resolveSymbolInput } from '../src/annotate/symbolInput'

const LIST = new Set(['AAPL', 'BRK-B', 'MSFT'])

describe('resolveSymbolInput', () => {
  it('空白 → empty', () => {
    expect(resolveSymbolInput('   ', LIST)).toEqual({ kind: 'empty' })
  })
  it('列表里有 → ok,去空白、转大写', () => {
    expect(resolveSymbolInput(' aapl ', LIST)).toEqual({ kind: 'ok', symbol: 'AAPL' })
    expect(resolveSymbolInput('brk-b', LIST)).toEqual({ kind: 'ok', symbol: 'BRK-B' })
  })
  it('列表里没有(如 2026 年才上市的)→ not_found', () => {
    expect(resolveSymbolInput('NEW26', LIST)).toEqual({ kind: 'not_found', symbol: 'NEW26' })
    expect(resolveSymbolInput('../x', LIST)).toEqual({ kind: 'not_found', symbol: '../X' })
  })
  it('列表没拿到 → 不拦,交给后端判', () => {
    expect(resolveSymbolInput('NEW26', null)).toEqual({ kind: 'ok', symbol: 'NEW26' })
  })
})
