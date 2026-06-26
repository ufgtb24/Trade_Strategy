// ECharts option 构造(纯函数,spec §8.3 方案 B)。类型无关:只依赖 start_idx/end_idx/source_tag + 色。
import type { Bar, EventDict, MatchDict, Level, Tier, Topology } from '../types'
import { colorOf } from './colors'
import { splitGeometry, packByBand, packBrackets } from './geometry'
import { isBandVisible, renderGridOf } from './visible'
import { ctrlState } from './ctrlState'

// ─── 新签名 ──────────────────────────────────────────────────────────────────

export interface TooltipClause {
  measured: unknown
  op: string | null
  threshold: unknown
  satisfied: boolean
}

export interface TooltipPayload {
  clauses: Record<string, TooltipClause>
  raw: Record<string, unknown>
}

export interface BandRenderInput {
  topology: Topology
  isolatedNodeIds: Set<string>
  tagList: string[]                                   // band 顺序(= deriveTagMap(topology.nodes).tagList)
  level: Level                                        // 门控档
  roleColors: Record<string, string>
  eventTier: (e: EventDict) => Tier
  roleOfEventByBand: (e: EventDict) => string | null
  bandKeyOf: (e: EventDict) => string
  // ── roleVisible: nodeId→false=隐藏;缺键=可见 ──────────────────────────────
  roleVisible?: Record<string, boolean>
  // tagToNodes: bandKey → nodeId[],用于 roleVisible 联查 ──────────────────────
  tagToNodes?: Record<string, string[]>
  // ── D2 可选扩展 ─────────────────────────────────────────────────────────────
  selectedEventId?: string | null
  tooltipResolver?: (eventId: string) => TooltipPayload
  // ── 缓冲窗/label 扩展(均可选,旧调用零改动) ──────────────────────────────────
  strictWindow?: { startIdx: number; endIdx: number } | null   // 严格窗边界(bar 索引);缺省不画
  matchLabel?: (matchId: string) => string | null              // match 归属带 tooltip 行;null 不显示
}

export function buildKlineOption(
  bars: Bar[], events: EventDict[], matches: MatchDict[],
  input: BandRenderInput,
) {
  const { topology, tagList, level, roleColors, eventTier, roleOfEventByBand, bandKeyOf,
          roleVisible, tagToNodes,
          selectedEventId, tooltipResolver, strictWindow, matchLabel } = input

  const dates = bars.map((b) => b.date)
  const candle = bars.map((b) => [b.o, b.c, b.l, b.h])
  const volume = bars.map((b) => b.v)

  // ── level 门控(matched=2,qualified=1,detected=0) + roleVisible band 筛选 ──
  const RANK: Record<Level, number> = { matched: 2, qualified: 1, detected: 0 }
  const filtered = events.filter((e) =>
    RANK[eventTier(e)] >= RANK[level] && isBandVisible(bandKeyOf(e), roleVisible, tagToNodes)
  )

  // ── render_grid 分流: priceAnchored 上 K线主图(grid0); 其余走原 grid2 通道 ──
  const priceAnchored = filtered.filter((e) => renderGridOf(e, topology, bandKeyOf) === 'price')
  const timeAnchored = filtered.filter((e) => renderGridOf(e, topology, bandKeyOf) !== 'price')

  const eColor = (e: EventDict): string =>
    colorOf(eventTier(e), roleOfEventByBand(e), roleColors)

  const { points, intervals } = splitGeometry(timeAnchored)

  // bo 三态映射: selectedEventId 命中 → current; eventTier=matched → matched; 其余 → plain
  // 对齐 dev UI styles.py:BO_LABEL_TIER_STYLE(current=深蓝底白字 / matched=灰底黑字 / plain=白底深蓝字)
  type BoTier = 'current' | 'matched' | 'plain'
  const boTierOf = (e: EventDict): BoTier => {
    if (selectedEventId && e.event_id === selectedEventId) return 'current'
    if (eventTier(e) === 'matched') return 'matched'
    return 'plain'
  }

  // price-anchored 主 marker: dev UI 复刻 = 圆角矩形蓝框 + [broken_peak_ids] 文本
  // - value=[start_idx, bar.h*1.005] 保留作 ECharts 坐标(测试契约 + 旧调用方);
  //   实际渲染锚 anchorY=bar.h,renderItem 内用 pt offset 堆叠在 K 线 high 上方。
  // - text = "[id1,id2,...]"(无空格);broken_peak_ids 缺省 → "[]" 兜底。
  const pricePointData = priceAnchored.map((e) => {
    const bar = bars[e.start_idx]
    const y = bar ? bar.h * 1.005 : 0
    const anchorY = bar ? bar.h : 0
    const ids = Array.isArray(e.broken_peak_ids) ? (e.broken_peak_ids as number[]) : []
    const text = '[' + ids.join(',') + ']'
    return {
      value: [e.start_idx, y],
      event_id: e.event_id,
      tier: eventTier(e),
      itemStyle: { color: eColor(e) },   // 兼容字段;新渲染走 boTier
      // ─ 新字段 ─
      anchorY,
      text,
      boTier: boTierOf(e),
    }
  })

  // satellites: 任何 anchor='price' event 的 referenced_points 平铺渲染。
  // dev UI 复刻 = 空心 ▽ 倒三角(黑边)+ ID 数字(三角正上方,黑色粗体)。
  // label 契约: "pk{id}"(详 path2/atoms/breakout.py:233-235);解析失败回落 label 原样作 ID。
  // value=[bar_idx, price] 保留(测试契约);anchorY=bars[bar_idx].h 用于实际渲染锚 K 线 high。
  const satelliteData: Array<{
    value: number[]; event_id: string; label: string; itemStyle: object;
    anchorY: number; pkId: string;
  }> = []
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

  // intervals → packByBand(各 band 独立 packLanes)
  const packedIntervals = packByBand(intervals, tagList, bandKeyOf)
  const intervalData = packedIntervals.map((e) => ({
    value: [e.start_idx, e.end_idx, e.lane, e.band, e.nBands],
    event_id: e.event_id,
    tier: eventTier(e),
    itemStyle: { color: eColor(e) },
  }))

  // points → band 归行,lane=0
  const pointData = points.map((e) => {
    const band = tagList.indexOf(bandKeyOf(e))
    const nBands = tagList.length
    return {
      value: [e.start_idx, e.start_idx, band < 0 ? 0 : band, nBands],
      event_id: e.event_id,
      tier: eventTier(e),
      itemStyle: { color: eColor(e) },
    }
  })

  // brackets
  const brackets = packBrackets(matches)
  const bracketData = brackets.map((m) => ({
    value: [m.start_idx, m.end_idx, m.lane, m.ordinal], match_id: m.event_id,
  }))

  // bandLabels:在 grid2 左缘每 band 一行文字
  const bandLabelData = tagList.map((tag, band) => {
    const node = topology.nodes.find((n) => n.source_tag === tag)
    const text = node ? (node.label || node.node_id || tag) : tag
    return { value: [0, band, tagList.length], text }
  })

  // ── D2: highlight overlay ─────────────────────────────────────────────────
  // 找到被选中 event(在当前 level 门控后的 filtered 集合里),追加描边高亮系列。
  // price-anchored events → highlightPriceData (grid0); others → highlightData (grid2)
  const highlightData: Array<{ value: number[]; event_id: string; kind: 'point' | 'interval' }> = []
  const highlightPriceData: Array<{ value: number[]; event_id: string; anchorY: number; text: string }> = []
  if (selectedEventId) {
    const selPoint = pointData.find((d) => d.event_id === selectedEventId)
    if (selPoint) {
      highlightData.push({ value: selPoint.value, event_id: selectedEventId, kind: 'point' })
    } else {
      const selInterval = intervalData.find((d) => d.event_id === selectedEventId)
      if (selInterval) {
        highlightData.push({ value: selInterval.value, event_id: selectedEventId, kind: 'interval' })
      } else {
        // price-anchored point events → dedicated grid0 highlight series
        const selPricePoint = pricePointData.find((d) => d.event_id === selectedEventId)
        if (selPricePoint) {
          highlightPriceData.push({
            value: selPricePoint.value,
            event_id: selectedEventId,
            anchorY: selPricePoint.anchorY,
            text: selPricePoint.text,
          })
        }
      }
    }
  }

  // ── Dev UI 复刻: global axis-trigger bar tooltip + 横线锁 close 由 KlineChart.vue 监听 updateAxisPointer 处理 ──
  const tooltip = {
    trigger: 'axis' as const,
    axisPointer: {
      // 普通模式 'line'(只竖线),横线由 KlineChart.vue 的 markLine 锁 close;
      // Ctrl 模式 KlineChart.vue 切回 'cross' 让 ECharts 自带横线跟鼠标。
      type: 'line' as const,
      lineStyle: { color: '#0088CC', type: 'dashed', width: 1.5, opacity: 0.7 },
      label: { show: false },
      snap: true,
    },
    formatter: buildBarTooltipFormatter(bars, ctrlState),
  }

  const markerTooltip = (tooltipResolver || matchLabel)
    ? { trigger: 'item' as const, formatter: buildMarkerTooltipFormatter(tooltipResolver, matchLabel) }
    : undefined

  // ── Dev UI 复刻: grid 3→2、初始 zoom 贴 [startIdx, endIdx]、yAxis[0] 动态 min/max ──
  const N = bars.length
  const sw = strictWindow ?? null
  const hasBuffer = sw !== null && (sw.startIdx > 0 || sw.endIdx < N - 1)
  const zoomStart = hasBuffer ? (sw!.startIdx / N) * 100 : 0
  const zoomEnd = hasBuffer ? ((sw!.endIdx + 1) / N) * 100 : 100

  // 初始可见区间 = 严格 scan 窗（有 buffer）或全集
  const initVisStart = sw ? sw.startIdx : 0
  const initVisEnd = sw ? sw.endIdx : N - 1

  // volume + yAxis override (可见区间口径)
  const { volSeries, yAxisOverride } = buildVolumeSeriesAndYAxis(bars, initVisStart, initVisEnd)

  // 灰阴影 markArea (含 off-by-one 修正)
  const shadingMarkArea = sw
    ? buildShadingMarkArea(bars, bars[sw.startIdx].date, bars[sw.endIdx].date)
    : null

  // kline 系列：删 markLine，加 markArea 阴影
  const klineSeries: Record<string, unknown> = {
    type: 'candlestick', name: 'kline', data: candle, xAxisIndex: 0, yAxisIndex: 0,
  }
  if (shadingMarkArea) {
    klineSeries.markArea = shadingMarkArea
  }

  return {
    animation: false,
    tooltip,
    axisPointer: { link: [{ xAxisIndex: [0, 1] }] },
    grid: [
      { left: 56, right: 16, top: 40, height: '72%' },          // 新 grid0 价格(含 volume 叠加)
      { left: 56, right: 16, top: '76%', height: '18%' },       // 新 grid1 markers (原 grid2)
    ],
    xAxis: [
      { type: 'category', data: dates, gridIndex: 0, boundaryGap: true,
        axisLine: { onZero: false }, splitLine: { show: false }, min: 'dataMin', max: 'dataMax' },
      { type: 'category', data: dates, gridIndex: 1, boundaryGap: true,
        axisLine: { onZero: false }, axisLabel: { show: false }, splitLine: { show: false } },
    ],
    yAxis: [
      // index 0: 价格(grid0)——固定 min/max 让 volume bar baseline 落在 displayBottom
      { gridIndex: 0, splitArea: { show: true }, min: yAxisOverride.min, max: yAxisOverride.max },
      // index 1: 隐藏 bracket 轴(grid0)
      { scale: true, gridIndex: 0, show: false },
      // index 2: 隐藏 marker 轴(grid1)
      { scale: true, gridIndex: 1, show: false },
    ],
    dataZoom: [
      { type: 'inside', xAxisIndex: [0, 1], start: zoomStart, end: zoomEnd },
      { type: 'slider', xAxisIndex: [0, 1], top: '92%', start: zoomStart, end: zoomEnd },
    ],
    series: [
      // 价格蜡烛(grid0)
      klineSeries,
      // 成交量(叠加在 grid0 价格区底部 20%，来自 buildVolumeSeriesAndYAxis)
      volSeries,
      // 点 markers(grid1,隐藏轴 yAxisIndex:2)
      { type: 'custom', name: 'points', xAxisIndex: 1, yAxisIndex: 2, data: pointData,
        renderItem: renderPoint, encode: { x: 0 }, z: 10, tooltip: markerTooltip },
      // 区间 markers(grid1,隐藏轴 yAxisIndex:2)
      { type: 'custom', name: 'intervals', xAxisIndex: 1, yAxisIndex: 2, data: intervalData,
        renderItem: renderInterval, encode: { x: [0, 1] }, z: 9, tooltip: markerTooltip },
      // 归属带 brackets(grid0,隐藏 bracket 轴 yAxisIndex:1)
      { type: 'custom', name: 'brackets', xAxisIndex: 0, yAxisIndex: 1, data: bracketData,
        renderItem: renderBracket, encode: { x: [0, 1] }, z: 11, tooltip: markerTooltip },
      // band 标签(grid1 左缘,低 z),同时叠灰阴影覆盖 grid1
      { type: 'custom', name: 'bandLabels', xAxisIndex: 1, yAxisIndex: 2,
        data: bandLabelData, renderItem: renderBandLabel, encode: { x: 0 }, z: 5,
        markArea: shadingMarkArea ?? undefined,
        tooltip: markerTooltip },
      // D2: 选中 event 描边高亮(最高 z,不影响原 points/intervals)
      { type: 'custom', name: 'highlight', xAxisIndex: 1, yAxisIndex: 2,
        data: highlightData, renderItem: renderHighlight, encode: { x: 0 }, z: 20,
        tooltip: markerTooltip },

      // ── render_grid='price' 主三角(grid0) ──
      // ⚠ ECharts 4/5 customSeries 不在 renderItem(params, api) 的 params 中暴露原始 data item;
      //   `params.data` 实测=undefined。要拿到非 value 维度的字段(text / anchorY / boTier / pkId),
      //   必须用 closure 捕获 *Data 数组、按 params.dataIndex 反查。
      { type: 'custom', name: 'price-points', xAxisIndex: 0, yAxisIndex: 0,
        data: pricePointData,
        renderItem: makeRenderPricePoint(pricePointData),
        encode: { x: 0, y: 1 }, z: 12, tooltip: markerTooltip },

      // ── 卫星 marker(referenced_points → grid0, dot + label) ──
      { type: 'custom', name: 'satellites', xAxisIndex: 0, yAxisIndex: 0,
        data: satelliteData,
        renderItem: makeRenderSatellite(satelliteData),
        encode: { x: 0, y: 1 }, z: 13, tooltip: markerTooltip },

      // D2: 选中 price-anchored event 描边高亮(grid0,置顶)
      { type: 'custom', name: 'highlight-price', xAxisIndex: 0, yAxisIndex: 0,
        data: highlightPriceData,
        renderItem: makeRenderPricePointHighlight(highlightPriceData),
        encode: { x: 0, y: 1 }, z: 21, tooltip: markerTooltip },
    ],
  }
}

// ── renderItem 原语(ECharts custom series;api 见 §0.6) ──

// 点:在其 band 行内画小三角。value=[start_idx, start_idx, band, nBands]
function renderPoint(params: any, api: any) {
  const x = api.coord([api.value(0), 0])[0]
  const band = api.value(2) || 0
  const nBands = api.value(3) || 1
  const cs = params.coordSys
  const bandH = cs.height / nBands
  const bandTop = cs.y + band * bandH
  const centerY = bandTop + bandH / 2
  const w = 5
  return {
    type: 'polygon',
    shape: { points: [[x, centerY + 4], [x - w, centerY - 3], [x + w, centerY - 3]] },
    style: api.style(),
  }
}

// 区间:在其 band 行内按 lane 堆叠。value=[start_idx, end_idx, lane, band, nBands]
function renderInterval(params: any, api: any) {
  const x0 = api.coord([api.value(0), 0])[0]
  const x1 = api.coord([api.value(1), 0])[0]
  const lane = api.value(2) || 0
  const band = api.value(3) || 0
  const nBands = api.value(4) || 1
  const cs = params.coordSys
  const bandH = cs.height / nBands
  const bandTop = cs.y + band * bandH
  const laneH = 7, gap = 2
  // 从 band 底部向上堆 lane(lane 超出 band 高度时钳制)
  const rawY = bandTop + bandH - laneH - lane * (laneH + gap)
  const y = Math.max(bandTop, Math.min(rawY, bandTop + bandH - laneH))
  return {
    type: 'rect',
    shape: { x: x0, y, width: Math.max(2, x1 - x0), height: laneH },
    style: api.style(),
  }
}

// D2: 高亮描边:对选中 event 按其 kind 用同坐标定位画描边形状(置顶,不动原系列)
// point → 空心放大三角描边;interval → 空心描边矩形
function renderHighlight(params: any, api: any) {
  const kind: 'point' | 'interval' = (params.data as any)?.kind ?? 'point'
  if (kind === 'point') {
    const x = api.coord([api.value(0), 0])[0]
    const band = api.value(2) || 0
    const nBands = api.value(3) || 1
    const cs = params.coordSys
    const bandH = cs.height / nBands
    const bandTop = cs.y + band * bandH
    const centerY = bandTop + bandH / 2
    // 比 renderPoint 稍大(w:7 vs 5)
    const w = 7
    return {
      type: 'polygon',
      shape: { points: [[x, centerY + 6], [x - w, centerY - 4], [x + w, centerY - 4]] },
      style: { fill: 'none', stroke: '#ffffff', lineWidth: 2 },
      z2: 20,
    }
  } else {
    // interval:复用 renderInterval 坐标逻辑,画空心描边矩形
    const x0 = api.coord([api.value(0), 0])[0]
    const x1 = api.coord([api.value(1), 0])[0]
    const lane = api.value(2) || 0
    const band = api.value(3) || 0
    const nBands = api.value(4) || 1
    const cs = params.coordSys
    const bandH = cs.height / nBands
    const bandTop = cs.y + band * bandH
    const laneH = 7, gap = 2
    const rawY = bandTop + bandH - laneH - lane * (laneH + gap)
    const y = Math.max(bandTop, Math.min(rawY, bandTop + bandH - laneH))
    return {
      type: 'rect',
      shape: { x: x0 - 1, y: y - 1, width: Math.max(2, x1 - x0) + 2, height: laneH + 2 },
      style: { fill: 'none', stroke: '#ffffff', lineWidth: 2 },
      z2: 20,
    }
  }
}

// D2: price-anchored event 高亮描边(grid0 价格轴)。
// 描边新 bo 圆角矩形盒子(渲染规约见 renderPricePoint);稍微外扩以便环绕可见。
// ⚠ closure factory:ECharts customSeries 不在 params 中传 data item,必须按 dataIndex 反查。
function makeRenderPricePointHighlight(
  data: Array<{ value: number[]; event_id: string; anchorY: number; text: string }>,
) {
  return function renderPricePointHighlight(params: any, api: any) {
    const item = data[params.dataIndex] ?? null
    const anchorY = item?.anchorY ?? api.value(1)
    const text = item?.text ?? ''
    const [cx, anchorPx] = api.coord([api.value(0), anchorY])
    // 与 renderPricePoint 几何严格一致(box 中心 = anchorPx - BO_STACK_PT)
    const cy = anchorPx - BO_STACK_PT
    const { w, h } = boBoxDims(text)
    const pad = 3
    return {
      type: 'rect',
      shape: {
        x: cx - w / 2 - pad,
        y: cy - h / 2 - pad,
        width: w + 2 * pad,
        height: h + 2 * pad,
        r: BO_BOX_RADIUS + pad,
      },
      style: { fill: 'none', stroke: '#ffffff', lineWidth: 2 },
      z2: 21,
    }
  }
}

// 归属带:价格区顶部按 lane 的横带 + 序号(grid0 隐藏 bracket 轴)。
function renderBracket(params: any, api: any) {
  const x0 = api.coord([api.value(0), 0])[0]
  const x1 = api.coord([api.value(1), 0])[0]
  const lane = api.value(2) || 0
  const bandH = 6, gap = 4
  const top = params.coordSys.y + 2 + lane * (bandH + gap)
  return {
    type: 'group',
    children: [
      { type: 'rect', shape: { x: x0, y: top, width: Math.max(2, x1 - x0), height: bandH },
        style: { fill: '#64748b', opacity: 0.5 } },
      { type: 'text', style: { text: '①②③④⑤⑥⑦⑧⑨'[(api.value(3) - 1) % 9] ?? '·',
        x: x0 + 2, y: top - 2, fill: '#334155', fontSize: 11, textVerticalAlign: 'bottom' } },
    ],
  }
}

// band 标签:grid2 左缘每 band 行文字。value=[0, band, nBands]
function renderBandLabel(params: any, api: any) {
  const band = api.value(1) || 0
  const nBands = api.value(2) || 1
  const cs = params.coordSys
  const bandH = cs.height / nBands
  const bandTop = cs.y + band * bandH
  const centerY = bandTop + bandH / 2
  const text = (params.data as any)?.text ?? ''
  return {
    type: 'text',
    style: {
      text,
      x: cs.x + 2,
      y: centerY,
      fill: '#94a3b8',
      fontSize: 10,
      textVerticalAlign: 'middle',
    },
    z2: 5,
  }
}

// ─── dev UI 视觉常量(对齐 BreakoutStrategy/UI/styles.py CHART_COLORS / MARKER_STACK_GAPS_PT
//     / BO_LABEL_TIER_STYLE;rubric=docs/tmp/2026-06-21-bo-pk-marker-rubric.md)──────────────
const MARKER_FONT_SIZE = 16            // dev UI fontsize=20;Web 端缩到 16 兼顾蜡烛密度可读
const PK_TRIANGLE_HALF_WIDTH = 9       // ▽ 边宽近 dev s=400 视觉
const PK_TRIANGLE_HEIGHT = 12
const PEAK_MARKER_COLOR = '#000000'    // CHART_COLORS["peak_marker"]
const PEAK_TEXT_COLOR = '#000000'      // CHART_COLORS["peak_text_id"]
const BO_BORDER_COLOR = '#0000FF'      // CHART_COLORS["bo_marker_current"](全 tier 统一)
const BO_BOX_RADIUS = 4
const BO_BOX_PAD_X = 5
const BO_BOX_PAD_Y = 3
// 堆叠 pt 偏移(锚 K 线 high 之上,自下而上):▽ → ID → [ids]
// dev UI styles.py:80-86 用 pt,Web 端用 px 等距;视觉次序与 rubric §3 一致即可。
const TRIANGLE_STACK_PT = 14           // ▽ 中心 y = anchor - 14
const PEAK_ID_STACK_PT = 30            // ID 中心 y = anchor - 30
const BO_STACK_PT = 50                 // [ids] 中心 y = anchor - 50

// BO_LABEL_TIER_STYLE(dev UI styles.py:168-172)三态查表
const BO_TIER_STYLE: Record<'current' | 'matched' | 'plain', { bg: string; fg: string }> = {
  current: { bg: '#0000FF', fg: '#FFFFFF' },
  matched: { bg: '#BFBFBF', fg: '#000000' },
  plain:   { bg: '#FFFFFF', fg: '#0000FF' },
}

// 文本框尺寸(浏览器无 measureText 时按字宽近似,bold 字体 char_w ≈ 0.6×fontSize)
function boBoxDims(text: string): { w: number; h: number } {
  const charW = MARKER_FONT_SIZE * 0.62
  const textW = Math.max(charW, text.length * charW)
  return {
    w: textW + 2 * BO_BOX_PAD_X,
    h: MARKER_FONT_SIZE + 2 * BO_BOX_PAD_Y,
  }
}

// price-anchored bo 主 marker: 圆角矩形蓝框 + [broken_peak_ids] 文本(dev UI 复刻)。
// 锚 bar.h(anchorY 由 buildKlineOption 注入),box 中心 = anchorPx - BO_STACK_PT。
// ⚠ closure factory:ECharts customSeries 不在 params 中传 data item,必须按 dataIndex 反查。
//   过去用 (params.data as any).text 实测=undefined → text 为空字符串 → ZRText 被创建但无文字渲染。
function makeRenderPricePoint(
  data: Array<{ value: number[]; event_id: string; anchorY: number; text: string;
                 boTier: 'current' | 'matched' | 'plain'; tier: Tier; itemStyle: object }>,
) {
  return function renderPricePoint(params: any, api: any) {
    const item = data[params.dataIndex] ?? null
    const anchorY = item?.anchorY ?? api.value(1)
    const text = item?.text ?? ''
    const tier = item?.boTier ?? 'plain'
    const tierStyle = BO_TIER_STYLE[tier]
    const [cx, anchorPx] = api.coord([api.value(0), anchorY])
    const cy = anchorPx - BO_STACK_PT
    const { w, h } = boBoxDims(text)
    return {
      type: 'group',
      children: [
        // 1. 圆角矩形背景 + 蓝色描边
        {
          type: 'rect',
          shape: { x: cx - w / 2, y: cy - h / 2, width: w, height: h, r: BO_BOX_RADIUS },
          style: {
            fill: tierStyle.bg,
            stroke: BO_BORDER_COLOR,
            lineWidth: 1.5,
            opacity: 0.95,
          },
        },
        // 2. 文本(居中,粗体,按 tier 取字色)
        {
          type: 'text',
          style: {
            text,
            x: cx,
            y: cy,
            fill: tierStyle.fg,
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
// anchorY=bars[bar_idx].h(buildKlineOption 注入)。锚 K 线 high,堆叠次序自下而上 ▽ → ID。
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
            lineWidth: 2,
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
): { itemStyle: { color: string; opacity: number }; data: Array<[{ xAxis: number }, { xAxis: number }]> } | null {
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
    data,
  }
}

/**
 * Dev UI 1:1 复刻 — volume 叠加进价格区底部 20% 高度带。
 *
 * 计算可见区间 priceMin/Max → displayHeight = priceRange / 0.8 → displayBottom 留 10% 底部空白。
 * volScale = (displayHeight * 0.2) / visVolMax，每根 bar 的 value = displayBottom + b.v * volScale。
 * yAxis[0].min/max 必须改为 displayBottom/displayTop（不能 scale:true），让 bar baseline 落在 displayBottom。
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
  const displayBottom = priceMin - displayHeight * 0.1
  const displayTop = displayBottom + displayHeight
  const visVolMax = Math.max(...visBars.map(b => b.v), 1)
  const volScale = (displayHeight * 0.2) / visVolMax

  const volSeries = {
    type: 'bar' as const,
    name: 'volume' as const,
    xAxisIndex: 0 as const,
    yAxisIndex: 0 as const,
    barWidth: '100%' as const,
    z: 1 as const,
    data: bars.map(b => ({
      value: displayBottom + b.v * volScale,
      itemStyle: {
        color: b.c >= b.o ? '#D3D3D3' : '#696969',
        borderColor: 'black',
        borderWidth: 0.5,
        opacity: 0.8,
      },
    })),
  }
  return {
    volSeries,
    yAxisOverride: { min: displayBottom, max: displayTop },
  }
}

/**
 * Bar tooltip formatter (global axis-trigger)。
 * 普通模式 8 行: Date / Open / High / Low / Close / Chg / Volume / RV
 * Ctrl 模式 1 行: Price: {mouseY:.2f}
 *
 * Ctrl 模式拿 mouseY: ctrlState.mouseY() 由 KlineChart.vue 在 chart.getZr() mousemove
 * 中 convertFromPixel({yAxisIndex:0}) 后 setMouseY 更新。
 */
export function buildBarTooltipFormatter(
  bars: Bar[],
  ctrlState: { isPressed: () => boolean; mouseY: () => number },
) {
  return (params: Array<{ seriesName?: string; dataIndex?: number }>): string => {
    if (ctrlState.isPressed()) {
      return `Price: ${ctrlState.mouseY().toFixed(2)}`
    }
    const klineParam = params.find(p => p.seriesName === 'kline')
    if (!klineParam || typeof klineParam.dataIndex !== 'number') return ''
    const idx = klineParam.dataIndex
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
      `Open:  ${b.o.toFixed(2)}`,
      `High:  ${b.h.toFixed(2)}`,
      `Low:   ${b.l.toFixed(2)}`,
      `Close: ${b.c.toFixed(2)}`,
      `Chg:   ${chgStr}`,
      `Volume: ${volStr}`,
      `RV:    ${rvStr}`,
    ].join('<br/>')
  }
}

/**
 * Marker tooltip formatter (series-level item-trigger)。
 * 逻辑与原 chart.ts:192-213 等价 (只搬位置不改语义):
 *  - params.data.match_id 命中 → matchLabel 行
 *  - params.data.event_id 命中 + tooltipResolver → clauses + raw (excl. "members")
 */
export function buildMarkerTooltipFormatter(
  tooltipResolver: ((eventId: string) => TooltipPayload) | undefined,
  matchLabel: ((matchId: string) => string | null) | undefined,
) {
  return (params: { data?: { event_id?: string; match_id?: string } }): string => {
    const matchId = params?.data?.match_id
    if (matchId) return (matchLabel && matchLabel(matchId)) ?? ''
    const eventId = params?.data?.event_id
    if (!eventId || !tooltipResolver) return ''
    const { clauses, raw } = tooltipResolver(eventId)
    const lines: string[] = []
    for (const [cid, c] of Object.entries(clauses)) {
      const opStr = c.op != null ? ` ${c.op} ${String(c.threshold)}` : ''
      const mark = c.satisfied ? '✓' : '✗'
      lines.push(`${cid}: ${String(c.measured)}${opStr} ${mark}`)
    }
    for (const [k, v] of Object.entries(raw)) {
      if (k === 'members') continue
      lines.push(`${k}: ${String(v)}`)
    }
    return lines.join('<br/>')
  }
}
