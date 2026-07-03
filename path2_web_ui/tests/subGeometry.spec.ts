import { describe, it, expect } from 'vitest'
import {
  computeSubGeometry,
  composeEffectiveSubH,
  DIVIDER_GAP,
  BAND_MARKER_H,
  BAND_LANE_GAP,
  BAND_LANE_H,
  BAND_TOP_PAD,
  BAND_BOT_PAD,
  BAND_MIN_H,
  SUB_CANVAS_MIN_H,
  HL_EXPAND_H,
  HL_EXPAND_OFFSET,
  SUB_DIVIDER_COLOR,
  SUB_DIVIDER_H,
  BAND_INNER_LINE_COLOR,
  BAND_INNER_LINE_H,
  MIN_SUB_H,
  SUB_GRID_LEFT,
  SUB_GRID_RIGHT,
  MAIN_MIN_H,
  BAND_ZOOM_MIN,
  BAND_ZOOM_MAX,
  BAND_ZOOM_STEP_BUTTON,
  BAND_ZOOM_STEP_WHEEL,
  LS_KEY_BAND_ZOOM,
} from '../src/render/subGeometry'

describe('computeSubGeometry (Task 2)', () => {
  it('empty input: bracketH=0, no bands, subCanvasH=SUB_CANVAS_MIN_H', () => {
    const g = computeSubGeometry({ bracketLaneCount: 0, bandLaneCounts: [] })
    expect(g.bracketH).toBe(0)
    expect(g.bandGeom).toEqual([])
    expect(g.subCanvasH).toBe(120)
    // divider y = bracketH + 2
    expect(g.dividerY).toBe(2)
  })

  it('bracketLaneCount=1: bracketH=17(4+9+4), one band', () => {
    // 新公式:BAND_TOP_PAD(4) + 1*BAND_LANE_H(9) + BAND_BOT_PAD(4) = 17
    const g = computeSubGeometry({ bracketLaneCount: 1, bandLaneCounts: [1] })
    expect(g.bracketH).toBe(17)
    expect(g.dividerY).toBe(17 + 2)   // 19
    // band_0: BAND_MIN_H=20 vs (1*9 + 4 + 4)=17 → clamp to 20
    expect(g.bandGeom.length).toBe(1)
    expect(g.bandGeom[0].h).toBe(20)
    expect(g.bandGeom[0].top).toBe(17 + 4)  // 21
    expect(g.bandGeom[0].laneCount).toBe(1)
    // subCanvasH = 17 + 4 + 20 = 41;非空内容不再被 SUB_CANVAS_MIN_H 垫高(留白修复)
    expect(g.subCanvasH).toBe(41)
  })

  it('非空小内容不垫高:canvas 高 = 自然高(复刻截图场景 bracket2+band[2,1])', () => {
    // bracketH = 4+2*9+4 = 26;burst band = max(20, 2*9+8) = 26;tb band = max(20, 17) = 20
    // subCanvasH = 26 + 4 + 26 + 20 = 76,不触 SUB_CANVAS_MIN_H(空数据专用兜底)
    const g = computeSubGeometry({ bracketLaneCount: 2, bandLaneCounts: [2, 1] })
    expect(g.subCanvasH).toBe(76)
  })

  it('bracketLaneCount=3, three bands with lane counts [1,2,5]', () => {
    const g = computeSubGeometry({ bracketLaneCount: 3, bandLaneCounts: [1, 2, 5] })
    // bracketH = 4 + 3*9 + 4 = 35
    expect(g.bracketH).toBe(35)
    expect(g.dividerY).toBe(35 + 2)   // 37
    // band_0: max(20, 1*9+8) = 20 / band_1: 26 / band_2: 53
    expect(g.bandGeom.map(b => b.h)).toEqual([20, 26, 53])
    expect(g.bandGeom[0].top).toBe(35 + 4)          // 39
    expect(g.bandGeom[1].top).toBe(39 + 20)              // 59
    expect(g.bandGeom[2].top).toBe(39 + 20 + 26)         // 85
    // subCanvasH = 39 + 20+26+53 = 138
    expect(g.subCanvasH).toBe(138)
  })

  it('large content: 5 bands × 20 lanes each', () => {
    const g = computeSubGeometry({ bracketLaneCount: 9, bandLaneCounts: [20, 20, 20, 20, 20] })
    // bracketH = 4 + 9*9 + 4 = 89
    // band_i.h = max(20, 20*9+8) = 188 each;5 bands = 940
    // subCanvasH = 89 + 4 + 940 = 1033
    expect(g.bracketH).toBe(89)
    expect(g.subCanvasH).toBe(1033)
    expect(g.bandGeom.every(b => b.h === 188)).toBe(true)
  })

  it('bracketLaneCount=0 with bands: divider still rendered', () => {
    const g = computeSubGeometry({ bracketLaneCount: 0, bandLaneCounts: [3] })
    expect(g.bracketH).toBe(0)
    expect(g.dividerY).toBe(2)
    expect(g.bandGeom[0].top).toBe(0 + 4)   // 4
  })
})

describe('subGeometry — Task 2 new constants', () => {
  it('SUB_DIVIDER_COLOR is slate-400 hex', () => {
    expect(SUB_DIVIDER_COLOR).toBe('#94a3b8')
  })
  it('SUB_DIVIDER_H is 2 px', () => {
    expect(SUB_DIVIDER_H).toBe(2)
  })
  it('BAND_INNER_LINE_COLOR is the legacy splitLine color', () => {
    expect(BAND_INNER_LINE_COLOR).toBe('#e0e6f1')
  })
  it('BAND_INNER_LINE_H is 1 px', () => {
    expect(BAND_INNER_LINE_H).toBe(1)
  })
  it('MIN_SUB_H is 60 px (below SUB_CANVAS_MIN_H=120 by design)', () => {
    expect(MIN_SUB_H).toBe(60)
    expect(MIN_SUB_H).toBeLessThan(SUB_CANVAS_MIN_H)
  })
  it('SUB_GRID_LEFT / RIGHT match chart.ts hardcoded values', () => {
    expect(SUB_GRID_LEFT).toBe(56)
    expect(SUB_GRID_RIGHT).toBe(16)
  })

  it('computeSubGeometry output shape unchanged', () => {
    const g = computeSubGeometry({ bracketLaneCount: 2, bandLaneCounts: [1, 3] })
    expect(g).toHaveProperty('bracketH')
    expect(g).toHaveProperty('bandGeom')
    expect(g).toHaveProperty('subCanvasH')
    expect(g).toHaveProperty('dividerY')
    expect(g.bandGeom.length).toBe(2)
    expect(g.bandGeom[0]).toHaveProperty('top')
    expect(g.bandGeom[0]).toHaveProperty('h')
    expect(g.bandGeom[0]).toHaveProperty('laneCount')
  })
})

describe('subGeometry — zoom factor & 新常量', () => {
  it('exports 常量 verbatim(clamp / step / MAIN_MIN_H / LS key)', () => {
    // 数值直断防错误改动 —— 这些常量是全 plan 契约锚点
    expect(MAIN_MIN_H).toBe(300)
    expect(BAND_ZOOM_MIN).toBe(1.0)
    expect(BAND_ZOOM_MAX).toBe(3.0)
    expect(BAND_ZOOM_STEP_BUTTON).toBe(0.2)
    expect(BAND_ZOOM_STEP_WHEEL).toBe(1.1)
    expect(LS_KEY_BAND_ZOOM).toBe('kline-band-zoom-v1')
  })

  it('computeSubGeometry(input)单参 = computeSubGeometry(input, 1.0)(backward-compat)', () => {
    const input = { bracketLaneCount: 1, bandLaneCounts: [1, 2] }
    const a = computeSubGeometry(input)
    const b = computeSubGeometry(input, 1.0)
    expect(a).toEqual(b)
  })

  it('computeSubGeometry(input, 2.0):bandGeom[i].h = laneCount*BAND_LANE_H*2 + pad,pad 不缩', () => {
    const input = { bracketLaneCount: 0, bandLaneCounts: [5, 5] }
    const g = computeSubGeometry(input, 2.0)
    // 5-lane band 自然 h = 5*9*2 + 4 + 4 = 98 ≥ BAND_MIN_H(20),不触底
    expect(g.bandGeom[0].h).toBe(5 * BAND_LANE_H * 2 + BAND_TOP_PAD + BAND_BOT_PAD)
    // 5-lane band h = 5*9*2 + 4 + 4 = 98
    expect(g.bandGeom[1].h).toBe(5 * BAND_LANE_H * 2 + BAND_TOP_PAD + BAND_BOT_PAD)
    // 自然 canvas 累计 = 0+DIVIDER(4)+98+98 = 200 > SUB_CANVAS_MIN_H(120),clamp 不生效
    // 直接对齐 累加(不写死具体数值,免耦合 DIVIDER_GAP 常量变更):
    // g.bandGeom[1].top = g.bandGeom[0].top + g.bandGeom[0].h
    expect(g.bandGeom[1].top).toBe(g.bandGeom[0].top + g.bandGeom[0].h)
    expect(g.subCanvasH).toBe(g.bandGeom[1].top + g.bandGeom[1].h)
    // 空 laneCount 情况保 BAND_MIN_H 兜底(zoomFactor=2 也不影响):
    const gZero = computeSubGeometry({ bracketLaneCount: 0, bandLaneCounts: [] }, 2.0)
    expect(gZero.bandGeom.length).toBe(0)
  })

  it('computeSubGeometry(input, 1.0)与既有 API 行为字节等同(核心不变量)', () => {
    // laneCount 取 2/3(而非原始 1/1/2):laneCount=1 时自然值 17 < BAND_MIN_H(20) 恒触底,
    // 与 zoomFactor 无关地让断言恒假 —— 与 Resolution A 同一原则修正,避免测试数据自身撞 clamp
    const input = { bracketLaneCount: 1, bandLaneCounts: [2, 1, 3] }
    const g = computeSubGeometry(input, 1.0)
    // 每 band h = laneCount*9 + 8;不触 BAND_MIN_H 时字节匹配
    expect(g.bandGeom[0].h).toBe(2 * BAND_LANE_H + BAND_TOP_PAD + BAND_BOT_PAD)
    expect(g.bandGeom[2].h).toBe(3 * BAND_LANE_H + BAND_TOP_PAD + BAND_BOT_PAD)
  })

  it('bracketH 随 zoomFactor 缩放(bracket-band-unify):lane 项乘 z,pads 不乘', () => {
    // bracketLaneCount=2, z=2 → bracketH = 4 + 2*9*2 + 4 = 44
    const g = computeSubGeometry({ bracketLaneCount: 2, bandLaneCounts: [3] }, 2.0)
    expect(g.bracketH).toBe(BAND_TOP_PAD + 2 * BAND_LANE_H * 2 + BAND_BOT_PAD)
    // z=1 backward-compat: bracketH = 4 + 18 + 4 = 26
    const g1 = computeSubGeometry({ bracketLaneCount: 2, bandLaneCounts: [3] }, 1.0)
    expect(g1.bracketH).toBe(BAND_TOP_PAD + 2 * BAND_LANE_H + BAND_BOT_PAD)
    // 空 bracket 情况保 0(与 zoomFactor 无关)
    const gZero = computeSubGeometry({ bracketLaneCount: 0, bandLaneCounts: [3] }, 2.0)
    expect(gZero.bracketH).toBe(0)
    // dividerY 与首 band top 按缩放后 bracketH 派生
    expect(g.dividerY).toBe(g.bracketH + Math.floor(DIVIDER_GAP / 2))
    expect(g.bandGeom[0].top).toBe(g.bracketH + DIVIDER_GAP)
  })
})

describe('subGeometry — bracket-band-unify 新常量(spec 2026-07-03-bracket-band-unify)', () => {
  it('BAND_MARKER_H / BAND_LANE_GAP / HL_EXPAND_* verbatim;BAND_LANE_H 派生值不变', () => {
    expect(BAND_MARKER_H).toBe(7)
    expect(BAND_LANE_GAP).toBe(2)
    expect(BAND_LANE_H).toBe(BAND_MARKER_H + BAND_LANE_GAP)  // 9
    expect(BAND_LANE_H).toBe(9)
    expect(HL_EXPAND_H).toBe(3)
    expect(HL_EXPAND_OFFSET).toBe(1.5)
  })
})

describe('composeEffectiveSubH(spec 2026-07-03-subchart-boundary-model §1)', () => {
  it('fit:offset null/0 → 恒等于 subCanvasH(无滚动条前提)', () => {
    expect(composeEffectiveSubH(120, null)).toBe(120)
    expect(composeEffectiveSubH(300, 0)).toBe(300)
  })

  it('负 offset:容器 = subCanvasH + offset(隐藏量 = -offset)', () => {
    expect(composeEffectiveSubH(300, -100)).toBe(200)
  })

  it('zoom 变化 offset 不变 → 隐藏量守恒、容器增量 = 内容增量', () => {
    const offset = -40
    const before = composeEffectiveSubH(120, offset)   // zoom 前
    const after = composeEffectiveSubH(200, offset)    // zoom 放大 subCanvasH 120→200
    expect(120 - before).toBe(40)   // 隐藏量恒 = -offset
    expect(200 - after).toBe(40)
    expect(after - before).toBe(80) // 分界线随 zoom 移动 80px
  })

  it('下限 clamp:subCanvasH + offset < MIN_SUB_H → MIN_SUB_H', () => {
    expect(composeEffectiveSubH(120, -100)).toBe(MIN_SUB_H)   // 20 < 60 → 60
  })

  it('上限 clamp:正 offset 防御性钳到 subCanvasH(永不留白)', () => {
    expect(composeEffectiveSubH(120, 50)).toBe(120)
  })

  it('内容 < MIN_SUB_H:下限退让到内容高,fit 不留白且不可再压', () => {
    // floor 收窄后 subCanvasH 可 < MIN_SUB_H(如单 band 24px):
    // fit 恒贴内容(不被 MIN_SUB_H 抬高出留白),drag 也压不出比内容更矮的容器
    expect(composeEffectiveSubH(24, null)).toBe(24)
    expect(composeEffectiveSubH(24, -10)).toBe(24)
  })
})
