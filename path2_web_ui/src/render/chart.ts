// ECharts option 构造(纯函数,spec §8.3 方案 B)。类型无关:只依赖 start_idx/end_idx/instance_id + 色。
import type { Bar, EventDict, HitDict, Level, Tier, Topology } from '../types'
import { colorOf } from './colors'
import { packLanes } from './geometry'
import { foldBand, foldHits, formatMemberLabel, hitLabels, memberLabels, HIT_FAMILY_PREFIX,
         type Family, type FoldMark, type HitFamily } from './fold'
import { isBandVisible, renderGridOf, splitIntervalAtScanEnd, subBandTagList } from './visible'
import { ctrlState } from './ctrlState'
import { derivePeakStates, peakIdIndex } from './peakState'
import { MONO } from './fonts'
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
  TIER_H,
  MARK_HALF_W,
  FAMILY_LINE_COLOR,
  FAMILY_LINE_AFTER_WINDOW,
  FAMILY_LINE_H,
  ACTIVE_LINE_H,
  CURSOR_COLOR,
  CURSOR_HALO,
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

/** tooltip 引用关系行:ref_slots 协议的通用投影,**不认识任何具体槽名**。
 *  slot 原样取自 ref_ids 的键(superseded / broken / ...),渲染层只按 dir 分「引用 / 被引」
 *  两组,不为任何事件类型写分支(契约 C7 类型无关红线)。
 *  dir='out':本事件的 ref_ids 引用了对方;dir='in':对方的 ref_ids 引用了本事件。 */
export interface TooltipRefRow {
  slot: string
  dir: 'out' | 'in'
  instanceId: string             // 对方实例(恒有;下面三项在对方不在本次 events 里时为空)
  nodeId: string | null          // 对方所属 node(通用身份轴)
  label: string | null           // 对方的图上短标识,由 refLabel 注入(如 pk 编号);无则 null
  date: string | null            // 对方锚定日期(bars[start_idx].date;越界回落索引字符串)
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
  refs: TooltipRefRow[]
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
  // 当前聚焦实例 instance_id(selectedInstanceId ?? focusedInstanceId 合并);用于
  // bracket 是否本身被点的判定(marker 分支必设, bracket 分支为 null)。
  selectedInstanceId?: string | null
  // ── Task 5 实例绑定:焦点实例(实例级)── marker 点击的精确实例(1 归属直选时非空)。
  // group 条目精确排除被点那一个实例(同身份兄弟实例不误伤)。
  focusedInstanceId?: string | null
  tooltipResolver?: (instanceId: string) => TooltipPayload
  // ── 缓冲窗/label 扩展(均可选,旧调用零改动) ──────────────────────────────────
  strictWindow?: { startIdx: number; endIdx: number } | null   // 严格窗边界(bar 索引);缺省不画
  hitLabel?: (hitId: string) => string | null              // hit 归属带 tooltip 行;null 不显示
  // ── dataZoom slider 显隐(可选,默认 true=显示,与历史行为一致) ──────────────
  sliderShow?: boolean
  // ── zoom 区间覆盖:传入则跳过 strictWindow 默认,保留用户当前 zoom(KlineChart
  //    render 时从 chart.getOption().dataZoom[0] 读出再回传,实现"非换股触发
  //    re-render 时不重置 zoom")。缺省/null = 走 strictWindow 默认,旧调用零回归。
  zoomOverride?: { start: number; end: number } | null
  // §7-4 整治：bracket marker 同时承载 hit_id + 端点 instance_id,让 buildMarkerTooltipFormatter
  // 的 event 三段分支也能触发。endNode 来自 eval_meta(铁律必有);缺省=不注入 instance_id(向后兼容)
  endNode?: string
  // ── M #3 / M' #19: bracket 三态 fill ────────────────────────────────────────
  selectedHitId?: string | null
  candidateHitIds?: ReadonlySet<string>
  // ── Task 5: highlight 三分支(group / focus / pendingDisambig) ───────────────
  highlightedEventIds?: ReadonlySet<string>
  pendingDisambigInstanceId?: string | null
  // ── spec 2026-07-10: 入口 D shift+click 已选中 marker 描边高亮 ────────────
  shiftSelectedEventIds?: ReadonlySet<string>
  hits?: HitDict[]  // buildSubOption 的 markerTooltip formatter 用（自 KlineChart.vue 透传）
  // ── 副图 band 竖直 zoom(spec 2026-07-03):由 KlineChart 传入,default 1.0 ──────
  zoomFactor?: number
  // ── 当前日(竖线落点,bar 索引)与当家行(←/→ 在其中走的那一族的 family_key);缺省都不画 ──
  currentDay?: number | null
  activeFamily?: string | null
  // ── band 表头:node 名后跟用户的特征名(mapping 对到它的特征)、compare 下没被任何框轨拉走的挂 app_only;键是 band ──
  bandExtras?: Readonly<Record<string, BandLabelExtra>>
}

/** band 表头 node 名后面跟的东西:用户特征名(浅灰底)、程序标记(如 app_only,等宽)。 */
export interface BandLabelExtra { feature?: string | null; tag?: string | null }

// ─── Task 5: 共享 event 数据抽取(供 buildMainOption/buildSubOption 消费) ──────

export interface EventBundle {
  pointData: any[]
  intervalData: any[]
  pricePointData: any[]
  bracketData: any[]
  highlightData: any[]
  highlightPriceData: any[]
  // ── spec 2026-07-11: shift+click 累积器命中 marker 的白蒙+黑线 overlay 数据 ──
  veilData: any[]         // 副图 point + interval
  veilPriceData: any[]    // 主图 pricePoint
  // bracket 每族一行的底线:{ value: [start, end, lane, ordinal], family_key, multi, active }(ordinal 只是族的先后,不画)
  bracketLineData: any[]
  // 副图每族一条底线:{ value: [start, end, lane, band, nBands], family_key, multi, active, afterWindow, summary }
  familyLineData: any[]
  // 当前日竖线:[{ value: [barIdx] }] 或空
  cursorData: any[]
  candle: number[][]
  volume: number[]
  dates: string[]
}

export function computeEventData(
  bars: Bar[], events: EventDict[], hits: HitDict[],
  input: BandRenderInput,
): EventBundle {
  const { topology, tagList, level, nodeColors, eventTier, nodeOfEventByBand, bandKeyOf,
          nodeVisible, tagToNodes, selectedInstanceId, endNode, strictWindow,
          highlightedEventIds: _highlightedEventIds,
          pendingDisambigInstanceId: _pendingDisambigInstanceId,
          shiftSelectedEventIds: _shiftSelectedEventIds,
          focusedInstanceId: _focusedInstanceId } = input
  const highlightedEventIds = _highlightedEventIds ?? new Set<string>()
  const pendingDisambigInstanceId = _pendingDisambigInstanceId ?? null
  const shiftSelectedEventIds = _shiftSelectedEventIds ?? new Set<string>()
  const focusedInstanceId = _focusedInstanceId ?? null
  // 副图分轨只含 time 轴 tag;render_grid='price' 的 tag(bo)不占轨道
  const subTags = subBandTagList(tagList, topology)

  // 段事件 node_id 由引擎 children 声明命名表直标子结构 node(tb_seg),
  // bandKeyOf(e)=e.node_id 天然分轨,无需前端路由。
  // tagToNodes 缺该键(旧调用/测试未传)时回落入参 nodeOfEventByBand。
  const nodeOf = (e: EventDict): string | null =>
    tagToNodes?.[bandKeyOf(e)]?.[0] ?? nodeOfEventByBand(e)

  const dates = bars.map((b) => b.date)
  const candle = bars.map((b) => [b.o, b.c, b.l, b.h])
  const volume = bars.map((b) => b.v)

  // pk 三态合成 + pk_id 反查(契约 C4/C5):必须按本股全部 events 算,在 level/nodeVisible
  // 过滤(下方 filtered)之前——被过滤掉的 bo 依然要能"突破"一个仍然可见的 pk。
  // 语义(槽名 broken/superseded、字段 peak_idx/pk_id)全封装在 peakState.ts,这里只调用。
  const pkStates = derivePeakStates(events)
  const pkIds = peakIdIndex(events)

  // ── level 门控 + nodeVisible band 筛选 ──
  // solve=False 的 node(如 pk 显示 node)不参与求解、恒为 detected tier;若按 RANK 过滤,
  // level=in_hit 时会被整段滤掉 → 免疫 level 门控(类型无关,solve 标志,Task 6 serialize 契约)。
  const RANK: Record<Level, number> = { in_hit: 2, qualified: 1, detected: 0 }
  const solveFreeNodes = new Set((topology?.nodes ?? []).filter(n => n.solve === false).map(n => n.node_id))
  // node 显隐筛选在前;副图的档位筛选放进 foldBand(梳子还是整条要用筛选前的成员数),主图价格点照旧按档位筛。
  const visibleEvents = events.filter((e) => isBandVisible(bandKeyOf(e), nodeVisible, tagToNodes))
  const passLevel = (e: EventDict): boolean =>
    solveFreeNodes.has(nodeOf(e) ?? '') || RANK[eventTier(e)] >= RANK[level]
  const priceAnchored = visibleEvents.filter((e) => renderGridOf(e, topology, bandKeyOf) === 'price' && passLevel(e))
  const timeAnchored = visibleEvents.filter((e) => renderGridOf(e, topology, bandKeyOf) !== 'price')

  // 事件色:一律 tier 色(类型无关)。pk 三态不走颜色——renderer 按 state 把 ▽ 画成
  // 实心/空心/浅灰虚线(pkTriStyle,spec 2026-08-31 §3.5.4),itemStyle.color 对 pk 不消费。
  const eColor = (e: EventDict): string => colorOf(eventTier(e), nodeOf(e), nodeColors)
  // 样本消费窗右端(tb v4 状态机 spec §10):events 全量下发,机器在尾缓冲区的轨迹
  // 有意可见;副图 band interval 越过 scanEnd(strictWindow.endIdx,= scan.end_date
  // 的 bar 索引)时拆两段——窗内段维持三档 level 色,窗后段降为 detected 灰
  // (「检测到但非样本」,与 detected/traced 灰色语义同族)。strictWindow 缺省不拆,
  // 与主图 buildShadingMarkArea shading 同门控。
  const scanEndIdx = strictWindow?.endIdx ?? null

  // pk 标签:只显示 id 数字,不带前缀、不带态名(spec 2026-08-31 §3.5.4)。pk_id 全局唯一,
  // 无需消歧;三态由 ▽ 形状编码,标签不再承担区分。
  const pkLabelOf = (e: EventDict): string =>
    typeof e.pk_id === 'number' ? String(e.pk_id) : ''

  // 与 bo 共锚的 bar 索引集合:pk 判别子 = 带 peak_idx(契约 C4),其余 price-anchored
  // 事件(bo 等)锚 start_idx。落在同一根 K 线上的 pk 需上移让开 bo 盒(PK_LIFT_OVER_BO)。
  const boAnchorIdx = new Set(
    priceAnchored
      .filter((e) => typeof e.peak_idx !== 'number')
      .map((e) => e.start_idx as number),
  )

  const pricePointData = priceAnchored.map((e) => {
    // 渲染锚点:pk 事件用 peak_idx(峰 bar 精确局部高点,serialize 平铺带出),价格查
    // bars[peak_idx].h(不读演化后的 price);start_idx 仍是事件几何锚(登记 bar)。
    // pk 判别子 = 带 peak_idx(number,契约 C4);bo 等其他 price-anchored 事件无 peak_idx,
    // 走 start_idx(原生锚,非"回退")。
    const isPk = typeof e.peak_idx === 'number'
    const renderIdx = (isPk ? e.peak_idx : e.start_idx) as number
    const bar = bars[renderIdx]
    const y = bar ? bar.h * 1.005 : 0
    const anchorY = bar ? bar.h : 0
    // bo 盒文本:ref_ids.broken 列出的被突破 pk instance_id → 查 pkIds 得 pk_id 数字
    // (契约 C5,取代已删的 broken_peak_ids 字段)。查不到(引用的 pk 不在本次 events 里)的
    // id 静默丢弃,不留 undefined 占位。
    const brokenIds = (e.ref_ids?.broken ?? []) as string[]
    const text = isPk
      ? pkLabelOf(e)
      : '[' + brokenIds.map((id) => pkIds.get(id)).filter((n): n is number => n != null).join(',') + ']'
    return {
      value: [renderIdx, y],
      instance_id: e.instance_id,
      tier: eventTier(e),
      itemStyle: { color: eColor(e) },
      anchorY, text,
      // pk marker 渲染元数据(renderer 按 state 存在性分派三角形/盒)。state 由
      // pkStates(derivePeakStates,契约 C4)合成,不再读事件自带字段。
      state: isPk ? pkStates.get(e.instance_id) ?? 'alive' : undefined,
      pkId: typeof e.pk_id === 'number' ? e.pk_id : undefined,
      // 同锚避让量:三个 pricePoint renderer(本体 / 高亮 / shift-veil)统一消费,
      // highlight 与 veil 条目由 { ...d } 复制携带,无需各自重算。
      pkLift: isPk && boAnchorIdx.has(renderIdx) ? PK_LIFT_OVER_BO : 0,
    }
  })

  // ── 副图:每条 band 折叠(render/fold.ts)→ 以族为单位分行 → 每个记号(整条 / 格 / 点)一条记录 ──
  // 点还是条按拓扑 node 的 is_point 声明分,不按单个实例碰巧只占一根 K 线。
  const byId = new Map(events.map((e) => [e.instance_id, e]))
  const anchorFields = [...new Set((topology?.edges ?? []).map((ed) => ed.anchor_field)
    .filter((f): f is string => !!f))]
  const pointNodes = new Set((topology?.nodes ?? []).filter((n) => n.is_point === true).map((n) => n.node_id))
  const activeFamily = input.activeFamily ?? null
  const intervalData: any[] = []
  const pointData: any[] = []
  const familyLineData: any[] = []
  // instance_id → 它在图上的位置:高亮、消歧、shift-veil 都经它反查
  const placeOf = new Map<string, { family: Family; mark: FoldMark; lane: number; band: number; rec: any }>()
  const nBands = subTags.length
  const lineParts = (start: number, end: number) =>
    scanEndIdx === null ? [{ start, end, afterWindow: false }] : splitIntervalAtScanEnd({ start, end }, scanEndIdx)
  subTags.forEach((tag, band) => {
    const inBand = timeAnchored.filter((e) => bandKeyOf(e) === tag)
    if (inBand.length === 0) return
    const node = tagToNodes?.[tag]?.[0] ?? tag
    const families = foldBand(inBand, {
      band: tag, isPoint: pointNodes.has(node), tierOf: eventTier, level, levelImmune: solveFreeNodes.has(node),
    })
    for (const { f, lane } of packLanes(families.map((f) => ({ start_idx: f.start, end_idx: f.end, f })))) {
      for (const part of lineParts(f.start, f.end)) {
        familyLineData.push({
          value: [part.start, part.end, lane, band, nBands], family_key: f.key, multi: f.multi,
          active: activeFamily === f.key, afterWindow: part.afterWindow,
          summary: familySummary(f, byId, eventTier, dates),
        })
      }
      for (const mark of f.marks) {
        const color = colorOf(mark.tier, node, nodeColors)
        const after = colorOf('detected', node, nodeColors)
        const base = {
          instance_id: mark.memberIds[0], member_ids: mark.memberIds,
          member_labels: mark.memberIds.length >= 2
            ? memberLabels(mark.memberIds, byId, anchorFields).map((l) => formatMemberLabel(l, dates))
            : undefined,
          member_k: mark.memberIds.map((id) => f.memberIds.indexOf(id) + 1),
          family_n: f.memberIds.length, family_key: f.key, family_start: f.start,
          mark_kind: mark.kind, tier: mark.tier,
        }
        const H = TIER_H[mark.tier]
        let first: any = null
        if (mark.kind === 'point') {
          first = { ...base, value: [mark.start, mark.end, lane, band, nBands, H], itemStyle: { color } }
          pointData.push(first)
        } else if (mark.kind === 'cell' || scanEndIdx === null) {
          // 格整格判在扫描窗前还是后
          const isAfter = scanEndIdx !== null && mark.start > scanEndIdx
          first = { ...base, value: [mark.start, mark.end, lane, band, nBands, H],
                    itemStyle: { color: isAfter ? after : color } }
          intervalData.push(first)
        } else {
          // 整条跨过扫描末日:拆窗内 / 窗后两段,共享成员与族
          for (const part of splitIntervalAtScanEnd({ start: mark.start, end: mark.end }, scanEndIdx)) {
            const rec = { ...base, value: [part.start, part.end, lane, band, nBands, H],
                          itemStyle: { color: part.afterWindow ? after : color } }
            intervalData.push(rec)
            first ??= rec
          }
        }
        for (const id of mark.memberIds) placeOf.set(id, { family: f, mark, lane, band, rec: first })
      }
    }
  })

  // ── bracket 轨:hit 按同起点折;每族一行,记号是 hit 的终点(整条 / 格),买入日 ▼ 叠在上面 ──
  const hitsById = new Map(hits.map((m) => [m.hit_id, m]))
  const nodeOrder = (topology?.nodes ?? []).map((n) => n.node_id)
  const hitLabelTexts = (ids: string[]): string[] | undefined => ids.length >= 2
    ? hitLabels(ids, hitsById, byId, nodeOrder, anchorFields).map((l) => formatMemberLabel(l, dates))
    : undefined
  const bracketData: any[] = []
  const bracketLineData: any[] = []
  const hitFamilies = foldHits(hits, events, endNode)
  const hitFamilyOf = new Map<string, { family: HitFamily; lane: number; ordinal: number }>()
  const packedHits = packLanes(hitFamilies.map((f, i) => ({ start_idx: f.start, end_idx: f.end, f, ordinal: i + 1 })))
  for (const { f, lane, ordinal } of packedHits) {
    for (const id of f.hitIds) hitFamilyOf.set(id, { family: f, lane, ordinal })
    bracketLineData.push({ value: [f.start, f.end, lane, ordinal], family_key: f.key, multi: f.multi,
                           active: activeFamily === f.key })
    for (const mark of f.marks) {
      const rec: { value: number[]; kind: 'mark'; mark_kind: string; hit_id: string; hit_ids: string[];
                   family_key: string; family_start: number; hit_labels?: string[]; instance_id?: string } = {
        value: [mark.start, mark.end, lane, ordinal], kind: 'mark', mark_kind: mark.kind,
        hit_id: mark.hitIds[0], hit_ids: mark.hitIds, family_key: f.key, family_start: f.start,
        hit_labels: hitLabelTexts(mark.hitIds),
      }
      if (endNode) {
        const v = hitsById.get(mark.hitIds[0])?.node_index?.[endNode]
        if (v) rec.instance_id = v
      }
      bracketData.push(rec)
    }
    for (const buy of f.buys) {
      bracketData.push({ value: [buy.day, buy.day, lane, ordinal], kind: 'buy', buy_day: buy.day,
                         buy_date: dates[buy.day] ?? String(buy.day),
                         hit_id: buy.hitIds[0], hit_ids: buy.hitIds, family_key: f.key, family_start: f.start,
                         hit_labels: hitLabelTexts(buy.hitIds) })
    }
  }

  // ── 高亮:成员所在族行上画空心跨度框([族起点, 成员终点])+ 它那一格粗框;点记号照旧画放大实心版 ──
  // group 条目跳过焦点实例(被点者由 focus 条目独家表达);同一个记号只画一次。
  type HlKind = 'group' | 'focus' | 'pendingDisambig'
  const highlightData: any[] = []
  const highlightPriceData: any[] = []
  const drawn = new Set<string>()
  const pushHl = (id: string, kind: HlKind): boolean => {
    const at = placeOf.get(id)
    if (!at) return false
    const ev = byId.get(id)
    const tag = `${kind}|${at.family.key}|${at.mark.start}`
    if (drawn.has(tag)) return true
    drawn.add(tag)
    const color = at.rec?.itemStyle?.color
    if (at.mark.kind === 'point') {
      highlightData.push({ ...at.rec, kind, shape: 'point' })
      return true
    }
    if (at.mark.kind === 'cell' && ev) {
      highlightData.push({ value: [at.family.start, ev.end_idx, at.lane, at.band, nBands], instance_id: id,
                           kind, shape: 'extent', itemStyle: { color } })
    }
    highlightData.push({ value: [at.mark.start, at.mark.end, at.lane, at.band, nBands, TIER_H[at.mark.tier]],
                         instance_id: id, kind, shape: 'mark', itemStyle: { color } })
    return true
  }
  if (highlightedEventIds.size > 0) {
    for (const id of highlightedEventIds) {
      if (id === focusedInstanceId) continue
      if (!pushHl(id, 'group')) {
        const pp = pricePointData.find((d) => d.instance_id === id)
        if (pp) highlightPriceData.push({ ...pp, kind: 'group' as HlKind })
      }
    }
  }
  if (pendingDisambigInstanceId && !pushHl(pendingDisambigInstanceId, 'pendingDisambig')) {
    const pp = pricePointData.find((d) => d.instance_id === pendingDisambigInstanceId)
    if (pp) highlightPriceData.push({ ...pp, kind: 'pendingDisambig' as HlKind })
  }
  // focus 条目按当前聚焦实例 —— selectedInstanceId 是合并 ref(= store selectedInstanceId ?? focusedInstanceId),
  // 覆盖 0 归属与 1 归属(直选 hit)
  if (selectedInstanceId && !pushHl(selectedInstanceId, 'focus')) {
    const pp = pricePointData.find((d) => d.instance_id === selectedInstanceId)
    if (pp) highlightPriceData.push({ ...pp, kind: 'focus' as HlKind })
  }

  // ── shift-veil overlay(z2:22 独立层,fill 白蒙 + 黑横线):记号里任一成员被 shift 选中就盖 ──
  const veilData: any[] = []
  const veilPriceData: any[] = []
  if (shiftSelectedEventIds.size > 0) {
    const hitAny = (d: { member_ids?: string[]; instance_id: string }) =>
      (d.member_ids ?? [d.instance_id]).some((id) => shiftSelectedEventIds.has(id))
    for (const d of pointData) if (hitAny(d)) veilData.push({ ...d, kind: 'point' })
    for (const d of intervalData) if (hitAny(d)) veilData.push({ ...d, kind: 'interval' })
    for (const d of pricePointData) {
      if (shiftSelectedEventIds.has(d.instance_id)) veilPriceData.push({ ...d, kind: 'pricePoint' })
    }
  }

  const currentDay = input.currentDay ?? null
  const cursorData = currentDay === null || currentDay < 0 || currentDay >= bars.length ? [] : [{ value: [currentDay] }]

  return {
    pointData, intervalData, pricePointData,
    bracketData, bracketLineData, familyLineData, cursorData,
    highlightData, highlightPriceData,
    veilData, veilPriceData,
    candle, volume, dates,
  }
}

/** 悬停族底线时的摘要(等宽、键值):起点、终点范围、成员数与各档个数。 */
function familySummary(f: Family, byId: ReadonlyMap<string, EventDict>, tierOf: (e: EventDict) => Tier,
                       dates: readonly string[]): string {
  const ends = f.memberIds.map((id) => byId.get(id)?.end_idx ?? f.end)
  const count: Record<Tier, number> = { in_hit: 0, qualified: 0, detected: 0 }
  for (const id of f.memberIds) {
    const e = byId.get(id)
    if (e) count[tierOf(e)] += 1
  }
  const d = (i: number) => dates[i] ?? String(i)
  return [
    `start: ${d(f.start)}`,
    `end: ${d(Math.min(...ends))} … ${d(Math.max(...ends))}`,
    `members: ${f.memberIds.length}`,
    `in_hit: ${count.in_hit}`, `qualified: ${count.qualified}`, `detected: ${count.detected}`,
  ].join('<br/>')
}

// ─── buildMainOption / buildSubOption(消费同一份 EventBundle,双 ECharts 实例架构)──

/** buildMainOption 用到的那部分渲染入参(annotate 模式只给 sliderShow / zoomOverride)。 */
export type MainOptionInput = Pick<BandRenderInput,
  'strictWindow' | 'sliderShow' | 'zoomOverride' | 'tooltipResolver' | 'hitLabel'
  | 'candidateHitIds' | 'hits'>

/** 没有任何 app 产物的 EventBundle:annotate 模式只画 K 线和成交量。 */
export function emptyEventBundle(bars: Bar[]): EventBundle {
  return {
    pointData: [], intervalData: [], pricePointData: [],
    bracketData: [], bracketLineData: [], familyLineData: [], cursorData: [],
    highlightData: [], highlightPriceData: [],
    veilData: [], veilPriceData: [],
    candle: bars.map((b) => [b.o, b.c, b.l, b.h]),
    volume: bars.map((b) => b.v),
    dates: bars.map((b) => b.date),
  }
}

// ── 主图布局:上面 K 线区(grid0),下面成交量带(grid1),共用 x 轴缩放 ──
/** 成交量带高度 / K 线区高度:默认「约主图的四分之一」,待验证。 */
export const VOLUME_HEIGHT_RATIO = 0.25
export const MAIN_GRID_TOP = 40        // 顶部留给代码标题条
export const MAIN_GRID_GAP = 16        // K 线区与成交量带之间(两条 y 轴的端点刻度不相撞)
export const MAIN_GRID_LEFT = 56
export const MAIN_GRID_RIGHT = 16
export const MAIN_DEFAULT_HEIGHT = 600 // 拿不到容器高度时(单元测试)的兜底
export const MAIN_BOTTOM_WITH_SLIDER = 60   // 成交量带下沿到容器底:日期刻度 + 缩放滑块
export const MAIN_BOTTOM_NO_SLIDER = 20     // 只剩日期刻度

/** 主图两个 grid 的像素布局:成交量带高 = K 线区高 × VOLUME_HEIGHT_RATIO,滑块留在最下方。 */
export function mainGridLayout(height: number, sliderShow: boolean) {
  const bottom = sliderShow ? MAIN_BOTTOM_WITH_SLIDER : MAIN_BOTTOM_NO_SLIDER
  const usable = Math.max(0, height - MAIN_GRID_TOP - MAIN_GRID_GAP - bottom)
  const priceH = usable / (1 + VOLUME_HEIGHT_RATIO)
  const volH = usable - priceH
  return [
    { left: MAIN_GRID_LEFT, right: MAIN_GRID_RIGHT, top: MAIN_GRID_TOP, height: priceH },
    { left: MAIN_GRID_LEFT, right: MAIN_GRID_RIGHT, top: MAIN_GRID_TOP + priceH + MAIN_GRID_GAP, height: volH },
  ]
}

/** 成交量轴刻度:1.2K / 3.4M / 5.6B。 */
function formatVolumeTick(v: number): string {
  const a = Math.abs(v)
  if (a >= 1e9) return `${+(v / 1e9).toFixed(1)}B`
  if (a >= 1e6) return `${+(v / 1e6).toFixed(1)}M`
  if (a >= 1e3) return `${+(v / 1e3).toFixed(1)}K`
  return String(v)
}

export function buildMainOption(
  bars: Bar[], bundle: EventBundle, input: MainOptionInput,
  opts?: { getChartEl?: () => HTMLElement | null; height?: number },
): unknown {
  const { strictWindow, sliderShow, zoomOverride,
          tooltipResolver, hitLabel, candidateHitIds } = input
  const { dates, candle, pricePointData, highlightPriceData, veilPriceData } = bundle

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

  const { volSeries, yAxisOverride, volAxisMax } = buildVolumeSeriesAndYAxis(bars, initVisStart, initVisEnd)
  const shadingMarkArea = sw ? buildShadingMarkArea(bars, bars[sw.startIdx].date, bars[sw.endIdx].date) : null

  const klineSeries: Record<string, unknown> = {
    type: 'candlestick', name: 'kline', data: candle, xAxisIndex: 0, yAxisIndex: 0,
    barWidth: '70%',
    itemStyle: {
      borderWidth: 2,
      color: CANDLE_UP,
      color0: CANDLE_DOWN,
      borderColor: CANDLE_UP,
      borderColor0: CANDLE_DOWN,
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

  const markerTooltip = (tooltipResolver || hitLabel)
    ? { trigger: 'item' as const, show: true, confine: false,
        position: opts?.getChartEl ? makeViewportAwarePosition(opts.getChartEl) : viewportAwareTooltipPosition,
        extraCssText: 'max-height: calc(100vh - 16px); overflow-y: auto;',
        formatter: buildMarkerTooltipFormatter(tooltipResolver, hitLabel,
          { hits: input.hits ?? [], candidateHitIds: candidateHitIds ?? new Set() }) }
    : undefined

  return {
    animation: false,
    tooltip,
    // axisPointer.link 删除:双实例 echarts.connect 接管
    grid: mainGridLayout(opts?.height ?? MAIN_DEFAULT_HEIGHT, sliderShow ?? true),
    xAxis: [{
      type: 'category', data: dates, gridIndex: 0, boundaryGap: true,
      axisLine: { onZero: false }, splitLine: { show: false },
      axisLabel: { show: false }, axisTick: { show: false },   // 日期刻度画在下面成交量带的 x 轴上
      min: 'dataMin', max: 'dataMax',
      // G2 视觉隐:真实竖线由 CrosshairOverlay(DOM)一根到底渲染,axisPointer 只留 hover 事件源(修 S3)
      axisPointer: {
        show: true, type: 'none', snap: true,
        label: { show: false },
        triggerTooltip: false,
      },
    }, {
      // 成交量带:与 K 线区同一组日期,hover 同样只当事件源
      type: 'category', data: dates, gridIndex: 1, boundaryGap: true,
      axisLine: { onZero: false }, splitLine: { show: false },
      min: 'dataMin', max: 'dataMax',
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
    }, {
      gridIndex: 1, min: 0, max: volAxisMax, splitNumber: 2,
      axisLabel: { formatter: formatVolumeTick, showMaxLabel: false },   // 上限是可见区间最大量,不是整数刻度
    }],
    dataZoom: [
      { type: 'inside', xAxisIndex: [0, 1], start: zoomStart, end: zoomEnd },
      { type: 'slider', xAxisIndex: [0, 1], top: '92%', start: zoomStart, end: zoomEnd,
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
      // 成交量带同样整列 hover 出同一份 K 线 tooltip
      { type: 'custom', name: 'volume-hit-spanner', xAxisIndex: 1, yAxisIndex: 1,
        data: bars.map((_, i) => [i]),
        renderItem: renderHitSpanner,
        encode: { x: 0 }, z: 0, zlevel: 0, silent: false, animation: false,
        tooltip: { show: true, confine: true,
                   formatter: buildBarTooltipFormatter(bars) } },
      { type: 'custom', name: 'price-points', xAxisIndex: 0, yAxisIndex: 0,
        data: pricePointData, renderItem: makeRenderPricePoint(pricePointData),
        encode: { x: 0, y: 1 }, z: 12, clip: false, tooltip: markerTooltip },
      // animation:true 同副图 highlight 系列:series 级显式开关放行 keyframeAnimation(pending 闪烁)
      { type: 'custom', name: 'highlight-price', xAxisIndex: 0, yAxisIndex: 0,
        data: highlightPriceData, animation: true,
        renderItem: makeRenderPricePointHighlight(highlightPriceData),
        encode: { x: 0, y: 1 }, z: 21, clip: false, tooltip: markerTooltip },
      { type: 'custom', name: 'shift-veil-price', xAxisIndex: 0, yAxisIndex: 0,
        data: veilPriceData, animation: false, silent: true,
        renderItem: makeRenderShiftVeilPrice(veilPriceData),
        z: 22 },
      // 当前日竖线(K 线区与成交量带各一条,z:10):压在 K 线柱子与成交量柱上层,鼠标移开后照样看得见
      // (画在下层时会被当天那根 K 线与上下影线整段盖住);两侧白边压在任何柱色上都拉开深浅。
      // 低于价格标记(z:12)与高亮(z:21),▲▼ 仍压在竖线上面。
      { type: 'custom', name: 'current-day', xAxisIndex: 0, yAxisIndex: 0,
        data: bundle.cursorData, silent: true, animation: false,
        renderItem: renderCursor, encode: { x: 0 }, z: 10 },
      { type: 'custom', name: 'current-day-volume', xAxisIndex: 1, yAxisIndex: 1,
        data: bundle.cursorData, silent: true, animation: false,
        renderItem: renderCursor, encode: { x: 0 }, z: 10 },
    ],
  }
}

// Task 3: 副图装饰几何 graphic 组件数组构造(独立于 dataZoom,像素坐标)
// spec: docs/superpowers/specs/2026-07-01-path2-web-subchart-fixed-decor-design.md
// 返回顺序: zebra(z=1) → subDivider(z=2) + band-inner splitLine(z=2) → bandLabels/hitsLabel(z=5)
// 用于 buildSubOption 的 option.graphic 字段;所有元素 silent=true 避免抢 hover 事件。
export function buildSubDecorGraphics(
  bandGeom: BandGeom[],
  dividerY: number,
  bracketH: number,
  bandLabelTexts: string[],
  hitsLabelVisible: boolean,
  chartSubWidth: number,
  zoomFactor: number = 1.0,
  active: { band?: number; hits?: boolean } = {},   // 当家行所在那条 band / bracket 的表头加粗
  extras: readonly (BandLabelExtra | null)[] = [],  // 表头 node 名后跟的用户特征名 / app_only(按 band 下标)
  hitsTop: number = BAND_TOP_PAD,                    // hits 表头的顶(compare 下让出上面的 user 行)
): any[] {
  const graphics: any[] = []
  const rectWidth = chartSubWidth - SUB_GRID_LEFT - SUB_GRID_RIGHT

  // 1. zebra: 每 band 一条 rect,隔行 fill
  bandGeom.forEach((g, bi) => {
    if (!g) return
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
    if (!g || g.laneCount <= 1) return
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
    if (!g) return
    const text = bandLabelTexts[bi] ?? ''
    const ex = extras[bi] ?? null
    const weight = active.band === bi ? 'bold' : 'normal'
    // 特征名是用户写的内容:正常字体、浅灰底;app_only 是程序固定文字:等宽
    const esc = (t: string) => t.replace(/[{}|]/g, ' ')
    const rich = ex && (ex.feature || ex.tag)
      ? `{n|${esc(text)}}${ex.feature ? `  {biz|${esc(ex.feature)}}` : ''}${ex.tag ? `  {tag|${esc(ex.tag)}}` : ''}`
      : null
    graphics.push({
      type: 'text',
      left: SUB_GRID_LEFT + 2,
      top: g.top + BAND_TOP_PAD,
      textAlign: 'left',
      textVerticalAlign: 'top',
      style: rich
        ? { text: rich, rich: {
            n: { fill: '#000000', fontSize: 13, fontWeight: weight },
            biz: { fill: '#000000', fontSize: 12, backgroundColor: '#f4f4f5', padding: [1, 4], borderRadius: 3 },
            tag: { fill: '#000000', fontSize: 11, fontFamily: MONO },
          } }
        : {
            text,
            fill: '#000000',
            fontSize: 13,
            fontWeight: weight,
          },
      z: 5,
      silent: true,
    })
  })

  // 5. hitsLabel: bracket 区左侧文字(仅在 hitsLabelVisible=true 时),同款靠上对齐
  if (hitsLabelVisible) {
    graphics.push({
      type: 'text',
      left: SUB_GRID_LEFT + 2,
      top: hitsTop,   // 与 bandLabels 的 pad 锚定语义对称(unify 顶 pad)
      textAlign: 'left',
      textVerticalAlign: 'top',
      style: {
        text: 'hits',
        fill: '#000000',
        fontSize: 13,
        fontFamily: MONO,
        fontWeight: active.hits ? 'bold' : 'normal',
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
  const { tooltipResolver, hitLabel, zoomOverride, strictWindow,
          selectedHitId, candidateHitIds } = input
  const { dates, pointData, intervalData, bracketData, highlightData, veilData } = bundle
  const z = input.zoomFactor ?? 1.0   // 副图 band 竖直 zoom(spec 2026-07-03)
  const bracketTop = subGeom.appBracketTop ?? BAND_TOP_PAD

  const N = bars.length
  const sw = strictWindow ?? null
  const hasBuffer = sw !== null && (sw.startIdx > 0 || sw.endIdx < N - 1)
  const zoomStart = zoomOverride?.start ?? (hasBuffer ? (sw!.startIdx / N) * 100 : 0)
  const zoomEnd   = zoomOverride?.end   ?? (hasBuffer ? ((sw!.endIdx + 1) / N) * 100 : 100)

  const markerTooltip = (tooltipResolver || hitLabel)
    ? { trigger: 'item' as const, show: true, confine: false,
        position: opts?.getChartEl ? makeViewportAwarePosition(opts.getChartEl) : viewportAwareTooltipPosition,
        extraCssText: 'max-height: calc(100vh - 16px); overflow-y: auto;',
        formatter: buildMarkerTooltipFormatter(tooltipResolver, hitLabel,
          { hits: input.hits ?? [], candidateHitIds: candidateHitIds ?? new Set() }) }
    : undefined

  // 装饰几何(zebra/subDivider/bandLabels/hitsLabel)改走 option.graphic,不再挂 series
  const bandLabelTexts = subBandTagList(input.tagList, input.topology)
  const hitsLabelVisible = bracketData.length > 0
  // 当家行所在那条 band(或 bracket)的表头名字加粗
  const activeKey = input.activeFamily ?? null
  const activeBand = activeKey ? bandLabelTexts.indexOf(activeKey.slice(0, activeKey.lastIndexOf('@'))) : -1
  const decorGraphics = buildSubDecorGraphics(
    subGeom.bandGeom,
    subGeom.dividerY,
    subGeom.bracketH,
    bandLabelTexts,
    hitsLabelVisible,
    chartSubWidth,
    z,
    { band: activeBand, hits: !!activeKey && activeKey.startsWith(`${HIT_FAMILY_PREFIX}@`) },
    bandLabelTexts.map((b) => input.bandExtras?.[b] ?? null),
    bracketTop,
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
      // 族底线(z:8,在条与格下层);透明命中区给族摘要悬停
      { type: 'custom', name: 'family-lines', xAxisIndex: 0, yAxisIndex: 0,
        data: bundle.familyLineData,
        renderItem: makeRenderFamilyLine(bundle.familyLineData, subGeom.bandGeom, z),
        encode: { x: [0, 1] }, z: 8,
        tooltip: { show: true, formatter: (p: any) => bundle.familyLineData[p.dataIndex]?.summary ?? '' } },
      // intervals (z:9):整条与格
      { type: 'custom', name: 'intervals', xAxisIndex: 0, yAxisIndex: 0,
        data: intervalData,
        renderItem: (p: any, api: any) => renderIntervalWithGeom(p, api, subGeom.bandGeom, z),
        encode: { x: [0, 1] }, z: 9, tooltip: markerTooltip },
      // points (z:10)
      { type: 'custom', name: 'points', xAxisIndex: 0, yAxisIndex: 0,
        data: pointData,
        renderItem: (p: any, api: any) => renderPointWithGeom(p, api, subGeom.bandGeom, z),
        encode: { x: 0 }, z: 10, tooltip: markerTooltip },
      // bracket 族底线(z:10)
      { type: 'custom', name: 'bracket-lines', xAxisIndex: 0, yAxisIndex: 0,
        data: bundle.bracketLineData, silent: true,
        renderItem: makeRenderBracketLine(bundle.bracketLineData, z, bracketTop),
        encode: { x: [0, 1] }, z: 10 },
      // brackets (z:11):hit 的记号与买入日 ▼。focus 信号:selectedHitId 存在且无实例焦点 ⟺ bracket
      // 本身是被点者(KlineChart.ts bracket 分支走 focusHit 不设实例;marker 分支必设)
      { type: 'custom', name: 'brackets', xAxisIndex: 0, yAxisIndex: 0,
        data: bracketData,
        renderItem: makeRenderBracket(bracketData, selectedHitId ?? null, candidateHitIds ?? new Set(), z,
          (selectedHitId ?? null) !== null && (input.selectedInstanceId ?? null) === null, bracketTop),
        encode: { x: [0, 1] }, z: 11, tooltip: markerTooltip,
        emphasis: { disabled: true } },
      // highlight (z:20)。animation:true 为 series 级显式开关:keyframeAnimation(pending 闪烁)
      // 被 isAnimationEnabled() 闸住,继承顶层 animation:false 会整体跳过动画。
      { type: 'custom', name: 'highlight', xAxisIndex: 0, yAxisIndex: 0,
        data: highlightData, animation: true,
        renderItem: makeRenderHighlightWithGeom(highlightData, subGeom.bandGeom, z),
        encode: { x: 0 }, z: 20, tooltip: markerTooltip },
      // shift-veil (z:22 高于 highlight,spec 2026-07-11):fill 白蒙 + 黑横线,与 highlight 三分支正交
      { type: 'custom', name: 'shift-veil', xAxisIndex: 0, yAxisIndex: 0,
        data: veilData, animation: false, silent: true,
        renderItem: makeRenderShiftVeil(veilData, subGeom.bandGeom, z),
        z: 22 },
      // 当前日竖线(z:30,最上层):缩小后连成一片的格会把下层的线整段盖住;两侧白边压在任何色块上都拉开深浅
      { type: 'custom', name: 'current-day', xAxisIndex: 0, yAxisIndex: 0,
        data: bundle.cursorData, silent: true, animation: false,
        renderItem: renderCursor, encode: { x: 0 }, z: 30 },
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

// 选中词汇(2026-07-08 改):三档皆保 node/tier 分色(in_hit=node本色,qualified/detected=灰),
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
// color 由 itemStyle.color 传入,已按 colorOf 三档分:in_hit=node本色 / qualified=中灰 / detected=浅灰。
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
// 重画盒+文本(字号不变)。stackOffset 与 renderPricePoint 同步(BO_STACK_PT)。
// 2026-07-08 改:同 buildHlShape,group/focus 保 tier 分色(in_hit=橙/灰) + 细/粗深边;
// 文字色全 tier 统一 HL_FOCUS_EDGE(灰底可读,橙底可读);pending 白底+闪烁分层不动。
// ⚠ closure factory:ECharts customSeries 不在 params 中传 data item,必须按 dataIndex 反查。
export function makeRenderPricePointHighlight(
  data: Array<{ value: number[]; instance_id: string; anchorY: number; text: string;
                 itemStyle: { color: string };
                 kind: 'group' | 'focus' | 'pendingDisambig';
                 state?: string; pkLift?: number }>,
) {
  return function renderPricePointHighlight(params: any, api: any) {
    const item = data[params.dataIndex] ?? null
    const hlKind = item?.kind ?? 'focus'
    const anchorY = item?.anchorY ?? api.value(1)
    const text = item?.text ?? ''
    const color = item?.itemStyle?.color ?? '#888888'
    const [cx, anchorPx] = api.coord([api.value(0), anchorY])

    // pk 事件(state 存在)→ 放大 ▽(×1.4)+ id 标签,与 makeRenderPricePoint 同一分派。
    // 三态形状编码(pkTriStyle:实心/空心/浅灰虚线)在高亮层原样保留,选中只加粗描边 + shadow
    // (group 细边 / focus 粗边,与 bo 盒同一词汇)。空心态放大版给白底:盖住下层本体 ▽,
    // 免得两层轮廓套叠成「双三角」(实心态本就不透)。
    if (item?.state) {
      const lift = item.pkLift ?? 0        // 与本体 renderer 同步的同锚避让量
      const triCy = anchorPx - TRIANGLE_STACK_PT - lift
      const tw = PK_TRIANGLE_HALF_WIDTH * 1.4
      const th = PK_TRIANGLE_HEIGHT * 1.4
      const idCy = anchorPx - PEAK_ID_STACK_PT - lift
      const tri = pkTriStyle(item.state)
      const hlFill = tri.fill === 'none' ? '#ffffff' : tri.fill
      const hlWidth = hlKind === 'group' ? HL_GROUP_STROKE_WIDTH : HL_FOCUS_STROKE_WIDTH
      const triShape = {
        points: [[cx - tw, triCy - th / 2], [cx + tw, triCy - th / 2], [cx, triCy + th / 2]],
      }
      const textEl = {
        type: 'text',
        style: { text, x: cx, y: idCy, fill: tri.stroke, fontSize: MARKER_FONT_SIZE,
                 fontWeight: 'bold', align: 'center', verticalAlign: 'middle' },
      }
      const children: any[] = hlKind === 'pendingDisambig'
        ? [
            { type: 'polygon', shape: triShape,
              style: { fill: '#ffffff', stroke: HL_STROKE, lineWidth: HL_FOCUS_STROKE_WIDTH, ...HL_SHADOW } },
            { type: 'polygon', shape: triShape,
              style: { ...tri, fill: hlFill, lineWidth: HL_FOCUS_STROKE_WIDTH },
              keyframeAnimation: pendingBlinkAnimation() },
            textEl,
          ]
        : [
            { type: 'polygon', shape: triShape,
              style: { ...tri, fill: hlFill, lineWidth: hlWidth, ...HL_SHADOW } },
            textEl,
          ]
      return { type: 'group', silent: true, z2: 21, children }
    }

    // bo 事件:圆角矩形盒 + [broken_peak_ids] 文本(原逻辑不变)
    const stackOffset = BO_STACK_PT
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
// (bandZebra/subDivider/hitsLabel/bandLabels 4 个 renderer 已随 Task 4 迁移到
//  buildSubDecorGraphics 的 option.graphic 装配,不再需要 ECharts custom series renderItem)

// renderIntervalWithGeom / renderPointWithGeom:改从 bandGeom 派生 bandTop/bandH
export function renderIntervalWithGeom(
  params: any,
  api: any,
  bandGeom: BandGeom[],
  zoomFactor: number = 1.0,
) {
  const lane = api.value(2) || 0
  const band = api.value(3) || 0
  const g = bandGeom[band]
  if (!g) return { type: 'group', children: [] }
  const { x0, x1 } = markXRange(api, api.value(0), api.value(1))
  const { y, laneH } = laneBox(g, lane, zoomFactor)
  // 档位按高度分三档、底对齐(value[5] = 高度比例;缺省满高)
  const h = laneH * (api.value(5) || 1)
  return {
    type: 'rect',
    shape: { x: x0, y: y + laneH - h, width: Math.max(2, x1 - x0), height: h },
    style: api.style(),
  }
}

/** lane 在 band 里的竖直范围:自顶向下堆叠,lane0 贴 band 顶 pad(与 bracket 区方向一致)。 */
export function laneBox(g: BandGeom, lane: number, zoomFactor: number): { y: number; laneH: number } {
  const laneH = BAND_MARKER_H * zoomFactor
  const gap = BAND_LANE_GAP * zoomFactor
  const rawY = g.top + BAND_TOP_PAD + lane * (laneH + gap)
  const y = Math.max(g.top + BAND_TOP_PAD, Math.min(rawY, g.top + g.h - BAND_BOT_PAD - laneH))
  return { y, laneH }
}

/** 记号的横向范围:从起点那根 K 线中心 −MARK_HALF_W 根到终点那根中心 +MARK_HALF_W 根(只占一根的记号也有一格宽)。 */
export function markXRange(api: any, start: number, end: number, pad = 0): { x0: number; x1: number } {
  const unitW = api.size([1, 0])[0]
  return {
    x0: api.coord([start, 0])[0] - MARK_HALF_W * unitW - pad,
    x1: api.coord([end, 0])[0] + MARK_HALF_W * unitW + pad,
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
  // 档位按大小分三档(value[5] = 高度比例;缺省满尺寸)
  const k = 0.6 + 0.4 * (api.value(5) || 1)
  const w = Math.max(5, Math.min(20, unitW * 0.35)) * k
  return {
    type: 'polygon',
    shape: { points: [[x, centerY + 4 * zoomFactor * k], [x - w, centerY - 3 * zoomFactor * k],
                      [x + w, centerY - 3 * zoomFactor * k]] },
    style: api.style(),
  }
}

// makeRenderHighlightWithGeom:三种形状——
//   point :点记号的放大实心版(group/focus 单图形,pending 白底+闪烁双层,见 buildHlShape);
//   extent:成员的完整跨度 [族起点, 成员终点],空心细框,不填色(实心复本会盖住族行里后面的格子);
//   mark  :成员所在的那一格(或整条),空心粗框;pending 时框闪烁。
// 线宽:group 细、focus / pending 粗。一律 silent:true 让 hover/click 穿透到本体系列。
export function makeRenderHighlightWithGeom(
  items: Array<{ value: number[]; instance_id: string; itemStyle?: { color?: string };
                 kind: 'group' | 'focus' | 'pendingDisambig'; shape?: 'point' | 'extent' | 'mark' }>,
  bandGeom: BandGeom[],
  zoomFactor: number = 1.0,   // 副图 band 竖直 zoom(spec 2026-07-03)
) {
  return function renderHighlight(params: any, api: any) {
    const item = items[params.dataIndex]
    const hlKind = item?.kind ?? 'focus'
    const color = item?.itemStyle?.color ?? '#888888'
    const lane = (item?.value?.[2] as number) || 0
    const band = (item?.value?.[3] as number) || 0
    const g = bandGeom[band]
    if (!item || !g) return { type: 'group', children: [] }
    const lw = hlKind === 'group' ? HL_GROUP_STROKE_WIDTH : HL_FOCUS_STROKE_WIDTH
    if (item.shape === 'point') {
      const x = api.coord([api.value(0), 0])[0]
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
    }
    const { y, laneH } = laneBox(g, lane, zoomFactor)
    if (item.shape === 'extent') {
      const { x0, x1 } = markXRange(api, item.value[0], item.value[1], 1)
      return {
        type: 'rect', silent: true, z2: 20,
        shape: { x: x0, y: y - HL_EXPAND_OFFSET * zoomFactor, width: Math.max(2, x1 - x0),
                 height: laneH + HL_EXPAND_H * zoomFactor },
        style: { fill: 'none', stroke: HL_FOCUS_EDGE, lineWidth: HL_GROUP_STROKE_WIDTH },
      }
    }
    // mark:框住那一格(高度跟格的档位走)
    const { x0, x1 } = markXRange(api, item.value[0], item.value[1], 1.5)
    const h = laneH * (item.value[5] || 1)
    const el: Record<string, unknown> = {
      type: 'rect', silent: true, z2: 21,
      shape: { x: x0, y: y + laneH - h - 1.5, width: Math.max(3, x1 - x0), height: h + 3 },
      style: { fill: 'none', stroke: HL_FOCUS_EDGE, lineWidth: lw, ...HL_SHADOW },
    }
    if (hlKind === 'pendingDisambig') el.keyframeAnimation = pendingBlinkAnimation()
    return el
  }
}

/** 族底线 + 透明命中区(悬停整行给族摘要;格在上层,点格不受影响)+ 当家行的粗底线。 */
export function makeRenderFamilyLine(
  items: Array<{ multi?: boolean; active?: boolean; afterWindow?: boolean }>,
  bandGeom: BandGeom[],
  zoomFactor: number = 1.0,
) {
  return function renderFamilyLine(params: any, api: any) {
    const item = items[params.dataIndex]
    const g = bandGeom[api.value(3) || 0]
    if (!item || !g) return { type: 'group', children: [] }
    const { x0, x1 } = markXRange(api, api.value(0), api.value(1))
    const { y, laneH } = laneBox(g, api.value(2) || 0, zoomFactor)
    const width = Math.max(2, x1 - x0)
    const bottom = y + laneH
    const children: any[] = [
      { type: 'rect', shape: { x: x0, y, width, height: laneH }, style: { fill: 'rgba(0,0,0,0.001)' } },
    ]
    if (item.multi) {
      children.push({ type: 'rect', silent: true,
                      shape: { x: x0, y: bottom - FAMILY_LINE_H, width, height: FAMILY_LINE_H },
                      style: { fill: item.afterWindow ? FAMILY_LINE_AFTER_WINDOW : FAMILY_LINE_COLOR } })
    }
    if (item.active) {
      children.push({ type: 'rect', silent: true,
                      shape: { x: x0, y: bottom - 1, width, height: ACTIVE_LINE_H },
                      style: { fill: HL_FOCUS_EDGE } })
    }
    return { type: 'group', children }
  }
}

/** bracket 族底线(每一族都画,bracket 一律是梳子)、当家行粗底线。 */
export function makeRenderBracketLine(
  items: Array<{ multi?: boolean; active?: boolean }>,
  zoomFactor: number = 1.0,
  bracketTop: number = BAND_TOP_PAD,   // hit 第 0 行的顶(compare 下让出上面的 user 行,见 subGeometry 的 appBracketTop)
) {
  return function renderBracketLine(params: any, api: any) {
    const item = items[params.dataIndex]
    if (!item) return { type: 'group', children: [] }
    const { x0, x1 } = markXRange(api, api.value(0), api.value(1))
    const top = bracketTop + (api.value(2) || 0) * BAND_LANE_H * zoomFactor
    const rectH = BAND_MARKER_H * zoomFactor
    const width = Math.max(2, x1 - x0)
    const children: any[] = [
      { type: 'rect', shape: { x: x0, y: top + rectH - FAMILY_LINE_H, width, height: FAMILY_LINE_H },
        style: { fill: FAMILY_LINE_COLOR } },
    ]
    if (item.active) {
      children.push({ type: 'rect', shape: { x: x0, y: top + rectH - 1, width, height: ACTIVE_LINE_H },
                      style: { fill: HL_FOCUS_EDGE } })
    }
    return { type: 'group', silent: true, children }
  }
}

/** 当前日竖线:1px 深色、两侧白边,贯穿所在 grid 的全高。 */
export function renderCursor(params: any, api: any) {
  const x = api.coord([api.value(0), 0])[0]
  const grid = params.coordSys
  const line = (stroke: string, lineWidth: number) => ({
    type: 'line', silent: true,
    shape: { x1: x, y1: grid.y, x2: x, y2: grid.y + grid.height },
    style: { stroke, lineWidth },
  })
  return { type: 'group', silent: true, children: [line(CURSOR_HALO, 3), line(CURSOR_COLOR, 1)] }
}

// ── spec 2026-07-11: shift-veil 副图 renderer(point + interval,fill 白蒙 + 黑横线) ──
// 每条 veil 数据一个 group,children = [半透明白蒙 shape, 黑横线],
// 复用与 renderPointWithGeom / renderIntervalWithGeom 同一 shape 派生逻辑。
// silent:true → hover/click 穿透到本体 marker;z2:22 高于 highlight overlay(21)。
export function makeRenderShiftVeil(
  items: Array<{ value: number[]; instance_id: string; kind: 'point' | 'interval' }>,
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

    // interval 分支:参 renderIntervalWithGeom(横向范围同记号)
    const { x0, x1 } = markXRange(api, api.value(0), api.value(1))
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

// ── spec 2026-07-11: shift-veil 主图 renderer(pricePoint,fill 白蒙 + 黑横线) ──
// 卫星 pk 通道已删(Task 7),veil 只覆盖 pricePoint;pk 事件(state 存在)走三角形白蒙,
// bo 事件走圆角矩形白蒙——与 makeRenderPricePoint 的形状分派一致。
export function makeRenderShiftVeilPrice(
  items: Array<{ value: number[]; instance_id: string; kind: 'pricePoint';
                 anchorY?: number; text?: string; state?: string; pkLift?: number }>,
) {
  return function renderShiftVeilPrice(params: any, api: any) {
    const item = items[params.dataIndex] ?? null
    if (!item) return { type: 'group', children: [] }
    const anchorY = item.anchorY ?? api.value(1)
    const [cx, anchorPx] = api.coord([api.value(0), anchorY])

    // pk 事件:白蒙 ▽ 倒三角(顶点在下,两上角在上)+ 黑横线
    if (item.state) {
      const triCy = anchorPx - TRIANGLE_STACK_PT - (item.pkLift ?? 0)
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

    // bo 事件:参 makeRenderPricePoint,圆角矩形背景,box 中心 = anchorPx - stackOffset
    const text = item.text ?? ''
    const cy = anchorPx - BO_STACK_PT
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
}

// bracket:副图独立坐标(canvas 局部 y=0 起,见 subGeometry.ts 几何约定)。一族 hit(同起点)一行,一律画梳子:
//   kind='mark':hit 的记号——每个 hit 一格立在它的终点(琥珀、满高),只有一次 hit 的族也是(不画整条);
//   kind='buy' :买入日 ▼(黑),叠在上面。
// 选中 hit:它的完整跨度 [族起点, hit 终点] 空心细框 + 它那一格深边框(点的是 bracket 本身用粗边,点组内 marker 用细边);
// 候选 hit:它那一格细实线框(不用虚线:虚线只表示用户画的;不闪)。族底线在 bracket-lines 系列。
export function makeRenderBracket(
  items: Array<{ hit_id: string; hit_ids?: string[]; kind?: 'mark' | 'buy'; family_start?: number }>,
  selectedHitId: string | null,
  candidateHitIds: ReadonlySet<string>,
  zoomFactor: number = 1.0,
  focusOnBracket: boolean = false,
  bracketTop: number = BAND_TOP_PAD,   // hit 第 0 行的顶(同 makeRenderBracketLine)
) {
  return function renderBracket(params: any, api: any) {
    const item = items[params.dataIndex]
    const lane = api.value(2) || 0
    const top = bracketTop + lane * BAND_LANE_H * zoomFactor
    const rectH = BAND_MARKER_H * zoomFactor
    const ids = item?.hit_ids ?? (item?.hit_id ? [item.hit_id] : [])
    if (item?.kind === 'buy') {
      const x = api.coord([api.value(0), 0])[0]
      const w = Math.max(3, Math.min(6, api.size([1, 0])[0] * 0.32))
      return { type: 'polygon',
               shape: { points: [[x - w, top + 0.5], [x + w, top + 0.5], [x, top + rectH * 0.65]] },
               style: { fill: '#111111' } }
    }
    const { x0, x1 } = markXRange(api, api.value(0), api.value(1))
    const children: any[] = [
      { type: 'rect', shape: { x: x0, y: top, width: Math.max(2, x1 - x0), height: rectH }, style: { fill: AMBER_FILL } },
    ]
    const isSelected = !!selectedHitId && ids.includes(selectedHitId)
    const isCandidate = !isSelected && ids.some((id) => candidateHitIds.has(id))
    if (isSelected) {
      const fs = item?.family_start ?? api.value(0)
      if (fs < api.value(0)) {
        const ext = markXRange(api, fs, api.value(1), 1)
        children.push({ type: 'rect',
                        shape: { x: ext.x0, y: top - HL_EXPAND_OFFSET * zoomFactor, width: ext.x1 - ext.x0,
                                 height: rectH + HL_EXPAND_H * zoomFactor },
                        style: { fill: 'none', stroke: HL_FOCUS_EDGE, lineWidth: HL_GROUP_STROKE_WIDTH } })
      }
      const box = markXRange(api, api.value(0), api.value(1), 1.5)
      children.push({ type: 'rect',
                      shape: { x: box.x0, y: top - HL_EXPAND_OFFSET * zoomFactor, width: box.x1 - box.x0,
                               height: rectH + HL_EXPAND_H * zoomFactor },
                      style: { fill: 'none', stroke: HL_FOCUS_EDGE,
                               lineWidth: focusOnBracket ? HL_FOCUS_STROKE_WIDTH : HL_GROUP_STROKE_WIDTH,
                               ...HL_SHADOW } })
    } else if (isCandidate) {
      const box = markXRange(api, api.value(0), api.value(1), 1.5)
      children.push({ type: 'rect',
                      shape: { x: box.x0, y: top - 1, width: box.x1 - box.x0, height: rectH + 2 },
                      style: { fill: 'none', stroke: HL_FOCUS_EDGE, lineWidth: HL_GROUP_STROKE_WIDTH } })
    }
    return { type: 'group', children }
  }
}

// ─── dev UI 视觉常量(对齐 BreakoutStrategy/UI/styles.py CHART_COLORS / MARKER_STACK_GAPS_PT
//     / BO_LABEL_TIER_STYLE;rubric=docs/tmp/2026-06-21-bo-pk-marker-rubric.md)──────────────
// 整组数值相对 dev pt 值按 ~0.6 比例缩放,补偿 web grid 容器较窄、相对蜡烛宽度偏大的视觉。
// 20pt @ 96dpi = 26.67 px;0.6× ≈ 16 px。
const MARKER_FONT_SIZE = 16            // dev fontsize=20pt;web px=16 ≈ 0.6× 视觉对齐
const PK_TRIANGLE_HALF_WIDTH = 8       // ▽ 半宽,对应 dev s=400 (≈20pt 边长) 0.6× 缩放
const PK_TRIANGLE_HEIGHT = 12
// pk ▽ 三态编码(spec 2026-08-31 §3.5.4;色盲纪律:一切区分不靠色相):
//   alive  = 实心 ▽(阻力仍压在头顶,信息价值最高)
//   broken = 空心 ▽(黑边无填充,即旧卫星 marker 外观)
//   eaten  = 浅灰虚线 ▽(靠明度 + 线型弱化)
// 标签只显示 id 数字。
const PEAK_MARKER_COLOR = '#000000'       // dev UI CHART_COLORS["peak_marker"]
const PEAK_MARKER_COLOR_DIM = '#9ca3af'   // eaten 态浅灰
export type PkTriStyle = { fill: string; stroke: string; lineWidth: number; lineDash?: number[] }
export function pkTriStyle(state: string): PkTriStyle {
  switch (state) {
    case 'alive': return { fill: PEAK_MARKER_COLOR, stroke: PEAK_MARKER_COLOR, lineWidth: 1.2 }
    case 'eaten': return { fill: 'none', stroke: PEAK_MARKER_COLOR_DIM, lineWidth: 1.0, lineDash: [2.5, 2] }
    default:      return { fill: 'none', stroke: PEAK_MARKER_COLOR, lineWidth: 1.2 }   // broken(未知态同此兜底)
  }
}
const BO_BOX_RADIUS = 4
const BO_BOX_PAD_X = 5
const BO_BOX_PAD_Y = 3
// 堆叠 px 偏移(锚 K 线 high 之上,自下而上):▽ → ID → [ids]
// dev UI styles.py:80-86 用 pt(triangle=20/peak_id=35/bo_label=15 无 PK)
// web 端按字号 16 等比缩:三角中心 13、ID 中心 28、BO 中心 15(卫星 pk 通道已删,
// bo 盒不再需要为 PK 三角让位,统一贴 bar.h 上方)
const TRIANGLE_STACK_PT = 13           // ▽ 中心 y = anchor - 13
const PEAK_ID_STACK_PT = 28            // ID 中心 y = anchor - 28
const BO_STACK_PT = 15                 // [ids] 中心 y = anchor - 15(dev styles.py:80 bo_label=15pt 缩放对应)
// 同锚避让:一根 K 线既是 pk 又是 bo 时(▽ 中心 anchor-13、bo 盒中心 anchor-15,必然叠住),
// pk 整组(▽ + id 标签)再上移这么多 px,整体抬到 bo 盒顶之上。
// 取值按最坏情况定:两者同时高亮(▽ 放大 1.4× → 底顶点 8.4px、bo 盒四周多 3px → 盒顶 29px)。
const PK_LIFT_OVER_BO = 28

// 文本框尺寸(浏览器无 measureText 时按字宽近似,bold 字体 char_w ≈ 0.62×fontSize)
function boBoxDims(text: string): { w: number; h: number } {
  const charW = MARKER_FONT_SIZE * 0.62
  const textW = Math.max(charW, text.length * charW)
  return {
    w: textW + 2 * BO_BOX_PAD_X,
    h: MARKER_FONT_SIZE + 2 * BO_BOX_PAD_Y,
  }
}

// price-anchored 主 marker(bo 盒 / pk 三角,按 item.state 存在性分派)。
// 锚 bar.h(anchorY 由 computeEventData 注入)。
// - bo:圆角矩形盒 + [broken_peak_ids] 文本(dev UI 复刻),box 中心 = anchorPx - BO_STACK_PT
// - pk:▽ 按三态编码形状(pkTriStyle:alive 实心 / broken 空心 / eaten 浅灰虚线)+ 标签
//        (只有 id 数字)在 ▽ 上方(spec 2026-08-31 §3.5.4)。
//        itemStyle.color 对 pk 不消费——三态全走形状,不靠色相(色盲纪律)。
// ⚠ closure factory:ECharts customSeries 不在 params 中传 data item,必须按 dataIndex 反查。
//   过去用 (params.data as any).text 实测=undefined → text 为空字符串 → ZRText 被创建但无文字渲染。
function makeRenderPricePoint(
  data: Array<{ value: number[]; instance_id: string; anchorY: number; text: string;
                 tier: Tier; itemStyle: { color: string };
                 state?: string; pkId?: number; pkLift?: number }>,
) {
  return function renderPricePoint(params: any, api: any) {
    const item = data[params.dataIndex] ?? null
    const anchorY = item?.anchorY ?? api.value(1)
    const text = item?.text ?? ''
    const color = item?.itemStyle?.color ?? '#888888'
    const [cx, anchorPx] = api.coord([api.value(0), anchorY])

    // ── pk 事件:三态形状 ▽ + id 标签(▽ 上方) ──
    if (item?.state) {
      const lift = item.pkLift ?? 0        // 同锚 bo 时整组上移,避让盒体
      const triCy = anchorPx - TRIANGLE_STACK_PT - lift
      const tw = PK_TRIANGLE_HALF_WIDTH
      const th = PK_TRIANGLE_HEIGHT
      const idCy = anchorPx - PEAK_ID_STACK_PT - lift
      const tri = pkTriStyle(item.state)
      const children: any[] = [
        {
          type: 'polygon',
          shape: {
            points: [
              [cx - tw, triCy - th / 2],   // 左上
              [cx + tw, triCy - th / 2],   // 右上
              [cx,      triCy + th / 2],   // 下顶点
            ],
          },
          style: tri,
        },
        // 标签:只显示 id 数字,颜色随三态描边(eaten 同步淡化)
        {
          type: 'text',
          style: {
            text, x: cx, y: idCy,
            fill: tri.stroke,
            fontSize: MARKER_FONT_SIZE,
            fontWeight: 'bold',
            align: 'center',
            verticalAlign: 'middle',
          },
        },
      ]
      return { type: 'group', children }
    }

    // ── bo 事件:圆角矩形盒 + [broken_peak_ids] 文本 ──
    const cy = anchorPx - BO_STACK_PT
    const { w, h } = boBoxDims(text)
    return {
      type: 'group',
      children: [
        // 1. 圆角矩形背景(按 tier 分色:in_hit=橙、qualified/detected=灰;无边框)
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

/** K 线涨跌色(阳 / 阴),成交量柱同色。这对红绿是用户指定保留的,优先于「冷暖或深浅区分」的配色通则。 */
export const CANDLE_UP = '#47b262'
export const CANDLE_DOWN = '#eb5454'
/** K 线区上下各留出价格区间的这一比例作空白。 */
const PRICE_PAD_RATIO = 0.05

/**
 * 成交量柱(画在 K 线区下方的成交量带 grid1)+ 可见区间的两条 y 轴范围。
 *
 * - 价格轴(yAxis[0]):可见区间 low 的最小值 ~ high 的最大值,上下各留 PRICE_PAD_RATIO 的空白,下限钳到 ≥ 0;
 * - 成交量轴(yAxis[1]):0 ~ 可见区间的最大成交量(全 0 时兜底 1);
 * - 柱色同 K 线:收盘 ≥ 开盘用 CANDLE_UP,否则 CANDLE_DOWN。
 * zoom/pan 时 KlineChart 按新的可见区间重算这两条轴。
 *
 * @param bars      完整 bars 数组
 * @param visStart  可见区间起始 bar 索引（含）
 * @param visEnd    可见区间结束 bar 索引（含）
 */
export function buildVolumeSeriesAndYAxis(bars: Bar[], visStart: number, visEnd: number) {
  const visBars = bars.slice(visStart, visEnd + 1)
  const priceMin = Math.min(...visBars.map(b => b.l))
  const priceMax = Math.max(...visBars.map(b => b.h))
  const range = priceMax - priceMin
  const pad = (range > 0 ? range : (Math.abs(priceMax) || 1)) * PRICE_PAD_RATIO
  const volAxisMax = Math.max(...visBars.map(b => b.v), 1)

  const volSeries = {
    type: 'bar' as const,
    name: 'volume' as const,
    xAxisIndex: 1 as const,
    yAxisIndex: 1 as const,
    barWidth: '70%' as const,
    // 纯展示 series,不接受 hit-event:hover 落到下面的 volume-hit-spanner,出 K 线 tooltip。
    silent: true as const,
    data: bars.map(b => ({
      value: b.v,
      itemStyle: { color: b.c >= b.o ? CANDLE_UP : CANDLE_DOWN },
    })),
  }
  return {
    volSeries,
    yAxisOverride: { min: Math.max(0, priceMin - pad), max: priceMax + pad },
    volAxisMax,
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
    // 允许 candlestick 'kline' 与两条 spanner(K 线区、成交量带)共享同一 OHLC formatter
    const isKlineSrc = (n?: string) => n === 'kline' || n === 'kline-hit-spanner' || n === 'volume-hit-spanner'
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

/** 悬停里的程序固定文字:等宽。MONO 里有双引号,属性值用单引号括。 */
const fixedLine = (s: string) => `<span style='font-family:${MONO}'>${s}</span>`

/**
 * Marker tooltip formatter (series-level item-trigger)。
 * 三段结构 + 可选 hit 顶行：
 *   - 顶行 (仅 params.data.hit_id 命中)：hit: {hitLabel(id)}
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
  tooltipResolver: ((instanceId: string) => TooltipPayload) | undefined,
  hitLabel: ((hitId: string) => string | null) | undefined,
  ctx: { hits: HitDict[]; candidateHitIds: ReadonlySet<string> } = { hits: [], candidateHitIds: new Set() },
) {
  return (params: { data?: { instance_id?: string; hit_id?: string; [key: string]: unknown } } | null): string => {
    const data = params?.data
    if (!data) return ''
    const lines: string[] = []

    // ── bracket 段：候选首行 + 买入日 + 同一记号上的几次 hit + hitLabel + 组成段 ────────
    const hitId = data.hit_id as string | undefined
    if (hitId) {
      const hitIds = (data.hit_ids as string[] | undefined) ?? [hitId]
      if (hitIds.some((id) => ctx.candidateHitIds.has(id))) lines.push(fixedLine('candidate'))
      if (data.kind === 'buy') lines.push(fixedLine(`buy: ${data.buy_date as string}`))
      const hitLabelTexts = data.hit_labels as string[] | undefined
      if (hitIds.length >= 2) {
        lines.push(fixedLine(`hits: ${hitIds.length}`))
        if (hitLabelTexts) for (const t of hitLabelTexts) lines.push(fixedLine(`  ${t}`))
      }
      // 既有 hitLabel
      if (hitLabel) {
        const label = hitLabel(hitId)
        if (label) lines.push(fixedLine(`hit: ${label}`))
      }
      // 组成段 (M #15)
      const hit = ctx.hits.find((m) => m.hit_id === hitId)
      if (hit) {
        lines.push(`组成 (${hit.children.length} events):`)
        for (const [nodeKey, instanceId] of Object.entries(hit.node_index)) {
          lines.push(`  ${nodeKey}: ${instanceId}`)
        }
      }
    }

    // ── 多确认段:该买点(实例)被几个 hit 共享 ────────────────────────────
    // 实例化契约:marker 的 data.instance_id 即买点锚 leaf(instance_id);共享计数按
    // hit.leaf(实例级,serialize 注入)匹配,同 leaf 被 >=2 hit 共享时输出确认行。
    const instanceId = data.instance_id as string | undefined
    if (instanceId && ctx.hits.length > 0) {
      const sharedBy = ctx.hits.filter(
        (m) => m.leaf === instanceId || m.children.includes(instanceId),
      ).length
      if (sharedBy >= 2) {
        lines.push(fixedLine(`shared_by_hits: ${sharedBy}`))
      }
    }

    // ── 族成员段:这个记号在族里第几个;同一格几个成员时逐个列出区分标签 ─────────────
    const memberIds = data.member_ids as string[] | undefined
    if (!hitId && memberIds) {
      const ks = (data.member_k as number[] | undefined) ?? []
      const n = data.family_n as number | undefined
      if (memberIds.length >= 2) {
        lines.push(fixedLine(`members: ${memberIds.length}`))
        const labels = (data.member_labels as string[] | undefined) ?? memberIds
        labels.forEach((t, i) => lines.push(fixedLine(`  ${ks[i] ?? '?'}/${n ?? '?'} ${t}`)))
      } else if (n != null && n >= 2) {
        lines.push(fixedLine(`member: ${ks[0] ?? '?'}/${n}`))
      }
    }

    // ── event 三段 ──────────────────────────────────────────────────────
    if (instanceId && tooltipResolver) {
      const { identity, clauses, raw, refs } = tooltipResolver(instanceId)

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

      // 段 4 Refs（ref_slots 协议的通用投影：本事件引用了谁 / 谁引用了本事件）
      //
      // 类型无关：槽名原样印出(superseded / broken / ...)，渲染层不解释其含义，
      // 只按 dir 分「引用 / 被引」两组。任何走 ref_slots 协议的事件白拿本段。
      // 对方标识优先用「node + 图上短标识」(如 `pk 3`，短标识由 refLabel 注入)；
      // 对方不在本次 events 里(被窗口截断等)时回落原始 instance_id，信息不丢。
      const refRows = refs ?? []
      if (refRows.length > 0) {
        lines.push('<hr/><b>Refs</b>')
        for (const dir of ['out', 'in'] as const) {
          const dirWord = dir === 'out' ? '引用' : '被引'
          for (const r of refRows.filter((x) => x.dir === dir)) {
            const who = r.nodeId == null ? r.instanceId
                                         : r.nodeId + (r.label == null ? '' : ` ${r.label}`)
            lines.push(`${dirWord} ${r.slot}: ${who}` + (r.date == null ? '' : ` · ${r.date}`))
          }
        }
      }
    }

    // ── marker 归属节 (M #16, 仅非 bracket marker: 无 hit_id) ──────────
    // bracket 折叠后一行有几十次 hit,逐个圈号已无意义,只报个数
    if (!hitId && instanceId && ctx.hits.length > 0) {
      const owned = ctx.hits.filter((m) => m.children.includes(instanceId)).length
      if (owned > 0) lines.push(fixedLine(`in_hits: ${owned}`))
    }

    return lines.join('<br/>')
  }
}

/** 浮点统一 4 位小数；整数 / 非数字原样 String 化。 */
function fmtNum(v: unknown): string {
  if (typeof v === 'number' && !Number.isInteger(v)) return v.toFixed(4)
  return String(v)
}
