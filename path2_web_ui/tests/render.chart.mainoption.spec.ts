// render.chart.mainoption.spec.ts — sliderShow / zoomOverride / strictWindow on buildMainOption
// (Task 6 review fix group 5; 恢复自 95f5554 版 render.chart.slider.spec.ts,原测试对象是已删除
//  的 buildKlineOption 单函数,行为现活在 buildMainOption/buildSubOption — 主体已换成 chartMain,
//  故本文件不再叫 "slider",改名反映新调用对象。)
import { describe, it, expect } from 'vitest'
import { computeEventData, buildMainOption, buildSubOption, makeRenderPricePointHighlight, pkTriStyle } from '../src/render/chart'
import type { BandRenderInput } from '../src/render/chart'
import { computeSubGeometry } from '../src/render/subGeometry'
import type { Bar, EventDict, Topology } from '../src/types'

const bars: Bar[] = [
  { date: '2024-01-01', o: 1, h: 2, l: 1, c: 2, v: 100, rv: 0.1 },
  { date: '2024-01-02', o: 2, h: 3, l: 2, c: 3, v: 200, rv: 0.2 },
  { date: '2024-01-03', o: 2, h: 3, l: 2, c: 3, v: 150, rv: 0.15 },
]

function baseInput(overrides: Partial<BandRenderInput> = {}): BandRenderInput {
  return {
    topology: { nodes: [], edges: [] } as Topology,
    isolatedNodeIds: new Set(),
    tagList: [],
    level: 'matched',
    nodeColors: {},
    eventTier: () => 'matched',
    nodeOfEventByBand: () => null,
    bandKeyOf: () => '',
    ...overrides,
  }
}

function mkBundle(input: BandRenderInput) {
  return computeEventData(bars, [], [], input)
}

describe('buildMainOption — sliderShow toggles dataZoom[1].show + grid[0].bottom (chart.ts:309,342)', () => {
  it('sliderShow=true → dataZoom[1].show=true, grid[0].bottom=60', () => {
    const input = baseInput({ sliderShow: true })
    const opt: any = buildMainOption(bars, mkBundle(input), input)
    expect(opt.dataZoom[1].show).toBe(true)
    expect(opt.grid[0].bottom).toBe(60)
  })

  it('sliderShow=false → dataZoom[1].show=false, grid[0].bottom=20', () => {
    const input = baseInput({ sliderShow: false })
    const opt: any = buildMainOption(bars, mkBundle(input), input)
    expect(opt.dataZoom[1].show).toBe(false)
    expect(opt.grid[0].bottom).toBe(20)
  })

  it('sliderShow undefined → 默认等价 true(向后兼容,show=true, bottom=60)', () => {
    const input = baseInput()
    const opt: any = buildMainOption(bars, mkBundle(input), input)
    expect(opt.dataZoom[1].show).toBe(true)
    expect(opt.grid[0].bottom).toBe(60)
  })
})

describe('buildMainOption / buildSubOption — zoomOverride passthrough (chart.ts:274-275,378-379)', () => {
  it('无 zoomOverride → 走 strictWindow 默认(无 buffer = 全集 0..100)', () => {
    const input = baseInput()
    const opt: any = buildMainOption(bars, mkBundle(input), input)
    expect(opt.dataZoom[0].start).toBe(0)
    expect(opt.dataZoom[0].end).toBe(100)
  })

  it('zoomOverride={start,end} → dataZoom[0].start/end 在 buildMainOption 与 buildSubOption 上均 passthrough', () => {
    const input = baseInput({ zoomOverride: { start: 30, end: 70 } })
    const bundle = mkBundle(input)
    const mainOpt: any = buildMainOption(bars, bundle, input)
    expect(mainOpt.dataZoom[0].start).toBe(30)
    expect(mainOpt.dataZoom[0].end).toBe(70)

    const subGeom = computeSubGeometry({ bracketLaneCount: 0, bandLaneCounts: [] })
    const subOpt: any = buildSubOption(bars, bundle, subGeom, input, 800)
    expect(subOpt.dataZoom[0].start).toBe(30)
    expect(subOpt.dataZoom[0].end).toBe(70)
  })

  it('zoomOverride=null → 等价于不传(走 strictWindow 默认)', () => {
    const input = baseInput({ zoomOverride: null })
    const opt: any = buildMainOption(bars, mkBundle(input), input)
    expect(opt.dataZoom[0].start).toBe(0)
    expect(opt.dataZoom[0].end).toBe(100)
  })
})

describe('buildMainOption — y 轴窗口跟随 zoomOverride(修 zoom-in 后 render 留白 bug)', () => {
  // 前低后高、价差悬殊的 10 根 bars:低价前段 h=2、高价后段 h=100。
  // 复现「zoom-in 到低价前段后全量 render → y 轴却按全窗 high 算 → K 线压底留白」。
  const wideBars: Bar[] = Array.from({ length: 10 }, (_, i) => {
    const lo = i < 5 ? 1 : 50
    const hi = i < 5 ? 2 : 100
    return { date: `2024-02-${String(i + 1).padStart(2, '0')}`, o: lo, h: hi, l: lo, c: hi, v: 100, rv: 1 }
  })
  const wideBundle = (input: BandRenderInput) => computeEventData(wideBars, [], [], input)

  it('zoomOverride 圈定低价前段 → yAxis.max 贴合可见窗(不回跳全局 high)', () => {
    // 可见窗 idx 0..3 全在低价段(h=2):displayHeight=(2-1)/0.8=1.25,
    // displayBottom=max(0,1-0.125)=0.875,displayTop=2.125。全局 high=100 → 全窗 max=123.75。
    const input = baseInput({ zoomOverride: { start: 0, end: 40 } })
    const opt: any = buildMainOption(wideBars, wideBundle(input), input)
    expect(opt.yAxis[0].max).toBeLessThan(10)          // 不得回跳到全局 high(123.75)
    expect(opt.yAxis[0].max).toBeCloseTo(2.125, 6)     // 贴合可见窗
  })

  it('无 zoomOverride → yAxis 覆盖全窗(既有行为不变)', () => {
    const input = baseInput()
    const opt: any = buildMainOption(wideBars, wideBundle(input), input)
    expect(opt.yAxis[0].max).toBeCloseTo(123.75, 6)    // 全窗 displayTop
  })
})

describe('buildMainOption — strictWindow markArea shading (chart.ts:280,287)', () => {
  it('strictWindow 存在 → kline 系列带 markArea 灰阴影', () => {
    const input = baseInput({ strictWindow: { startIdx: 1, endIdx: 1 } })
    const opt: any = buildMainOption(bars, mkBundle(input), input)
    const kline = opt.series.find((s: any) => s.name === 'kline')
    expect(kline.markArea).toBeDefined()
    expect(kline.markArea.data.length).toBeGreaterThanOrEqual(1)
  })

  it('strictWindow 缺省 → kline 系列无 markArea(老行为)', () => {
    const input = baseInput()
    const opt: any = buildMainOption(bars, mkBundle(input), input)
    const kline = opt.series.find((s: any) => s.name === 'kline')
    expect(kline.markArea).toBeUndefined()
  })
})

describe('S1 fix: chartSub tooltip 挂 body + 删 markerTooltip 系列级冗余', () => {
  it('chartSub 顶层 tooltip 有 appendToBody: true + confine: true', () => {
    const input = baseInput()
    const subGeom = computeSubGeometry({ bracketLaneCount: 0, bandLaneCounts: [] })
    const option: any = buildSubOption(bars, mkBundle(input), subGeom, input, 800)
    expect((option.tooltip as any).appendToBody).toBe(true)
    expect((option.tooltip as any).confine).toBe(true)
  })

  it('chartSub 所有系列级 markerTooltip 不含 appendToBody(v5 系列级不生效,冗余删)', () => {
    const input = baseInput()
    const subGeom = computeSubGeometry({ bracketLaneCount: 0, bandLaneCounts: [] })
    const option: any = buildSubOption(bars, mkBundle(input), subGeom, input, 800)
    for (const s of (option.series || []) as any[]) {
      if (s.tooltip) {
        expect('appendToBody' in s.tooltip).toBe(false)
      }
    }
  })

  it('chartMain 所有系列级 markerTooltip 不含 appendToBody', () => {
    const input = baseInput()
    const option: any = buildMainOption(bars, mkBundle(input), input)
    for (const s of (option.series || []) as any[]) {
      if (s.tooltip) {
        expect('appendToBody' in s.tooltip).toBe(false)
      }
    }
  })
})

// ── Task 7: solve=False node 免疫 level 门控 + pk marker 三态色/peak_idx 定位 ──
// ── Task 5(2026-09-02):pk 三态由 ref_ids 关系合成(契约 C4)、bo 盒文本派生自 ref_ids+pk_id(契约 C5) ──
describe('solve=False node 免疫 level 门控 + pk marker 三态色/peak_idx', () => {
  // pk/bo 都 render_grid='price' → 主图 marker;pk solve=False 独立显示 node
  const pkTopo: Topology = {
    nodes: [
      { node_id: 'pk', solve: false, render_grid: 'price', where_rules: [] },
      { node_id: 'bo', render_grid: 'price', where_rules: [] },
    ],
    edges: [],
  }
  // 三根 bar,h 各不相同:idx1 的 h=5 作为 peak 精确高点
  const pkBars: Bar[] = [
    { date: '2024-03-01', o: 1, h: 2, l: 1, c: 2, v: 100, rv: 0.1 },
    { date: '2024-03-02', o: 1, h: 5, l: 1, c: 2, v: 100, rv: 0.1 },
    { date: '2024-03-03', o: 1, h: 3, l: 1, c: 2, v: 100, rv: 0.1 },
  ]
  const pkEvents: EventDict[] = [
    // peak_idx=1 ≠ start_idx=0:位置应由 peak_idx 决定
    { instance_id: 'pk_2#0', node_id: 'pk', start_idx: 0, end_idx: 0,
      peak_idx: 1, kind: 'convex', pk_id: 7 } as any,
    { instance_id: 'pk_0#0', node_id: 'pk', start_idx: 0, end_idx: 0,
      peak_idx: 0, kind: 'bear', pk_id: 8 } as any,
    // bo 引用事件:突破 pk_2#0 → 三态合成 broken(契约 C4);bo 盒文本派生自 ref_ids.broken
    // 查 pk_id(契约 C5)。不带 broken_peak_ids(已删字段)。
    { instance_id: 'bo_1#0', node_id: 'bo', start_idx: 2, end_idx: 2,
      ref_ids: { broken: ['pk_2#0'] } } as any,
  ]
  // 全部 tier=detected:无 solve 免疫时 level=matched 会被 RANK 过滤整段滤掉
  const pkInput = (level: 'matched' | 'qualified' | 'detected' = 'matched'): BandRenderInput =>
    baseInput({
      topology: pkTopo,
      tagList: ['pk', 'bo'],
      nodeColors: {},
      eventTier: () => 'detected',
      bandKeyOf: (e) => e.node_id,
      nodeOfEventByBand: (e) => e.node_id,
      tagToNodes: { pk: ['pk'], bo: ['bo'] },
      level,
    })

  it('level=matched: solve=False 的 pk 事件免疫 RANK 过滤,仍进 pricePointData', () => {
    const bundle = computeEventData(pkBars, pkEvents, [], pkInput('matched'))
    expect(bundle.pricePointData.map((d) => d.instance_id)).toEqual(
      expect.arrayContaining(['pk_2#0', 'pk_0#0']),
    )
  })

  it('level=matched: 无 solve 免疫的 bo detected 事件仍被滤掉(免疫只对 solve=False)', () => {
    const withBo: EventDict[] = [
      ...pkEvents,
      { instance_id: 'bo_det#0', node_id: 'bo', start_idx: 1, end_idx: 1 } as any,
    ]
    const bundle = computeEventData(pkBars, withBo, [], pkInput('matched'))
    expect(bundle.pricePointData.map((d) => d.instance_id)).not.toContain('bo_det#0')
  })

  it('pk marker: 位置=peak_idx(anchorY=bars[peak_idx].h);标签只有 id 数字;state 由 ref_ids 合成得出', () => {
    const bundle = computeEventData(pkBars, pkEvents, [], pkInput('matched'))
    const d = bundle.pricePointData.find((x) => x.instance_id === 'pk_2#0')!
    expect(d.value[0]).toBe(1)                    // peak_idx=1,不是 start_idx=0
    expect(d.anchorY).toBe(pkBars[1].h)           // bars[1].h = 5
    expect(d.text).toBe('7')                      // 不带 'pk' 前缀、不带态名
    // pk_2#0 自身不带 state 字段——broken 是被 pkEvents 里 bo_1#0 的
    // ref_ids.broken=['pk_2#0'] 合成出来的(契约 C4),不是读回事件自带字段
    expect(d.state).toBe('broken')
    expect(d.pkKind).toBe('convex')
  })

  it('bo(price-anchored,无 peak_idx)锚点走 start_idx 原生锚(chart.ts:181 的 : e.start_idx 分支)', () => {
    // level=detected 让 bo(detected tier)也过 RANK,能在 pricePointData 里取到
    const bundle = computeEventData(pkBars, pkEvents, [], pkInput('detected'))
    const bo = bundle.pricePointData.find((x) => x.instance_id === 'bo_1#0')!
    // bo_1#0.start_idx=2,无 peak_idx(isPk=false)→ renderIdx 应取 start_idx,不是别的字段
    expect(bo.value[0]).toBe(2)
    expect(bo.anchorY).toBe(pkBars[2].h)          // bars[2].h = 3
  })

  it('bo 盒文本由 ref_ids.broken 查 pk_id 派生:[7](7 = pk_2#0 的 pk_id,契约 C5)', () => {
    // level=detected 让 bo(detected tier)也过 RANK,能在 pricePointData 里取到
    const bundle = computeEventData(pkBars, pkEvents, [], pkInput('detected'))
    const bo = bundle.pricePointData.find((x) => x.instance_id === 'bo_1#0')!
    expect(bo.text).toBe('[7]')
  })

  it('bo 被 nodeVisible 隐藏时,pk 三态仍按合成结果(证明合成发生在 filtered 之前)', () => {
    const input = pkInput('detected')
    const hidden: BandRenderInput = { ...input, nodeVisible: { bo: false } }
    const bundle = computeEventData(pkBars, pkEvents, [], hidden)
    // 先证非空转:bo_1#0 确实被 nodeVisible 隐藏,不进 pricePointData
    expect(bundle.pricePointData.map((d) => d.instance_id)).not.toContain('bo_1#0')
    const pk = bundle.pricePointData.find((x) => x.instance_id === 'pk_2#0')!
    expect(pk.state).toBe('broken')
  })

  it('bo 被 level 过滤掉时,pk 三态仍按合成结果(证明合成发生在 filtered 之前)', () => {
    // level=matched:bo_1#0 tier=detected(RANK 0)< matched(RANK 2)→ 被 RANK 过滤;
    // pk_2#0 靠 solve=False 免疫仍进 pricePointData
    const bundle = computeEventData(pkBars, pkEvents, [], pkInput('matched'))
    // 先证非空转:bo_1#0 确实被 level 过滤,不进 pricePointData
    expect(bundle.pricePointData.map((d) => d.instance_id)).not.toContain('bo_1#0')
    const pk = bundle.pricePointData.find((x) => x.instance_id === 'pk_2#0')!
    expect(pk.state).toBe('broken')
  })

  it('itemStyle.color 类型无关一律 tier 色:带 state 的 pk 与 bo 同口径(三态不走颜色)', () => {
    const withBo: EventDict[] = [
      { instance_id: 'bo_match#0', node_id: 'bo', start_idx: 1, end_idx: 1 } as any,
      ...pkEvents,
    ]
    // level=detected 让 bo(detected tier)也过 RANK;pk 免疫与否都不影响
    const bundle = computeEventData(pkBars, withBo, [], pkInput('detected'))
    const bo = bundle.pricePointData.find((x) => x.instance_id === 'bo_match#0')!
    expect(bo.itemStyle.color).toBe('#d1d5db')    // detected tier 浅灰
    const pk = bundle.pricePointData.find((x) => x.instance_id === 'pk_2#0')!
    expect(pk.itemStyle.color).toBe('#d1d5db')    // 同 tier 色,state 不影响颜色
  })

  // 渲染一组事件(pk 事件 + 其三态合成所需的引用事件),返回 pk 事件的 renderItem 产出的 group。
  // 三态不再是原始字段,必须把"引用它的事件"一并喂入 computeEventData 才能合成出目标态
  // (契约 C4),故入参改整批 EventDict[],目标事件固定取 evs[0]。
  const renderPk = (evs: EventDict[]) => {
    const bundle = computeEventData(pkBars, evs, [], pkInput('matched'))
    const opt: any = buildMainOption(pkBars, bundle, pkInput('matched'))
    const pp = opt.series.find((s: any) => s.name === 'price-points')
    const i = pp.data.findIndex((d: any) => d.instance_id === evs[0].instance_id)
    expect(i).toBeGreaterThanOrEqual(0)
    const fakeApi: any = { value: () => 0, coord: () => [100, 200] }
    return pp.renderItem({ dataIndex: i }, fakeApi) as any
  }
  // 按目标态构造 [pk 事件, ...合成所需的引用事件]:alive 不需要引用;broken 靠一条
  // ref_ids.broken 命中的 bo;eaten 靠另一 pk 的 ref_ids.superseded 命中(elevation 抬升语义)。
  const mkPkGroup = (state: 'alive' | 'broken' | 'eaten', kind = 'convex', pk_id = 3): EventDict[] => {
    const pk: EventDict = { instance_id: `pk_${state}_${pk_id}#0`, node_id: 'pk',
      start_idx: 1, end_idx: 1, peak_idx: 1, kind, pk_id } as any
    if (state === 'alive') return [pk]
    if (state === 'broken') {
      const bo: EventDict = { instance_id: `bo_${state}_${pk_id}#0`, node_id: 'bo',
        start_idx: 2, end_idx: 2, ref_ids: { broken: [pk.instance_id] } } as any
      return [pk, bo]
    }
    const supersedePk: EventDict = { instance_id: `pk_${state}_sup_${pk_id}#0`, node_id: 'pk',
      start_idx: 2, end_idx: 2, peak_idx: 2, kind: 'convex', pk_id: pk_id + 1000,
      ref_ids: { superseded: [pk.instance_id] } } as any
    return [pk, supersedePk]
  }

  it('pk 三态形状编码(spec 2026-08-31 §3.5.4):alive 实心 / broken 空心 / eaten 浅灰虚线,不靠色相', () => {
    const alive = renderPk(mkPkGroup('alive')).children[0]
    expect(alive.type).toBe('polygon')
    expect(alive.style.fill).toBe('#000000')
    expect(alive.style.stroke).toBe('#000000')
    expect(alive.style.lineDash).toBeUndefined()

    const broken = renderPk(mkPkGroup('broken')).children[0]
    expect(broken.style.fill).toBe('none')                 // 空心 = 旧卫星外观
    expect(broken.style.stroke).toBe('#000000')
    expect(broken.style.lineDash).toBeUndefined()

    const eaten = renderPk(mkPkGroup('eaten')).children[0]
    expect(eaten.style.fill).toBe('none')
    expect(eaten.style.stroke).toBe('#9ca3af')             // 浅灰
    expect(eaten.style.lineDash).toEqual([2.5, 2])         // 虚线

    // 未知态兜底=空心(不抛、不实心)
    expect(pkTriStyle('nope')).toMatchObject({ fill: 'none', stroke: '#000000' })
  })

  it('pk 标签只显示 id 数字(无前缀无态名),颜色随三态描边;convex 无短横线', () => {
    for (const state of ['alive', 'broken', 'eaten'] as const) {
      const g = renderPk(mkPkGroup(state, 'convex', 42))
      expect(g.children).toHaveLength(2)                   // ▽ + 标签,无 bear 线
      const label = g.children[1]
      expect(label.type).toBe('text')
      expect(label.style.text).toBe('42')
      expect(label.style.fill).toBe(g.children[0].style.stroke)
    }
  })

  it('buildMainOption 不再有 satellites 系列(卫星 pk 通道删除)', () => {
    const bundle = computeEventData(pkBars, pkEvents, [], pkInput('matched'))
    const opt: any = buildMainOption(pkBars, bundle, pkInput('matched'))
    const names = (opt.series || []).map((s: any) => s.name)
    expect(names).not.toContain('satellites')
  })

  it('pk kind=bear marker: ▽ 下方短横线(与 convex 区分,spec §5.2)', () => {
    const bundle = computeEventData(pkBars, pkEvents, [], pkInput('matched'))
    const opt: any = buildMainOption(pkBars, bundle, pkInput('matched'))
    const pp = opt.series.find((s: any) => s.name === 'price-points')
    const i = pp.data.findIndex((d: any) => d.instance_id === 'pk_0#0')   // kind='bear'
    expect(i).toBeGreaterThanOrEqual(0)
    const fakeApi: any = { value: () => 0, coord: () => [100, 200] }
    const shape = pp.renderItem({ dataIndex: i }, fakeApi) as any
    expect(shape.type).toBe('group')
    // children[0]=▽ polygon,children[1]=标签 text,children[2]=bear 短横线(▽ 底顶点下方 3px)
    expect(shape.children[2].type).toBe('line')
    const bottomY = shape.children[0].shape.points[2][1]   // ▽ 底顶点 y
    expect(shape.children[2].shape.y1).toBe(bottomY + 3)
    expect(shape.children[2].shape.y2).toBe(bottomY + 3)
    expect(shape.children[2].shape.x2 - shape.children[2].shape.x1).toBe(2 * 8)   // 2*PK_TRIANGLE_HALF_WIDTH
    expect(shape.children[2].style.stroke).toBe(shape.children[0].style.stroke)   // 颜色随三态描边
  })

  it('pk 高亮层保留三态形状编码:空心态白底盖本体、eaten 仍虚线、alive 仍实心;bear 短横线随高亮放大', () => {
    const fakeApi: any = { value: () => 0, coord: () => [100, 200] }
    const mk = (state: string, kind: 'group' | 'focus' | 'pendingDisambig', pkKind = 'convex') =>
      makeRenderPricePointHighlight([
        { value: [0, 0], instance_id: 'e1', anchorY: 1, text: '3',
          itemStyle: { color: '#d1d5db' }, kind, state, pkKind },
      ])({ dataIndex: 0 }, fakeApi) as any

    const brokenFocus = mk('broken', 'focus')
    expect(brokenFocus.children[0].style.fill).toBe('#ffffff')       // 空心态放大版白底盖住本体
    expect(brokenFocus.children[0].style.stroke).toBe('#000000')
    expect(brokenFocus.children[0].style.lineWidth).toBe(2.5)         // focus 粗边
    expect(brokenFocus.children[0].style.shadowBlur).toBe(6)
    expect(brokenFocus.children[1].style.text).toBe('3')
    expect(brokenFocus.children).toHaveLength(2)

    const eatenGroup = mk('eaten', 'group')
    expect(eatenGroup.children[0].style.lineDash).toEqual([2.5, 2])
    expect(eatenGroup.children[0].style.stroke).toBe('#9ca3af')
    expect(eatenGroup.children[0].style.lineWidth).toBe(1.5)          // group 细边

    const aliveFocus = mk('alive', 'focus')
    expect(aliveFocus.children[0].style.fill).toBe('#000000')         // 实心不变

    const bearFocus = mk('alive', 'focus', 'bear')
    expect(bearFocus.children).toHaveLength(3)
    expect(bearFocus.children[2].type).toBe('line')
    const bottomY = bearFocus.children[0].shape.points[2][1]
    expect(bearFocus.children[2].shape.y1).toBe(bottomY + 3)

    const pending = mk('broken', 'pendingDisambig')
    expect(pending.children).toHaveLength(3)
    expect(pending.children[0].style.stroke).toBe('#fbbf24')          // 白底垫层琥珀边不动
    expect(pending.children[1].keyframeAnimation).toMatchObject({ duration: 1200, loop: true })
    expect(pending.children[1].style.fill).toBe('#ffffff')            // 闪烁层保持空心态(白底)
    expect(pending.children[1].style.stroke).toBe('#000000')
  })
})
