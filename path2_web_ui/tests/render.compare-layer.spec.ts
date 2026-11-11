// compare 的标注层(render/annotateLanes.ts 的 annotateLayer + LaneDraw.compare)与合进主视图副图的几样东西:
// 轨标题的 ⇣ node / unmapped、组的竖线、bracket 的 user 行与 ▲ 字母后的 ✓ / ✗、框右端的 missing、
// 主视图副图 band 表头带用户特征名与 app_only、hit 行让出 user 行。
//
// 规格变更(spec 5.8,2026-11-05),不是放宽:实施票 11 的旧测试(tests/render.compare-overlay.spec.ts,已删)断言
// 「compare 只把 event 叠到用户框所在的轨上、图上没有任何对照 tag 的字样」。spec 5.8 改为 compare = 主视图那张副图 +
// 标注层,并把 ⇣ node、unmapped、✓ / ✗、missing 提前到第一段显示,所以那条断言换成下面「只出这几样、不出别的」的检查:
// 第二段的 link tag、diff tag、chance_high 与档位小字(detected_only / qualified_only)仍一个都不许出现。
import { describe, it, expect } from 'vitest'
import {
  COMPARE_BRACKET_ROW_H, INK, LANE_PAD, UNMAPPED_EDGE, VERMILION, annotateLayer, bracketGeometry,
  buildAnnotateSubOption,
  bracketContentBottom, bracketPick, bracketRects, laneGeometry, packBrackets, type BracketItem, type CompareMarks,
} from '../src/render/annotateLanes'
import { buildSubDecorGraphics, buildSubOption, computeEventData, makeRenderBracket } from '../src/render/chart'
import {
  computeSubGeometry, BAND_TOP_PAD, BAND_LANE_H, HITS_FILL, USER_APP_EDGE_COLOR, USER_APP_EDGE_H, USER_APP_GAP,
} from '../src/render/subGeometry'
import { buyDaysOf } from '../src/render/fold'
import type { Lane } from '../src/annotate/model'
import type { EventDict, HitDict } from '../src/types'

const DATES = Array.from({ length: 12 }, (_, i) => `2025-01-${String(i + 2).padStart(2, '0')}`)
const BARS = DATES.map(date => ({ date } as any))
const box = (id: string, feature: string | null, start: string, end: string) => ({ id, feature, start, end })
const LANES: Lane[] = [
  { key: 'w-a', parent: null, rows: 1, boxes: [{ box: box('b1', 'w-a', DATES[1], DATES[4]), row: 0 }] },
  { key: 'w-b', parent: null, rows: 1, boxes: [{ box: box('b2', 'w-b', DATES[6], DATES[7]), row: 0 }] },
  { key: null, parent: null, rows: 1, boxes: [{ box: box('b3', null, DATES[0], DATES[0]), row: 0 }] },
]
const NAMES: Record<string, string> = { 'w-a': '站上新平台', 'w-b': '底部平稳' }
const nameOf = (f: string | null) => (f ? NAMES[f] ?? f : null)

const items: BracketItem[] = [
  { id: 's1', start: DATES[1], end: DATES[4], pos: true, letter: 'a', faded: false, emphasis: 0,
    mark: { sign: '✓', tip: 'matched · buy +0' } },
  { id: 's2', start: DATES[1], end: DATES[6], pos: false, letter: 'b', faded: false, emphasis: 0,
    mark: { sign: '✗', tip: 'matched · buy -1' } },
]
const CMP: CompareMarks = {
  laneNode: new Map([[0, 'plateau']]), unmapped: new Set([1]),
  userActive: false,
}

function layer(cmp: CompareMarks | null) {
  const bg = bracketGeometry(1)
  const { geom } = laneGeometry(LANES, bg.top + bg.h)
  return annotateLayer(BARS, {
    lanes: LANES, geom, nameOf, selectedId: null, preview: null, draft: null, zoom: null, width: 800,
    bracket: { geom: bg, placed: packBrackets(items, DATES).placed }, compare: cmp,
  })
}
const texts = (l: { graphics: any[] }) => l.graphics.filter(g => g.type === 'text').map(g => g.style.text as string)
const api = (row: any[]) => ({ size: () => [10], coord: ([i]: number[]) => [i * 10 + 5], value: (k: number) => row[k] })

describe('compare 的标注层', () => {
  it('map 了的轨标题在特征名后写 ⇣ node;没 map 的挂 unmapped(白底中蓝描边黑字);unnamed 轨不挂', () => {
    const l = layer(CMP)
    const t = texts(l)
    expect(t[0]).toBe('user')
    expect(t[1]).toBe('{biz|站上新平台}{node|  ⇣ plateau}')
    expect(t[2]).toBe('{biz|底部平稳}{node|  }{tag|unmapped}')
    expect(t[3]).toBe('{sym|unnamed}')
    const g = l.graphics.find(x => x.type === 'text' && x.style.text.includes('unmapped'))
    expect(g.style.rich.tag.backgroundColor).toBe('#ffffff')
    expect(g.style.rich.tag.borderColor).toBe(UNMAPPED_EDGE)
    expect(g.style.rich.tag.borderWidth).toBe(1.5)
    expect(g.style.rich.tag.color).toBe(INK)
  })
  it('annotate(不给 compare)照旧:bracket 标题、轨标题里没有 ⇣ / unmapped', () => {
    const t = texts(layer(null))
    expect(t[0]).toBe('bracket')
    expect(t.join(' ')).not.toMatch(/⇣|unmapped/)
  })
  it('compare 的 bracket 可以放在用户区最后一行(特征轨下面):bracketGeometry 按给的顶排', () => {
    const g = bracketGeometry(2, COMPARE_BRACKET_ROW_H, 90)
    expect(g.top).toBe(90)
    expect(g.h).toBe(LANE_PAD * 2 + 2 * COMPARE_BRACKET_ROW_H)
  })
  it('▲ 字母后挂 ✓ / ✗:✗ 垫朱红底,字一律黑;matched / unmatched 在悬停', () => {
    const s = layer(CMP).series.find(x => x.name === 'annotation-brackets')
    const kids = (i: number) => s.renderItem({ dataIndex: i }, api(s.data[i])).children
    const txt = (i: number) => kids(i).find((c: any) => c.type === 'text').style
    const ia = [0, 1].find(i => txt(i).text.startsWith('a'))!, ib = 1 - ia
    expect(txt(ia).text).toBe('a {bg|✓}')
    expect(txt(ia).rich.bg.backgroundColor).toBeUndefined()
    expect(txt(ib).text).toBe('b {bg|✗}')
    expect(txt(ib).rich.bg.backgroundColor).toBe(VERMILION)
    expect([txt(ia).fill, txt(ib).fill]).toEqual([INK, INK])
    expect(s.tooltip.formatter({ dataIndex: ib })).toContain('matched · buy -1')
  })
  it('compare 的 user 行放大:▲ 跟着变宽,字母和记号在 ▲ 右边、不压在 ▲ 上', () => {
    const bg = bracketGeometry(1, COMPARE_BRACKET_ROW_H)
    expect(bg.h).toBe(LANE_PAD * 2 + COMPARE_BRACKET_ROW_H)
    const l = annotateLayer(BARS, {
      lanes: LANES, geom: laneGeometry(LANES, bg.top + bg.h).geom, nameOf, selectedId: null, preview: null, draft: null,
      zoom: null, width: 800, bracket: { geom: bg, placed: packBrackets(items, DATES).placed }, compare: CMP,
    })
    const s = l.series.find(x => x.name === 'annotation-brackets')
    const kids = s.renderItem({ dataIndex: 0 }, api(s.data[0])).children
    const tri = kids.find((c: any) => c.type === 'polygon').shape.points
    const txt = kids.find((c: any) => c.type === 'text').style
    expect(txt.x).toBeGreaterThan(tri[2][0])
    expect(txt.font).toContain('11.5px')
    expect(s.data[0][3] - s.data[0][2]).toBe(COMPARE_BRACKET_ROW_H - 4)
  })
  it('框旁和框的悬停里都不写 app 把它认成什么样(missing、start not compared 都没有)', () => {
    const s = layer(CMP).series.find(x => x.name === 'annotation-boxes')
    const k = s.data.findIndex((r: any[]) => r[6] === 'b1')
    expect(JSON.stringify(s.renderItem({ dataIndex: k }, api(s.data[k])).children)).not.toContain('missing')
    const tip = s.tooltip.formatter({ dataIndex: k, value: s.data[k] })
    expect(tip).not.toMatch(/missing|start not compared/)
  })
  it('当家行是样本时 user 行头加粗', () => {
    const l = layer({ ...CMP, userActive: true })
    expect(l.graphics.find(g => g.type === 'text' && g.style.text === 'user').style.fontWeight).toBe('bold')
  })
  it('用户的框与 app 的轨相邻处:每个给定的 y 一道全宽分界线', () => {
    const l = layer({ ...CMP, edges: [40, 120] })
    const lines = l.graphics.filter(g => g.type === 'rect' && g.style.fill === USER_APP_EDGE_COLOR)
    expect(lines.map(g => g.top + g.shape.height / 2)).toEqual([40, 120])
    expect(lines.every(g => g.shape.height === USER_APP_EDGE_H)).toBe(true)
    expect(layer(CMP).graphics.some(g => g.type === 'rect' && g.style.fill === USER_APP_EDGE_COLOR)).toBe(false)
  })
  it('只多出这几样;第二段的对照 tag 与档位小字一个都不出', () => {
    const all = JSON.stringify(layer(CMP).graphics) + JSON.stringify(layer(CMP).series.map(s => s.name))
    for (const w of ['connected', 'disconnected', 'not_qualified', 'chance_high', 'excluded', 'optional', 'must_not',
                     'remapped', 'detected_only', 'qualified_only']) {
      expect(all).not.toContain(w)
    }
    expect(layer(CMP).series.map(s => s.name)).toEqual(['annotation-boxes', 'annotation-brackets'])
  })
  it('悬停在合进 app 副图后也出(app 副图顶层 tooltip 关着,标注层每个系列自己开)', () => {
    for (const s of layer(CMP).series) expect(s.tooltip.show).toBe(true)
  })
})

describe('bracket 的样本跨度按起点折', () => {
  it('起点相同的并成一行,每个样本日一个 ▲;起点不同、不交叠的仍可同一行', () => {
    const its: BracketItem[] = [
      { ...items[0] }, { ...items[1] },
      { id: 's3', start: DATES[2], end: DATES[3], pos: true, letter: 'c', faded: false, emphasis: 0 },
      { id: 's4', start: DATES[8], end: DATES[9], pos: true, letter: 'd', faded: false, emphasis: 0 },
    ]
    const { rows, placed } = packBrackets(its, DATES)
    const row = Object.fromEntries(placed.map(p => [p.item.id, p.row]))
    expect(row.s1).toBe(row.s2)
    expect(row.s3).not.toBe(row.s1)
    expect(row.s4).toBe(row.s1)
    expect(rows).toBe(2)
  })
  it('点选:同起点并成一行时取 ▲ 离点最近的样本;▲ 右半边伸出跨度的那截也算点中它', () => {
    // 三个样本同起点(第 1 天),终点第 4 / 6 / 8 天:跨度一个包着一个
    const its: BracketItem[] = [4, 6, 8].map((e, k) =>
      ({ id: `s${k}`, start: DATES[1], end: DATES[e], pos: true, letter: 'abc'[k], faded: false, emphasis: 0 }))
    const { rows, placed } = packBrackets(its, DATES)
    expect(rows).toBe(1)
    const g = bracketGeometry(rows, COMPARE_BRACKET_ROW_H)
    const toPx = (i: number) => i * 20, bw = 10
    const rects = bracketRects(placed, g, DATES, toPx, bw)
    const y = (rects[0].top + rects[0].bottom) / 2
    expect(bracketPick(rects, bw, 4 * 20, y)).toBe('s0')            // 点在 a 的 ▲ 上(另两段跨度也盖着这一点)
    expect(bracketPick(rects, bw, 4 * 20 + 6, y)).toBe('s0')        // ▲ 右半边、已出了 a 的跨度(跨度右沿 +5)
    expect(bracketPick(rects, bw, 2 * 20, y)).toBe('s0')            // a 的 ▲ 左边:三段都盖着,a 的 ▲ 最近
    expect(bracketPick(rects, bw, 6 * 20, y)).toBe('s1')
    expect(bracketPick(rects, bw, 8 * 20, y)).toBe('s2')
    expect(bracketPick(rects, bw, 8 * 20, rects[0].bottom + 5)).toBeNull()   // 不在这一行
    expect(bracketPick(rects, bw, 0, y)).toBeNull()                  // 起点之前
  })
  it('annotate 也照这条排(同一个函数)', () => {
    const opt: any = buildAnnotateSubOption(BARS, {
      lanes: LANES, geom: laneGeometry(LANES, 30).geom, nameOf, selectedId: null, preview: null, draft: null, zoom: null,
      width: 800, bracket: { geom: bracketGeometry(1), placed: packBrackets(items, DATES).placed },
    })
    const br = opt.series.find((s: any) => s.name === 'annotation-brackets')
    expect(br.data[0][2]).toBe(br.data[1][2])
  })
})

describe('合进的主视图副图', () => {
  const topology = { nodes: [{ node_id: 'plateau', where_rules: [] }, { node_id: 'step', where_rules: [], produced_by: 'plateau', child_slot: 'step' }],
                     edges: [] } as any
  const ev = (node: string, s: number, e: number): EventDict =>
    ({ instance_id: `${node}@${s}-${e}`, node_id: node, instance_idx: 0, start_idx: s, end_idx: e })
  const input: any = {
    topology, isolatedNodeIds: new Set(), tagList: ['plateau', 'step'], level: 'detected', nodeColors: {},
    eventTier: () => 'detected', nodeOfEventByBand: (e: EventDict) => e.node_id, bandKeyOf: (e: EventDict) => e.node_id,
    tagToNodes: { plateau: ['plateau'], step: ['step'] },
  }
  const bars = DATES.map(date => ({ date, o: 1, h: 1, l: 1, c: 1, v: 1, rv: 1 }))

  it('band 表头:node 名后跟用户特征名(正常字体、浅灰底)与 app_only(等宽);不给就只有 node 名', () => {
    const geom = computeSubGeometry({ bracketLaneCount: 0, bandLaneCounts: [1, 1] })
    const g = buildSubDecorGraphics(geom.bandGeom, geom.bracketH, ['plateau', 'step'], false, 800, 1, {},
                                    [{ feature: '站上新平台' }, { tag: 'app_only', tagTip: 'why app_only' }])
    const t = g.filter(x => x.type === 'text').map(x => x.style)
    expect(t[0].text).toBe('{n|plateau}  {biz|站上新平台}')
    expect(t[0].rich.biz.backgroundColor).toBe('#f4f4f5')
    expect(t[0].rich.biz.fontFamily).toBeUndefined()
    expect(t[1].text).toBe('{n|step}  {tag|app_only}')
    expect(t[1].rich.tag.fontFamily).toMatch(/mono/i)
    // 挂了 app_only 的表头接鼠标、悬停弹说明;别的表头照旧不接鼠标(点击落到底下的格上)
    const titles = g.filter(x => x.type === 'text')
    expect([titles[0].silent, titles[0].tooltip]).toEqual([true, undefined])
    expect(titles[1].silent).toBe(false)
    expect(titles[1].tooltip.formatter).toContain('why app_only')
    const plain = buildSubDecorGraphics(geom.bandGeom, geom.bracketH, ['plateau', 'step'], false, 800)
    expect(plain.filter(x => x.type === 'text').map(x => x.style.text)).toEqual(['plateau', 'step'])
  })
  it('buildSubOption 读 input.hoverBand(反馈面板悬停的 node):那一行垫浅蓝底、描中蓝边;不给不画', () => {
    const bundle = computeEventData(bars, [ev('plateau', 1, 4), ev('step', 2, 2)], [], input)
    const geom = computeSubGeometry({ bracketLaneCount: 0, bandLaneCounts: [1, 1] })
    const lit = (o: any) => o.graphic.filter((x: any) => x.type === 'rect' && x.style.stroke === 'rgb(26, 128, 186)')
    const opt: any = buildSubOption(bars, bundle, geom, { ...input, hoverBand: 'step' }, 800)
    const r = lit(opt)
    expect(r).toHaveLength(1)
    expect(r[0].top).toBe(geom.bandGeom[1].top + 1)
    expect(r[0].shape.height).toBe(geom.bandGeom[1].h - 2)
    expect(lit(buildSubOption(bars, bundle, geom, input, 800))).toEqual([])
    expect(lit(buildSubOption(bars, bundle, geom, { ...input, hoverBand: 'nope' }, 800))).toEqual([])
  })
  it('buildSubOption 读 input.linkedBands:选中框对的 band 表头加粗,其余照常', () => {
    const bundle = computeEventData(bars, [ev('plateau', 1, 4), ev('step', 2, 2)], [], input)
    const geom = computeSubGeometry({ bracketLaneCount: 0, bandLaneCounts: [1, 1] })
    const opt: any = buildSubOption(bars, bundle, geom, { ...input, linkedBands: ['step'] }, 800)
    const label = (t: string) => opt.graphic.find((x: any) => x.type === 'text' && String(x.style.text).endsWith(t))
    expect(label('step').style.fontWeight).toBe('bold')
    expect(label('plateau').style.fontWeight).toBe('normal')
  })
  it('buildSubOption 读 input.bandExtras(按 band 名)', () => {
    const bundle = computeEventData(bars, [ev('plateau', 1, 4), ev('step', 2, 2)], [], input)
    const geom = computeSubGeometry({ bracketLaneCount: 0, bandLaneCounts: [1, 1] })
    const opt: any = buildSubOption(bars, bundle, geom, { ...input, bandExtras: { plateau: { feature: '站上新平台' } } }, 800)
    expect(opt.graphic.filter((x: any) => x.type === 'text').map((x: any) => x.style.text))
      .toContain('{n|plateau}  {biz|站上新平台}')
  })
  it('user 行最后一行样本跨度的下沿:行底往上让出轨的内边距与条外的空', () => {
    const g = bracketGeometry(1, 18, 50)                       // h = 4*2 + 18 = 26,条高 18-(13-9) = 14
    expect(bracketContentBottom(g)).toBe(50 + 4 + 2 + 14)
    expect(bracketContentBottom(bracketGeometry(2, 18, 50))).toBe(50 + 4 + 18 + 2 + 14)
  })

  it('compare 下 hit 行接在用户区下面(分界线到上面跨度下沿、到下面 hit 行上沿一样远),hits 表头跟着下移', () => {
    const geom = computeSubGeometry({ bracketLaneCount: 1, bandLaneCounts: [1, 1], userContentBottom: 30 })
    const r = makeRenderBracket([{ hit_id: 'h', kind: 'mark' }], null, new Set(), 1, false, geom.appBracketTop)
    const out: any = r({ dataIndex: 0 }, { ...api([2, 4, 0, 1]), coord: ([i]: number[]) => [i * 10] })
    expect(out.children[0].shape.y).toBe(30 + 2 * USER_APP_GAP)
    const bundle = computeEventData(bars, [ev('plateau', 1, 4)],
      [{ hit_id: 'h', start_idx: 1, end_idx: 4, node_index: { plateau: 'plateau@1-4' } } as unknown as HitDict], input)
    const opt: any = buildSubOption(bars, bundle, geom, input, 800)
    expect(opt.graphic.find((x: any) => x.type === 'text' && x.style.text === 'hits').top).toBe(30 + 2 * USER_APP_GAP)
    // 浅黄底从分界线起
    expect(opt.graphic.find((x: any) => x.type === 'rect' && x.style.fill === HITS_FILL).top).toBe(30 + USER_APP_GAP)
    expect(BAND_TOP_PAD + BAND_LANE_H).toBeGreaterThan(0)
  })
})

describe('buyDaysOf(从票 11 的 compare 测试移来:node.slot 取 slot 里 child 的跨度并起来)', () => {
  it('node 取它的 event 跨度,node.slot 取 slot 里各个 child 的跨度', () => {
    const ev = (node: string, s: number, e: number): EventDict =>
      ({ instance_id: `${node}@${s}-${e}#0`, node_id: node, instance_idx: 0, start_idx: s, end_idx: e })
    const tb: EventDict = { ...ev('tb', 4, 12), child_refs: { segments: ['seg@5-6#0', 'seg@9-9#0'] } }
    const evs = [tb, ev('seg', 5, 6), ev('seg', 9, 9), ev('burst', 2, 3)]
    const m = { hit_id: 'm0', start_idx: 2, end_idx: 12, node_index: { tb: tb.instance_id, burst: 'burst@2-3#0' } } as unknown as HitDict
    const byId = new Map(evs.map(e => [e.instance_id, e]))
    expect(buyDaysOf(m, byId, 'tb.segments')).toEqual([5, 6, 9])
    expect(buyDaysOf(m, byId, 'burst')).toEqual([2, 3])
    expect(buyDaysOf(m, byId, 'nope')).toEqual([])
  })
})
