/**
 * annotate 下的副图:第一条是 bracket 轨(每个样本的跨度画一条虚线,右端是样本的三角),下面一个特征一条轨,
 * 用户的框画在自己特征的轨上(虚线:全界面虚线只表示「用户画的」)。
 * 轨的排法(轨序、子框轨、交叠的框分行)由 annotate/model.ts 的 computeLanes 给,框旁的标记由
 * annotate/samples.ts 的 boxMarks 给;本模块只管几何与画法,以及主图 K 线区上的几层:
 * 「选中的框」「正在拖的框」的范围、样本的三角、选中样本时样本日之后暗一档。
 *
 * 配色:框、三角和文字一律黑(#111),选中的框填浅灰;不引入新色相。区分靠线宽、线型和深浅:
 * - 选中样本时,它的成员框线加粗、虚线拉长;画了没收的框换短虚线、右侧挂 ◂;跨过样本日收不进的空槽画淡、
 *   右侧挂 ⇥;其余画淡;
 * - 只被别的 pattern 的样本收进的框、别的 pattern 的样本(三角、bracket)画淡;
 * - 正样本实心 ▲、负样本空心 △(白底黑边);
 * - 暗一档:样本日之后的 K 线区盖一层 7% 的黑,K 线的形状仍看得清。
 * 轨标题里的特征名是用户写的内容,用正常字体加浅灰底(--chip-bg 同值),「⊂」、unnamed、bracket 与字母是程序
 * 固定文字,用等宽字体。
 *
 * compare 下这一层(annotateLayer 的 graphics + series)合进主视图那张副图(render/chart.ts 的 buildSubOption),
 * 副图分两区(见 render/compareLayout.ts):上区是用户的,特征轨照 annotate 的顺序在上,样本跨度那一行(user)在
 * 这一区最后一行;下区是 app 的,和主视图那张副图一样(hits 第一行,band 在下)。这一层在 compare 下多画(LaneDraw.compare):
 * - 轨标题:map 了的轨在特征名后写 `⇣ <node>`,没 map 的挂会话蓝 `unmapped`;
 * - bracket 的 user 行:▲ 字母后挂 app 与用户判断一致与否的记号 `✓` / `✗`(✗ 朱红底),matched / unmatched 在悬停;
 *   当家行是样本时(←/→ 在样本间走)user 行头加粗;
 * - 两区之间一道分界线(位置由 subGeometry 的 userAppEdges 给):线上是用户画的、线下是 app 认的,
 *   user 行与 hits 隔着这道线正好上下对照;
 * - 框终点那天它对的 node 一个 event 都没有:框右端挂琥珀 `missing`;map 了的框悬停写 `start not compared`
 *   (框的左端不和 app 比,见 stores/compare.ts)。
 * app 的东西一律不画进用户轨:用户轨只有用户画的框。
 */
import type { Bar } from '../types'
import type { AnnBox, Lane } from '../annotate/model'
import { triOf, type BoxMark } from '../annotate/samples'
import { CROSSES_SAMPLE_DATE, UNCLAIMED } from '../annotate/membership'
import { endIndex, startIndex, type BoxPx } from '../annotate/boxGeometry'
import {
  SUB_CANVAS_MIN_H, SUB_GRID_LEFT, SUB_GRID_RIGHT, SUB_ROW_LEFT, SUB_TITLE_LEFT, USER_APP_EDGE_COLOR, USER_APP_EDGE_H,
} from './subGeometry'
import { MONO } from './fonts'

export const LANE_ROW_H = 18          // 轨里一行的高度
export const LANE_BOX_H = 13          // 框的高度(行高减去上下空隙)
export const LANE_PAD = 4             // 轨的上下内边距
export const LANES_TOP = 4            // 第一条轨上方留白

export const INK = '#111'             // 文字与框线一律黑
export const CHIP_BG = '#f4f4f5'      // 用户写的内容(不在输入框里)的浅灰底,同 App.vue 的 --chip-bg
export const LANE_LINE = '#e4e4e7'    // 轨之间的分隔线,同 --line-soft
export const SELECTED_FILL = 'rgba(0,0,0,0.10)'   // 选中的框:填浅灰(填充只表示「选中」)
export const SELECTED_SPAN_FILL = 'rgba(0,0,0,0.06)'   // 主图 K 线区上选中的框的范围:面积大,比轨里的浅一档,免得压住 K 线
export const NO_FILL = 'rgba(255,255,255,0)'
export const TITLE_BG = 'rgba(255,255,255,0.85)'  // 轨标题垫白,压在框上也读得出
export const BOX_DASH = [5, 3]        // 用户的框:虚线
export const DRAFT_DASH = [2, 2]      // 正在拖出的框:短虚线
export const MEMBER_DASH = [7, 2]     // 选中样本时它的成员框:长虚线、线加粗
export const UNCLAIMED_DASH = [2, 2]  // 画了没收的框:短虚线(右侧挂 ◂)
export const DIM_OPACITY = 0.28       // 选中样本时不相干的框、跨过样本日的空槽:画淡
export const AWAY_OPACITY = 0.4       // 只属于别的 pattern 的样本的框、别的 pattern 的样本:画淡
export const POS_FILL = INK           // 正样本:实心三角
export const NEG_FILL = '#ffffff'     // 负样本:空心三角(白底黑边)
export const AFTER_DIM = 'rgba(0,0,0,0.07)'   // 选中样本时样本日之后的 K 线区:暗一档,形状仍看得清
export const BRACKET_ROW_H = 13       // bracket 轨里一行的高度
export const BRACKET_BAR_H = 9        // bracket 轨里一条样本跨度的高度
export const COMPARE_BRACKET_ROW_H = 18   // compare 的 user 行:行高放大,▲ 与字母、✓ / ✗ 第一屏读得出(待验证)
// compare 的两个小标签不铺浅色底(浅蓝、浅琥珀底在白图上和底色深浅相近,色盲下看不出):白底 + 中等深度
// 描边 + 黑字。描边色取用户确认过的安全色板(1 蓝、2 橙),两者冷暖相反:unmapped 是冷(会话这一侧的事),
// missing 是暖(app 那一侧缺东西)。
export const UNMAPPED_EDGE = '#0072B2' // 蓝:compare 下没 map 的轨挂的 unmapped 的描边
export const MISSING_EDGE = '#E69F00'  // 橙:compare 下框右端 missing 的描边
const TAG_BOX = { backgroundColor: '#ffffff', borderWidth: 1.5, padding: [1, 3], borderRadius: 2 }
export const VERMILION = '#D55E00'    // 朱红:只表示「app 的判断和你相反」(▲ 字母后的 ✗ 底色)
export { MONO }
/** 悬停文字:等宽、黑字。MONO 里有双引号,属性值用单引号括,否则 style 在字体名那里就断了。 */
const monoTip = (html: string) => `<span style='font-family:${MONO};color:${INK}'>${html}</span>`

/** 轨的位置与高度;rowH 只有 bracket 轨用(一行样本跨度的高度,缺省 BRACKET_ROW_H)。 */
export interface LaneGeom { top: number; h: number; rowH?: number }

/** 正在拖出的新框:起止日期,以及它要进的那条轨(下标;等于轨数时画在最后另起的一条)。 */
export interface Draft { start: string; end: string; lane: number }

/** custom 系列里一个框占的横向像素:从起点那根 K 线的左边到终点那根的右边。 */
function spanPx(api: any): [number, number] {
  const bw = api.size([1, 0])[0]
  return [api.coord([api.value(0), 0])[0] - bw / 2, api.coord([api.value(1), 0])[0] + bw / 2]
}

/** 每条轨的位置与高度,以及副图需要的总高(至少 SUB_CANVAS_MIN_H)。top:第一条特征轨的上沿(bracket 轨之下)。 */
export function laneGeometry(lanes: readonly Lane[], top = LANES_TOP): { geom: LaneGeom[]; height: number } {
  const geom: LaneGeom[] = []
  let y = top
  for (const l of lanes) {
    const h = LANE_PAD * 2 + l.rows * LANE_ROW_H
    geom.push({ top: y, h })
    y += h
  }
  return { geom, height: Math.max(SUB_CANVAS_MIN_H, y + LANES_TOP) }
}

// ── bracket 轨 ────────────────────────────────────────────────────────

/** bracket 轨上的一个样本:跨度、正负、字母(当前 pattern 才有)、画淡(别的 pattern)、加粗(选中 2、当前样本 1)。 */
export interface BracketItem {
  id: string
  start: string
  end: string
  pos: boolean
  letter: string | null
  faded: boolean
  emphasis: 0 | 1 | 2
  /** compare:字母后的记号(app 与这个样本的判断一致 ✓ / 不一致 ✗)与它的悬停;annotate 不给 */
  mark?: { sign: '✓' | '✗'; tip: string } | null
}
export interface PlacedBracket { item: BracketItem; row: number }

/**
 * bracket 轨的排法:起点相同的样本跨度并成一行(同 app 副图「同起点折成一族」的规则,每个样本日一个 ▲);
 * 起点不同的按起点排,一行里不交叠(按 K 线下标比)。
 */
export function packBrackets(items: readonly BracketItem[], dates: readonly string[]): { rows: number; placed: PlacedBracket[] } {
  const sorted = [...items].sort((a, b) => (a.start < b.start ? -1 : a.start > b.start ? 1 : a.end > b.end ? -1 : 1))
  const ends: number[] = []
  const placed: PlacedBracket[] = []
  const rowOfStart = new Map<number, number>()
  for (const it of sorted) {
    const st = startIndex(dates, it.start), en = endIndex(dates, it.end)
    let row = rowOfStart.get(st) ?? -1
    if (row < 0) {
      row = ends.findIndex(x => x < st)
      if (row < 0) { row = ends.length; ends.push(-1) }
      rowOfStart.set(st, row)
    }
    ends[row] = Math.max(ends[row], en)
    placed.push({ item: it, row })
  }
  return { rows: Math.max(1, ends.length), placed }
}

/** bracket 轨的位置与高度(没有样本时也留一行)。rowH:一行的高(compare 的 user 行放大);
 *  top:annotate 在最上面,compare 在用户区最后一行(特征轨下面)。 */
export function bracketGeometry(rows: number, rowH: number = BRACKET_ROW_H, top: number = LANES_TOP): LaneGeom {
  return { top, h: LANE_PAD * 2 + Math.max(1, rows) * rowH, rowH }
}

/** bracket 轨里一行的竖直范围(条高 = 行高减去上下各 2 像素的空)。 */
function bracketYRange(g: LaneGeom, row: number): { top: number; bottom: number } {
  const rowH = g.rowH ?? BRACKET_ROW_H
  const barH = rowH - (BRACKET_ROW_H - BRACKET_BAR_H)
  const top = g.top + LANE_PAD + row * rowH + (rowH - barH) / 2
  return { top, bottom: top + barH }
}

/** bracket 轨最后一行样本跨度的下沿(compare 下两区分界线到它、到 hit 行上沿的距离相等,见 subGeometry 的 USER_APP_GAP)。 */
export function bracketContentBottom(g: LaneGeom): number {
  const rows = Math.max(1, Math.round((g.h - LANE_PAD * 2) / (g.rowH ?? BRACKET_ROW_H)))
  return bracketYRange(g, rows - 1).bottom
}

/** bracket 轨上各样本跨度的像素范围(点选样本用),toPx、bw 同 boxRects。 */
export function bracketRects(placed: readonly PlacedBracket[], g: LaneGeom, dates: readonly string[],
                             toPx: (i: number) => number, bw: number): BoxPx[] {
  if (!dates.length) return []
  return placed.map(({ item, row }) => {
    const { top, bottom } = bracketYRange(g, row)
    return { id: item.id, left: toPx(startIndex(dates, item.start)) - bw / 2,
             right: toPx(endIndex(dates, item.end)) + bw / 2, top, bottom }
  })
}

/** bracket 一行里样本终点那个 ▲ 的半宽(随行高放大):画 ▲ 与点选样本共用。 */
export function bracketMarkHalf(top: number, bottom: number): number {
  return Math.max(4.5, (bottom - top) * 0.5)
}

/**
 * bracket 轨上这一点点中的样本(rects 为 bracketRects 的结果)。同起点的几个样本并在一行、跨度一个包着一个,
 * 所以在落进的几个里取终点(▲)离这一点最近的那个;▲ 右半边伸出跨度的那一截也算点中它。没点中为 null。
 */
export function bracketPick(rects: readonly BoxPx[], bw: number, x: number, y: number): string | null {
  let best: { id: string; d: number } | null = null
  for (const r of rects) {
    const end = r.right - bw / 2
    const right = Math.max(r.right, end + bracketMarkHalf(r.top, r.bottom))
    if (x < r.left || x > right || y < r.top || y > r.bottom) continue
    const d = Math.abs(end - x)
    if (!best || d < best.d) best = { id: r.id, d }
  }
  return best?.id ?? null
}

/** 落在哪条轨上(按 y);不在任何轨上为 -1。 */
export function laneAt(geom: readonly LaneGeom[], y: number): number {
  return geom.findIndex(g => y >= g.top && y < g.top + g.h)
}

/** 一个框在轨里的竖直范围。 */
export function boxYRange(g: LaneGeom, row: number): { top: number; bottom: number } {
  const top = g.top + LANE_PAD + row * LANE_ROW_H + (LANE_ROW_H - LANE_BOX_H) / 2
  return { top, bottom: top + LANE_BOX_H }
}

export interface LaneDraw {
  lanes: readonly Lane[]
  geom: readonly LaneGeom[]
  /** bracket 轨:位置与排好的样本跨度(不给就不画这条轨) */
  bracket?: { geom: LaneGeom; placed: readonly PlacedBracket[] } | null
  /** 框旁的标记(字母、画淡、选中样本时的成员框 / 画了没收 / 跨过样本日) */
  marks?: ReadonlyMap<string, BoxMark> | null
  nameOf: (fid: string | null) => string | null
  selectedId: string | null
  /** 改起止时拖着的框:画在它新的位置上 */
  preview: AnnBox | null
  /** 正在拖出的新框:画在它要进的那条轨上(没有就画在最后) */
  draft: Draft | null
  zoom: { start: number; end: number } | null
  width: number
  /** compare 下多画的东西(不给就是 annotate) */
  compare?: CompareMarks | null
}

/** compare 下标注层多画的东西(只是记号与标题,app 的条、hit 画在 app 那张副图里)。 */
export interface CompareMarks {
  /** 轨(下标)→ 它对的 node:标题写 `⇣ node` */
  laneNode: ReadonlyMap<number, string>
  /** 没 map 的特征轨(下标):标题挂 unmapped */
  unmapped: ReadonlySet<number>
  /** 框终点那天它对的 node 一个 event 都没有的框:右端挂 missing */
  missing: ReadonlySet<string>
  /** map 了的框(悬停写 start not compared) */
  compared: ReadonlySet<string>
  /** 当家行是样本(←/→ 在样本间走):user 行头加粗 */
  userActive: boolean
  /** 用户的框与 app 的轨上下相邻处的 y(像素):画分界线 */
  edges?: readonly number[]
}

/**
 * 轨标题:特征名(浅灰底)、子框轨写成「缩量 ⊂ 横盘」,还没起名的轨写 unnamed。
 * compare:map 了的轨后面写 `⇣ <node>`(等宽),没 map 的挂会话蓝 unmapped。
 */
function laneTitle(l: Lane, nameOf: LaneDraw['nameOf'], cmp: { node?: string | null; unmapped?: boolean } = {}): any {
  const rich = {
    biz: { backgroundColor: CHIP_BG, color: INK, fontSize: 12, padding: [1, 4], borderRadius: 3 },
    sym: { fontFamily: MONO, fontSize: 12, color: INK, fontWeight: 'bold' },
    node: { fontFamily: MONO, fontSize: 12, color: INK },
    tag: { fontFamily: MONO, fontSize: 11, color: INK, ...TAG_BOX, borderColor: UNMAPPED_EDGE },
  }
  if (l.key === null) return { text: '{sym|unnamed}', rich }
  const esc = (t: string) => t.replace(/[{}|]/g, ' ')
  const biz = (t: string) => `{biz|${esc(t)}}`
  let text = l.parent ? `${biz(nameOf(l.key) ?? '')}{sym| ⊂ }${biz(nameOf(l.parent) ?? '')}` : biz(nameOf(l.key) ?? '')
  if (cmp.node) text += `{node|  ⇣ ${esc(cmp.node)}}`
  else if (cmp.unmapped) text += '{node|  }{tag|unmapped}'
  return { text, rich }
}

/** 一个框的画法:线宽、线型、深浅,以及框左侧的字母、右侧的 ◂ / ⇥。 */
function boxLook(mark: BoxMark | undefined, sel: boolean, draft: boolean) {
  const f = mark?.focus ?? null
  const opacity = sel || draft ? 1 : f === 'dim' || f === CROSSES_SAMPLE_DATE ? DIM_OPACITY
    : mark?.away && f !== 'member' && f !== UNCLAIMED ? AWAY_OPACITY : 1
  return {
    lineWidth: sel || f === 'member' ? 2.5 : 1.5,
    lineDash: draft ? DRAFT_DASH : f === 'member' ? MEMBER_DASH : f === UNCLAIMED ? UNCLAIMED_DASH : BOX_DASH,
    opacity,
    owners: mark?.owners.join(' ') ?? '',
    side: f === UNCLAIMED ? '◂' : f === CROSSES_SAMPLE_DATE ? '⇥' : '',
  }
}

/** 框右侧挂 ◂ / ⇥ 的那一小块的横向范围(相对框的右边):点 ◂ 收进当前选中的样本。 */
export const SIDE_MARK_X: readonly [number, number] = [6, 20]

/** annotate 副图的 ECharts option:标注层(annotateLayer)单独成一张副图。 */
export function buildAnnotateSubOption(bars: Bar[], d: LaneDraw): unknown {
  const dates = bars.map(b => b.date)
  const { graphics, series } = annotateLayer(bars, d)
  return {
    animation: false,
    tooltip: { trigger: 'item', show: true, appendToBody: true, confine: true },
    grid: [{ left: SUB_GRID_LEFT, right: SUB_GRID_RIGHT, top: 0, bottom: 0 }],
    graphic: graphics,
    xAxis: [{
      type: 'category', data: dates, gridIndex: 0, boundaryGap: true,
      axisLine: { show: false }, axisTick: { show: false }, axisLabel: { show: false }, splitLine: { show: false },
      axisPointer: { show: true, type: 'none', snap: true, label: { show: false }, triggerTooltip: false },
    }],
    yAxis: [{ type: 'value', gridIndex: 0, show: false, min: 0, max: 1 }],
    dataZoom: [annotateDataZoom(d.zoom)],
    series,
  }
}

/**
 * 标注层副图的缩放:拖动留给画框和改起止;滚轮照常缩放(和主图同步)。
 * weakFilter:框、bracket 是一段(起止两个 x),只要有一端在图窗里、或横跨整个图窗就照画(画到图窗边为止);
 * 默认的 filter 要两端都在图窗里,起点在图窗左边外的框和 bracket 会整条消失。compare 合进 app 副图时也用它。
 */
export function annotateDataZoom(zoom: { start: number; end: number } | null): Record<string, unknown> {
  return { type: 'inside', xAxisIndex: 0, start: zoom?.start ?? 0, end: zoom?.end ?? 100,
           moveOnMouseMove: false, filterMode: 'weakFilter' }
}

/**
 * 标注层:轨的分隔线与标题(graphic)+ bracket 轨的样本跨度 + 框(custom series)。annotate 单独成图,
 * compare 合进主视图那张副图(几何由调用方按合并后的位置给)。
 */
export function annotateLayer(bars: Bar[], d: LaneDraw): { graphics: any[]; series: any[] } {
  const dates = bars.map(b => b.date)
  const graphics: any[] = []
  const w = d.width - SUB_ROW_LEFT - SUB_GRID_RIGHT   // 分隔线从容器最左起,轨名写在左边的轨名栏里
  const cmp = d.compare ?? null
  if (d.bracket) {
    const g = d.bracket.geom
    graphics.push({ type: 'rect', left: SUB_ROW_LEFT, top: g.top + g.h - 0.5, shape: { width: w, height: 1 },
                    style: { fill: LANE_LINE }, z: 1, silent: true })
    graphics.push({ type: 'text', left: SUB_TITLE_LEFT, top: g.top + LANE_PAD - 1, z: 30, silent: true,
                    style: { text: cmp ? 'user' : 'bracket', fontFamily: MONO, fontSize: 12, fill: INK,
                             fontWeight: cmp?.userActive ? 'bold' : 'normal', backgroundColor: TITLE_BG,
                             padding: [0, 2] } })
  }
  d.geom.forEach((g, i) => {
    if (!g) return
    graphics.push({ type: 'rect', left: SUB_ROW_LEFT, top: g.top + g.h - 0.5, shape: { width: w, height: 1 },
                    style: { fill: LANE_LINE }, z: 1, silent: true })
    const t = laneTitle(d.lanes[i], d.nameOf, { node: cmp?.laneNode.get(i) ?? null, unmapped: cmp?.unmapped.has(i) })
    graphics.push({ type: 'text', left: SUB_TITLE_LEFT, top: g.top + LANE_PAD, z: 30, silent: true,
                    style: { ...t, fill: INK, fontSize: 12, backgroundColor: TITLE_BG, padding: [0, 2] } })
  })
  for (const y of cmp?.edges ?? []) {
    graphics.push({ type: 'rect', left: SUB_ROW_LEFT, top: y - USER_APP_EDGE_H / 2, shape: { width: w, height: USER_APP_EDGE_H },
                    style: { fill: USER_APP_EDGE_COLOR }, z: 3, silent: true })
  }

  // 每个框一行数据:[起点下标, 终点下标, 顶, 底, 选中, 拖出中, 编号];画法(boxLook)按行号另存
  const rows: any[] = []
  const looks: ReturnType<typeof boxLook>[] = []
  const tips: string[] = []
  const push = (b: { id: string; start: string; end: string }, top: number, bottom: number, sel: boolean, draft: boolean) => {
    if (!dates.length) return
    const mark = draft ? undefined : d.marks?.get(b.id)
    rows.push([startIndex(dates, b.start), endIndex(dates, b.end), top, bottom, sel ? 1 : 0, draft ? 1 : 0, b.id])
    looks.push(boxLook(mark, sel, draft))
    tips.push([
      mark?.owners.length ? `member box of sample ${mark.owners.join(', ')}` : '',
      mark?.focus === UNCLAIMED ? 'maybe drawn but not added; click ◂ to add' : '',
      mark?.focus === CROSSES_SAMPLE_DATE ? 'crosses sample date: cannot be a member box of the selected sample' : '',
      mark?.away ? 'member box of samples of another pattern only' : '',
      cmp?.missing.has(b.id) ? 'missing: no app event of its node on its end date' : '',
      cmp?.compared.has(b.id) ? 'start not compared' : '',
    ].filter(Boolean).join('<br>'))
  }
  d.lanes.forEach((l, i) => {
    for (const lb of l.boxes) {
      const b = d.preview && d.preview.id === lb.box.id ? d.preview : lb.box
      const { top, bottom } = boxYRange(d.geom[i], lb.row)
      push(b, top, bottom, b.id === d.selectedId, false)
    }
  })
  if (d.draft) {
    const g = d.geom[d.draft.lane] ?? { top: (d.geom.at(-1)?.top ?? LANES_TOP) + (d.geom.at(-1)?.h ?? 0), h: LANE_ROW_H + 2 * LANE_PAD }
    const { top, bottom } = boxYRange(g, 0)
    push({ id: '__draft', start: d.draft.start, end: d.draft.end }, top, bottom, false, true)
  }

  // bracket 轨:每个样本一行数据 [起点下标, 样本日下标, 顶, 底];画法按行号另存
  const bRows: number[][] = []
  const bItems: BracketItem[] = []
  if (d.bracket && dates.length) {
    for (const { item, row } of d.bracket.placed) {
      const { top, bottom } = bracketYRange(d.bracket.geom, row)
      bRows.push([startIndex(dates, item.start), endIndex(dates, item.end), top, bottom])
      bItems.push(item)
    }
  }

  const missing = rows.map(r => (cmp?.missing.has(r[6]) ? 1 : 0))

  const series: any[] = [{
    type: 'custom', name: 'annotation-boxes', xAxisIndex: 0, yAxisIndex: 0, clip: true,
    data: rows, encode: { x: [0, 1] }, z: 10,
    tooltip: {
      show: true,
      formatter: (p: any) => {
        const [s, e] = [p.value[0], p.value[1]]
        const tip = tips[p.dataIndex]
        return monoTip(`${dates[s]} – ${dates[e]}${tip ? `<br>${tip}` : ''}`)
      },
    },
    renderItem: (p: any, api: any) => {
      const [x0, x1] = spanPx(api)
      const top = api.value(2), bottom = api.value(3)
      const sel = api.value(4) === 1
      const look = looks[p.dataIndex]
      const mid = (top + bottom) / 2
      const children: any[] = [{
        type: 'rect',
        shape: { x: x0, y: top, width: Math.max(3, x1 - x0), height: bottom - top, r: 2 },
        style: { fill: sel ? SELECTED_FILL : NO_FILL, stroke: INK, lineWidth: look.lineWidth, lineDash: look.lineDash,
                 opacity: look.opacity },
      }]
      if (look.owners) {
        children.push({ type: 'text', style: { text: look.owners, x: x0 - 3, y: mid, align: 'right', verticalAlign: 'middle',
                                               font: `bold 10.5px ${MONO}`, fill: INK, opacity: look.opacity } })
      }
      if (look.side) {
        children.push({ type: 'text', style: { text: look.side, x: x1 + (SIDE_MARK_X[0] + SIDE_MARK_X[1]) / 2, y: mid,
                                               align: 'center', verticalAlign: 'middle', font: `bold 14px ${MONO}`, fill: INK } })
      }
      if (missing[p.dataIndex]) {
        children.push({ type: 'text', style: { text: 'missing', x: x1 + (look.side ? SIDE_MARK_X[1] + 4 : 4), y: mid,
                                               align: 'left', verticalAlign: 'middle', font: `10.5px ${MONO}`, fill: INK,
                                               ...TAG_BOX, borderColor: MISSING_EDGE } })
      }
      return { type: 'group', children }
    },
  }, {
    type: 'custom', name: 'annotation-brackets', xAxisIndex: 0, yAxisIndex: 0, clip: true,
    data: bRows, encode: { x: [0, 1] }, z: 9,
    tooltip: {
      show: true,
      formatter: (p: any) => {
        const it = bItems[p.dataIndex]
        return monoTip(`${it.letter ? `${it.letter} ` : ''}${triOf(it.pos ? 'pos' : 'neg')} ${it.end}<br>${it.start} – ${it.end}`
                       + (it.mark ? `<br>${it.mark.tip}` : ''))
      },
    },
    renderItem: (p: any, api: any) => {
      const [x0, x1] = spanPx(api)
      const top = api.value(2), bottom = api.value(3)
      const it = bItems[p.dataIndex]
      const opacity = it.faded ? AWAY_OPACITY : 1
      const xs = api.coord([api.value(1), 0])[0]
      // ▲ 的半宽随行高放大;字母与 ✓ / ✗ 在 ▲ 右边、隔 3 像素,竖直居中(不压在 ▲ 上)
      const half = bracketMarkHalf(top, bottom)
      const fontPx = bottom - top >= 12 ? 11.5 : 9.5
      const children: any[] = [{
        type: 'rect',
        shape: { x: x0, y: top, width: Math.max(3, x1 - x0), height: bottom - top },
        style: { fill: it.emphasis === 2 ? SELECTED_FILL : NO_FILL, stroke: INK, lineWidth: it.emphasis ? 2.5 : 1.3,
                 lineDash: BOX_DASH, opacity },
      }, {
        type: 'polygon',
        shape: { points: [[xs, top + 1], [xs - half, bottom], [xs + half, bottom]] },
        style: { fill: it.pos ? POS_FILL : NEG_FILL, stroke: INK, lineWidth: 1.2, opacity },
      }]
      if (it.letter || it.mark) {
        // ✗ 垫朱红底(只表示 app 的判断和你相反);字一律黑
        const rich = { bg: it.mark?.sign === '✗' ? { backgroundColor: VERMILION, padding: [0, 1] } : {} }
        const text = `${it.letter ?? ''}${it.mark ? ` {bg|${it.mark.sign}}` : ''}`
        children.push({ type: 'text', style: { text, rich, x: xs + half + 3, y: (top + bottom) / 2, align: 'left',
                                               verticalAlign: 'middle', font: `bold ${fontPx}px ${MONO}`, fill: INK, opacity } })
      }
      return { type: 'group', children }
    },
  }]
  return { graphics, series }
}

/** 框在副图上的像素范围(点选、改起止用)。toPx:K 线下标 → 该根 K 线中心的 x;bw:一根 K 线的宽度。 */
export function boxRects(lanes: readonly Lane[], geom: readonly LaneGeom[], dates: readonly string[],
                         toPx: (i: number) => number, bw: number): BoxPx[] {
  const out: BoxPx[] = []
  if (!dates.length) return out
  lanes.forEach((l, i) => {
    for (const lb of l.boxes) {
      const { top, bottom } = boxYRange(geom[i], lb.row)
      out.push({ id: lb.box.id, left: toPx(startIndex(dates, lb.box.start)) - bw / 2,
                 right: toPx(endIndex(dates, lb.box.end)) + bw / 2, top, bottom })
    }
  })
  return out
}

/**
 * 主图 K 线区上标出的范围:选中的框(浅灰底、虚线边)和正在拖出或改起止的框(虚线边),
 * 竖直方向占满 K 线区,左右和副图上的框对齐(整根 K 线)。返回一个 custom 系列,按名字合并更新。
 */
export const MAIN_MARKS_SERIES = 'annotation-marks'

export function mainMarksSeries(dates: readonly string[],
                                selected: { start: string; end: string } | null,
                                live: { start: string; end: string } | null): Record<string, unknown> {
  const data: number[][] = []
  if (dates.length && selected) data.push([startIndex(dates, selected.start), endIndex(dates, selected.end), 1])
  if (dates.length && live) data.push([startIndex(dates, live.start), endIndex(dates, live.end), 0])
  return {
    type: 'custom', name: MAIN_MARKS_SERIES, xAxisIndex: 0, yAxisIndex: 0, data, silent: true, z: 1,
    encode: { x: [0, 1] }, clip: true, tooltip: { show: false },
    renderItem: (params: any, api: any) => {
      const [x0, x1] = spanPx(api)
      const cs = params.coordSys
      return {
        type: 'rect',
        shape: { x: x0, y: cs.y, width: Math.max(1, x1 - x0), height: cs.height },
        style: { fill: api.value(2) === 1 ? SELECTED_SPAN_FILL : NO_FILL,
                 stroke: INK, lineWidth: 1, lineDash: BOX_DASH },
      }
    },
  }
}

// ── 主图:样本的三角、样本日之后暗一档 ───────────────────────────────

/** 主图上的一个样本:样本日、正负、选中、画淡(别的 pattern)、字母(当前 pattern 才有)。 */
export interface SampleMark { id: string; date: string; pos: boolean; selected: boolean; faded: boolean; letter: string | null }

export const SAMPLES_SERIES = 'annotation-samples'
export const AFTER_DIM_SERIES = 'annotation-after-dim'
export const TRI_GAP = 6           // 三角顶点在样本日那根 K 线最低价下方几像素
export const TRI_H = 12            // 三角的高
export const TRI_HALF_W = 7        // 三角底边的一半

/** 一个样本三角在主图上的像素范围(点选用):(x, yLow) 是样本日那根 K 线的中心与最低价。 */
export function triangleRect(x: number, yLow: number): { left: number; right: number; top: number; bottom: number } {
  return { left: x - TRI_HALF_W - 1, right: x + TRI_HALF_W + 1, top: yLow + TRI_GAP - 1, bottom: yLow + TRI_GAP + TRI_H + 1 }
}

/** 主图上样本的三角(正样本实心 ▲、负样本空心 △),选中的线加粗,别的 pattern 的画淡,字母写在右下。 */
export function mainSamplesSeries(bars: readonly Bar[], marks: readonly SampleMark[]): Record<string, unknown> {
  const dates = bars.map(b => b.date)
  const data: number[][] = []
  const meta: SampleMark[] = []
  for (const m of marks) {
    const i = dates.indexOf(m.date)
    if (i < 0) continue
    data.push([i, bars[i].l])
    meta.push(m)
  }
  return {
    type: 'custom', name: SAMPLES_SERIES, xAxisIndex: 0, yAxisIndex: 0, data, silent: true, z: 15, clip: false,
    encode: { x: 0, y: 1 }, tooltip: { show: false },
    renderItem: (p: any, api: any) => {
      const m = meta[p.dataIndex]
      const [x, y] = api.coord([api.value(0), api.value(1)])
      const y0 = y + TRI_GAP
      const opacity = m.faded ? AWAY_OPACITY : 1
      const children: any[] = [{
        type: 'polygon',
        shape: { points: [[x, y0], [x - TRI_HALF_W, y0 + TRI_H], [x + TRI_HALF_W, y0 + TRI_H]] },
        style: { fill: m.pos ? POS_FILL : NEG_FILL, stroke: INK, lineWidth: m.selected ? 3 : 1.5, opacity },
      }]
      if (m.letter) {
        children.push({ type: 'text', style: { text: m.letter, x: x + TRI_HALF_W + 2, y: y0 + TRI_H, align: 'left',
                                               verticalAlign: 'bottom', font: `bold 12.5px ${MONO}`, fill: INK, opacity } })
      }
      return { type: 'group', children }
    },
  }
}

/** 选中样本时样本日之后的 K 线区盖一层浅黑(暗一档),压在 K 线上面、不挡鼠标;from 为 null 时不画。 */
export function afterDimSeries(dates: readonly string[], from: string | null): Record<string, unknown> {
  const i = from ? dates.indexOf(from) : -1
  const data = i >= 0 && i + 1 < dates.length ? [[i + 1, dates.length - 1]] : []
  return {
    type: 'custom', name: AFTER_DIM_SERIES, xAxisIndex: 0, yAxisIndex: 0, data, silent: true, z: 3,
    encode: { x: [0, 1] }, clip: true, tooltip: { show: false },
    renderItem: (params: any, api: any) => {
      const [x0, x1] = spanPx(api)
      const cs = params.coordSys
      return { type: 'rect', shape: { x: x0, y: cs.y, width: Math.max(1, x1 - x0), height: cs.height },
               style: { fill: AFTER_DIM } }
    },
  }
}
