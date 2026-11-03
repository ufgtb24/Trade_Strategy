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
 * compare 下(LaneDraw.compare)再叠上当前 pattern 的 app 的输出(哪条轨、哪一行见 render/compareOverlay.ts):
 * - event 画成实心的条(和主视图副图的 event 条一样,不描边),颜色按档位:进了 hit 的画 node 本色,qualified 深灰
 *   #9ca3af,detected 浅灰 #d1d5db(render/colors.ts),不套琥珀;压在用户的框下面,框的虚线边照样看得见;
 *   tiers 开着时灰条右端挂 tier tag(render/tierTags.ts);
 * - hit 画在 bracket 轨上:app 琥珀 #F2C25C 底、细黑实线边(tag 和 app 的东西一律实线;虚线只表示用户画的);
 * - 悬停只给状态(档位、起止),不给 node(那等于露出 mapping)、实测值和门槛。
 */
import type { Bar } from '../types'
import type { AnnBox, Lane } from '../annotate/model'
import type { OverlayHit, OverlayLane } from './compareOverlay'
import { colorOf } from './colors'
import { nextStarts, tierTagLimit, tierTagOf, tierTagShape, tierTagWidth, TIER_TAG_GAP, TIER_TAG_TIP } from './tierTags'
import { triOf, type BoxMark } from '../annotate/samples'
import { CROSSES_SAMPLE_DATE, UNCLAIMED } from '../annotate/membership'
import { endIndex, startIndex, type BoxPx } from '../annotate/boxGeometry'
import { SUB_CANVAS_MIN_H, SUB_GRID_LEFT, SUB_GRID_RIGHT } from './subGeometry'

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
export const APP_BAR_H = 7            // compare:轨里一个 event 条的高度(同主视图副图的 event 条)
export const APP_ROW_H = 9            // compare:event 块里一行的高度(条高 + 行间空)
export const APP_AMBER = '#F2C25C'    // app 琥珀(配色规范的来源轴):compare 下 bracket 轨上 hit 的底色
export const MONO = 'ui-monospace, "JetBrains Mono", "DejaVu Sans Mono", Consolas, monospace'

export interface LaneGeom { top: number; h: number }

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
}
export interface PlacedBracket { item: BracketItem; row: number }

/** bracket 轨的排法:按起点排,一行里不交叠(按 K 线下标比)。 */
export function packBrackets(items: readonly BracketItem[], dates: readonly string[]): { rows: number; placed: PlacedBracket[] } {
  const sorted = [...items].sort((a, b) => (a.start < b.start ? -1 : a.start > b.start ? 1 : a.end > b.end ? -1 : 1))
  const ends: number[] = []
  const placed: PlacedBracket[] = []
  for (const it of sorted) {
    const s = startIndex(dates, it.start)
    let row = ends.findIndex(e => e < s)
    if (row < 0) { row = ends.length; ends.push(0) }
    ends[row] = endIndex(dates, it.end)
    placed.push({ item: it, row })
  }
  return { rows: Math.max(1, ends.length), placed }
}

/** bracket 轨的位置与高度(在最上面;没有样本时也留一行)。 */
export function bracketGeometry(rows: number): LaneGeom {
  return { top: LANES_TOP, h: LANE_PAD * 2 + Math.max(1, rows) * BRACKET_ROW_H }
}

/** bracket 轨里一行的竖直范围。 */
function bracketYRange(g: LaneGeom, row: number): { top: number; bottom: number } {
  const top = g.top + LANE_PAD + row * BRACKET_ROW_H + (BRACKET_ROW_H - BRACKET_BAR_H) / 2
  return { top, bottom: top + BRACKET_BAR_H }
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
  /** compare:叠上去的 app 输出(不给就是 annotate) */
  compare?: CompareDraw | null
}

/** compare 下叠到图上的 app 输出。 */
export interface CompareDraw {
  /** 每条轨上叠的 event,和 lanes 按下标对齐 */
  app: readonly OverlayLane[]
  /** bracket 轨上的 hit;hitRow0 是 hit 的第 0 行在 bracket 轨里排第几行(样本跨度占了前面几行) */
  hits: readonly OverlayHit[]
  hitRow0: number
  nodeColors: Record<string, string>
  /** 顶栏 tiers:灰条右端挂不挂 tier tag */
  tiers: boolean
}

/** event 在轨里的竖直范围:event 块竖直居中在轨里(去掉上下内边距),row 是块里的第几行。 */
export function appBarY(g: LaneGeom, rows: number, row: number): { top: number; bottom: number } {
  const blockH = rows * APP_ROW_H - (APP_ROW_H - APP_BAR_H)
  const top = g.top + LANE_PAD + (g.h - 2 * LANE_PAD - blockH) / 2 + row * APP_ROW_H
  return { top, bottom: top + APP_BAR_H }
}

// 悬停里档位的叫法:标注工具一律用 spec 4.3 的新名字,事件三档是 detected / qualified / bound(主视图沿用 matched)
const TIER_WORD = { matched: 'bound', qualified: 'qualified', detected: 'detected' } as const

/** 轨标题:特征名(浅灰底)、子框轨写成「缩量 ⊂ 横盘」,还没起名的轨写 unnamed。 */
function laneTitle(l: Lane, nameOf: LaneDraw['nameOf']): any {
  if (l.key === null) return { text: '{sym|unnamed}', rich: { sym: { fontFamily: MONO, fontSize: 12, color: INK } } }
  const biz = (s: string) => `{biz|${s.replace(/[{}|]/g, ' ')}}`
  const text = l.parent ? `${biz(nameOf(l.key) ?? '')}{sym| ⊂ }${biz(nameOf(l.parent) ?? '')}` : biz(nameOf(l.key) ?? '')
  return {
    text,
    rich: {
      biz: { backgroundColor: CHIP_BG, color: INK, fontSize: 12, padding: [1, 4], borderRadius: 3 },
      sym: { fontFamily: MONO, fontSize: 12, color: INK, fontWeight: 'bold' },
    },
  }
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

/** annotate 副图的 ECharts option:轨的分隔线与标题(graphic)+ bracket 轨的样本跨度 + 框(custom series)。 */
export function buildAnnotateSubOption(bars: Bar[], d: LaneDraw): unknown {
  const dates = bars.map(b => b.date)
  const graphics: any[] = []
  const w = d.width - SUB_GRID_LEFT - SUB_GRID_RIGHT
  if (d.bracket) {
    const g = d.bracket.geom
    graphics.push({ type: 'rect', left: SUB_GRID_LEFT, top: g.top + g.h - 0.5, shape: { width: w, height: 1 },
                    style: { fill: LANE_LINE }, z: 1, silent: true })
    graphics.push({ type: 'text', left: SUB_GRID_LEFT + 2, top: g.top + LANE_PAD - 1, z: 30, silent: true,
                    style: { text: 'bracket', fontFamily: MONO, fontSize: 12, fill: INK, backgroundColor: TITLE_BG,
                             padding: [0, 2] } })
  }
  d.geom.forEach((g, i) => {
    graphics.push({ type: 'rect', left: SUB_GRID_LEFT, top: g.top + g.h - 0.5, shape: { width: w, height: 1 },
                    style: { fill: LANE_LINE }, z: 1, silent: true })
    const t = laneTitle(d.lanes[i], d.nameOf)
    graphics.push({ type: 'text', left: SUB_GRID_LEFT + 2, top: g.top + LANE_PAD, z: 30, silent: true,
                    style: { ...t, fill: INK, fontSize: 12, backgroundColor: TITLE_BG, padding: [0, 2] } })
  })

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

  const cmp = buildCompareSeries(dates, d)

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
    // 拖动留给画框和改起止;滚轮照常缩放(和主图同步)。
    // weakFilter:框、bracket 是一段(起止两个 x),只要有一端在图窗里、或横跨整个图窗就照画(画到图窗边为止);
    // 默认的 filter 要两端都在图窗里,起点在图窗左边外的框和 bracket 会整条消失
    dataZoom: [{ type: 'inside', xAxisIndex: 0, start: d.zoom?.start ?? 0, end: d.zoom?.end ?? 100,
                 moveOnMouseMove: false, filterMode: 'weakFilter' }],
    series: [{
      type: 'custom', name: 'annotation-boxes', xAxisIndex: 0, yAxisIndex: 0, clip: true,
      data: rows, encode: { x: [0, 1] }, z: 10,
      tooltip: {
        formatter: (p: any) => {
          const [s, e] = [p.value[0], p.value[1]]
          const tip = tips[p.dataIndex]
          return `<span style="font-family:${MONO};color:${INK}">${dates[s]} – ${dates[e]}${tip ? `<br>${tip}` : ''}</span>`
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
        return { type: 'group', children }
      },
    }, {
      type: 'custom', name: 'annotation-brackets', xAxisIndex: 0, yAxisIndex: 0, clip: true,
      data: bRows, encode: { x: [0, 1] }, z: 9,
      tooltip: {
        formatter: (p: any) => {
          const it = bItems[p.dataIndex]
          return `<span style="font-family:${MONO};color:${INK}">${it.letter ? `${it.letter} ` : ''}${triOf(it.pos ? 'pos' : 'neg')} `
            + `${it.end}<br>${it.start} – ${it.end}</span>`
        },
      },
      renderItem: (p: any, api: any) => {
        const [x0, x1] = spanPx(api)
        const top = api.value(2), bottom = api.value(3)
        const it = bItems[p.dataIndex]
        const opacity = it.faded ? AWAY_OPACITY : 1
        const xs = api.coord([api.value(1), 0])[0]
        const children: any[] = [{
          type: 'rect',
          shape: { x: x0, y: top, width: Math.max(3, x1 - x0), height: bottom - top },
          style: { fill: it.emphasis === 2 ? SELECTED_FILL : NO_FILL, stroke: INK, lineWidth: it.emphasis ? 2.5 : 1.3,
                   lineDash: BOX_DASH, opacity },
        }, {
          type: 'polygon',
          shape: { points: [[xs, top + 1], [xs - 4.5, bottom], [xs + 4.5, bottom]] },
          style: { fill: it.pos ? POS_FILL : NEG_FILL, stroke: INK, lineWidth: 1.2, opacity },
        }]
        if (it.letter) {
          children.push({ type: 'text', style: { text: it.letter, x: xs + 6, y: bottom, align: 'left', verticalAlign: 'bottom',
                                                 font: `bold 9.5px ${MONO}`, fill: INK, opacity } })
        }
        return { type: 'group', children }
      },
    }, ...cmp],
  }
}

/** compare 的三个系列:轨上的 event(压在框下)、灰条右端的 tier tag(压在框上)、bracket 轨上的 hit。 */
function buildCompareSeries(dates: readonly string[], d: LaneDraw): any[] {
  const c = d.compare
  if (!c || !dates.length) return []
  // event:每个一行数据 [起点下标, 终点下标, 顶, 同一行下一个的起点(-1 = 没有)];画法按行号另存
  const items: { key: string; start: number; end: number; top: number; color: string; tip: string;
                 tag: ReturnType<typeof tierTagOf>; boxes: [number, number][] }[] = []
  c.app.forEach((la, i) => {
    const g = d.geom[i]
    if (!g) return
    // 这条轨上用户的框(K 线下标):tier tag 不压框的竖边
    const boxes = (d.lanes[i]?.boxes ?? []).map((lb): [number, number] => [startIndex(dates, lb.box.start), endIndex(dates, lb.box.end)])
    for (const e of la.events) {
      items.push({
        key: `${i}:${e.row}`, start: e.start, end: e.end, top: appBarY(g, la.rows, e.row).top, boxes,
        color: colorOf(e.tier, e.node, c.nodeColors), tag: e.tiered ? tierTagOf(e.tier) : null,
        tip: `${TIER_WORD[e.tier]}<br>${dates[e.start] ?? e.start} – ${dates[e.end] ?? e.end}`,
      })
    }
  })
  const nexts = nextStarts(items)
  const evRows = items.map((it, k) => [it.start, it.end, it.top, nexts[k]])
  const tagIdx = c.tiers ? items.map((it, k) => (it.tag ? k : -1)).filter(k => k >= 0) : []
  const tagRows = tagIdx.map(k => evRows[k])
  const tip = (html: string) => `<span style="font-family:${MONO};color:${INK}">${html}</span>`
  const series: any[] = [{
    type: 'custom', name: 'compare-events', xAxisIndex: 0, yAxisIndex: 0, clip: true,
    data: evRows, encode: { x: [0, 1] }, z: 8,
    tooltip: { formatter: (p: any) => tip(items[p.dataIndex].tip) },
    renderItem: (p: any, api: any) => {
      const [x0, x1] = spanPx(api)
      return { type: 'rect', shape: { x: x0, y: api.value(2), width: Math.max(3, x1 - x0), height: APP_BAR_H },
               style: { fill: items[p.dataIndex].color } }
    },
  }, {
    type: 'custom', name: 'compare-tier-tags', xAxisIndex: 0, yAxisIndex: 0, clip: true,
    data: tagRows, encode: { x: [0, 1] }, z: 12,
    tooltip: { formatter: (p: any) => tip(TIER_TAG_TIP[items[tagIdx[p.dataIndex]].tag!]) },
    renderItem: (p: any, api: any) => {
      const it = items[tagIdx[p.dataIndex]]
      const [, x1] = spanPx(api)
      const bw = api.size([1, 0])[0]
      const shape = tierTagShape(it.tag!, x1, api.value(2), APP_BAR_H, tierTagLimit(api, p.coordSys, api.value(3)))
      if (!shape) return { type: 'group', children: [] }
      // tag 横跨了用户框的竖边(左边或右边)就不挂:框边是用户画的,不能被 tag 盖住
      const [t0, t1] = [x1, x1 + TIER_TAG_GAP * 2 + tierTagWidth(it.tag!)]
      const cuts = it.boxes.some(([bs, be]) => [api.coord([bs, 0])[0] - bw / 2, api.coord([be, 0])[0] + bw / 2]
        .some(edge => edge > t0 && edge < t1))
      return cuts ? { type: 'group', children: [] } : shape
    },
  }]
  if (d.bracket) {
    const g = d.bracket.geom
    const hRows = c.hits.map(h => { const { top, bottom } = bracketYRange(g, c.hitRow0 + h.row); return [h.start, h.end, top, bottom] })
    series.push({
      type: 'custom', name: 'compare-hits', xAxisIndex: 0, yAxisIndex: 0, clip: true,
      data: hRows, encode: { x: [0, 1] }, z: 9,
      tooltip: { formatter: (p: any) => {
        const h = c.hits[p.dataIndex]
        return tip(`hit<br>${dates[h.start] ?? h.start} – ${dates[h.end] ?? h.end}`)
      } },
      renderItem: (_p: any, api: any) => {
        const [x0, x1] = spanPx(api)
        return { type: 'rect', shape: { x: x0, y: api.value(2), width: Math.max(3, x1 - x0), height: api.value(3) - api.value(2) },
                 style: { fill: APP_AMBER, stroke: INK, lineWidth: 1 } }
      },
    })
  }
  return series
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
