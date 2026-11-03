// 大涨段清单的排序(symbol / date / rise,同值按 date、symbol 定序)与涨幅格式
import { describe, it, expect } from 'vitest'
import { formatRise, sortRally } from '../src/annotate/rallyList'
import type { RallyItem } from '../src/types'

const item = (symbol: string, date: string, rise: number): RallyItem => ({
  symbol, date, rise, rel: 2, peak_date: date, view_start: date, view_end: date,
})
const ITEMS = [item('MSFT', '2024-03-01', 0.5), item('AAPL', '2025-01-02', 1.2),
               item('ZZ', '2022-06-01', 0.5), item('AAPL', '2023-05-05', 0.8)]
const keys = (xs: RallyItem[]) => xs.map(x => `${x.symbol}@${x.date}`)

describe('sortRally', () => {
  it('按 rise:降序,同值按 date 升序', () => {
    expect(keys(sortRally(ITEMS, 'rise', true))).toEqual(
      ['AAPL@2025-01-02', 'AAPL@2023-05-05', 'ZZ@2022-06-01', 'MSFT@2024-03-01'])
  })
  it('按 symbol:升序,同股按 date', () => {
    expect(keys(sortRally(ITEMS, 'symbol', false))).toEqual(
      ['AAPL@2023-05-05', 'AAPL@2025-01-02', 'MSFT@2024-03-01', 'ZZ@2022-06-01'])
  })
  it('按 date:降序;不改原数组', () => {
    const before = keys(ITEMS)
    expect(keys(sortRally(ITEMS, 'date', true))).toEqual(
      ['AAPL@2025-01-02', 'MSFT@2024-03-01', 'AAPL@2023-05-05', 'ZZ@2022-06-01'])
    expect(keys(ITEMS)).toEqual(before)
  })
})

describe('formatRise', () => {
  it('带符号的百分数,一位小数', () => {
    expect(formatRise(0.4567)).toBe('+45.7%')
    expect(formatRise(3.0717)).toBe('+307.2%')
    expect(formatRise(-0.05)).toBe('-5.0%')
  })
})
