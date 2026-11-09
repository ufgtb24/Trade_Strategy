// 直达链接的格式:解析三种链接(股票 + 日期、落在 compare 的股票 + 日期、样本编号)、认不出的写法、日期截到训练段末日、
// 图窗(含包住一段日期的),以及前端的训练段末日和后端同值。
import { describe, it, expect } from 'vitest'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { TRAIN_END, chartLinkWindow, parseLink, rangeLinkWindow } from '../src/annotate/directLinks'

describe('parseLink', () => {
  it('股票 + 日期:代码去空白、转大写,键的先后不限', () => {
    expect(parseLink('#symbol=aapl&date=2024-05-10')).toEqual({ kind: 'chart', symbol: 'AAPL', date: '2024-05-10' })
    expect(parseLink('#date=2024-05-10&symbol=%20MSFT%20')).toEqual({ kind: 'chart', symbol: 'MSFT', date: '2024-05-10' })
  })
  it('代码里的点、横线原样保留(要编码的字符按查询串解码)', () => {
    expect(parseLink('#symbol=BRK.B&date=2024-05-10')).toEqual({ kind: 'chart', symbol: 'BRK.B', date: '2024-05-10' })
    expect(parseLink('#symbol=%5EAA&date=2024-05-10')).toEqual({ kind: 'chart', symbol: '^AA', date: '2024-05-10' })
  })
  it('落在 compare 的股票 + 日期:pattern 名按查询串解码(中文、空格、加号)、去首尾空白,键的先后不限', () => {
    expect(parseLink('#symbol=crnc&date=2024-10-31&pattern=new_step&mode=compare'))
      .toEqual({ kind: 'compare', symbol: 'CRNC', date: '2024-10-31', pattern: 'new_step' })
    expect(parseLink('#mode=compare&pattern=%E5%B9%B3%E5%8F%B0%20%E7%AA%81%E7%A0%B4&date=2024-10-31&symbol=CRNC'))
      .toEqual({ kind: 'compare', symbol: 'CRNC', date: '2024-10-31', pattern: '平台 突破' })
    expect(parseLink('#symbol=CRNC&date=2024-10-31&pattern=+W%E5%BA%95+&mode=compare'))
      .toEqual({ kind: 'compare', symbol: 'CRNC', date: '2024-10-31', pattern: 'W底' })
    // 会话侧按 urllib 的 quote 编码的写法(path2_web/annotation/revision.py)
    expect(parseLink('#symbol=CRNC&date=2024-10-31&pattern=a%26b%3Dc&mode=compare'))
      .toEqual({ kind: 'compare', symbol: 'CRNC', date: '2024-10-31', pattern: 'a&b=c' })
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
                     '#symbol=AAPL&date=2024-05-10&x=1', '#whatever',
                     // 落在 compare 的写法:mode 只认 compare、pattern 不能为空、四个键缺一不可、键不能重复
                     '#symbol=AAPL&date=2024-05-10&pattern=p&mode=app', '#symbol=AAPL&date=2024-05-10&pattern=p&mode=',
                     '#symbol=AAPL&date=2024-05-10&pattern=%20&mode=compare', '#symbol=AAPL&date=2024-05-10&mode=compare',
                     '#symbol=AAPL&date=2024-05-10&pattern=p', '#symbol=AAPL&date=2024-02-30&pattern=p&mode=compare',
                     '#date=2024-05-10&pattern=p&mode=compare', '#symbol=AAPL&date=2024-05-10&pattern=p&mode=compare&x=1',
                     '#symbol=AAPL&date=2024-05-10&pattern=p&pattern=q&mode=compare']) {
      expect(parseLink(h), h).toEqual({ kind: 'bad', raw: h.slice(1) })
    }
  })
})

describe('chartLinkWindow', () => {
  it('那天往前约半年、往后约两个月(日历日)', () => {
    expect(chartLinkWindow('2024-05-10')).toEqual({ start: '2023-11-12', end: '2024-07-09' })
  })
  it('晚于训练段末日的先截到训练段末日', () => {
    expect(chartLinkWindow('2026-03-01')).toEqual(chartLinkWindow(TRAIN_END))
    expect(chartLinkWindow('2026-03-01')).toEqual({ start: '2025-07-04', end: '2026-03-01' })
  })
})

describe('rangeLinkWindow', () => {
  it('包住整段:起点那天往前约半年、终点那天往后约两个月', () => {
    expect(rangeLinkWindow('2024-05-10', '2024-08-01')).toEqual({ start: '2023-11-12', end: '2024-09-30' })
    expect(rangeLinkWindow('2024-05-10', '2024-05-10')).toEqual(chartLinkWindow('2024-05-10'))
  })
  it('终点晚于训练段末日的先截到训练段末日', () => {
    expect(rangeLinkWindow('2025-12-01', '2026-02-01').end).toBe(chartLinkWindow(TRAIN_END).end)
  })
})

describe('训练段末日', () => {
  it('和后端 path2_web/data.py 的 TRAIN_END 同值', () => {
    const py = readFileSync(resolve(__dirname, '../../path2_web/data.py'), 'utf8')
    expect(/^TRAIN_END = "([0-9-]+)"/m.exec(py)?.[1]).toBe(TRAIN_END)
  })
})
