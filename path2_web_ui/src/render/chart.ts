// ECharts option 构造(纯函数,spec §8.3 方案 B)。类型无关:只依赖 start_idx/end_idx/source_tag + 色。
import type { Bar, EventDict, MatchDict, Level, Tier, Topology } from '../types'
import { colorOf } from './colors'
import { packByBand, packBrackets } from './geometry'
import { isBandVisible, renderGridOf, subBandTagList } from './visible'
import { ctrlState } from './ctrlState'
import {
  BAND_TOP_PAD,
  BAND_BOT_PAD,
  BAND_LANE_H,
  BAND_MARKER_H,
  BAND_LANE_GAP,
  HL_EXPAND_H,
  HL_EXPAND_OFFSET,
  SUB_DIVIDER_COLOR,
  SUB_DIVIDER_H,
  BAND_INNER_LINE_COLOR,
  BAND_INNER_LINE_H,
  SUB_GRID_LEFT,
  SUB_GRID_RIGHT,
  type BandGeom,
  type SubGeometry,
} from './subGeometry'

// ─── 新签名 ──────────────────────────────────────────────────────────────────

export interface TooltipClauseRow {
  cid: string
  node: string
  measured: unknown
  op: string | null
  threshold: unknown
  satisfied: boolean
  depth: number
  kind: string | null
  /** 树线前缀(├ └ │ + 空格),由 visible.flattenChildren 按兄弟位置算好;顶层为 ''。 */
  guide?: string
}

export interface TooltipPayload {
  identity: {
    nodes: string[]
    dateStart: string
    dateEnd: string | null
    eventId: string
  }
  clauses: TooltipClauseRow[]
  raw: Record<string, unknown>
}

export interface BandRenderInput {
  topology: Topology
  isolatedNodeIds: Set<string>
  tagList: string[]                                   // band 顺序(= deriveTagMap(topology.nodes).tagList)
  level: Level                                        // 门控档
  nodeColors: Record<string, string>
  eventTier: (e: EventDict) => Tier
  nodeOfEventByBand: (e: EventDict) => string | null
  bandKeyOf: (e: EventDict) => string
  // ── nodeVisible: nodeId→false=隐藏;缺键=可见 ──────────────────────────────
  nodeVisible?: Record<string, boolean>
  // tagToNodes: bandKey → nodeId[],用于 nodeVisible 联查 ──────────────────────
  tagToNodes?: Record<string, string[]>
  // ── D2 可选扩展 ─────────────────────────────────────────────────────────────
  selectedEventId?: string | null
  tooltipResolver?: (eventId: string) => TooltipPayload
  // ── 缓冲窗/label 扩展(均可选,旧调用零改动) ──────────────────────────────────
  strictWindow?: { startIdx: number; endIdx: number } | null   // 严格窗边界(bar 索引);缺省不画
  matchLabel?: (matchId: string) => string | null              // match 归属带 tooltip 行;null 不显示
  // ── dataZoom slider 显隐(可选,默认 true=显示,与历史行为一致) ──────────────
  sliderShow?: boolean
  // ── zoom 区间覆盖:传入则跳过 strictWindow 默认,保留用户当前 zoom(KlineChart
  //    render 时从 chart.getOption().dataZoom[0] 读出再回传,实现"非换股触发
  //    re-render 时不重置 zoom")。缺省/null = 走 strictWindow 默认,旧调用零回归。
  zoomOverride?: { start: number; end: number } | null
  // §7-4 整治：bracket marker 同时承载 match_id + 端点 event_id,让 buildMarkerTooltipFormatter
  // 的 event 三段分支也能触发。endNode 来自 eval_meta(铁律必有);缺省=不注入 event_id(向后兼容)
  endNode?: string
  // ── M #3 / M' #19: bracket 三态 fill ────────────────────────────────────────
  selectedMatchId?: string | null
  candidateMatchIds?: ReadonlySet<string>
  // ── Task 5: highlight 三分支(group / focus / pendingDisambig) ───────────────
  highlightedEventIds?: ReadonlySet<string>
  pendingDisambigEventId?: string | null
  // ── spec 2026-07-10: 入口 D shift+click 已选中 marker 描边高亮 ────────────
  shiftSelectedEventIds?: ReadonlySet<string>
  matches?: MatchDict[]  // buildSubOption 的 markerTooltip formatter 用（自 KlineChart.vue 透传）
  // ── 副图 band 竖直 zoom(spec 2026-07-03):由 KlineChart 传入,default 1.0 ──────
  zoomFactor?: number
}

// ─── Task 5: 共享 event 数据抽取(供 buildMainOption/buildSubOption 消费) ──────

export interface EventBundle {
  pointData: any[]
  intervalData: any[]
  pricePointData: any[]
  satelliteData: any[]
  bracketData: any[]
  highlightData: any[]
  highlightPriceData: any[]
  // ── spec 2026-07-11: shift+click 累积器命中 marker 的白蒙+黑线 overlay 数据 ──
  veilData: any[]         // 副图 point + interval
  veilPriceData: any[]    // 主图 pricePoint + satellite
  candle: number[][]
  volume: number[]
  dates: string[]
}

export function computeEventData(
  bars: Bar[], events: EventDict[], matches: MatchDict[],
  input: BandRenderInput,
): EventBundle {
  const { topology, tagList, level, nodeColors, eventTier, nodeOfEventByBand, bandKeyOf,
          nodeVisible, tagToNodes, selectedEventId, endNode,
          highlightedEventIds: _highlightedEventIds,
          pendingDisambigEventId: _pendingDisambigEventId,
          shiftSelectedEventIds: _shiftSelectedEventIds } = input
  const highlightedEventIds = _highlightedEventIds ?? new Set<string>()
  const pendingDisambigEventId = _pendingDisambigEventId ?? null
  const shiftSelectedEventIds = _shiftSelectedEventIds ?? new Set<string>()
  // 副图分轨只含 time 轴 tag;render_grid='price' 的 tag(bo)不占轨道
  const subTags = subBandTagList(tagList, topology)

  const dates = bars.map((b) => b.date)
  const candle = bars.map((b) => [b.o, b.c, b.l, b.h])
  const volume = bars.map((b) => b.v)

  // ── level 门控 + nodeVisible band 筛选 ──
  const RANK: Record<Level, number> = { matched: 2, qualified: 1, detected: 0 }
  const filtered = events.filter((e) =>
    RANK[eventTier(e)] >= RANK[level] && isBandVisible(bandKeyOf(e), nodeVisible, tagToNodes)
  )
  const priceAnchored = filtered.filter((e) => renderGridOf(e, topology, bandKeyOf) === 'price')
  const timeAnchored = filtered.filter((e) => renderGridOf(e, topology, bandKeyOf) !== 'price')

  const eColor = (e: EventDict): string =>
    colorOf(eventTier(e), nodeOfEventByBand(e), nodeColors)

  // pkBarIndices
  const pkBarIndices = new Set<number>()
  for (const e of priceAnchored) {
    const rp = e.referenced_points
    if (Array.isArray(rp)) {
      for (const [barIdx] of rp as Array<[number, number, string]>) {
        pkBarIndices.add(barIdx)
      }
    }
  }

  const pricePointData = priceAnchored.map((e) => {
    const bar = bars[e.start_idx]
    const y = bar ? bar.h * 1.005 : 0
    const anchorY = bar ? bar.h : 0
    const ids = Array.isArray(e.broken_peak_ids) ? (e.broken_peak_ids as number[]) : []
    const text = '[' + ids.join(',') + ']'
    const hasPks = pkBarIndices.has(e.start_idx)
    return {
      value: [e.start_idx, y],
      event_id: e.event_id,
      tier: eventTier(e),
      itemStyle: { color: eColor(e) },
      anchorY, text, hasPks,
    }
  })

  const satelliteData: any[] = []
  for (const e of priceAnchored) {
    const rp = e.referenced_points
    if (!rp || !Array.isArray(rp)) continue
    for (const [barIdx, price, label] of rp as Array<[number, number, string]>) {
      const m = typeof label === 'string' ? /^pk(\d+)$/.exec(label) : null
      const pkId = m ? m[1] : (label ?? '')
      const anchorBar = bars[barIdx]
      satelliteData.push({
        value: [barIdx, price],
        event_id: e.event_id,
        label,
        itemStyle: { color: eColor(e) },
        anchorY: anchorBar ? anchorBar.h : price,
        pkId,
      })
    }
  }

  // 合并 spot + span 一并送 packByBand,同 band 内共享同一次 packLanes 分 lane
  // (spec 2026-07-13:spot 从 band 中心固定位置改为参与 lane packing,消除视觉重叠 bug)
  const packedAll = packByBand(timeAnchored, subTags, bandKeyOf)
  const intervalData: any[] = []
  const pointData: any[] = []
  for (const e of packedAll) {
    const isPoint = e.start_idx === e.end_idx
    const record = {
      value: [e.start_idx, e.end_idx, e.lane, e.band, e.nBands],
      event_id: e.event_id,
      tier: eventTier(e),
      itemStyle: { color: eColor(e) },
    }
    if (isPoint) pointData.push(record)
    else intervalData.push(record)
  }

  const brackets = packBrackets(matches)
  const bracketData = brackets.map((m) => {
    const data: { value: number[]; match_id: string; event_id?: string } = {
      value: [m.start_idx, m.end_idx, m.lane, m.ordinal],
      match_id: m.event_id,
    }
    if (endNode) {
      const v = m.node_index?.[endNode]
      const eid = Array.isArray(v) ? v[0] : v
      if (eid) data.event_id = eid
    }
    return data
  })

  // highlight overlay 三分支
  type HlKind = 'group' | 'focus' | 'pendingDisambig'
  const highlightData: any[] = []
  const highlightPriceData: any[] = []

  // group 条目跳过 selectedEventId:被点 marker 由 focus 条目独家表达
  // (放大实心版双条目 = 同坐标双阴影,被点者投影会明显深于组员)。
  if (highlightedEventIds.size > 0) {
    const inGroup = (id: string) => highlightedEventIds.has(id) && id !== selectedEventId
    for (const d of pointData) {
      if (inGroup(d.event_id)) highlightData.push({ ...d, kind: 'group' as HlKind })
    }
    for (const d of intervalData) {
      if (inGroup(d.event_id)) highlightData.push({ ...d, kind: 'group' as HlKind })
    }
    for (const d of pricePointData) {
      if (inGroup(d.event_id)) highlightPriceData.push({ ...d, kind: 'group' as HlKind })
    }
  }
  if (pendingDisambigEventId) {
    const pd = pointData.find((d) => d.event_id === pendingDisambigEventId)
    if (pd) highlightData.push({ ...pd, kind: 'pendingDisambig' as HlKind })
    else {
      const pi = intervalData.find((d) => d.event_id === pendingDisambigEventId)
      if (pi) highlightData.push({ ...pi, kind: 'pendingDisambig' as HlKind })
      else {
        const pp = pricePointData.find((d) => d.event_id === pendingDisambigEventId)
        if (pp) highlightPriceData.push({ ...pp, kind: 'pendingDisambig' as HlKind })
      }
    }
  }
  if (selectedEventId) {
    const selPoint = pointData.find((d) => d.event_id === selectedEventId)
    if (selPoint) highlightData.push({ ...selPoint, kind: 'focus' as HlKind })
    else {
      const selInterval = intervalData.find((d) => d.event_id === selectedEventId)
      if (selInterval) highlightData.push({ ...selInterval, kind: 'focus' as HlKind })
      else {
        const selPricePoint = pricePointData.find((d) => d.event_id === selectedEventId)
        if (selPricePoint) highlightPriceData.push({ ...selPricePoint, kind: 'focus' as HlKind })
      }
    }
  }

  // ── spec 2026-07-11: shift-veil overlay 数据(z2:22 独立层,fill 白蒙 + 黑横线) ──
  const veilData: any[] = []
  const veilPriceData: any[] = []
  if (shiftSelectedEventIds.size > 0) {
    for (const d of pointData) {
      if (shiftSelectedEventIds.has(d.event_id))
        veilData.push({ ...d, kind: 'point' })
    }
    for (const d of intervalData) {
      if (shiftSelectedEventIds.has(d.event_id))
        veilData.push({ ...d, kind: 'interval' })
    }
    for (const d of pricePointData) {
      if (shiftSelectedEventIds.has(d.event_id))
        veilPriceData.push({ ...d, kind: 'pricePoint' })
    }
    for (const d of satelliteData) {
      if (shiftSelectedEventIds.has(d.event_id))
        veilPriceData.push({ ...d, kind: 'satellite' })
    }
  }

  return {
    pointData, intervalData, pricePointData, satelliteData,
    bracketData, highlightData, highlightPriceData,
    veilData, veilPriceData,
    candle, volume, dates,
  }
}

// ─── buildMainOption / buildSubOption(消费同一份 EventBundle,双 ECharts 实例架构)──

export function buildMainOption(
  bars: Bar[], bundle: EventBundle, input: BandRenderInput,
  opts?: { getChartEl?: () => HTMLElement | null },
): unknown {
  const { strictWindow, sliderShow, zoomOverride,
          tooltipResolver, matchLabel, candidateMatchIds } = input
  const { dates, candle, pricePointData, satelliteData, highlightPriceData, veilPriceData } = bundle

  const N = bars.length
  const sw = strictWindow ?? null
  const hasBuffer = sw !== null && (sw.startIdx > 0 || sw.endIdx < N - 1)
  const zoomStart = zoomOverride?.start ?? (hasBuffer ? (sw!.startIdx / N) * 100 : 0)
  const zoomEnd   = zoomOverride?.end   ?? (hasBuffer ? ((sw!.endIdx + 1) / N) * 100 : 100)
  // y 轴计算窗口跟随最终生效的 zoom(而非固定 strictWindow/全窗),口径与
  // KlineChart.vue datazoom handler 一致:否则 zoom-in 后全量 render 时 y 轴按全窗
  // 价格范围算 → 可见段在低价区时 K 线压底、上方留白。无 zoomOverride 时数学回退到
  // 旧值(zoomStart=(sw.startIdx/N)*100 换算回 sw.startIdx,余同)。max 兜极窄 zoom
  // 致空切片(Math.min(...[])=Infinity)。
  const initVisStart = Math.max(0, Math.round((zoomStart / 100) * N))
  const initVisEnd = Math.max(initVisStart, Math.min(N - 1, Math.round((zoomEnd / 100) * N) - 1))

  const { volSeries, yAxisOverride } = buildVolumeSeriesAndYAxis(bars, initVisStart, initVisEnd)
  const shadingMarkArea = sw ? buildShadingMarkArea(bars, bars[sw.startIdx].date, bars[sw.endIdx].date) : null

  const klineSeries: Record<string, unknown> = {
    type: 'candlestick', name: 'kline', data: candle, xAxisIndex: 0, yAxisIndex: 0,
    barWidth: '70%',
    itemStyle: {
      borderWidth: 2,
      color: '#47b262',
      color0: '#eb5454',
      borderColor: '#47b262',
      borderColor0: '#eb5454',
    },
  }
  if (shadingMarkArea) klineSeries.markArea = shadingMarkArea

  // G2: item-trigger + 无 axisPointer 字段(axisPointer 挂 xAxis/yAxis 组件级)
  const tooltip = {
    trigger: 'item' as const,
    confine: true,
    appendToBody: true,
    formatter: buildBarTooltipFormatter(bars),
  }

  const markerTooltip = (tooltipResolver || matchLabel)
    ? { trigger: 'item' as const, show: true, confine: false,
        position: opts?.getChartEl ? makeViewportAwarePosition(opts.getChartEl) : viewportAwareTooltipPosition,
        extraCssText: 'max-height: calc(100vh - 16px); overflow-y: auto;',
        formatter: buildMarkerTooltipFormatter(tooltipResolver, matchLabel,
          { matches: input.matches ?? [], candidateMatchIds: candidateMatchIds ?? new Set() }) }
    : undefined

  return {
    animation: false,
    tooltip,
    // axisPointer.link 删除:双实例 echarts.connect 接管
    grid: [{ left: 56, right: 16, top: 40, bottom: (sliderShow ?? true) ? 60 : 20 }],
    xAxis: [{
      type: 'category', data: dates, gridIndex: 0, boundaryGap: true,
      axisLine: { onZero: false }, splitLine: { show: false },
      min: 'dataMin', max: 'dataMax',
      // G2 视觉隐:真实竖线由 CrosshairOverlay(DOM)一根到底渲染,axisPointer 只留 hover 事件源(修 S3)
      axisPointer: {
        show: true, type: 'none', snap: true,
        label: { show: false },
        triggerTooltip: false,
      },
    }],
    yAxis: [{
      gridIndex: 0, splitArea: { show: true }, min: yAxisOverride.min, max: yAxisOverride.max,
      axisLabel: { formatter: (v: number) => Math.abs(v) >= 100 ? v.toFixed(0)
                                          : Math.abs(v) >= 1 ? v.toFixed(2)
                                          : v.toFixed(3) },
      // G2 橙色 Price 标签(Ctrl 模式,Ctrl subscriber toggle show)
      axisPointer: {
        show: false, type: 'line', snap: false,
        lineStyle: { color: '#FF6600', type: 'dashed', width: 1 },
        label: {
          show: true,
          formatter: (p: { value: number | string }) => `Price: ${(+p.value).toFixed(2)}`,
          backgroundColor: '#FF6600', color: '#fff',
        },
        triggerTooltip: false,
      },
    }],
    dataZoom: [
      { type: 'inside', xAxisIndex: 0, start: zoomStart, end: zoomEnd },
      { type: 'slider', xAxisIndex: 0, top: '92%', start: zoomStart, end: zoomEnd,
        show: sliderShow ?? true },
    ],
    series: [
      klineSeries,
      volSeries,
      // kline-hit-spanner: 透明覆盖整列,让 grid0 任意 y hover 触发 K-bar OHLC
      { type: 'custom', name: 'kline-hit-spanner', xAxisIndex: 0, yAxisIndex: 0,
        data: bars.map((_, i) => [i]),
        renderItem: renderHitSpanner,
        encode: { x: 0 }, z: 0, zlevel: 0, silent: false, animation: false,
        tooltip: { show: true, confine: true,
                   formatter: buildBarTooltipFormatter(bars) } },
      { type: 'custom', name: 'price-points', xAxisIndex: 0, yAxisIndex: 0,
        data: pricePointData, renderItem: makeRenderPricePoint(pricePointData),
        encode: { x: 0, y: 1 }, z: 12, clip: false, tooltip: markerTooltip },
      { type: 'custom', name: 'satellites', xAxisIndex: 0, yAxisIndex: 0,
        data: satelliteData, renderItem: makeRenderSatellite(satelliteData),
        encode: { x: 0, y: 1 }, z: 13, clip: false, tooltip: markerTooltip },
      // animation:true 同副图 highlight 系列:series 级显式开关放行 keyframeAnimation(pending 闪烁)
      { type: 'custom', name: 'highlight-price', xAxisIndex: 0, yAxisIndex: 0,
        data: highlightPriceData, animation: true,
        renderItem: makeRenderPricePointHighlight(highlightPriceData),
        encode: { x: 0, y: 1 }, z: 21, clip: false, tooltip: markerTooltip },
      { type: 'custom', name: 'shift-veil-price', xAxisIndex: 0, yAxisIndex: 0,
        data: veilPriceData, animation: false, silent: true,
        renderItem: makeRenderShiftVeilPrice(veilPriceData),
        z: 22 },
    ],
  }
}

// Task 3: 副图装饰几何 graphic 组件数组构造(独立于 dataZoom,像素坐标)
// spec: docs/superpowers/specs/2026-07-01-path2-web-subchart-fixed-decor-design.md
// 返回顺序: zebra(z=1) → subDivider(z=2) + band-inner splitLine(z=2) → bandLabels/matchesLabel(z=5)
// 用于 buildSubOption 的 option.graphic 字段;所有元素 silent=true 避免抢 hover 事件。
export function buildSubDecorGraphics(
  bandGeom: BandGeom[],
  dividerY: number,
  bracketH: number,
  bandLabelTexts: string[],
  matchesLabelVisible: boolean,
  chartSubWidth: number,
  zoomFactor: number = 1.0,
): any[] {
  const graphics: any[] = []
  const rectWidth = chartSubWidth - SUB_GRID_LEFT - SUB_GRID_RIGHT

  // 1. zebra: 每 band 一条 rect,隔行 fill
  bandGeom.forEach((g, bi) => {
    graphics.push({
      type: 'rect',
      left: SUB_GRID_LEFT,
      top: g.top,
      shape: { width: rectWidth, height: g.h },
      style: { fill: bi % 2 === 0 ? 'rgba(0,0,0,0.03)' : 'rgba(0,0,0,0)' },
      z: 1,
      silent: true,
    })
  })

  // 2. subDivider: 1 条 2px 横线,bracket 与 band 之间
  graphics.push({
    type: 'rect',
    left: SUB_GRID_LEFT,
    top: dividerY - SUB_DIVIDER_H / 2,
    shape: { width: rectWidth, height: SUB_DIVIDER_H },
    style: { fill: SUB_DIVIDER_COLOR },
    z: 2,
    silent: true,
  })

  // 3. band 内 lane splitLine: 相邻 lane 之间 1px 线
  bandGeom.forEach((g) => {
    if (g.laneCount <= 1) return
    for (let lane = 0; lane < g.laneCount - 1; lane++) {
      // 分隔线落在 lane 与 lane+1 之间 gap 末端(自顶向下堆叠口径);乘 z 修 zoom 错位
      const topY = g.top + BAND_TOP_PAD + (lane + 1) * BAND_LANE_H * zoomFactor
      graphics.push({
        type: 'rect',
        left: SUB_GRID_LEFT,
        top: topY - BAND_INNER_LINE_H / 2,
        shape: { width: rectWidth, height: BAND_INNER_LINE_H },
        style: { fill: BAND_INNER_LINE_COLOR },
        z: 2,
        silent: true,
      })
    }
  })

  // 4. bandLabels: 每 band 一个 text,靠 band 上边(top pad = BAND_TOP_PAD),grid 左侧 +2 px
  //    ⚠ textAlign / textVerticalAlign 必须放元素顶层 —— style 内是 zrender TextStyle,
  //    键名是 align/verticalAlign,写 textVerticalAlign 会被静默无视。
  //    verticalAlign: 'top' + top = band 顶 + pad → label 顶部对齐 band 顶部内边距,
  //    单/多 lane 视觉统一(不再随 band 高度浮到中间/下半)。
  bandGeom.forEach((g, bi) => {
    const text = bandLabelTexts[bi] ?? ''
    graphics.push({
      type: 'text',
      left: SUB_GRID_LEFT + 2,
      top: g.top + BAND_TOP_PAD,
      textAlign: 'left',
      textVerticalAlign: 'top',
      style: {
        text,
        fill: '#424242',
        fontSize: 13,
      },
      z: 5,
      silent: true,
    })
  })

  // 5. matchesLabel: bracket 区左侧文字(仅在 matchesLabelVisible=true 时),同款靠上对齐
  if (matchesLabelVisible) {
    graphics.push({
      type: 'text',
      left: SUB_GRID_LEFT + 2,
      top: BAND_TOP_PAD,   // 与 bandLabels 的 pad 锚定语义对称(unify 顶 pad)
      textAlign: 'left',
      textVerticalAlign: 'top',
      style: {
        text: 'matches',
        fill: '#424242',
        fontSize: 13,
      },
      z: 5,
      silent: true,
    })
  }

  return graphics
}

export function buildSubOption(
  bars: Bar[], bundle: EventBundle, subGeom: SubGeometry, input: BandRenderInput,
  chartSubWidth: number,
  opts?: { getChartEl?: () => HTMLElement | null },
): unknown {
  const { tooltipResolver, matchLabel, zoomOverride, strictWindow,
          selectedMatchId, candidateMatchIds } = input
  const { dates, pointData, intervalData, bracketData, highlightData, veilData } = bundle
  const z = input.zoomFactor ?? 1.0   // 副图 band 竖直 zoom(spec 2026-07-03)

  const N = bars.length
  const sw = strictWindow ?? null
  const hasBuffer = sw !== null && (sw.startIdx > 0 || sw.endIdx < N - 1)
  const zoomStart = zoomOverride?.start ?? (hasBuffer ? (sw!.startIdx / N) * 100 : 0)
  const zoomEnd   = zoomOverride?.end   ?? (hasBuffer ? ((sw!.endIdx + 1) / N) * 100 : 100)

  const markerTooltip = (tooltipResolver || matchLabel)
    ? { trigger: 'item' as const, show: true, confine: false,
        position: opts?.getChartEl ? makeViewportAwarePosition(opts.getChartEl) : viewportAwareTooltipPosition,
        extraCssText: 'max-height: calc(100vh - 16px); overflow-y: auto;',
        formatter: buildMarkerTooltipFormatter(tooltipResolver, matchLabel,
          { matches: input.matches ?? [], candidateMatchIds: candidateMatchIds ?? new Set() }) }
    : undefined

  // 装饰几何(zebra/subDivider/bandLabels/matchesLabel)改走 option.graphic,不再挂 series
  const bandLabelTexts = subBandTagList(input.tagList, input.topology)
  const matchesLabelVisible = bracketData.length > 0
  const decorGraphics = buildSubDecorGraphics(
    subGeom.bandGeom,
    subGeom.dividerY,
    subGeom.bracketH,
    bandLabelTexts,
    matchesLabelVisible,
    chartSubWidth,
    z,
  )

  return {
    animation: false,
    // 顶层 tooltip 关闭,marker 三系列各自带 markerTooltip(item-trigger)覆盖
    // appendToBody+confine:tooltip DOM 挂 document.body(非 .sub-inner),避免撑高 sub-outer 滚动条(修 S1)
    tooltip: { trigger: 'item' as const, show: false, appendToBody: true, confine: true },
    grid: [{ left: SUB_GRID_LEFT, right: SUB_GRID_RIGHT, top: 0, bottom: 0 }],
    graphic: decorGraphics,
    xAxis: [{
      type: 'category', data: dates, gridIndex: 0, boundaryGap: true,
      axisLine: { onZero: false }, axisLabel: { show: false }, splitLine: { show: false },
      // 副图 axisPointer 视觉隐:真实竖线由 CrosshairOverlay(DOM)一根到底渲染(修 S3)
      // manual sync(KlineChart.vue relay)负责主图 hover x 同步过来
      axisPointer: {
        show: true, type: 'none', snap: true,
        label: { show: false },
        triggerTooltip: false,
      },
    }],
    yAxis: [{ scale: true, gridIndex: 0, show: false }],
    dataZoom: [{ type: 'inside', xAxisIndex: 0, start: zoomStart, end: zoomEnd }],
    series: [
      // intervals (z:9)
      { type: 'custom', name: 'intervals', xAxisIndex: 0, yAxisIndex: 0,
        data: intervalData,
        renderItem: (p: any, api: any) => renderIntervalWithGeom(p, api, subGeom.bandGeom, z),
        encode: { x: [0, 1] }, z: 9, tooltip: markerTooltip },
      // points (z:10)
      { type: 'custom', name: 'points', xAxisIndex: 0, yAxisIndex: 0,
        data: pointData,
        renderItem: (p: any, api: any) => renderPointWithGeom(p, api, subGeom.bandGeom, z),
        encode: { x: 0 }, z: 10, tooltip: markerTooltip },
      // brackets (z:11)。focus 信号:selectedMatchId 存在且无 selectedEventId ⟺ bracket
      // 本身是被点者(KlineChart.ts bracket 分支 selectEvent(null);marker 分支必设 eventId)
      { type: 'custom', name: 'brackets', xAxisIndex: 0, yAxisIndex: 0,
        data: bracketData,
        renderItem: makeRenderBracket(bracketData, selectedMatchId ?? null, candidateMatchIds ?? new Set(), z,
          (selectedMatchId ?? null) !== null && (input.selectedEventId ?? null) === null),
        encode: { x: [0, 1] }, z: 11, tooltip: markerTooltip,
        emphasis: { disabled: true } },
      // highlight (z:20)。animation:true 为 series 级显式开关:keyframeAnimation(pending 闪烁)
      // 被 isAnimationEnabled() 闸住,继承顶层 animation:false 会整体跳过动画。
      // 图形绘制全在 shape 字段,不涉及默认 x/y transition,无过渡副作用。
      { type: 'custom', name: 'highlight', xAxisIndex: 0, yAxisIndex: 0,
        data: highlightData, animation: true,
        renderItem: makeRenderHighlightWithGeom(highlightData, subGeom.bandGeom, z),
        encode: { x: 0 }, z: 20, tooltip: markerTooltip },
      // shift-veil (z:22 高于 highlight,spec 2026-07-11):fill 白蒙 + 黑横线,与 highlight 三分支正交
      { type: 'custom', name: 'shift-veil', xAxisIndex: 0, yAxisIndex: 0,
        data: veilData, animation: false, silent: true,
        renderItem: makeRenderShiftVeil(veilData, subGeom.bandGeom, z),
        z: 22 },
    ],
  }
}

// ── renderItem 原语(ECharts custom series;api 见 §0.6) ──

// 隐形 spanner:每根 bar 一个透明 rect,覆盖整列 x(barWidth)+ grid0 整 y 全幅。
// 复刻 dev_ui 的"全 ax 监听 + round to nearest bar"语义:鼠标在 grid0 任意 y 都能命中、触发 K-bar OHLC tooltip。
// fill 用接近透明 rgba 而非 'transparent'/opacity:0 — 保证 zrender hit-test 不被某些版本优化跳过。
function renderHitSpanner(params: any, api: any) {
  const x = api.coord([api.value(0), 0])[0]
  const colWidth = api.size([1, 0])[0]
  const grid = params.coordSys  // cartesian2d: { x, y, width, height }
  return {
    type: 'rect' as const,
    shape: {
      x: x - colWidth / 2,
      y: grid.y,
      width: colWidth,
      height: grid.height,
    },
    style: { fill: 'rgba(0,0,0,0.001)' },
    silent: false,
  }
}

// 选中词汇(2026-07-08 改):三档皆保 node/tier 分色(matched=node本色,qualified/detected=灰),
// group=细深边, focus=粗深边;琥珀不再代表选中。AMBER_FILL 仅剩 bracket 默认底(bracket 无 tier 语义)。
const AMBER_FILL = '#fbbf24'      // bracket 默认底(琥珀,非选中语义)
const HL_FOCUS_EDGE = '#1e293b'   // slate-800(group/focus 深边、BO 文本、bracket 序号)
const HL_STROKE = '#fbbf24'       // 收窄:仅 pendingDisambig 白底垫层的琥珀边消费
const HL_FOCUS_STROKE_WIDTH = 2.5
const HL_GROUP_STROKE_WIDTH = 1.5
const HL_SHADOW = { shadowBlur: 6, shadowColor: 'rgba(15,23,42,0.4)', shadowOffsetY: 2 } as const

// 闪烁关键帧(每次调用新建对象——zrender 内部状态会污染共享常量)。
// ⚠ keyframeAnimation 受 series 级 isAnimationEnabled() 闸控(实测):顶层 animation:false
// 会连带跳过它,highlight / highlight-price 系列必须显式 animation:true。
export function pendingBlinkAnimation() {
  return {
    duration: 1200,
    loop: true,
    keyframes: [
      { percent: 0, style: { opacity: 1 } },
      { percent: 0.5, style: { opacity: 0.45 } },
      { percent: 1, style: { opacity: 1 } },
    ],
  }
}

// 按三态装配放大版图形(2026-07-08 改):group/focus 都保 node/tier 分色,
// 靠边框粗细区分——group=细深边(1.5)、focus=粗深边(2.5),琥珀不再代表选中。
// color 由 itemStyle.color 传入,已按 colorOf 三档分:matched=node本色 / qualified=中灰 / detected=浅灰。
// 放大实心版盖住下层本体 marker → 一律 silent:true 让 hover/click 穿透到本体系列。
// pending 分层固定:白底垫层(阴影+琥珀边恒定)+ 本色 fill 层(单独闪)。
// 禁止本色静态垫层——fill 闪暗时露出同色垫层 = 视觉不闪(c94baf7 同构陷阱)。
function buildHlShape(
  base: { type: string; shape: Record<string, unknown> },
  kind: 'group' | 'focus' | 'pendingDisambig',
  color: string,
  z2: number,
): Record<string, unknown> {
  if (kind === 'group') {
    return {
      ...base,
      style: { fill: color, stroke: HL_FOCUS_EDGE, lineWidth: HL_GROUP_STROKE_WIDTH, ...HL_SHADOW },
      silent: true, z2,
    }
  }
  if (kind === 'focus') {
    return {
      ...base,
      style: { fill: color, stroke: HL_FOCUS_EDGE, lineWidth: HL_FOCUS_STROKE_WIDTH, ...HL_SHADOW },
      silent: true, z2,
    }
  }
  return {
    type: 'group',
    silent: true, z2,
    children: [
      { ...base, style: { fill: '#ffffff', stroke: HL_STROKE, lineWidth: HL_FOCUS_STROKE_WIDTH, ...HL_SHADOW } },
      { ...base, style: { fill: color }, keyframeAnimation: pendingBlinkAnimation() },
    ],
  }
}

// 主图 price-anchored bo 盒放大版(grid0 价格轴)。实心放大版遮住本体文字 →
// 重画盒+文本(字号不变)。stackOffset 与 renderPricePoint 同步按 hasPks 切换。
// 2026-07-08 改:同 buildHlShape,group/focus 保 tier 分色(matched=橙/灰) + 细/粗深边;
// 文字色全 tier 统一 HL_FOCUS_EDGE(灰底可读,橙底可读);pending 白底+闪烁分层不动。
// ⚠ closure factory:ECharts customSeries 不在 params 中传 data item,必须按 dataIndex 反查。
export function makeRenderPricePointHighlight(
  data: Array<{ value: number[]; event_id: string; anchorY: number; text: string; hasPks: boolean;
                 itemStyle: { color: string };
                 kind: 'group' | 'focus' | 'pendingDisambig' }>,
) {
  return function renderPricePointHighlight(params: any, api: any) {
    const item = data[params.dataIndex] ?? null
    const hlKind = item?.kind ?? 'focus'
    const anchorY = item?.anchorY ?? api.value(1)
    const text = item?.text ?? ''
    const hasPks = item?.hasPks ?? false
    const color = item?.itemStyle?.color ?? '#888888'
    const [cx, anchorPx] = api.coord([api.value(0), anchorY])
    const stackOffset = hasPks ? BO_STACK_PT : BO_STACK_PT_NO_PKS
    const cy = anchorPx - stackOffset
    const { w, h } = boBoxDims(text)
    const pad = 3
    const boxShape = {
      x: cx - w / 2 - pad, y: cy - h / 2 - pad,
      width: w + 2 * pad, height: h + 2 * pad, r: BO_BOX_RADIUS + pad,
    }
    const textEl = {
      type: 'text',
      style: { text, x: cx, y: cy, fill: HL_FOCUS_EDGE, fontSize: MARKER_FONT_SIZE,
               fontWeight: 'bold', align: 'center', verticalAlign: 'middle' },
    }
    const children: any[] = hlKind === 'pendingDisambig'
      ? [
          { type: 'rect', shape: boxShape,
            style: { fill: '#ffffff', stroke: HL_STROKE, lineWidth: HL_FOCUS_STROKE_WIDTH, ...HL_SHADOW } },
          { type: 'rect', shape: boxShape, style: { fill: color },
            keyframeAnimation: pendingBlinkAnimation() },
          textEl,
        ]
      : [
          { type: 'rect', shape: boxShape,
            style: hlKind === 'group'
              ? { fill: color, stroke: HL_FOCUS_EDGE, lineWidth: HL_GROUP_STROKE_WIDTH, ...HL_SHADOW }
              : { fill: color, stroke: HL_FOCUS_EDGE, lineWidth: HL_FOCUS_STROKE_WIDTH, ...HL_SHADOW } },
          textEl,
        ]
    return { type: 'group', silent: true, z2: 21, children }
  }
}

// ─── 副图 renderer(独立坐标,消费 computeSubGeometry 派生的 bandGeom) ───────
// (bandZebra/subDivider/matchesLabel/bandLabels 4 个 renderer 已随 Task 4 迁移到
//  buildSubDecorGraphics 的 option.graphic 装配,不再需要 ECharts custom series renderItem)

// renderIntervalWithGeom / renderPointWithGeom:改从 bandGeom 派生 bandTop/bandH
export function renderIntervalWithGeom(
  params: any,
  api: any,
  bandGeom: BandGeom[],
  zoomFactor: number = 1.0,
) {
  const x0 = api.coord([api.value(0), 0])[0]
  const x1 = api.coord([api.value(1), 0])[0]
  const lane = api.value(2) || 0
  const band = api.value(3) || 0
  const g = bandGeom[band]
  if (!g) return { type: 'group', children: [] }
  const laneH = BAND_MARKER_H * zoomFactor
  const gap = BAND_LANE_GAP * zoomFactor
  // 自顶向下堆叠:lane0 贴 band 顶 pad(与 bracket 区方向一致,spec 2026-07-03-bracket-band-unify)
  const rawY = g.top + BAND_TOP_PAD + lane * (laneH + gap)
  const y = Math.max(g.top + BAND_TOP_PAD, Math.min(rawY, g.top + g.h - BAND_BOT_PAD - laneH))
  return {
    type: 'rect',
    shape: { x: x0, y, width: Math.max(2, x1 - x0), height: laneH },
    style: api.style(),
  }
}

export function renderPointWithGeom(
  params: any,
  api: any,
  bandGeom: BandGeom[],
  zoomFactor: number = 1.0,   // 副图 band 竖直 zoom(spec 2026-07-03)
) {
  const x = api.coord([api.value(0), 0])[0]
  const lane = api.value(2) || 0
  const band = api.value(3) || 0
  const g = bandGeom[band]
  if (!g) return { type: 'group', children: [] }
  const laneH = BAND_MARKER_H * zoomFactor
  const gap = BAND_LANE_GAP * zoomFactor
  const centerY = g.top + BAND_TOP_PAD + lane * (laneH + gap) + laneH / 2
  const unitW = api.size([1, 0])[0]
  const w = Math.max(5, Math.min(20, unitW * 0.35))
  return {
    type: 'polygon',
    shape: { points: [[x, centerY + 4 * zoomFactor], [x - w, centerY - 3 * zoomFactor], [x + w, centerY - 3 * zoomFactor]] },
    style: api.style(),
  }
}

// makeRenderHighlightWithGeom:point/interval 分支都从 bandGeom 派生。
// 画放大实心版(非描边框):group/focus 单图形,pending 白底+闪烁双层,见 buildHlShape。
export function makeRenderHighlightWithGeom(
  items: Array<{ value: number[]; event_id: string; itemStyle?: { color?: string };
                 kind: 'group' | 'focus' | 'pendingDisambig' }>,
  bandGeom: BandGeom[],
  zoomFactor: number = 1.0,   // 副图 band 竖直 zoom(spec 2026-07-03)
) {
  return function renderHighlight(params: any, api: any) {
    const item = items[params.dataIndex]
    const hlKind = item?.kind ?? 'focus'
    const color = item?.itemStyle?.color ?? '#888888'
    // pointData/intervalData 均为 5 元组(spec 2026-07-13),不能再用 length 判别;
    // 改用 start!==end(与 computeEventData 里 isPoint = start_idx===end_idx 同一口径)。
    const isInterval = item ? item.value[0] !== item.value[1] : false
    if (!isInterval) {
      const x = api.coord([api.value(0), 0])[0]
      const lane = (item?.value?.[2] as number) || 0
      const band = (item?.value?.[3] as number) || 0
      const g = bandGeom[band]
      if (!g) return { type: 'group', children: [] }
      const laneH = BAND_MARKER_H * zoomFactor
      const gap = BAND_LANE_GAP * zoomFactor
      const centerY = g.top + BAND_TOP_PAD + lane * (laneH + gap) + laneH / 2
      const unitW = api.size([1, 0])[0]
      // 本体三角(renderPointWithGeom):高 7(+4/−3)、半宽 ≤20;放大版:高 10(+6/−4)、半宽 ×1.4
      const w = Math.max(7, Math.min(28, unitW * 0.35 * 1.4))
      const base = {
        type: 'polygon',
        shape: { points: [[x, centerY + 6 * zoomFactor], [x - w, centerY - 4 * zoomFactor], [x + w, centerY - 4 * zoomFactor]] },
      }
      return buildHlShape(base, hlKind, color, 20)
    } else {
      const x0 = api.coord([api.value(0), 0])[0]
      const x1 = api.coord([api.value(1), 0])[0]
      const lane = (item?.value?.[2] as number) || 0
      const band = (item?.value?.[3] as number) || 0
      const g = bandGeom[band]
      if (!g) return { type: 'group', children: [] }
      const laneH = BAND_MARKER_H * zoomFactor
      const gap = BAND_LANE_GAP * zoomFactor
      const rawY = g.top + BAND_TOP_PAD + lane * (laneH + gap)
      const y = Math.max(g.top + BAND_TOP_PAD, Math.min(rawY, g.top + g.h - BAND_BOT_PAD - laneH))
      // 放大版:高 laneH→laneH+3z 居中外扩(offset −1.5z),比例恒 10/7,长度不变(时间跨度语义);
      // 共享常量 HL_EXPAND_*(与 makeRenderBracket 选中态同一组数,spec §3.1)
      const base = {
        type: 'rect',
        shape: { x: x0, y: y - HL_EXPAND_OFFSET * zoomFactor, width: Math.max(2, x1 - x0),
                 height: laneH + HL_EXPAND_H * zoomFactor },
      }
      return buildHlShape(base, hlKind, color, 20)
    }
  }
}

// ── spec 2026-07-11: shift-veil 副图 renderer(point + interval,fill 白蒙 + 黑横线) ──
// 每条 veil 数据一个 group,children = [半透明白蒙 shape, 黑横线],
// 复用与 renderPointWithGeom / renderIntervalWithGeom 同一 shape 派生逻辑。
// silent:true → hover/click 穿透到本体 marker;z2:22 高于 highlight overlay(21)。
export function makeRenderShiftVeil(
  items: Array<{ value: number[]; event_id: string; kind: 'point' | 'interval' }>,
  bandGeom: BandGeom[],
  zoomFactor: number = 1.0,
) {
  return function renderShiftVeil(params: any, api: any) {
    const item = items[params.dataIndex] ?? null
    if (!item) return { type: 'group', children: [] }

    if (item.kind === 'point') {
      // 参 renderPointWithGeom:三角 polygon,底顶点在下、两上角在上
      const x = api.coord([api.value(0), 0])[0]
      const lane = api.value(2) || 0
      const band = api.value(3) || 0
      const g = bandGeom[band]
      if (!g) return { type: 'group', children: [] }
      const laneH = BAND_MARKER_H * zoomFactor
      const gap = BAND_LANE_GAP * zoomFactor
      const centerY = g.top + BAND_TOP_PAD + lane * (laneH + gap) + laneH / 2
      const unitW = api.size([1, 0])[0]
      const w = Math.max(5, Math.min(20, unitW * 0.35))
      const triPoints = [
        [x, centerY + 4 * zoomFactor],
        [x - w, centerY - 3 * zoomFactor],
        [x + w, centerY - 3 * zoomFactor],
      ]
      const lineLen = w * 2 * 0.7   // 横线长度 = 三角底宽 × 0.7
      return {
        type: 'group',
        silent: true,
        z2: 22,
        children: [
          { type: 'polygon', shape: { points: triPoints },
            style: { fill: 'rgba(255,255,255,0.45)', stroke: 'none' } },
          { type: 'line',
            shape: { x1: x - lineLen / 2, y1: centerY, x2: x + lineLen / 2, y2: centerY },
            style: { stroke: '#000000', lineWidth: HL_FOCUS_STROKE_WIDTH } },
        ],
      }
    }

    // interval 分支:参 renderIntervalWithGeom
    const x0 = api.coord([api.value(0), 0])[0]
    const x1 = api.coord([api.value(1), 0])[0]
    const lane = api.value(2) || 0
    const band = api.value(3) || 0
    const g = bandGeom[band]
    if (!g) return { type: 'group', children: [] }
    const laneH = BAND_MARKER_H * zoomFactor
    const gap = BAND_LANE_GAP * zoomFactor
    const rawY = g.top + BAND_TOP_PAD + lane * (laneH + gap)
    const y = Math.max(g.top + BAND_TOP_PAD, Math.min(rawY, g.top + g.h - BAND_BOT_PAD - laneH))
    const width = Math.max(2, x1 - x0)
    const midY = y + laneH / 2
    const lineLen = width * 0.7
    const lineCenterX = x0 + width / 2
    return {
      type: 'group',
      silent: true,
      z2: 22,
      children: [
        { type: 'rect', shape: { x: x0, y, width, height: laneH },
          style: { fill: 'rgba(255,255,255,0.45)', stroke: 'none' } },
        { type: 'line',
          shape: { x1: lineCenterX - lineLen / 2, y1: midY,
                   x2: lineCenterX + lineLen / 2, y2: midY },
          style: { stroke: '#000000', lineWidth: HL_FOCUS_STROKE_WIDTH } },
      ],
    }
  }
}

// ── spec 2026-07-11: shift-veil 主图 renderer(pricePoint + satellite,fill 白蒙 + 黑横线) ──
export function makeRenderShiftVeilPrice(
  items: Array<{ value: number[]; event_id: string; kind: 'pricePoint' | 'satellite';
                 anchorY?: number; text?: string; hasPks?: boolean }>,
) {
  return function renderShiftVeilPrice(params: any, api: any) {
    const item = items[params.dataIndex] ?? null
    if (!item) return { type: 'group', children: [] }

    if (item.kind === 'pricePoint') {
      // 参 makeRenderPricePoint:圆角矩形背景,box 中心 = anchorPx - stackOffset
      const anchorY = item.anchorY ?? api.value(1)
      const text = item.text ?? ''
      const hasPks = item.hasPks ?? false
      const [cx, anchorPx] = api.coord([api.value(0), anchorY])
      const stackOffset = hasPks ? BO_STACK_PT : BO_STACK_PT_NO_PKS
      const cy = anchorPx - stackOffset
      const { w, h } = boBoxDims(text)
      const lineLen = w * 0.7
      return {
        type: 'group',
        silent: true,
        z2: 22,
        children: [
          { type: 'rect',
            shape: { x: cx - w / 2, y: cy - h / 2, width: w, height: h, r: BO_BOX_RADIUS },
            style: { fill: 'rgba(255,255,255,0.45)', stroke: 'none' } },
          { type: 'line',
            shape: { x1: cx - lineLen / 2, y1: cy, x2: cx + lineLen / 2, y2: cy },
            style: { stroke: '#000000', lineWidth: HL_FOCUS_STROKE_WIDTH } },
        ],
      }
    }

    // satellite 分支:参 makeRenderSatellite,倒三角(顶点在下,两上角在上)
    // 三角形 fill='none' 原本空心;白蒙给 fill 半透明白,让原轮廓仍在、内部变白
    const anchorY = item.anchorY ?? api.value(1)
    const [cx, anchorPx] = api.coord([api.value(0), anchorY])
    const triCy = anchorPx - TRIANGLE_STACK_PT
    const tw = PK_TRIANGLE_HALF_WIDTH
    const th = PK_TRIANGLE_HEIGHT
    const triPoints = [
      [cx - tw, triCy - th / 2],
      [cx + tw, triCy - th / 2],
      [cx,      triCy + th / 2],
    ]
    const lineLen = 2 * tw * 0.7
    return {
      type: 'group',
      silent: true,
      z2: 22,
      children: [
        { type: 'polygon', shape: { points: triPoints },
          style: { fill: 'rgba(255,255,255,0.45)', stroke: 'none' } },
        { type: 'line',
          shape: { x1: cx - lineLen / 2, y1: triCy, x2: cx + lineLen / 2, y2: triCy },
          style: { stroke: '#000000', lineWidth: HL_FOCUS_STROKE_WIDTH } },
      ],
    }
  }
}

// bracket:副图独立坐标(canvas 局部 y=0 起,见 subGeometry.ts 几何约定)。
// 几何与 band interval 统一(spec 2026-07-03-bracket-band-unify):本体高 BAND_MARKER_H*z、
// stride BAND_LANE_H*z、区顶 BAND_TOP_PAD 呼吸;选中放大 +HL_EXPAND_H*z / −HL_EXPAND_OFFSET*z
// (比例恒 10/7)。
// 选中词汇(2026-07-08 改):bracket 默认底改为琥珀 AMBER_FILL(琥珀不再代表选中);
// selected 非 focus = 琥珀 + 细深边 + shadow(与 marker in-group 一致);
// focusOnBracket = 琥珀 + 粗深边 + shadow;candidate = 0.35 琥珀底 + 琥珀虚线边不动。
export function makeRenderBracket(
  items: Array<{ match_id: string }>,
  selectedMatchId: string | null,
  candidateMatchIds: ReadonlySet<string>,
  zoomFactor: number = 1.0,
  focusOnBracket: boolean = false,
) {
  return function renderBracket(params: any, api: any) {
    const x0 = api.coord([api.value(0), 0])[0]
    const x1 = api.coord([api.value(1), 0])[0]
    const lane = api.value(2) || 0
    const top = BAND_TOP_PAD + lane * BAND_LANE_H * zoomFactor
    const rectH = BAND_MARKER_H * zoomFactor
    const matchId: string | undefined = items[params.dataIndex]?.match_id
    const isSelected = !!matchId && selectedMatchId === matchId
    const isCandidate = !isSelected && !!matchId && candidateMatchIds.has(matchId)
    const fill = isCandidate ? 'rgba(251,191,36,0.35)' : AMBER_FILL
    // 选中:居中外扩 + 投影(组员悬浮语义)。
    // 居中外扩后中心不变(−1.5z + (h+3z)/2 = rectH/2)→ 序号 text 的 y 公式不动。
    const rectShape = isSelected
      ? { x: x0, y: top - HL_EXPAND_OFFSET * zoomFactor, width: Math.max(2, x1 - x0),
          height: rectH + HL_EXPAND_H * zoomFactor }
      : { x: x0, y: top, width: Math.max(2, x1 - x0), height: rectH }
    const rectStyle = isSelected
      ? (focusOnBracket
          ? { fill, stroke: HL_FOCUS_EDGE, lineWidth: HL_FOCUS_STROKE_WIDTH, ...HL_SHADOW }
          : { fill, stroke: HL_FOCUS_EDGE, lineWidth: HL_GROUP_STROKE_WIDTH, ...HL_SHADOW })
      : isCandidate
        ? { fill, stroke: '#f59e0b', lineWidth: 1.5, lineDash: [4, 3] }
        : { fill }
    return {
      type: 'group',
      children: [
        { type: 'rect', shape: rectShape, style: rectStyle },
        { type: 'text',
          style: { text: '①②③④⑤⑥⑦⑧⑨'[(api.value(3) - 1) % 9] ?? '·',
                   x: x1 + 4, y: top + rectH / 2,
                   fill: '#334155', fontSize: 12,
                   textAlign: 'left', textVerticalAlign: 'middle' } },
      ],
    }
  }
}

// ─── dev UI 视觉常量(对齐 BreakoutStrategy/UI/styles.py CHART_COLORS / MARKER_STACK_GAPS_PT
//     / BO_LABEL_TIER_STYLE;rubric=docs/tmp/2026-06-21-bo-pk-marker-rubric.md)──────────────
// 整组数值相对 dev pt 值按 ~0.6 比例缩放,补偿 web grid 容器较窄、相对蜡烛宽度偏大的视觉。
// 20pt @ 96dpi = 26.67 px;0.6× ≈ 16 px。
const MARKER_FONT_SIZE = 16            // dev fontsize=20pt;web px=16 ≈ 0.6× 视觉对齐
const PK_TRIANGLE_HALF_WIDTH = 8       // ▽ 半宽,对应 dev s=400 (≈20pt 边长) 0.6× 缩放
const PK_TRIANGLE_HEIGHT = 12
const PEAK_MARKER_COLOR = '#000000'    // CHART_COLORS["peak_marker"]
const PEAK_TEXT_COLOR = '#000000'      // CHART_COLORS["peak_text_id"]
const BO_BOX_RADIUS = 4
const BO_BOX_PAD_X = 5
const BO_BOX_PAD_Y = 3
// 堆叠 px 偏移(锚 K 线 high 之上,自下而上):▽ → ID → [ids]
// dev UI styles.py:80-86 用 pt(triangle=20/peak_id=35/bo_label=65 有 PK,bo_label=15 无 PK)
// web 端按字号 16 等比缩:三角中心 13、ID 中心 28、BO 中心 48(有 PK)/15(无 PK)
const TRIANGLE_STACK_PT = 13           // ▽ 中心 y = anchor - 13
const PEAK_ID_STACK_PT = 28            // ID 中心 y = anchor - 28
const BO_STACK_PT = 48                 // [ids] 中心 y = anchor - 48(hasPks=true 时)
// hasPks=false:同 bar 无 PK,BO 单独贴近 K 线 high(dev styles.py:80 bo_label=15pt 缩放对应)。
// 这是 HEAD 相对 94e21934 的胜出语义点 — 按是否同 bar 有 PK 动态切换偏移。
const BO_STACK_PT_NO_PKS = 15

// 文本框尺寸(浏览器无 measureText 时按字宽近似,bold 字体 char_w ≈ 0.62×fontSize)
function boBoxDims(text: string): { w: number; h: number } {
  const charW = MARKER_FONT_SIZE * 0.62
  const textW = Math.max(charW, text.length * charW)
  return {
    w: textW + 2 * BO_BOX_PAD_X,
    h: MARKER_FONT_SIZE + 2 * BO_BOX_PAD_Y,
  }
}

// price-anchored bo 主 marker: 圆角矩形蓝框 + [broken_peak_ids] 文本(dev UI 复刻)。
// 锚 bar.h(anchorY 由 computeEventData 注入),box 中心 = anchorPx - stackOffset。
// stackOffset 按 hasPks 切换(保留自 HEAD 的胜出语义):
//   hasPks=true  → BO_STACK_PT=50(同 bar 有 PK 三角,堆叠在 PK ID 之上)
//   hasPks=false → BO_STACK_PT_NO_PKS=15(无 PK,BO 单独贴近 bar.h,对齐 dev 15pt)
// ⚠ closure factory:ECharts customSeries 不在 params 中传 data item,必须按 dataIndex 反查。
//   过去用 (params.data as any).text 实测=undefined → text 为空字符串 → ZRText 被创建但无文字渲染。
function makeRenderPricePoint(
  data: Array<{ value: number[]; event_id: string; anchorY: number; text: string;
                 tier: Tier; hasPks: boolean; itemStyle: { color: string } }>,
) {
  return function renderPricePoint(params: any, api: any) {
    const item = data[params.dataIndex] ?? null
    const anchorY = item?.anchorY ?? api.value(1)
    const text = item?.text ?? ''
    const hasPks = item?.hasPks ?? false
    const color = item?.itemStyle?.color ?? '#888888'
    const [cx, anchorPx] = api.coord([api.value(0), anchorY])
    const stackOffset = hasPks ? BO_STACK_PT : BO_STACK_PT_NO_PKS
    const cy = anchorPx - stackOffset
    const { w, h } = boBoxDims(text)
    return {
      type: 'group',
      children: [
        // 1. 圆角矩形背景(按 tier 分色:matched=橙、qualified/detected=灰;无边框)
        {
          type: 'rect',
          shape: { x: cx - w / 2, y: cy - h / 2, width: w, height: h, r: BO_BOX_RADIUS },
          style: {
            fill: color,
            opacity: 0.75,
          },
        },
        // 2. 文本(居中,粗体,统一深灰蓝——橙/灰底皆可读)
        {
          type: 'text',
          style: {
            text,
            x: cx,
            y: cy,
            fill: HL_FOCUS_EDGE,
            fontSize: MARKER_FONT_SIZE,
            fontWeight: 'bold',
            align: 'center',
            verticalAlign: 'middle',
          },
        },
      ],
    }
  }
}

// 卫星 marker: 每个 referenced_point 渲染 = 空心 ▽ + ID 数字。
// anchorY=bars[bar_idx].h(computeEventData 注入)。锚 K 线 high,堆叠次序自下而上 ▽ → ID。
// ⚠ closure factory:ECharts customSeries 不在 params 中传 data item,必须按 dataIndex 反查。
function makeRenderSatellite(
  data: Array<{ value: number[]; event_id: string; label: string; itemStyle: object;
                 anchorY: number; pkId: string }>,
) {
  return function renderSatellite(params: any, api: any) {
    const item = data[params.dataIndex] ?? null
    const anchorY = item?.anchorY ?? api.value(1)
    const pkId = item?.pkId ?? ''
    const [cx, anchorPx] = api.coord([api.value(0), anchorY])
    // ▽ 中心
    const triCy = anchorPx - TRIANGLE_STACK_PT
    const tw = PK_TRIANGLE_HALF_WIDTH
    const th = PK_TRIANGLE_HEIGHT
    // ID 文本中心(▽ 上方)
    const idCy = anchorPx - PEAK_ID_STACK_PT
    return {
      type: 'group',
      children: [
        // 1. 空心 ▽ 倒三角(顶点在下,两上角在上)— 黑边、无填充
        {
          type: 'polygon',
          shape: {
            points: [
              [cx - tw, triCy - th / 2],   // 左上
              [cx + tw, triCy - th / 2],   // 右上
              [cx,      triCy + th / 2],   // 下顶点
            ],
          },
          style: {
            fill: 'none',
            stroke: PEAK_MARKER_COLOR,
            lineWidth: 1.2,
          },
        },
        // 2. ID 数字(▽ 正上方,黑色粗体居中,无背景框)
        {
          type: 'text',
          style: {
            text: pkId,
            x: cx,
            y: idCy,
            fill: PEAK_TEXT_COLOR,
            fontSize: MARKER_FONT_SIZE,
            fontWeight: 'bold',
            align: 'center',
            verticalAlign: 'middle',
          },
        },
      ],
    }
  }
}

// ─── Pure helpers (Dev UI 复刻) ───────────────────────────────────────────────

/**
 * 计算两段灰色阴影 markArea: [bars[0], bars[startIdx-1]] 和 [bars[endIdx+1], bars[last]]。
 * Off-by-one 修正: bars[startIdx] 和 bars[endIdx] 本身落在白区。
 *
 * @param bars       完整 bars 数组
 * @param scanStart  严格 scan 窗起始日期 (YYYY-MM-DD)
 * @param scanEnd    严格 scan 窗结束日期 (YYYY-MM-DD)
 * @returns          markArea 配置；scan 窗覆盖全集时返回 null
 */
export function buildShadingMarkArea(
  bars: Bar[], scanStart: string, scanEnd: string,
): { itemStyle: { color: string; opacity: number }; silent: true; data: Array<[{ xAxis: number }, { xAxis: number }]> } | null {
  if (bars.length === 0) return null
  const startIdx = bars.findIndex(b => b.date >= scanStart)
  if (startIdx < 0) return null
  let endIdx = -1
  for (let i = bars.length - 1; i >= 0; i--) {
    if (bars[i].date <= scanEnd) { endIdx = i; break }
  }
  if (endIdx < 0) return null
  const data: Array<[{ xAxis: number }, { xAxis: number }]> = []
  if (startIdx > 0) data.push([{ xAxis: 0 }, { xAxis: startIdx - 1 }])
  if (endIdx < bars.length - 1) data.push([{ xAxis: endIdx + 1 }, { xAxis: bars.length - 1 }])
  if (data.length === 0) return null
  return {
    itemStyle: { color: '#808080', opacity: 0.15 },
    silent: true,
    data,
  }
}

/**
 * Dev UI 1:1 复刻 — volume 叠加进价格区底部 20% 高度带。
 *
 * 计算可见区间 priceMin/Max → displayHeight = priceRange / 0.8 → displayBottom 留 10% 底部空白。
 * volScale = (displayHeight * 0.2) / visVolMax，每根 bar 的 value = displayBottom + b.v * volScale。
 *
 * displayBottom 钳到 ≥ 0：ECharts bar 的 baseline 恒为 value=0，无法像 matplotlib 那样
 * 显式指定 bottom。若 priceMin < priceRange/8 导致 displayBottom 算成负数（低价股），
 * 0 进入 yAxis 范围，volume bar 就会以 0 为基线双向溢出（小成交量 bar 朝下挂在 0 下方）。
 * 钳到 ≥ 0 后 0 永远 ≤ yAxis.min，bar 被 clip 后视觉等价于"从 grid 底向上单向"。代价：
 * 低价股底部 10% 价格 padding 被压扁、K 线最低点贴 axis 底；高价股完全无影响。
 *
 * @param bars      完整 bars 数组
 * @param visStart  可见区间起始 bar 索引（含）
 * @param visEnd    可见区间结束 bar 索引（含）
 */
export function buildVolumeSeriesAndYAxis(bars: Bar[], visStart: number, visEnd: number) {
  const visBars = bars.slice(visStart, visEnd + 1)
  const priceMin = Math.min(...visBars.map(b => b.l))
  const priceMax = Math.max(...visBars.map(b => b.h))
  const priceRange = priceMax - priceMin
  const displayHeight = priceRange / 0.8
  const displayBottom = Math.max(0, priceMin - displayHeight * 0.1)
  const displayTop = displayBottom + displayHeight
  const visVolMax = Math.max(...visBars.map(b => b.v), 1)
  const volScale = (displayHeight * 0.2) / visVolMax

  const volSeries = {
    type: 'bar' as const,
    name: 'volume' as const,
    xAxisIndex: 0 as const,
    yAxisIndex: 0 as const,
    barWidth: '100%' as const,
    z: 3 as const,
    // 纯展示 series,不接受 hit-event:让 hover volume bar 的鼠标事件 fall-through 到
    // 下面的 kline-hit-spanner (z=0) 触发 K-bar OHLC tooltip。未来若 volume 需要独立
    // tooltip,关掉 silent 并加 tooltip.formatter 即可。
    silent: true as const,
    data: bars.map(b => ({
      value: displayBottom + b.v * volScale,
      itemStyle: {
        color: b.c >= b.o ? '#D3D3D3' : '#696969',
        borderColor: 'black',
        borderWidth: 0.5,
        opacity: 0.5,
      },
    })),
  }
  return {
    volSeries,
    yAxisOverride: { min: displayBottom, max: displayTop },
  }
}

/**
 * Viewport-aware tooltip position(borrowed from dev UI BreakoutStrategy/UI/charts/tooltip_anchor.py 思路)。
 *
 * 用于 markerTooltip 的 ECharts position 字段:显式 confine tooltip 到 window viewport,
 * 不只 chart 矩形——ECharts 内置 confine 用的是 chart canvas 维度,当 chart_bottom == viewport_bottom
 * 时,tooltip 起点 + 尺寸仍可能出 viewport 底(R5T2 实测 90px 溢出)。
 *
 * 设计要点:
 * - point 是 chart-local 坐标(zr 像素,R3 tom 报告 §B Q1 校正过)
 * - appendToBody:true 时,ECharts 把返回值经 transformLocalCoord 转 body-local
 *   → 我们仍返回 chart-local;但内部 flip 决策用 viewport 页坐标做
 * - size.contentSize 是当次 tooltip 实际 DOM 尺寸(R3 tom 报告 §B Q3)
 * - 配合 confine:false 才能让本 position fn 输出不被 ECharts 二次钳到 chart 矩形
 * - 兜底:tooltip 比 viewport 还高时贴顶(extraCssText max-height 会截 + scroll)
 */
function viewportAwareTooltipPosition(
  point: [number, number],
  _params: unknown,
  dom: HTMLElement,
  _rect: unknown,
  size: { contentSize: [number, number]; viewSize: [number, number] },
): [number, number] {
  const [tooltipW, tooltipH] = size.contentSize
  const margin = 8
  // chart-local point → 页坐标(用 dom 在 body,沿父链找 echarts 容器 rect)
  const chartEl = (dom.ownerDocument || document).querySelector('[_echarts_instance_]')
  const chartRect = chartEl
    ? (chartEl as HTMLElement).getBoundingClientRect()
    : { left: 0, top: 0 }
  const cursorPageX = chartRect.left + point[0]
  const cursorPageY = chartRect.top + point[1]
  // 默认 right-down,溢 viewport 则 flip
  let pageX = cursorPageX + margin
  if (pageX + tooltipW > window.innerWidth - margin) {
    pageX = cursorPageX - tooltipW - margin
  }
  if (pageX < margin) pageX = margin
  let pageY = cursorPageY + margin
  if (pageY + tooltipH > window.innerHeight - margin) {
    pageY = cursorPageY - tooltipH - margin
  }
  if (pageY < margin) pageY = margin
  // 兜底:tooltip 比 viewport 还高,贴顶(extraCssText max-height 会截断 + scroll)
  if (pageY + tooltipH > window.innerHeight - margin) {
    pageY = margin
  }
  // 返回 chart-local(ECharts 会经 transformLocalCoord 转回 body-local 因 appendToBody:true)
  return [pageX - chartRect.left, pageY - chartRect.top]
}

/**
 * Viewport-aware tooltip position factory —— 双实例架构下必须用此 factory 传入
 * 正确的源 chart element getter,否则 querySelector('[_echarts_instance_]') 返回
 * DOM 第一个匹配(通常 chartMain),副图 markerTooltip 的 flip 判定会拿到错的
 * chartRect(cursorPageY 少了副图 top offset)导致不翻转、tooltip 超屏。
 * 逻辑与 legacy `viewportAwareTooltipPosition` 一致,只是 chartRect 源改自参数。
 */
export function makeViewportAwarePosition(getChartEl: () => HTMLElement | null) {
  return function viewportAwarePositionFn(
    point: [number, number],
    _params: unknown,
    _dom: HTMLElement,
    _rect: unknown,
    size: { contentSize: [number, number]; viewSize: [number, number] },
  ): [number, number] {
    const [tooltipW, tooltipH] = size.contentSize
    const margin = 8
    const chartEl = getChartEl()
    const chartRect = chartEl
      ? chartEl.getBoundingClientRect()
      : { left: 0, top: 0 }
    const cursorPageX = chartRect.left + point[0]
    const cursorPageY = chartRect.top + point[1]
    let pageX = cursorPageX + margin
    if (pageX + tooltipW > window.innerWidth - margin) {
      pageX = cursorPageX - tooltipW - margin
    }
    if (pageX < margin) pageX = margin
    let pageY = cursorPageY + margin
    if (pageY + tooltipH > window.innerHeight - margin) {
      pageY = cursorPageY - tooltipH - margin
    }
    if (pageY < margin) pageY = margin
    if (pageY + tooltipH > window.innerHeight - margin) {
      pageY = margin
    }
    return [pageX - chartRect.left, pageY - chartRect.top]
  }
}

/**
 * Bar tooltip formatter (G2: candlestick item-trigger)。
 * 8 行: Date / Open / High / Low / Close / Chg / Volume / RV
 *
 * G2 改动:
 * - 删 Ctrl 模式 Price:{mouseY} 分支(挪到 yAxis[0].axisPointer.label.formatter)
 * - 删 ctrlState 入参(无外部消费者)
 * - 接受 item-trigger 单 param(候选 axis-trigger array 兼容回滚,实际线上只走 item-trigger)
 */
export function buildBarTooltipFormatter(bars: Bar[]) {
  return (
    params: { seriesName?: string; dataIndex?: number } | Array<{ seriesName?: string; dataIndex?: number }>,
  ): string => {
    // item-trigger:单 param;axis-trigger:array(本 G2 不走此路径,但兼容防回滚)
    // 允许 candlestick 'kline' 与 spanner 'kline-hit-spanner' 共享同一 OHLC formatter
    const isKlineSrc = (n?: string) => n === 'kline' || n === 'kline-hit-spanner'
    const p = Array.isArray(params) ? params.find(x => isKlineSrc(x.seriesName)) : params
    if (!p || !isKlineSrc(p.seriesName) || typeof p.dataIndex !== 'number') return ''
    const idx = p.dataIndex
    const b = bars[idx]
    if (!b) return ''
    const prev = idx > 0 ? bars[idx - 1] : null
    let chgStr: string
    if (prev) {
      const chg = (b.c - prev.c) / prev.c * 100
      const sign = chg >= 0 ? '+' : ''
      chgStr = `${sign}${chg.toFixed(2)}%`
    } else {
      chgStr = 'N/A'
    }
    const rvStr = b.rv > 0 ? b.rv.toFixed(2) : 'N/A'
    const volStr = Math.round(b.v).toLocaleString('en-US')
    return [
      `Date: ${b.date}`,
      `Index: ${idx}`,
      `<hr/>Open:  ${b.o.toFixed(2)}`,
      `High:  ${b.h.toFixed(2)}`,
      `Low:   ${b.l.toFixed(2)}`,
      `Close: ${b.c.toFixed(2)}`,
      `<hr/>Chg:   ${chgStr}`,
      `Volume: ${volStr}`,
      `RV:    ${rvStr}`,
    ].join('<br/>')
  }
}

/**
 * Marker tooltip formatter (series-level item-trigger)。
 * 三段结构 + 可选 match 顶行：
 *   - 顶行 (仅 params.data.match_id 命中)：Match: {matchLabel(id)}
 *   - 段 1 Identity：node / time / id
 *   - 段 2 Clauses：失败 ✗ 置顶 + 加粗；多 node 同 cid 行末加 (in: <node>)
 *   - 段 3 Attributes：raw（已去重）
 *
 * 段空时省略段头；身份段恒存在但 node 行可省。
 * HTML：使用 <br/> <b> <hr>（echarts tooltip formatter 支持）。
 * 注：当前 measured 类型受控（数字 / 字符串 / 元组），不引入 HTML escape；
 *     未来若 detector 引入用户输入字符串型 measured 且可能含 HTML，
 *     需在 fmtNum 旁追加 escape 步骤。
 * spec 见 docs/superpowers/specs/2026-06-29-marker-tooltip-cleanup-design.md
 */
export function buildMarkerTooltipFormatter(
  tooltipResolver: ((eventId: string) => TooltipPayload) | undefined,
  matchLabel: ((matchId: string) => string | null) | undefined,
  ctx: { matches: MatchDict[]; candidateMatchIds: ReadonlySet<string> } = { matches: [], candidateMatchIds: new Set() },
) {
  return (params: { data?: { event_id?: string; match_id?: string; [key: string]: unknown } } | null): string => {
    const data = params?.data
    if (!data) return ''
    const lines: string[] = []

    // ── bracket 段：候选首行 + matchLabel + 组成段 (M #15 / M' #25) ────────
    const matchId = data.match_id as string | undefined
    if (matchId) {
      // 候选态首行 (M' #25)
      if (ctx.candidateMatchIds.has(matchId)) {
        lines.push('候选: click 此 bracket 选中该 group')
      }
      // 既有 matchLabel
      if (matchLabel) {
        const ml = matchLabel(matchId)
        if (ml) lines.push(`Match: ${ml}`)
      }
      // 组成段 (M #15)
      const match = ctx.matches.find((m) => m.event_id === matchId)
      if (match) {
        lines.push(`组成 (${match.children.length} events):`)
        for (const [nodeKey, rawVal] of Object.entries(match.node_index)) {
          const val: string | string[] = rawVal as unknown as string | string[]
          if (Array.isArray(val)) {
            const first = val[0] ?? '?'
            lines.push(`  ${nodeKey}: ${first} (×${val.length} kleene)`)
          } else {
            lines.push(`  ${nodeKey}: ${val}`)
          }
        }
      }
    }

    // ── event 三段 ──────────────────────────────────────────────────────
    const eventId = data.event_id as string | undefined
    if (eventId && tooltipResolver) {
      const { identity, clauses, raw } = tooltipResolver(eventId)

      // 段 1 Identity
      const idBody: string[] = []
      if (identity.nodes.length > 0) idBody.push(`node: ${identity.nodes.join(' / ')}`)
      const timeStr = identity.dateEnd == null
        ? `time: ${identity.dateStart}`
        : `time: ${identity.dateStart} → ${identity.dateEnd}`
      idBody.push(timeStr)
      idBody.push(`id:   ${identity.eventId}`)
      lines.push(lines.length > 0 ? '<hr/><b>Identity</b>' : '<b>Identity</b>')
      lines.push(...idBody)

      // 段 2 Clauses（失败已置顶；多 node 同 cid 行末加 (in: <node>)）
      //
      // 层次靠【树线 ├ └ │】显式画出,不靠留白暗示;等宽字体让三列(名/实测/阈值)对齐。
      // 两个正交信道:粗体=顶层 clause(结构),红色=未通过(状态)。此前二者都压在粗体上,
      // 导致深层失败叶子比它的顶层父行还醒目、视觉层级倒置。
      // 组合子行不出 n/m 聚合——子分支恒全量展开(不短路),数字数一眼就有,属冗余。
      if (clauses.length > 0) {
        const cidCounts: Record<string, number> = {}
        for (const c of clauses) if (c.depth === 0) cidCounts[c.cid] = (cidCounts[c.cid] ?? 0) + 1
        // 组合子无 clause_id 时 visible.flattenChildren 用 witness.label 兜底 → cid === kind,
        // 此时不把 kind 印两遍("and (and)");顶层 clause 有真名则保留 "cid (kind)"。
        const cells = clauses.map((c) => ({
          c,
          name: (c.guide ?? '') + (c.kind == null ? c.cid
                                   : c.cid === c.kind ? c.kind : `${c.cid} (${c.kind})`),
          meas: c.kind == null ? fmtNum(c.measured) : '',
          rule: c.kind == null && c.op != null ? `${c.op} ${fmtNum(c.threshold)}` : '',
        }))
        const wName = Math.max(...cells.map((x) => x.name.length))
        const wMeas = Math.max(...cells.map((x) => x.meas.length))
        const wRule = Math.max(...cells.map((x) => x.rule.length))
        const pad = (s: string, w: number) => (s + ' '.repeat(Math.max(0, w - s.length) + 2))
        const clauseLines = cells.map(({ c, name, meas, rule }) => {
          const mark = c.satisfied ? '✓' : '✗'
          const inSuffix = c.depth === 0 && cidCounts[c.cid] > 1 ? ` (in: ${c.node})` : ''
          const body = (pad(name, wName) + pad(meas, wMeas) + pad(rule, wRule) + mark + inSuffix)
            .replace(/ /g, '&nbsp;')
          const colored = c.satisfied ? body : `<span style="color:#d33">${body}</span>`
          return c.depth === 0 ? `<b>${colored}</b>` : colored
        })
        lines.push('<hr/><b>Clauses</b>')
        // 用 span 不用 div:div 是块级,会在 join 的 <br/> 之外再自带一次换行 → 段头后多一空行
        lines.push(`<span style="font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace">`
                   + clauseLines.join('<br/>') + '</span>')
      }

      // 段 3 Attributes（raw 已去重）
      const rawEntries = Object.entries(raw)
      if (rawEntries.length > 0) {
        lines.push('<hr/><b>Attributes</b>')
        for (const [k, v] of rawEntries) lines.push(`${k}: ${fmtNum(v)}`)
      }
    }

    // ── marker 归属节 (M #16, 仅非 bracket marker: 无 match_id) ──────────
    if (!matchId && eventId && ctx.matches.length > 0) {
      // 按 start_idx 排序,与 packBrackets(geometry.ts:47-49)的 ordinal 语义一致;
      // 同时从 sortedByStart 过滤,保证 ordinals 以升序列出
      const sortedByStart = [...ctx.matches].sort((a, b) => a.start_idx - b.start_idx)
      const ownedBy = sortedByStart.filter((m) => m.children.includes(eventId))
      if (ownedBy.length > 0) {
        const ORDINAL_CHARS = '①②③④⑤⑥⑦⑧⑨'
        const ords = ownedBy.map((m) => {
          const ord = sortedByStart.indexOf(m) + 1
          return ord >= 1 && ord <= 9 ? ORDINAL_CHARS[ord - 1] : String(ord)
        })
        lines.push(`归属: match ${ords.join(' ')}`)
      }
    }

    return lines.join('<br/>')
  }
}

/** 浮点统一 4 位小数；整数 / 非数字原样 String 化。 */
function fmtNum(v: unknown): string {
  if (typeof v === 'number' && !Number.isInteger(v)) return v.toFixed(4)
  return String(v)
}
