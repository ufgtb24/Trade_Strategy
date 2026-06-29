// ECharts option 构造(纯函数,spec §8.3 方案 B)。类型无关:只依赖 start_idx/end_idx/source_tag + 色。
import type { Bar, EventDict, MatchDict, Level, Tier, Topology } from '../types'
import { colorOf } from './colors'
import { splitGeometry, packByBand, packBrackets } from './geometry'
import { isBandVisible, renderGridOf } from './visible'
import { ctrlState } from './ctrlState'

// ─── 新签名 ──────────────────────────────────────────────────────────────────

export interface TooltipClauseRow {
  cid: string
  role: string
  measured: unknown
  op: string | null
  threshold: unknown
  satisfied: boolean
}

export interface TooltipPayload {
  identity: {
    roles: string[]
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
  // ── dataZoom slider 显隐(可选,默认 true=显示,与历史行为一致) ──────────────
  sliderShow?: boolean
  // ── zoom 区间覆盖:传入则跳过 strictWindow 默认,保留用户当前 zoom(KlineChart
  //    render 时从 chart.getOption().dataZoom[0] 读出再回传,实现"非换股触发
  //    re-render 时不重置 zoom")。缺省/null = 走 strictWindow 默认,旧调用零回归。
  zoomOverride?: { start: number; end: number } | null
  // §7-4 整治：bracket marker 同时承载 match_id + 端点 event_id,让 buildMarkerTooltipFormatter
  // 的 event 三段分支也能触发。endRole 来自 eval_meta(铁律必有);缺省=不注入 event_id(向后兼容)
  endRole?: string
}

export function buildKlineOption(
  bars: Bar[], events: EventDict[], matches: MatchDict[],
  input: BandRenderInput,
) {
  const { topology, tagList, level, roleColors, eventTier, roleOfEventByBand, bandKeyOf,
          roleVisible, tagToNodes,
          selectedEventId, tooltipResolver, strictWindow, matchLabel, sliderShow,
          zoomOverride, endRole } = input

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

  // bo 三态映射(dev UI styles.py:BO_LABEL_TIER_STYLE 对齐):
  //   selectedEventId 命中 → current(深蓝底白字)
  //   eventTier=matched     → matched(灰底黑字)
  //   其余                  → plain(白底深蓝字)
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
  // - hasPks: 该 bar 是否同时有 satellite PK 三角(HEAD 胜出语义保留),用于切换堆叠偏移。
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
      itemStyle: { color: eColor(e) },   // 兼容字段;新渲染走 boTier
      // ─ 新字段 ─
      anchorY,
      text,
      boTier: boTierOf(e),
      hasPks,
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
  const bracketData = brackets.map((m) => {
    const data: { value: number[]; match_id: string; event_id?: string } = {
      value: [m.start_idx, m.end_idx, m.lane, m.ordinal],
      match_id: m.event_id,
    }
    // §7-4：注入端点 event_id 让 tooltip 三段分支可触发；role_index 值兼容 string|string[]
    if (endRole) {
      const v = m.role_index?.[endRole]
      const eid = Array.isArray(v) ? v[0] : v
      if (eid) data.event_id = eid
    }
    return data
  })

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
  const highlightPriceData: Array<{
    value: number[]; event_id: string; anchorY: number; text: string; hasPks: boolean;
  }> = []
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
  // zoomOverride 优先(KlineChart 把用户当前 zoom 回传以保 UI 显隐/level 等切换不重置);
  // 缺省走 strictWindow 默认,与首次加载/换股 reset 时的初始视图一致
  const zoomStart = zoomOverride?.start ?? (hasBuffer ? (sw!.startIdx / N) * 100 : 0)
  const zoomEnd   = zoomOverride?.end   ?? (hasBuffer ? ((sw!.endIdx + 1) / N) * 100 : 100)

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
    barWidth: '70%',
    itemStyle: {
      borderWidth: 2,   // 默认 1;影线和实体边框同时变粗
    },

  }
  if (shadingMarkArea) {
    klineSeries.markArea = shadingMarkArea
  }

  return {
    animation: false,
    tooltip,
    axisPointer: { link: [{ xAxisIndex: [0, 1] }] },
    // sliderShow=false 时把底部 ~8% 还给 grid0/grid1:grid0 扩高到 80%,grid1 下移到 84%/height 16%,
    // 整个面板占满到底,主图+副图明显变大;sliderShow=true 保历史几何
    grid: [
      { left: 56, right: 16, top: 40, height: (sliderShow ?? true) ? '72%' : '80%' },
      { left: 56, right: 16, top: (sliderShow ?? true) ? '76%' : '84%',
        height: (sliderShow ?? true) ? '18%' : '16%' },
    ],
    xAxis: [
      { type: 'category', data: dates, gridIndex: 0, boundaryGap: true,
        axisLine: { onZero: false }, splitLine: { show: false }, min: 'dataMin', max: 'dataMax' },
      { type: 'category', data: dates, gridIndex: 1, boundaryGap: true,
        axisLine: { onZero: false }, axisLabel: { show: false }, splitLine: { show: false } },
    ],
    yAxis: [
      // index 0: 价格(grid0)——固定 min/max 让 volume bar 显示区间贴 grid 底部 20%
      // (displayBottom 钳到 ≥ 0，详见 buildVolumeSeriesAndYAxis 注释)
      { gridIndex: 0, splitArea: { show: true }, min: yAxisOverride.min, max: yAxisOverride.max },
      // index 1: 隐藏 bracket 轴(grid0)
      { scale: true, gridIndex: 0, show: false },
      // index 2: 隐藏 marker 轴(grid1)
      { scale: true, gridIndex: 1, show: false },
    ],
    dataZoom: [
      { type: 'inside', xAxisIndex: [0, 1], start: zoomStart, end: zoomEnd },
      { type: 'slider', xAxisIndex: [0, 1], top: '92%', start: zoomStart, end: zoomEnd,
        show: sliderShow ?? true },
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
        data: bandLabelData, renderItem: makeRenderBandLabel(bandLabelData), encode: { x: 0 }, z: 5,
        markArea: shadingMarkArea ?? undefined,
        tooltip: markerTooltip },
      // D2: 选中 event 描边高亮(最高 z,不影响原 points/intervals)
      { type: 'custom', name: 'highlight', xAxisIndex: 1, yAxisIndex: 2,
        data: highlightData, renderItem: makeRenderHighlight(highlightData), encode: { x: 0 }, z: 20,
        tooltip: markerTooltip },

      // ── render_grid='price' 主三角(grid0) ──
      // ⚠ ECharts 4/5 customSeries 不在 renderItem(params, api) 的 params 中暴露原始 data item;
      //   `params.data` 实测=undefined。要拿到非 value 维度的字段(text / anchorY / boTier / pkId),
      //   必须用 closure 捕获 *Data 数组、按 params.dataIndex 反查。
      // clip:false 让 BO 方框/PK 三角+数字渲染到 grid 边界外(价格区顶部附近不被裁剪)。
      { type: 'custom', name: 'price-points', xAxisIndex: 0, yAxisIndex: 0,
        data: pricePointData,
        renderItem: makeRenderPricePoint(pricePointData),
        encode: { x: 0, y: 1 }, z: 12, clip: false, tooltip: markerTooltip },

      // ── 卫星 marker(referenced_points → grid0, dot + label) ──
      // clip:false 同上,PK 数字 ID 在三角上方会超出 grid 顶边。
      { type: 'custom', name: 'satellites', xAxisIndex: 0, yAxisIndex: 0,
        data: satelliteData,
        renderItem: makeRenderSatellite(satelliteData),
        encode: { x: 0, y: 1 }, z: 13, clip: false, tooltip: markerTooltip },

      // D2: 选中 price-anchored event 描边高亮(grid0,置顶)
      { type: 'custom', name: 'highlight-price', xAxisIndex: 0, yAxisIndex: 0,
        data: highlightPriceData,
        renderItem: makeRenderPricePointHighlight(highlightPriceData),
        encode: { x: 0, y: 1 }, z: 21, clip: false, tooltip: markerTooltip },
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
// ECharts 5 custom series renderItem 的 params 不含 .data(实测 params.data===undefined),
// 故工厂函数 closure 捕获 items,renderItem 内用 params.dataIndex 反查 item。
function makeRenderHighlight(items: Array<{ value: number[]; event_id: string; kind: 'point' | 'interval' }>) {
  return function renderHighlight(params: any, api: any) {
    const item = items[params.dataIndex]
    const kind: 'point' | 'interval' = item?.kind ?? 'point'
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
}

// D2: price-anchored event 高亮描边(grid0 价格轴)。
// 描边新 bo 圆角矩形盒子(渲染规约见 renderPricePoint);稍微外扩以便环绕可见。
// stackOffset 与 renderPricePoint 同步按 hasPks 切换(保留自 HEAD 的胜出语义)。
// ⚠ closure factory:ECharts customSeries 不在 params 中传 data item,必须按 dataIndex 反查。
function makeRenderPricePointHighlight(
  data: Array<{ value: number[]; event_id: string; anchorY: number; text: string; hasPks: boolean }>,
) {
  return function renderPricePointHighlight(params: any, api: any) {
    const item = data[params.dataIndex] ?? null
    const anchorY = item?.anchorY ?? api.value(1)
    const text = item?.text ?? ''
    const hasPks = item?.hasPks ?? false
    const [cx, anchorPx] = api.coord([api.value(0), anchorY])
    // 与 renderPricePoint 几何严格一致(box 中心 = anchorPx - stackOffset)
    const stackOffset = hasPks ? BO_STACK_PT : BO_STACK_PT_NO_PKS
    const cy = anchorPx - stackOffset
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
// ECharts 5 custom renderItem 不含 params.data → factory closure 捕获 items。
function makeRenderBandLabel(items: Array<{ value: number[]; text: string }>) {
  return function renderBandLabel(params: any, api: any) {
    const band = api.value(1) || 0
    const nBands = api.value(2) || 1
    const cs = params.coordSys
    const bandH = cs.height / nBands
    const bandTop = cs.y + band * bandH
    const centerY = bandTop + bandH / 2
    const text = items[params.dataIndex]?.text ?? ''
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
}

// ─── dev UI 视觉常量(对齐 BreakoutStrategy/UI/styles.py CHART_COLORS / MARKER_STACK_GAPS_PT
//     / BO_LABEL_TIER_STYLE;rubric=docs/tmp/2026-06-21-bo-pk-marker-rubric.md)──────────────
// 整组数值相对 dev pt 值按 ~0.6 比例缩放,补偿 web grid 容器较窄、相对蜡烛宽度偏大的视觉。
const MARKER_FONT_SIZE = 12            // dev fontsize=20pt;web px=12 对齐 dev 视觉
const PK_TRIANGLE_HALF_WIDTH = 6       // ▽ 半宽,对应 dev s=400 (≈20pt 边长) 等比缩放
const PK_TRIANGLE_HEIGHT = 9
const PEAK_MARKER_COLOR = '#000000'    // CHART_COLORS["peak_marker"]
const PEAK_TEXT_COLOR = '#000000'      // CHART_COLORS["peak_text_id"]
const BO_BORDER_COLOR = '#0000FF'      // CHART_COLORS["bo_marker_current"](全 tier 统一)
const BO_BOX_RADIUS = 3
const BO_BOX_PAD_X = 4
const BO_BOX_PAD_Y = 2
// 堆叠 px 偏移(锚 K 线 high 之上,自下而上):▽ → ID → [ids]
// dev UI styles.py:80-86 用 pt(triangle=20/peak_id=35/bo_label=65 有 PK,bo_label=15 无 PK)
// web 端按字号 12 等比缩:三角中心 10、ID 中心 21、BO 中心 36(有 PK)/11(无 PK)
const TRIANGLE_STACK_PT = 10           // ▽ 中心 y = anchor - 10
const PEAK_ID_STACK_PT = 21            // ID 中心 y = anchor - 21
const BO_STACK_PT = 36                 // [ids] 中心 y = anchor - 36(hasPks=true 时)
// hasPks=false:同 bar 无 PK,BO 单独贴近 K 线 high(dev styles.py:80 bo_label=15pt 缩放对应)。
// 这是 HEAD 相对 94e21934 的胜出语义点 — 按是否同 bar 有 PK 动态切换偏移。
const BO_STACK_PT_NO_PKS = 11

// BO_LABEL_TIER_STYLE(dev UI styles.py:168-172)三态查表
const BO_TIER_STYLE: Record<'current' | 'matched' | 'plain', { bg: string; fg: string }> = {
  current: { bg: '#0000FF', fg: '#FFFFFF' },
  matched: { bg: '#BFBFBF', fg: '#000000' },
  plain:   { bg: '#FFFFFF', fg: '#0000FF' },
}

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
// 锚 bar.h(anchorY 由 buildKlineOption 注入),box 中心 = anchorPx - stackOffset。
// stackOffset 按 hasPks 切换(保留自 HEAD 的胜出语义):
//   hasPks=true  → BO_STACK_PT=50(同 bar 有 PK 三角,堆叠在 PK ID 之上)
//   hasPks=false → BO_STACK_PT_NO_PKS=15(无 PK,BO 单独贴近 bar.h,对齐 dev 15pt)
// ⚠ closure factory:ECharts customSeries 不在 params 中传 data item,必须按 dataIndex 反查。
//   过去用 (params.data as any).text 实测=undefined → text 为空字符串 → ZRText 被创建但无文字渲染。
function makeRenderPricePoint(
  data: Array<{ value: number[]; event_id: string; anchorY: number; text: string;
                 boTier: 'current' | 'matched' | 'plain'; tier: Tier; hasPks: boolean; itemStyle: object }>,
) {
  return function renderPricePoint(params: any, api: any) {
    const item = data[params.dataIndex] ?? null
    const anchorY = item?.anchorY ?? api.value(1)
    const text = item?.text ?? ''
    const tier = item?.boTier ?? 'plain'
    const hasPks = item?.hasPks ?? false
    const tierStyle = BO_TIER_STYLE[tier]
    const [cx, anchorPx] = api.coord([api.value(0), anchorY])
    const stackOffset = hasPks ? BO_STACK_PT : BO_STACK_PT_NO_PKS
    const cy = anchorPx - stackOffset
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
 * 三段结构 + 可选 match 顶行：
 *   - 顶行 (仅 params.data.match_id 命中)：Match: {matchLabel(id)}
 *   - 段 1 Identity：role / time / id
 *   - 段 2 Clauses：失败 ✗ 置顶 + 加粗；多 role 同 cid 行末加 (in: <role>)
 *   - 段 3 Attributes：raw（已去重）
 *
 * 段空时省略段头；身份段恒存在但 role 行可省。
 * HTML：使用 <br/> <b> <hr>（echarts tooltip formatter 支持）。
 * 注：当前 measured 类型受控（数字 / 字符串 / 元组），不引入 HTML escape；
 *     未来若 detector 引入用户输入字符串型 measured 且可能含 HTML，
 *     需在 fmtNum 旁追加 escape 步骤。
 * spec 见 docs/superpowers/specs/2026-06-29-marker-tooltip-cleanup-design.md
 */
export function buildMarkerTooltipFormatter(
  tooltipResolver: ((eventId: string) => TooltipPayload) | undefined,
  matchLabel: ((matchId: string) => string | null) | undefined,
) {
  return (params: { data?: { event_id?: string; match_id?: string } } | null): string => {
    const data = params?.data
    if (!data) return ''
    const lines: string[] = []

    // ── 顶行：match 归属 ─────────────────────────────────────────────────
    const matchId = data.match_id
    if (matchId && matchLabel) {
      const ml = matchLabel(matchId)
      if (ml) lines.push(`Match: ${ml}`)
    }

    // ── event 三段 ──────────────────────────────────────────────────────
    const eventId = data.event_id
    if (eventId && tooltipResolver) {
      const { identity, clauses, raw } = tooltipResolver(eventId)

      // 段 1 Identity
      const idBody: string[] = []
      if (identity.roles.length > 0) idBody.push(`role: ${identity.roles.join(' / ')}`)
      const timeStr = identity.dateEnd == null
        ? `time: ${identity.dateStart}`
        : `time: ${identity.dateStart} → ${identity.dateEnd}`
      idBody.push(timeStr)
      idBody.push(`id:   ${identity.eventId}`)
      if (lines.length > 0) lines.push('<hr/>')
      lines.push('<b>Identity</b>')
      lines.push(...idBody)

      // 段 2 Clauses（失败已置顶；多 role 同 cid 行末加 (in: <role>)）
      if (clauses.length > 0) {
        const cidCounts: Record<string, number> = {}
        for (const c of clauses) cidCounts[c.cid] = (cidCounts[c.cid] ?? 0) + 1
        const clauseLines = clauses.map((c) => {
          const opStr = c.op != null ? ` ${c.op} ${fmtNum(c.threshold)}` : ''
          const mark = c.satisfied ? '✓' : '✗'
          const inSuffix = cidCounts[c.cid] > 1 ? ` (in: ${c.role})` : ''
          const body = `${c.cid}: ${fmtNum(c.measured)}${opStr} ${mark}${inSuffix}`
          return c.satisfied ? body : `<b>${body}</b>`
        })
        lines.push('<hr/>')
        lines.push('<b>Clauses</b>')
        lines.push(...clauseLines)
      }

      // 段 3 Attributes（raw 已去重）
      const rawEntries = Object.entries(raw)
      if (rawEntries.length > 0) {
        lines.push('<hr/>')
        lines.push('<b>Attributes</b>')
        for (const [k, v] of rawEntries) lines.push(`${k}: ${fmtNum(v)}`)
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
