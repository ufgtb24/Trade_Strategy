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

  // 预计算: 哪些 bar 索引上有 PK satellite(用于 BO 方框动态堆叠偏移)
  const pkBarIndices = new Set<number>()
  for (const e of priceAnchored) {
    const rp = e.referenced_points
    if (Array.isArray(rp)) {
      for (const [barIdx] of rp as Array<[number, number, string]>) {
        pkBarIndices.add(barIdx)
      }
    }
  }

  // price-anchored BO 方框:蓝边白底蓝字 [id1,id2,...],锚在 bar.h
  // boLabelText = 从 referenced_points labels 剥去 'pk' 前缀取数字, 逗号拼接后加 []
  // hasPks: 该 bar 是否同时有 satellite PK 三角,用于控制 BO 方框的纵向堆叠偏移
  const pricePointData = priceAnchored.map((e) => {
    const bar = bars[e.start_idx]
    const barH = bar ? bar.h : 0
    const rp = e.referenced_points
    const ids: string[] = Array.isArray(rp)
      ? (rp as Array<[number, number, string]>).map(([, , lbl]) => lbl.replace(/^pk/i, ''))
      : []
    const boLabelText = ids.length > 0 ? `[${ids.join(',')}]` : null
    const hasPks = pkBarIndices.has(e.start_idx)
    return {
      value: [e.start_idx, barH],
      event_id: e.event_id,
      tier: eventTier(e),
      boLabelText,
      hasPks,
      itemStyle: { color: eColor(e) },
    }
  })

  // satellites: 任何 anchor='price' event 的 referenced_points → PK 倒三角+数字
  // label 剥 'pk' 前缀作为显示数字(仅显示文本处理,非类型条件分支)
  // barH: 该 PK 所在 bar 的 high 价格,用于统一锚点
  const satelliteData: Array<{
    value: number[]
    event_id: string
    label: string
    barH: number
    itemStyle: object
  }> = []
  for (const e of priceAnchored) {
    const rp = e.referenced_points
    if (!rp || !Array.isArray(rp)) continue
    for (const [barIdx, , label] of rp as Array<[number, number, string]>) {
      const pkBar = bars[barIdx]
      const barH = pkBar ? pkBar.h : 0
      satelliteData.push({
        value: [barIdx, barH],
        event_id: e.event_id,
        label,
        barH,
        itemStyle: { color: eColor(e) },
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
    const text = node ? node.node_id : tag
    return { value: [0, band, tagList.length], text }
  })

  // ── D2: highlight overlay ─────────────────────────────────────────────────
  // 找到被选中 event(在当前 level 门控后的 filtered 集合里),追加描边高亮系列。
  // price-anchored events → highlightPriceData (grid0); others → highlightData (grid2)
  const highlightData: Array<{ value: number[]; event_id: string; kind: 'point' | 'interval' }> = []
  const highlightPriceData: Array<{ value: number[]; event_id: string; hasPks: boolean }> = []
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
            hasPks: selPricePoint.hasPks,
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
      // clip:false 让 BO 方框/PK 三角+数字渲染到 grid 边界外(价格区顶部附近不被裁剪)
      { type: 'custom', name: 'price-points', xAxisIndex: 0, yAxisIndex: 0,
        data: pricePointData, renderItem: renderPricePoint, encode: { x: 0, y: 1 }, z: 12, clip: false },

      // ── 卫星 marker(referenced_points → grid0, dot + label) ──
      // clip:false 同上,PK 数字 ID 在三角上方会超出 grid 顶边
      { type: 'custom', name: 'satellites', xAxisIndex: 0, yAxisIndex: 0,
        data: satelliteData, renderItem: renderSatellite, encode: { x: 0, y: 1 }, z: 13, clip: false },

      // D2: 选中 price-anchored event 描边高亮(grid0,置顶)
      { type: 'custom', name: 'highlight-price', xAxisIndex: 0, yAxisIndex: 0,
        data: highlightPriceData, renderItem: renderPricePointHighlight, encode: { x: 0, y: 1 }, z: 21, clip: false },
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
// BO 现在是方框,高亮画一个稍大的白色描边矩形覆盖在 BO 方框外侧。
// baseOffset 与 renderPricePoint 保持一致(hasPks=true→46, false→12)。
function renderPricePointHighlight(params: any, api: any) {
  const [cx, cy] = api.coord([api.value(0), api.value(1)])
  const hasPks: boolean = (params.data as any)?.hasPks ?? false
  // 与 renderPricePoint 保持一致的偏移(fontSize=18, padV=4 → boxH≈26)
  const baseOffset = hasPks ? 46 : 12
  const boxY = cy - baseOffset
  const boxH = 26   // fontSize(18) + padV*2(8) ≈ 26
  const boxW = 70   // 保守估算最宽文字
  return {
    type: 'rect',
    shape: { x: cx - boxW / 2 - 2, y: boxY - boxH - 2, width: boxW + 4, height: boxH + 4, r: 5 },
    style: { fill: 'none', stroke: '#ffffff', lineWidth: 2 },
    z2: 21,
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

// price-anchored BO 方框: 蓝边白底蓝字圆角框 [id1,id2,...], 锚在 bar.h 像素偏移上方。
// 若 referenced_points 为空或缺(无 boLabelText),降级画一个小蓝实心三角。
// 堆叠规则(与 renderSatellite 共享参数保持一致):
//   仅 BO(hasPks=false): BO 方框底边距 bar.h 约 20px
//   BO + PK 同 bar(hasPks=true): gap(8) + triH(16) + idFontSize(18) + margin(4) ≈ 46px
// hasPks 由数据层(pricePointData 构造时)注入,避免 renderItem 间无状态共享限制。
// clip:false 在系列级设置,确保方框不被 grid 顶边裁剪。
function renderPricePoint(params: any, api: any) {
  const [cx, cy] = api.coord([api.value(0), api.value(1)])
  const boLabelText: string | null = (params.data as any)?.boLabelText ?? null
  const hasPks: boolean = (params.data as any)?.hasPks ?? false
  if (!boLabelText) {
    // 降级: 无 referenced_points, 画蓝实心小三角(朝上↑)
    const w = 6
    return {
      type: 'polygon',
      shape: { points: [[cx, cy - 6], [cx - w, cy], [cx + w, cy]] },
      style: { fill: '#0000FF' },
    }
  }
  // 与 renderSatellite 保持一致: gap=8, triH=16, idFontSize=18, margin=4
  // hasPks=true: 箱底 = bar.h - (gap + triH + idFontSize + margin) = bar.h - 46
  // hasPks=false: 箱底距 bar.h 约 12px(仅留 bar 上方最小间距)
  const baseOffset = hasPks ? 46 : 12
  const boxY = cy - baseOffset
  const fontSize = 18   // spec ≈ 18-20px
  const padH = 6   // 水平内边距
  const padV = 4   // 垂直内边距
  // 估算文字宽度: 每字符约 10.5px @ fontSize=18
  const textWidth = boLabelText.length * 10.5
  const boxW = textWidth + padH * 2
  const boxH = fontSize + padV * 2
  const boxX = cx - boxW / 2
  return {
    type: 'group',
    children: [
      // 圆角矩形背景+边框
      {
        type: 'rect',
        shape: { x: boxX, y: boxY - boxH, width: boxW, height: boxH, r: 4 },
        style: { fill: '#FFFFFF', stroke: '#0000FF', lineWidth: 2 },
        z2: 12,
      },
      // 蓝色粗体文字
      {
        type: 'text',
        style: {
          text: boLabelText,
          x: cx,
          y: boxY - boxH / 2,
          fill: '#0000FF',
          fontSize,
          fontWeight: 'bold',
          textAlign: 'center',
          textVerticalAlign: 'middle',
        },
        z2: 13,
      },
    ],
  }
}

// 卫星 marker: PK 倒三角(空心黑色▽,顶点朝下指向 K线 high) + 数字 ID(黑色粗体在三角上方)。
// label 剥去 'pk' 前缀取数字作为显示文本(纯显示文本处理,非条件分支)。
// 堆叠(ECharts canvas y 向下增大,向上 = 减 y):
//   triApexY  = baseY - gap              ← 三角顶点(下顶,指向 K线 high),最靠近 bar
//   triTopY   = triApexY - triH          ← 三角顶边(两个上角),更上
//   ID 数字   = triTopY - 4              ← 数字在三角顶边上方(bottom 对齐)
// clip:false 在系列级设置,确保数字 ID 不被 grid 顶边裁剪。
// renderPricePoint(hasPks=true) 的 baseOffset 与此处 gap+triH+idFontSize+margin 保持同步。
function renderSatellite(params: any, api: any) {
  const [cx] = api.coord([api.value(0), api.value(1)])
  const barH: number = (params.data as any)?.barH ?? api.value(1)
  const [, baseY] = api.coord([api.value(0), barH])

  const label: string = (params.data as any)?.label ?? ''
  // 剥去 'pk' 前缀取数字部分用于显示(无前缀则原样显示)
  const displayId = label.replace(/^pk/i, '')

  // 三角参数: 大小对应 matplotlib s=400 ≈ 16-20px 边长
  const triHalfW = 11   // 顶边半宽(两个上角)
  const triH = 16       // 三角高度
  const gap = 8         // 三角下顶点(apex)到 bar.h 的像素间距(向上=减 y)
  // ECharts canvas: y 向下增大,所以向上 = 减 y
  // 倒三角▽: 顶点(apex)朝下指向 K线,两个上角在上方
  const triApexY = baseY - gap          // 下顶点 y (最靠近 bar.h)
  const triTopY  = triApexY - triH      // 上边 y (两个上角,更高=更小 y 值)

  // ID 数字在三角顶边上方(bottom 对齐于 triTopY - 4)
  const idY = triTopY - 4

  return {
    type: 'group',
    children: [
      // 空心倒三角▽(顶点朝下,指向 K线 high)
      {
        type: 'polygon',
        shape: {
          points: [
            [cx - triHalfW, triTopY],   // 左上角
            [cx + triHalfW, triTopY],   // 右上角
            [cx, triApexY],             // 下顶点(朝下,指向 bar.h)
          ],
        },
        style: { fill: 'none', stroke: '#000000', lineWidth: 2 },
        z2: 13,
      },
      // 数字 ID: 粗体黑色,在三角上方; spec ≈ 18-20px
      {
        type: 'text',
        style: {
          text: displayId,
          x: cx,
          y: idY,
          fill: '#000000',
          fontSize: 18,
          fontWeight: 'bold',
          textAlign: 'center',
          textVerticalAlign: 'bottom',
        },
        z2: 14,
      },
    ],
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
