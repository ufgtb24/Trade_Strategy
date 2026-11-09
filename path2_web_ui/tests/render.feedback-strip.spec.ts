// compare 的反馈(spec 6.13「三种对象落成一段日期」「图上」):hits 行数据带的范围字段、族那一行的透明命中区、
// 反馈带的几何 / 错行 / 配色 / 悬停文字;app 模式(不传 feedback)副图与原来逐项相同。
import { describe, it, expect } from 'vitest'
import { buildSubOption, computeEventData, makeRenderBracketLine, makeRenderFeedbackMark } from '../src/render/chart'
import { computeSubGeometry, BAND_LANE_H, BAND_BOT_PAD, DIVIDER_GAP, FEEDBACK_ROW_H, USER_APP_GAP } from '../src/render/subGeometry'
import {
  FEEDBACK_SERIES, FEEDBACK_TONE, dateSpanToIdx, feedbackLabelFits, feedbackMarks, feedbackRowCount, feedbackTip,
  feedbackTone,
} from '../src/render/feedbackStrip'
import type { EventDict, HitDict } from '../src/types'
import type { AnnFeedback } from '../src/annotate/model'

const bars = Array.from({ length: 12 }, (_, i) =>
  ({ date: `2025-01-${String(i + 2).padStart(2, '0')}`, o: 1, h: 1, l: 1, c: 1, v: 1, rv: 1 }))
const DATES = bars.map(b => b.date)

const ev = (node: string, s: number, e: number, idx = 0, child_refs: Record<string, string[]> = {}): EventDict =>
  ({ instance_id: `${node}_${s}_${e}#${idx}`, node_id: node, instance_idx: idx, start_idx: s, end_idx: e, child_refs })
// 买点 node = plateau.today。族 hits@0:h4 买 4、h6 买 5~6;h8 的终点在 8、买点在 7(格那一列没有 ▼)。族 hits@9:h10 没有买点
const T4 = ev('today', 4, 4), T6 = ev('today', 5, 6), T7 = ev('today', 7, 7)
const P4 = ev('plateau', 0, 4, 0, { today: [T4.instance_id] })
const P6 = ev('plateau', 0, 6, 0, { today: [T6.instance_id] })
const P8 = ev('plateau', 0, 8, 0, { today: [T7.instance_id] })
const P10 = ev('plateau', 9, 10, 0, {})
const hit = (id: string, p: EventDict): HitDict =>
  ({ hit_id: id, start_idx: p.start_idx, end_idx: p.end_idx, node_index: { plateau: p.instance_id }, children: [] })
const EVENTS = [T4, T6, T7, P4, P6, P8, P10]
const HITS = [hit('h4', P4), hit('h6', P6), hit('h8', P8), hit('h10', P10)]

function input(extra: any = {}): any {
  return {
    topology: { nodes: [{ node_id: 'plateau', where_rules: [] }, { node_id: 'today', where_rules: [] }], edges: [] },
    isolatedNodeIds: new Set(), tagList: [], level: 'detected', nodeColors: {},
    eventTier: () => 'in_hit', nodeOfEventByBand: (e: EventDict) => e.node_id, bandKeyOf: (e: EventDict) => e.node_id,
    tagToNodes: {}, endNode: 'plateau.today', ...extra,
  }
}

const fb = (id: string, start: string, end: string, extra: Partial<AnnFeedback> = {}): AnnFeedback => ({
  id, pattern: 'p', app_id: 'app1', app_ver: 'v0', start, end, target: 'range', source: 'picked', answer: 'neg',
  note: 'x', ...extra })

describe('hits 行数据带的范围字段(K 线下标)', () => {
  const b = computeEventData(bars as any, EVENTS, HITS, input())

  it('族那一行:族起点与这一族全部买入日;没有买点的族 buy_days 为空', () => {
    expect(b.bracketLineData.map((d: any) => [d.family_key, d.family_start, d.buy_days]))
      .toEqual([['hits@0', 0, [4, 5, 6, 7]], ['hits@9', 9, []]])
  })

  it('▼:buy_day / buy_date / family_start', () => {
    const buys = b.bracketData.filter((d: any) => d.kind === 'buy')
    expect(buys.map((d: any) => [d.buy_day, d.buy_date, d.family_start]))
      .toEqual([[4, DATES[4], 0], [5, DATES[5], 0], [6, DATES[6], 0], [7, DATES[7], 0]])
  })

  it('格:那一列(同一行)有 ▼ 才带 buy_day;都带 family_start', () => {
    const marks = b.bracketData.filter((d: any) => d.kind === 'mark')
    expect(marks.map((d: any) => [d.value[0], d.buy_day, d.family_start]))
      .toEqual([[4, 4, 0], [6, 6, 0], [8, undefined, 0], [10, undefined, 9]])
  })
})

describe('computeSubGeometry · 反馈带', () => {
  it('反馈行加在 hit 行下面:每行固定 14px、不乘缩放,计入 hits 区高度;band 整体顺移', () => {
    for (const z of [1, 2]) {
      const base = computeSubGeometry({ bracketLaneCount: 2, bandLaneCounts: [1], userContentBottom: 30 }, z)
      const g = computeSubGeometry({ bracketLaneCount: 2, bandLaneCounts: [1], userContentBottom: 30,
                                     feedbackRowCount: 3 }, z)
      expect(g.feedbackTop).toBe(g.appBracketTop + 2 * BAND_LANE_H * z)
      expect(g.bracketH).toBe(g.feedbackTop + 3 * FEEDBACK_ROW_H + BAND_BOT_PAD)
      expect(g.bracketH - base.bracketH).toBe(3 * FEEDBACK_ROW_H)
      expect(g.bandGeom[0].top).toBe(g.bracketH + DIVIDER_GAP)
      expect(g.bandGeom[0].top - base.bandGeom[0].top).toBe(3 * FEEDBACK_ROW_H)
      // 分界线(上下对称)不受影响
      expect(g.userAppEdges).toEqual(base.userAppEdges)
      expect(g.appBracketTop).toBe(30 + 2 * USER_APP_GAP)
    }
  })

  it('不传 feedbackRowCount 与传 0 逐项相同;只有反馈没有 hit 时 hits 区照样有高度', () => {
    const a = computeSubGeometry({ bracketLaneCount: 1, bandLaneCounts: [2] })
    expect(computeSubGeometry({ bracketLaneCount: 1, bandLaneCounts: [2], feedbackRowCount: 0 })).toEqual(a)
    const only = computeSubGeometry({ bracketLaneCount: 0, bandLaneCounts: [1], feedbackRowCount: 1 })
    expect(only.bracketH).toBe(only.feedbackTop + FEEDBACK_ROW_H + BAND_BOT_PAD)
  })
})

describe('buildSubOption · 只在 compare 生成族命中区与反馈带', () => {
  const b = computeEventData(bars as any, EVENTS, HITS, input())
  const geom = computeSubGeometry({ bracketLaneCount: 2, bandLaneCounts: [], feedbackRowCount: 1 })
  const api = { value: (i: number) => [0, 8, 0, 1][i] ?? 0, coord: ([x]: number[]) => [x * 10, 0], size: () => [10, 0] }

  it('app 模式(不传 feedback):族底线整层不响应鼠标、没有反馈带系列', () => {
    const sub: any = buildSubOption(bars as any, b, geom, input(), 800)
    const lines = sub.series.find((s: any) => s.name === 'bracket-lines')
    expect(lines.silent).toBe(true)
    expect(sub.series.some((s: any) => s.name === FEEDBACK_SERIES)).toBe(false)
    const g = lines.renderItem({ dataIndex: 0 }, api)
    expect(g.silent).toBe(true)
    expect(g.children.some((c: any) => c.style.fill === 'rgba(0,0,0,0.001)')).toBe(false)
  })

  it('compare:有买点的族垫一整行高的透明命中区(在格与 ▼ 下面),线不响应鼠标;没有买点的族不垫', () => {
    const marks = feedbackMarks([fb('f-pc-1', DATES[4], DATES[6])], DATES, {}, null)
    const sub: any = buildSubOption(bars as any, b, geom, input({ feedback: { marks, tip: () => 'tip' } }), 800)
    const zOf = (n: string) => sub.series.find((s: any) => s.name === n).z
    const lines = sub.series.find((s: any) => s.name === 'bracket-lines')
    expect(lines.silent).toBe(false)
    expect(zOf('bracket-lines')).toBeLessThan(zOf('brackets'))
    const g = lines.renderItem({ dataIndex: 0 }, api)
    expect(g.silent).toBeUndefined()
    const [area, ...rest] = g.children
    expect(area.style.fill).toBe('rgba(0,0,0,0.001)')
    expect(area.silent).toBeUndefined()
    expect(area.shape.height).toBe(BAND_LANE_H)
    expect(rest.every((c: any) => c.silent === true)).toBe(true)
    const none = lines.renderItem({ dataIndex: 1 }, api)
    expect(none.silent).toBe(true)
    // 反馈带系列:每条一项,带编号;悬停文字走 tip
    const strip = sub.series.find((s: any) => s.name === FEEDBACK_SERIES)
    expect(strip.data).toEqual([{ value: [4, 6, 0], feedback_id: 'f-pc-1' }])
    expect(strip.tooltip.formatter({ dataIndex: 0 })).toBe('tip')
  })

  it('makeRenderBracketLine 不传 clickable 时与原来一样', () => {
    const g = makeRenderBracketLine([{ multi: true, active: false, buy_days: [1] }])({ dataIndex: 0 }, api) as any
    expect(g.silent).toBe(true)
    expect(g.children).toHaveLength(2)
  })
})

describe('反馈带的记号', () => {
  it('日期 → K 线下标:起点取当天或之后第一根、终点取当天或之前最后一根;整段落在 K 线外为 null', () => {
    expect(dateSpanToIdx(DATES, DATES[2], DATES[5])).toEqual([2, 5])
    expect(dateSpanToIdx(DATES, '2025-01-01', '2025-01-05')).toEqual([0, 3])
    expect(dateSpanToIdx(DATES, '2026-01-01', '2026-01-02')).toBeNull()
    expect(dateSpanToIdx(DATES, '2024-01-01', '2024-12-31')).toBeNull()
  })

  it('只画用户挑的;范围交叠的错行;配色档照 red / status;选中的那条标出', () => {
    const list = [
      fb('a', DATES[1], DATES[4]), fb('b', DATES[3], DATES[6]), fb('c', DATES[5], DATES[8]),
      fb('blind', DATES[1], DATES[2], { source: 'random', answer: 'pos' }),
    ]
    const st = { a: { status: 'matched', tag: null, red: true, reason: null },
                 b: { status: 'lost', tag: null, red: false, reason: null } } as any
    const marks = feedbackMarks(list, DATES, st, 'c')
    expect(marks.map(m => [m.id, m.start, m.end, m.lane, m.tone, m.selected]))
      .toEqual([['a', 1, 4, 0, 'red', false], ['b', 3, 6, 1, 'lost', false], ['c', 5, 8, 0, 'plain', true]])
    expect(feedbackRowCount(marks)).toBe(2)
    expect(feedbackRowCount([])).toBe(0)
    expect(feedbackTone(undefined)).toBe('plain')
    expect(feedbackTone({ status: 'unmatched', tag: 'for_tuning', red: false, reason: null })).toBe('plain')
  })

  it('画法:行高固定;朱红底 / 橙描边 / 常色深灰描边,字一律黑;选中描边加粗;放得下才写字', () => {
    const api = { coord: ([x]: number[]) => [x * 10, 0], size: () => [10, 0] }
    const marks = [
      { id: 'a', start: 0, end: 9, lane: 1, label: 'off_pattern', tone: 'red', selected: true },
      { id: 'b', start: 2, end: 2, lane: 0, label: 'neg', tone: 'lost', selected: false },
      { id: 'c', start: 3, end: 6, lane: 0, label: 'neg', tone: 'plain', selected: false },
    ] as const
    const render = makeRenderFeedbackMark(marks as any, 50)
    const [a, b2, c] = [0, 1, 2].map(i => render({ dataIndex: i }, api) as any)
    expect(a.children[0].shape.y).toBe(50 + FEEDBACK_ROW_H + 1.5)
    expect(a.children[0].style.fill).toBe(FEEDBACK_TONE.red.fill)
    expect(a.children[0].style.lineWidth).toBe(3)
    expect(a.children[1].style.text).toBe('off_pattern')
    expect(a.children[1].style.fill).toBe('#000000')
    expect(b2.children[0].style).toMatchObject({ fill: '#ffffff', stroke: '#E69F00', lineWidth: 1.5 })
    expect(b2.children).toHaveLength(1)                       // 一根 K 线宽放不下 neg:只画记号
    expect(c.children[0].style).toMatchObject({ fill: '#ffffff', stroke: '#555555' })
    expect(c.children[1].style.text).toBe('neg')
    expect(feedbackLabelFits('off_pattern', 40)).toBe(false)
  })

  it('悬停写全:答案、理由(转义)、分段(拓扑里没有的原样)、状态、原因标签、pos sample inside;不提旧版本 / 过期', () => {
    const f = fb('f-pc-1', DATES[1], DATES[4], { target: 'family', family_start: DATES[0], answer: 'off_pattern',
                                              note: 'a<b & "c"', segments: ['plateau', 'gone_node'] })
    const html = feedbackTip(f, { status: 'matched', tag: 'for_tuning', red: true, reason: null }, true)
    for (const s of ['answer: off_pattern', 'segments: plateau, gone_node', 'status: matched', 'tag: for_tuning',
                     'pos sample inside', `family_start: ${DATES[0]}`, 'a&lt;b &amp; &quot;c&quot;']) {
      expect(html).toContain(s)
    }
    expect(html).not.toMatch(/stale|outdated|old version|过期|旧版/)
    const bare = feedbackTip(fb('x', DATES[1], DATES[1], { note: undefined }), undefined, false)
    expect(bare).toContain('status: null')
    expect(bare).toContain(`range: ${DATES[1]}<br/>`)
    expect(bare).not.toContain('pos sample inside')
    expect(bare).not.toContain('note:')
  })
})
