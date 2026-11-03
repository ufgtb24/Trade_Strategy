// 直达链接的格式:解析两种链接、认不出的写法、日期截到训练段末日、图窗,以及前端的训练段末日和后端同值。
import { describe, it, expect } from 'vitest'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { TRAIN_END, chartLinkWindow, parseLink } from '../src/annotate/directLinks'

describe('parseLink', () => {
  it('股票 + 日期:代码去空白、转大写,键的先后不限', () => {
    expect(parseLink('#symbol=aapl&date=2024-05-10')).toEqual({ kind: 'chart', symbol: 'AAPL', date: '2024-05-10' })
    expect(parseLink('#date=2024-05-10&symbol=%20MSFT%20')).toEqual({ kind: 'chart', symbol: 'MSFT', date: '2024-05-10' })
  })
  it('代码里的点、横线原样保留(要编码的字符按查询串解码)', () => {
    expect(parseLink('#symbol=BRK.B&date=2024-05-10')).toEqual({ kind: 'chart', symbol: 'BRK.B', date: '2024-05-10' })
    expect(parseLink('#symbol=%5EAA&date=2024-05-10')).toEqual({ kind: 'chart', symbol: '^AA', date: '2024-05-10' })
  })
  it('样本编号原样', () => {
    expect(parseLink('#sample=s-pc-12')).toEqual({ kind: 'sample', id: 's-pc-12' })
  })
  it('没有 # 部分 → 不是链接', () => {
    expect(parseLink('')).toBeNull()
    expect(parseLink('#')).toBeNull()
  })
  it('认不出的写法 → bad,带原文', () => {
    for (const h of ['#symbol=AAPL', '#date=2024-05-10', '#symbol=AAPL&date=2024-13-01', '#symbol=AAPL&date=2024-02-30',
                     '#symbol=AAPL&date=20240510', '#symbol=&date=2024-05-10', '#sample=', '#sample=a&symbol=b',
                     '#symbol=AAPL&date=2024-05-10&x=1', '#whatever']) {
      expect(parseLink(h), h).toEqual({ kind: 'bad', raw: h.slice(1) })
    }
  })
})

describe('chartLinkWindow', () => {
  it('那天往前约半年、往后约两个月(日历日)', () => {
    expect(chartLinkWindow('2024-05-10')).toEqual({ date: '2024-05-10', window: { start: '2023-11-12', end: '2024-07-09' } })
  })
  it('晚于训练段末日的截到训练段末日', () => {
    expect(chartLinkWindow('2026-03-01')).toEqual({ date: TRAIN_END, window: { start: '2025-07-04', end: '2026-03-01' } })
    expect(chartLinkWindow(TRAIN_END).date).toBe(TRAIN_END)
  })
})

describe('训练段末日', () => {
  it('和后端 path2_web/data.py 的 TRAIN_END 同值', () => {
    const py = readFileSync(resolve(__dirname, '../../path2_web/data.py'), 'utf8')
    expect(/^TRAIN_END = "([0-9-]+)"/m.exec(py)?.[1]).toBe(TRAIN_END)
  })
})
