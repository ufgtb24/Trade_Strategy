/**
 * 副图 chartSub canvas 几何计算 —— 由 bracket lane 数 + 各 band 内 lane 数
 * 计算 bracket 区高度、每 band 的 top offset / height、divider #2 y 位置、
 * canvas 需要的总高度 subCanvasH。
 *
 * spec: docs/superpowers/specs/2026-07-01-path2-web-subchart-scroll-drag-design.md §2.2
 * spec: docs/superpowers/specs/2026-07-03-subchart-boundary-model-design.md
 *
 * 约定 canvas 局部坐标 y=0 是 canvas 顶,自上而下:
 *   [0, bracketH)                        — bracket 区(lane_i 的 rect y = 4 + i*9·z, h = 7·z)
 *   [bracketH, bracketH + DIVIDER_GAP)   — 内画 1px divider #2, y = bracketH + 2
 *   [bracketH + DIVIDER_GAP, subCanvasH) — band 区,band_i 累积堆叠
 *
 * (CandidateStatusBar banner 已是滚动容器外的独立 DOM 行,不再占 canvas 顶部预留;
 *  spec 2026-07-03-subchart-boundary-model §3)
 *
 * 空数据(bracketLaneCount=0, bandLaneCounts=[])兜底: subCanvasH = SUB_CANVAS_MIN_H = 120,
 * 避免 chartSub 容器塌陷到零高度导致 ECharts 报错。
 */

export const BAND_MARKER_H = 7       // 时段 marker 本体高(bracket 与 band interval 共用,乘 z)
export const BAND_LANE_GAP = 2       // lane 间隙(乘 z,gap 整体等比语义)
export const BAND_LANE_H = BAND_MARKER_H + BAND_LANE_GAP  // 9,lane stride(乘 z)
export const BAND_TOP_PAD = 4
export const BAND_BOT_PAD = 4
export const BAND_MIN_H = 20         // 保 node 名 10px + 上下呼吸空间
export const SUB_CANVAS_MIN_H = 120  // 空数据兜底
// 高亮放大公式(bracket 选中与 band interval 高亮共用;spec 2026-07-03-bracket-band-unify §3.1)
export const HL_EXPAND_H = 3         // 高度增量(乘 z),比例恒 (7+3)/7
export const HL_EXPAND_OFFSET = 1.5  // y 上移(乘 z),保居中外扩
export const DIVIDER_GAP = 4

// Task 2 新增常量: 装饰几何视觉参数 + sub-outer 最小可压缩高度 + chartSub grid 左右内边距
// spec: docs/superpowers/specs/2026-07-01-path2-web-subchart-fixed-decor-design.md
export const SUB_DIVIDER_COLOR = '#94a3b8'    // slate-400,bracket-band 分隔线
export const SUB_DIVIDER_H = 2                // bracket-band 分隔线粗细(px)
export const BAND_INNER_LINE_COLOR = '#e0e6f1' // 与旧 splitLine 同色
export const BAND_INNER_LINE_H = 1            // band 内 lane 分隔线粗细(px)
export const MIN_SUB_H = 60                   // sub-outer 可压缩到的最小像素高度(120 仅为空数据兜底,60 为容器可视下界;内容更矮时退让到内容高)
export const SUB_GRID_LEFT = 56               // chartSub grid[0].left
export const SUB_GRID_RIGHT = 16              // chartSub grid[0].right

// ── band zoom 交互常量(spec 2026-07-03-subchart-band-zoom)──────────────
// MAIN_MIN_H:zoom 拉大副图时主图至少保留的高度,防 K 线被挤压至不可读。
export const MAIN_MIN_H = 300
export const BAND_ZOOM_MIN = 1.0
export const BAND_ZOOM_MAX = 3.0
export const BAND_ZOOM_STEP_BUTTON = 0.2      // 按钮 -/+ 每次绝对步进
export const BAND_ZOOM_STEP_WHEEL = 1.1       // Shift+wheel 每 tick 乘/除因子(相对步进)
export const LS_KEY_BAND_ZOOM = 'kline-band-zoom-v1'

export interface BandGeom {
  top: number       // band 顶在 canvas 局部 y
  h: number         // band 高
  laneCount: number // 输入透传,便于渲染时按 lane 数分配 lane 位置
}

export interface SubGeometry {
  bracketH: number      // bracket 区总高(空 matches 时 = 0)
  bandGeom: BandGeom[]  // 每 band 的 top/h/laneCount,顺序与输入 bandLaneCounts 一致
  subCanvasH: number    // 副图 canvas 需要的总高
  dividerY: number      // divider #2 的 y(1px 线)
}

export interface SubGeometryInput {
  bracketLaneCount: number     // packBrackets 后的 max lane + 1(即 lane 数)
  bandLaneCounts: number[]     // 每 band 的 lane 数(顺序按 tagList 排)
}

export function computeSubGeometry(
  input: SubGeometryInput,
  zoomFactor: number = 1.0,   // ← 新增,default 1.0 保 backward-compat
): SubGeometry {
  // bracket 区与 band 同一套几何:顶/底呼吸 pad(不乘 z)+ laneCount * BAND_LANE_H * z
  // (spec 2026-07-03-bracket-band-unify §3.2;顶 pad 为本次新增,原区顶紧贴 banner)
  const bracketH = input.bracketLaneCount > 0
    ? BAND_TOP_PAD + input.bracketLaneCount * BAND_LANE_H * zoomFactor + BAND_BOT_PAD
    : 0
  const dividerY = bracketH + Math.floor(DIVIDER_GAP / 2)
  const bandAreaTop = bracketH + DIVIDER_GAP

  let cursor = bandAreaTop
  const bandGeom: BandGeom[] = []
  for (const laneCount of input.bandLaneCounts) {
    // zoomFactor 只影响 lane 高度,pad 不缩(spec §4.1)
    const natural = laneCount * BAND_LANE_H * zoomFactor + BAND_TOP_PAD + BAND_BOT_PAD
    const h = Math.max(BAND_MIN_H, natural)
    bandGeom.push({ top: cursor, h, laneCount })
    cursor += h
  }

  const naturalCanvasH = cursor
  // SUB_CANVAS_MIN_H 仅在真正空数据时兜底(防 ECharts 零高容器报错);
  // 非空小内容用自然高,fit 态才能贴内容无留白(boundary-model 留白修复)
  const isEmpty = input.bracketLaneCount === 0 && input.bandLaneCounts.length === 0
  const subCanvasH = isEmpty ? SUB_CANVAS_MIN_H : naturalCanvasH
  return { bracketH, bandGeom, subCanvasH, dividerY }
}

/**
 * 副图容器高度合成(spec 2026-07-03-subchart-boundary-model §1)。
 * offset = 用户 drag 藏掉的像素数(恒 ≤ 0;null = fit)。
 * 不变量:返回值 ≤ subCanvasH(永不留白);offset=null/0 时 = subCanvasH(fit,无滚动条)。
 * zoom 只改 subCanvasH、不碰 offset → 分界线随 zoom 移动而隐藏量守恒。
 */
export function composeEffectiveSubH(subCanvasH: number, offset: number | null): number {
  const lo = Math.min(MIN_SUB_H, subCanvasH)   // 内容比 MIN_SUB_H 还矮时,下限退让到内容高(不留白优先)
  return Math.max(lo, Math.min(subCanvasH + (offset ?? 0), subCanvasH))
}
