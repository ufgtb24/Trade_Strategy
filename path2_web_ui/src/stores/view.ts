// 视图状态:scanFile / symbol / activePatternId / node 显隐 / 选中对象;
// 派生 unionRows/sortedRows/pattern/currentAnalysis/effective 三件套。
import { defineStore } from 'pinia'

// ─────────────────────────────────────────────────────────────────
// v2 event-debug-multi-anchor(2026-07-15) · anchorsOf 表 + findBoBar helper
//
// 契约(见 docs/research/2026-07-15_event-debug-dual-emit-multi-anchor/final_report.md):
// - 项数守恒(#3): UI 菜单项数 ≤ 后端埋点数(允许后端多处合并到 UI 单项)
// - 参数对齐(#4): anchor.bar 必须与后端 debug_break 参数值一致
// - dead-code 保护(#5): _DEBUG_MODE=False 时后端零成本
// - 前后端同 PR(#6): 后端 debug_break 与前端 anchorsOf 映射同 PR
// ─────────────────────────────────────────────────────────────────

export type DebugAnchor = {
  key: 'entry' | 'trough' | 'end'
  bar: number
  label: string
  hint: string
  disabled?: boolean
  disabledReason?: string
}

export function findBoBar(anchor_bo_id: string, events: readonly any[]): number | null {
  if (!anchor_bo_id) return null
  const bo = events.find(x => x.event_id === anchor_bo_id)
  return bo?.end_idx ?? null
}

export const anchorsOf: Record<string, (e: any, events: readonly any[]) => DebugAnchor[]> = {
  tb: (e, events) => {
    const boBar = findBoBar(e.anchor_bo_id ?? '', events)
    return [
      {
        key: 'entry',
        bar: boBar ?? e.start_idx,   // fallback 避免 null 传导; disabled 阻塞点击
        label: 'entry',
        hint: '停在 evaluate_throwback 入口 · 看 anchor / atr 起点(F10 可下潜到子函数)',
        disabled: boBar == null,
        disabledReason: boBar == null
          ? `未找到 anchor bo event (id=${e.anchor_bo_id ?? ''}), 契约可能漂移; 可从 trough/end 断点`
          : undefined,
      },
      {
        key: 'trough',
        bar: e.start_idx,
        label: 'trough',
        hint: '停在 _find_start_idx return 前 · 已算好 trough_idx, 可看 depth / base_min',
      },
      {
        key: 'end',
        bar: e.end_idx,
        label: 'end',
        hint: '停在 _find_end_idx return 前 · 大涨 / timeout 两分支(pydevd 源码行区分)',
      },
    ]
  },
  _default: () => [],  // D7 · 不给未埋点 class 生成菜单项(防"菜单显示但 breakpoint 不 hit"的无声失败)
}

// D8 · DEBUG_ENABLED_CLASSES 与 anchorsOf 硬耦合(单一 source of truth):
// 后端埋新 detector 时,前端只改 anchorsOf,whitelist 自动同步。
export const DEBUG_ENABLED_CLASSES = Object.keys(anchorsOf).filter(k => k !== '_default')

import { computed, ref, shallowRef, watch } from 'vue'
import type {
  MultiScanResultFile, StockResult, PerPatternResult,
  MatchDict, EventDict, Tier, Diagnostics, Level, SerializedPattern, Analysis, ScanMeta,
  TimeScopeResponse, PairScopeResponse,
} from '../types'
import { deriveNodeColors } from '../render/colors'
import {
  deriveTagMap, isolatedNodeIds,
  qualifiedIdsOf, matchedIds as matchedIdsOf,
  bandKeyOf, eventTierOf, windowOf, nodeOfEventByBand,
} from '../render/visible'
import { getDiagnose, getPreview, getTimeDiagnose, getPairDiagnose, type PreviewResp } from '../api'
import { useConfigStore } from './config'

// shift+click 累积器条目(入口 D · KlineChart.ts::handleShiftClick 消费/写入)。
export type ShiftSelectedEvent = { event_id: string; class_id: string; source: 'main' | 'sub' }

export type Selected =
  | { kind: 'match'; matchId: string }
  | { kind: 'node'; nodeId: string }
  | null

export type UnionCell = { pid: string; num: number | null; fr: number | null; matched: boolean }
export type UnionRow  = { symbol: string; cells: UnionCell[] }

// sortByPid 哨兵值:按 symbol 字典序排序(非 pid)。
// '__symbol__' 双下划线前缀不会与用户 pattern_id 撞(pid 由 dag_spec 注册的人类可读字符串)。
export const SYMBOL_SORT_KEY = '__symbol__'

// 列可见性(field 轴)localStorage 持久化:key 与 value 格式见 view store 说明。
const LS_KEY_VISIBLE_FIELDS = 'path2_web_ui.visibleFields'
function loadFieldsFromLS(): Set<'num' | 'fr'> {
  try {
    const raw = localStorage.getItem(LS_KEY_VISIBLE_FIELDS)
    if (raw == null) return new Set(['num', 'fr'])
    const arr = JSON.parse(raw) as unknown
    if (!Array.isArray(arr)) return new Set(['num', 'fr'])
    return new Set(arr.filter(x => x === 'num' || x === 'fr') as ('num'|'fr')[])
  } catch { return new Set(['num', 'fr']) }
}
function saveFieldsToLS(s: Set<'num' | 'fr'>): void {
  try { localStorage.setItem(LS_KEY_VISIBLE_FIELDS, JSON.stringify([...s])) }
  catch { /* silent */ }
}

const LS_KEY_LEVEL = 'path2_web_ui.level'
const LEVEL_VALUES: readonly Level[] = ['matched', 'qualified', 'detected']
function loadLevelFromLS(): Level {
  try {
    const raw = localStorage.getItem(LS_KEY_LEVEL)
    if (raw == null) return 'matched'
    return (LEVEL_VALUES as readonly string[]).includes(raw) ? (raw as Level) : 'matched'
  } catch { return 'matched' }
}
function saveLevelToLS(l: Level): void {
  try { localStorage.setItem(LS_KEY_LEVEL, l) } catch { /* silent */ }
}

export const useViewStore = defineStore('view', () => {
  // ── state ────────────────────────────────────────────────────────
  // shallowRef:scanFile 全程整体替换(loadScanFile/clearScanFile),无内部 mutate,
  // 避免对 4000+ stocks×{events,matches,clauses} 树建深 Proxy 拖慢首屏与排序
  const scanFile = shallowRef<MultiScanResultFile | null>(null)
  const symbol = ref<string | null>(null)
  const activePatternId = ref<string | null>(null)
  const sortByPid = ref<string | null>(null)
  const sortDesc = ref(true)
  const visiblePatterns = ref<Set<string>>(new Set())
  const visibleFields = ref<Set<'num' | 'fr'>>(loadFieldsFromLS())
  const symbolQuery = ref<string>('')

  const nodeVisible = ref<Record<string, boolean>>({})
  // 焦点意图两条正交轴(spec §3.1):
  //   focusedMatchId 非空 & focusedEventId 空 → bracket-focus,展 trace
  //   focusedEventId 非空 → event-focus,不展 trace(可能同时有 focusedMatchId=唯一归属 m)
  //   两者都空 & candidateMatchIds 非空 → 多归属 pending 态
  const focusedMatchId = ref<string | null>(null)
  const focusedEventId = ref<string | null>(null)
  // sidebar 漏斗手动 toggle 兜底:仅在 focusedEventId/pendingDisambigEventId 都空时生效
  // sidebar 漏斗手动展开集合(多 node 可同时展开)。语义分层:
  //   手动入口(sidebar 漏斗行 / TopologyControl dblclick)= toggleExpandedNode (add/remove,不折叠其他)
  //   自动入口(focusEvent · marker/candidate/trace node click)= add 焦点 node(不折叠其他)
  //   focusMatch(bracket / 命中匹配 click)= 清空(trace 独占)
  //   4 处初始化(切数据源)= 清空
  const manualExpandedNodes = ref<Set<string>>(new Set())
  const level = ref<Level>(loadLevelFromLS())
  const candidateMatchIds = ref<ReadonlySet<string>>(new Set())
  const pendingDisambigEventId = ref<string | null>(null)
  const hoveredEventId = ref<string | null>(null)
  const diag = ref<Diagnostics | null>(null)

  // ── 入口 A/D(Task 18):KlineChart brush(scope=time)+ shift+click 跨图(scope=pair) ──
  // shiftSelectedEvents 是唯一跨组件状态载体(同 selectedEventId/candidateMatchIds 既有模式;
  // KlineChart 本身零 props/零 emit,靠 store 与 DetailSidebar 通信),故放这里而非组件内 ref。
  const shiftSelectedEvents = ref<ShiftSelectedEvent[]>([])
  const activeDetailCard = ref<'time' | 'pair' | 'debug' | null>(null)

  // v2 event-debug(2026-07-15) · marker 右键触发的精准断点 pending 状态。
  // 单槽位覆盖模型(与 activeDetailCard 单值互斥模式一致): 新 debug 请求 abort 旧 controller。
  const debugPending = ref(false)
  const debugTarget = ref<{ eventId: string; bar: number; className: string; anchor: string } | null>(null)
  // fetch 失败(network/500)态 · 与 debugPending=false 组合区分"断点已释放"(成功)vs"请求失败"
  const debugError = ref<string | null>(null)
  let debugAbortRef: AbortController | null = null
  const timeScopeResponse = ref<TimeScopeResponse | null>(null)
  // 入口 A · FailedAttemptsCard 下拉过滤态 · '' = 全部;提升到 store 让 KlineChart brush handler 可透传给 triggerTimeQuery
  const currentTimeEventClass = ref<string>('')
  const pairScopeResponse = ref<PairScopeResponse | null>(null)

  const previewEnabled = ref(false)
  const preview = shallowRef<{
    symbol: string
    analysis: PreviewResp['analysis']
    pattern_spec: PreviewResp['pattern_spec']
    scan: PreviewResp['scan']
  } | null>(null)
  const previewLoading = ref(false)
  const previewError = ref<string | null>(null)

  // ── computed ─────────────────────────────────────────────────────
  const patternIds = computed<string[]>(() => scanFile.value?.pattern_ids ?? [])

  const currentPerStock = computed<StockResult | null>(() =>
    scanFile.value?.results.find(r => r.symbol === symbol.value) ?? null)

  const pattern = computed<SerializedPattern | null>(() => {
    if (!activePatternId.value || !scanFile.value) return null
    return scanFile.value.per_pattern[activePatternId.value]?.pattern_spec ?? null
  })

  const currentAnalysis = computed<Analysis | null>(() => {
    if (!activePatternId.value) return null
    return currentPerStock.value?.per_pattern[activePatternId.value]?.analysis ?? null
  })

  // preview-aware effective 三件套
  const _previewHits = computed(() =>
    previewEnabled.value && preview.value
    && preview.value.symbol === symbol.value
    && preview.value.pattern_spec.pattern_id === activePatternId.value)

  const effectivePattern = computed<SerializedPattern | null>(() =>
    _previewHits.value ? preview.value!.pattern_spec : pattern.value)

  const effectiveAnalysis = computed<Analysis | null>(() =>
    _previewHits.value ? preview.value!.analysis : currentAnalysis.value)

  const effectiveScan = computed<ScanMeta | PreviewResp['scan'] | null>(() => {
    if (_previewHits.value) return preview.value!.scan
    return scanFile.value?.scan ?? null
  })

  // 列表 union / sort
  const unionRows = computed<UnionRow[]>(() => {
    const f = scanFile.value
    if (!f) return []
    return f.results.map(r => ({
      symbol: r.symbol,
      cells: f.pattern_ids.map(pid => {
        const pp: PerPatternResult | undefined = r.per_pattern[pid]
        return {
          pid,
          num: pp ? (pp.summary?.matches ?? 0) : null,
          fr:  pp?.max_forward_return ?? null,
          matched: (pp?.summary?.matches ?? 0) > 0,
        } as UnionCell
      }),
    }))
  })

  const sortedRows = computed<UnionRow[]>(() => {
    const rows = unionRows.value
    const pid = effectiveSortKey.value
    if (!pid) return rows
    const dir = sortDesc.value ? -1 : 1
    if (pid === SYMBOL_SORT_KEY) {
      return rows.slice().sort((a, b) => a.symbol.localeCompare(b.symbol) * dir)
    }
    const m = pid.match(/^(.+)_(num|fr)$/)
    if (!m) return rows
    const targetPid = m[1]
    const targetField = m[2] as 'num' | 'fr'
    // 一次 O(N·P) 预聚 key,后续比较器零 lookup(干掉 O(N log N · P) 的 .find())
    const N = rows.length
    const keys = new Float64Array(N)
    const isNull = new Uint8Array(N)
    for (let i = 0; i < N; i++) {
      const cells = rows[i].cells
      let v: number | null = null
      for (let j = 0; j < cells.length; j++) {
        if (cells[j].pid === targetPid) { v = cells[j][targetField]; break }
      }
      if (v == null) isNull[i] = 1
      else keys[i] = v
    }
    const idx = new Array<number>(N)
    for (let i = 0; i < N; i++) idx[i] = i
    idx.sort((a, b) => {
      // null 永远沉底(无论升降)
      if (isNull[a] && isNull[b]) return 0
      if (isNull[a]) return 1
      if (isNull[b]) return -1
      return (keys[a] - keys[b]) * dir
    })
    const out = new Array<UnionRow>(N)
    for (let i = 0; i < N; i++) out[i] = rows[idx[i]]
    return out
  })

  const filteredSortedRows = computed<UnionRow[]>(() => {
    const q = symbolQuery.value.trim().toLowerCase()
    return sortedRows.value.filter(row => {
      if (!row.cells.some(c => visiblePatterns.value.has(c.pid) && c.matched)) return false
      if (q === '') return true
      return row.symbol.toLowerCase().startsWith(q)
    })
  })

  // K 线 / 拓扑 等下游派生(同旧)
  const nodeColors = computed(() =>
    effectivePattern.value ? deriveNodeColors(effectivePattern.value.topology, effectivePattern.value.event_styles) : {})

  // ── actions ──────────────────────────────────────────────────────
  function loadScanFile(f: MultiScanResultFile) {
    scanFile.value = f
    nodeVisible.value = {}
    clearFocus()
    manualExpandedNodes.value = new Set()   // 切数据源清空展开集
    hoveredEventId.value = null
    sortByPid.value = null
    sortDesc.value = true
    symbol.value = f.results[0]?.symbol ?? null
    previewEnabled.value = false
    preview.value = null
    previewError.value = null
    // active 默认值:优先 config.last_selected_pattern 若在 pattern_ids 中
    const cfg = useConfigStore()
    const last = cfg.config?.last_selected_pattern
    activePatternId.value = (last && f.pattern_ids.includes(last))
      ? last : (f.pattern_ids[0] ?? null)
    candidateMatchIds.value = new Set()
    pendingDisambigEventId.value = null
    clearDetailCard()
    symbolQuery.value = ''
    initVisiblePatterns(f.pattern_ids)
  }
  function clearScanFile() {
    scanFile.value = null
    symbol.value = null
    activePatternId.value = null
    sortByPid.value = null
    nodeVisible.value = {}
    clearFocus()
    manualExpandedNodes.value = new Set()   // 切数据源清空展开集
    hoveredEventId.value = null
    previewEnabled.value = false
    preview.value = null
    previewError.value = null
    candidateMatchIds.value = new Set()
    pendingDisambigEventId.value = null
    visiblePatterns.value = new Set()
    symbolQuery.value = ''
    clearDetailCard()
  }
  function selectSymbol(s: string) {
    // 锚-active 解耦:只切股、不动 activePatternId
    symbol.value = s
    clearFocus()
    manualExpandedNodes.value = new Set()   // 切数据源清空展开集
    hoveredEventId.value = null
    preview.value = null
    previewError.value = null
    candidateMatchIds.value = new Set()
    pendingDisambigEventId.value = null
    clearDetailCard()
    if (previewEnabled.value) void runPreview()
  }
  function setActivePattern(pid: string) {
    activePatternId.value = pid
    useConfigStore().saveLastPattern(pid)
    clearFocus()
    manualExpandedNodes.value = new Set()   // 切数据源清空展开集
    candidateMatchIds.value = new Set()
    pendingDisambigEventId.value = null
    clearDetailCard()
    if (previewEnabled.value) void runPreview()
    symbolQuery.value = ''
  }
  function setSort(pid: string) {
    if (sortByPid.value === pid) {
      sortDesc.value = !sortDesc.value
    } else {
      sortByPid.value = pid
      sortDesc.value = true
    }
  }
  function setSymbolQuery(q: string) { symbolQuery.value = q }
  function clearSymbolQuery() { symbolQuery.value = '' }
  function initVisiblePatterns(pids: string[]) {
    visiblePatterns.value = new Set(pids)
  }
  function togglePattern(pid: string) {
    const s = new Set(visiblePatterns.value)
    if (s.has(pid)) s.delete(pid); else s.add(pid)
    visiblePatterns.value = s
  }
  function setPatternsAllOn()  { visiblePatterns.value = new Set(patternIds.value) }
  function setPatternsAllOff() { visiblePatterns.value = new Set() }
  function invertPatterns() {
    const s = new Set<string>()
    for (const p of patternIds.value) if (!visiblePatterns.value.has(p)) s.add(p)
    visiblePatterns.value = s
  }
  function toggleField(f: 'num' | 'fr') {
    const s = new Set(visibleFields.value)
    if (s.has(f)) s.delete(f); else s.add(f)
    visibleFields.value = s
    saveFieldsToLS(visibleFields.value)
  }
  function isColumnVisible(pid: string, field: 'num' | 'fr'): boolean {
    return visiblePatterns.value.has(pid) && visibleFields.value.has(field)
  }
  const effectiveSortKey = computed<string | null>(() => {
    const k = sortByPid.value
    if (k == null || k === SYMBOL_SORT_KEY) return k
    const m = k.match(/^(.+)_(num|fr)$/)
    if (!m) return SYMBOL_SORT_KEY
    return isColumnVisible(m[1], m[2] as 'num' | 'fr') ? k : SYMBOL_SORT_KEY
  })
  function toggleNode(nodeId: string) {
    nodeVisible.value = { ...nodeVisible.value, [nodeId]: nodeVisible.value[nodeId] === false }
  }
  // 手动入口:sidebar 漏斗行 click / TopologyControl dblclick 都调这个。
  // toggle 语义:点已展开 → set delete;点未展开 → set add;不折叠其他(用户诉求"多 node 同时展开")。
  function toggleExpandedNode(nodeId: string): void {
    const s = new Set(manualExpandedNodes.value)
    if (s.has(nodeId)) s.delete(nodeId)
    else s.add(nodeId)
    manualExpandedNodes.value = s
  }

  // ── Task 2 高层 action(spec §3.3)· 消费点将在 Task 3/4 迁移到这三个 ─────────────
  function focusMatch(matchId: string): void {
    focusedMatchId.value = matchId
    focusedEventId.value = null
    manualExpandedNodes.value = new Set()  // collapse all · trace 独占视野
    clearCandidates()
  }

  function focusEvent(eventId: string): void {
    const matches = effectiveAnalysis.value?.matches ?? []
    const events  = effectiveAnalysis.value?.events  ?? []
    const edges   = effectivePattern.value?.topology.edges ?? []
    const ms = matches.filter(m => matchedIdsOf([m], events, edges).has(eventId))

    // 焦点意图:add 焦点所在 node 到展开集(不折叠其他 node);node 无解则不动集合。
    const ev = events.find(e => e.event_id === eventId)
    if (ev) {
      const node = nodeOfEventByBand(ev, tagMap.value.tagToNodes, tagMap.value.tagList)
      if (node && !manualExpandedNodes.value.has(node)) {
        const s = new Set(manualExpandedNodes.value)
        s.add(node)
        manualExpandedNodes.value = s
      }
    }

    if (ms.length === 0) {
      focusedMatchId.value = null
      focusedEventId.value = eventId
      clearCandidates()
    } else if (ms.length === 1) {
      focusedMatchId.value = ms[0].event_id
      focusedEventId.value = eventId
      clearCandidates()
    } else {
      // 多归属:信息层(markedMatchIds=candidates)+ 视觉层(不亮 group,等 disambig)
      focusedMatchId.value = null
      focusedEventId.value = null
      setCandidateMatches(ms.map(m => m.event_id))
      setPendingDisambig(eventId)
    }
    autoFollowLevel(eventId)
  }

  function clearFocus(): void {
    focusedMatchId.value = null
    focusedEventId.value = null
    clearCandidates()
    clearShiftSelection()
  }

  // spec §3.5:单向放松门控;只降不升;仅 focusEvent 调用
  function autoFollowLevel(eventId: string): void {
    const ev = effectiveAnalysis.value?.events.find(e => e.event_id === eventId)
    if (!ev) return
    const evTier = eventTier(ev)
    const RANK: Record<Level, number> = { matched: 2, qualified: 1, detected: 0 }
    if (RANK[evTier] < RANK[level.value]) setLevel(evTier)
  }

  function setLevel(l: Level) { level.value = l; saveLevelToLS(l) }
  function hoverEvent(id: string | null) { hoveredEventId.value = id }
  function setCandidateMatches(ids: string[]) {
    candidateMatchIds.value = new Set(ids)
    if (ids.length === 0) pendingDisambigEventId.value = null
  }
  function clearCandidates() {
    candidateMatchIds.value = new Set()
    pendingDisambigEventId.value = null
  }
  function setPendingDisambig(eid: string | null) {
    pendingDisambigEventId.value = eid
  }

  // ── 入口 A(brush)+ 入口 D(shift+click)query actions(Task 18) ──────────────
  function setShiftSelectedEvents(next: ShiftSelectedEvent[]) {
    shiftSelectedEvents.value = next
  }
  function clearShiftSelection(): void {
    shiftSelectedEvents.value = []
  }
  const shiftPairPending = computed<boolean>(() => shiftSelectedEvents.value.length === 1)
  const shiftSelectedEventIds = computed<ReadonlySet<string>>(
    () => new Set(shiftSelectedEvents.value.map(e => e.event_id))
  )
  /** 清掉当前展示的 time/pair/candidate 查询卡片(DetailSidebar 关闭按钮 · undo-swap · 切股/切
   * pattern 防陈旧残留)。loadScanFile/clearScanFile/selectSymbol/setActivePattern 4 处 reset
   * 均经此单一入口(承 Task 18 前例)。*/
  function clearDetailCard() {
    activeDetailCard.value = null
    timeScopeResponse.value = null
    pairScopeResponse.value = null
    shiftSelectedEvents.value = []
    currentTimeEventClass.value = ''
    // v2 D9 · 同步清 debug state · abort 挂起的 debug fetch
    if (debugAbortRef) {
      debugAbortRef.abort()
      debugAbortRef = null
    }
    debugTarget.value = null
    debugPending.value = false
    debugError.value = null
  }
  async function triggerTimeQuery(startBar: number, endBar: number, eventClass?: string): Promise<void> {
    if (!symbol.value || !activePatternId.value || !scanFile.value) return
    const w = windowOf((effectiveScan.value ?? scanFile.value.scan) as any)
    try {
      timeScopeResponse.value = await getTimeDiagnose(
        activePatternId.value, symbol.value, w.start, w.end, startBar, endBar,
        eventClass, undefined, 'gate')   // ★ v3 · 入口 A 硬编码 anchorKind='gate'
      activeDetailCard.value = 'time'
    } catch { timeScopeResponse.value = null }
  }
  async function triggerPairQuery(srcEventId: string, dstEventId: string): Promise<void> {
    if (!symbol.value || !activePatternId.value || !scanFile.value) return
    const w = windowOf((effectiveScan.value ?? scanFile.value.scan) as any)
    try {
      pairScopeResponse.value = await getPairDiagnose(
        activePatternId.value, symbol.value, w.start, w.end, srcEventId, dstEventId)
      activeDetailCard.value = 'pair'
    } catch { pairScopeResponse.value = null }
  }

  // v2 event-debug(2026-07-15) · marker 右键 → 精准断点触发
  // spec: docs/research/2026-07-15_event-debug-dual-emit-multi-anchor/final_report.md
  async function triggerEventDebug(
    eventId: string, anchorKey: 'entry' | 'trough' | 'end'
  ): Promise<void> {
    if (!symbol.value || !activePatternId.value || !scanFile.value) return
    const events = effectiveAnalysis.value?.events ?? []
    const event = events.find(e => e.event_id === eventId)
    if (!event) return
    const anchorFn = anchorsOf[event.class_id] ?? anchorsOf._default
    const anchors = anchorFn(event, events)
    const anchor = anchors.find(a => a.key === anchorKey)
    if (!anchor || anchor.disabled) return
    // 单槽位覆盖: abort 旧 controller
    if (debugAbortRef) debugAbortRef.abort()
    const controller = new AbortController()
    debugAbortRef = controller
    debugError.value = null   // 清上一次错误 · 防混叠
    debugTarget.value = {
      eventId, bar: anchor.bar, className: event.class_id, anchor: anchor.key,
    }
    debugPending.value = true
    activeDetailCard.value = 'debug'
    const w = windowOf((effectiveScan.value ?? scanFile.value.scan) as any)
    try {
      await getTimeDiagnose(
        activePatternId.value, symbol.value, w.start, w.end,
        anchor.bar, anchor.bar, event.class_id, controller.signal,
        anchor.key,                                       // ★ v3 · anchor.key 直接透传为 anchorKind
      )
    } catch (e: any) {
      // AbortError 是正常路径(用户切事件/取消),不清 debugTarget 让新请求覆盖
      if (e?.name !== 'AbortError') {
        console.warn('triggerEventDebug fetch error:', e)
        debugError.value = e?.message ?? String(e)
      }
    } finally {
      if (debugAbortRef === controller) {
        debugPending.value = false
        debugAbortRef = null
      }
    }
  }

  function cancelDebug(): void {
    if (debugAbortRef) {
      debugAbortRef.abort()
      debugAbortRef = null
    }
    debugPending.value = false
    debugError.value = null
  }
  async function setPreviewEnabled(v: boolean): Promise<void> {
    previewEnabled.value = v
    if (v) await runPreview()
    else { preview.value = null; previewError.value = null }
  }

  async function runPreview(): Promise<void> {
    if (!scanFile.value || !symbol.value || !activePatternId.value) return
    previewLoading.value = true
    previewError.value = null
    const reqSymbol = symbol.value
    const reqPid = activePatternId.value
    const reqEnabled = previewEnabled.value
    try {
      const baseScan = scanFile.value.scan
      const labelHorizon = baseScan.label_horizon ?? 20
      const resp = await getPreview(reqPid, reqSymbol,
                                     baseScan.start_date, baseScan.end_date, labelHorizon)
      if (symbol.value !== reqSymbol || activePatternId.value !== reqPid
          || previewEnabled.value !== reqEnabled) return
      preview.value = { symbol: reqSymbol, analysis: resp.analysis,
                        pattern_spec: resp.pattern_spec, scan: resp.scan }
    } catch (e: any) {
      if (symbol.value !== reqSymbol || activePatternId.value !== reqPid
          || previewEnabled.value !== reqEnabled) return
      previewError.value = String(e?.message ?? e)
    } finally {
      if (symbol.value === reqSymbol && activePatternId.value === reqPid
          && previewEnabled.value === reqEnabled)
        previewLoading.value = false
    }
  }
  function clearPreview(): void {
    preview.value = null
    previewError.value = null
  }

  // diag 预取 watch:依赖 activePatternId
  watch([symbol, scanFile, activePatternId, preview, previewEnabled], async () => {
    if (!symbol.value || !scanFile.value || !activePatternId.value) {
      diag.value = null
      return
    }
    const reqSymbol = symbol.value
    const reqPid = activePatternId.value
    try {
      const eff = effectiveScan.value ?? scanFile.value.scan
      const w = windowOf(eff as any)
      const d = await getDiagnose(reqPid, symbol.value, w.start, w.end)
      if (symbol.value !== reqSymbol || activePatternId.value !== reqPid) return
      diag.value = d
    } catch { if (symbol.value === reqSymbol && activePatternId.value === reqPid) diag.value = null }
  }, { immediate: true })

  // spec §3.1 派生:导出符号保持,内部从 focusedMatchId/focusedEventId 派生。
  // selected 从 ref → computed(渲染层零改动 · storeToRefs 拿到的仍是 reactive)。
  const selected = computed<Selected>(() =>
    focusedMatchId.value ? { kind: 'match' as const, matchId: focusedMatchId.value } : null)

  const selectedMatchId = computed<string | null>(() => focusedMatchId.value)
  const selectedEventId = computed<string | null>(() => focusedEventId.value)

  const selectedMatch = computed<MatchDict | null>(() => {
    if (!focusedMatchId.value || !effectiveAnalysis.value) return null
    return effectiveAnalysis.value.matches.find(m => m.event_id === focusedMatchId.value) ?? null
  })

  // 视觉层(spec §3.1 分层):focusedMatchId 存在 → 亮 group 展开集;多归属 pending 时不亮
  // (candidateMatchIds 副轴驱动候选 bracket 虚线闪烁,不进 highlightedEventIds)。
  const highlightedEventIds = computed<ReadonlySet<string>>(() => {
    const m = selectedMatch.value
    if (!m) return new Set<string>()
    return matchedIdsOf(
      [m],
      effectiveAnalysis.value?.events ?? [],
      effectivePattern.value?.topology.edges ?? [],
    )
  })

  // 匹配 trace 展开的唯一判据(spec §3.1)
  const showTrace = computed<boolean>(() =>
    focusedMatchId.value !== null && focusedEventId.value === null)

  // 漏斗展开集合:单 source = manualExpandedNodes。手动/自动分层写入:
  //   toggleExpandedNode (sidebar 漏斗行 / topology dblclick) = add/remove(不折叠其他)
  //   focusEvent (marker click) = add 焦点 node(不折叠其他)
  //   focusMatch (bracket click) = 清空(trace 独占)
  const expandedNodeIds = computed<ReadonlySet<string>>(() => manualExpandedNodes.value)

  // sidebar「命中匹配」列表"选中"样式判据(spec §3.1 信息层):
  //   bracket-focus / disambig 后 → 单值 {focusedMatchId}
  //   多归属 pending → candidateMatchIds(如实反映所有归属)
  //   0 焦点 → 空集
  const markedMatchIds = computed<ReadonlySet<string>>(() => {
    if (focusedMatchId.value) return new Set([focusedMatchId.value])
    if (candidateMatchIds.value.size > 0) return candidateMatchIds.value
    return new Set()
  })

  // sidebar 候选表"选中"样式判据(spec §3.1 信息层):
  //   focus event → {focusedEventId}
  //   多归属 pending → {pendingDisambigEventId}
  //   都空 → 空集
  const markedEventIds = computed<ReadonlySet<string>>(() => {
    if (focusedEventId.value) return new Set([focusedEventId.value])
    if (pendingDisambigEventId.value) return new Set([pendingDisambigEventId.value])
    return new Set()
  })

  const tagMap = computed(() => effectivePattern.value
    ? deriveTagMap(effectivePattern.value.topology.nodes)
    : { tagToNodes: {} as Record<string, string[]>, tagList: [] as string[] })

  const isolated = computed<Set<string>>(() => effectivePattern.value
    ? isolatedNodeIds(effectivePattern.value.topology) : new Set())

  const matchedIds = computed<Set<string>>(() => matchedIdsOf(
    effectiveAnalysis.value?.matches ?? [], effectiveAnalysis.value?.events ?? [],
    effectivePattern.value?.topology.edges ?? []))

  const qualifiedIds = computed<Set<string>>(() => qualifiedIdsOf(diag.value))

  function bandKey(e: EventDict): string { return bandKeyOf(e, tagMap.value.tagList) }
  function eventTier(e: EventDict): Tier { return eventTierOf(e, matchedIds.value, qualifiedIds.value) }

  return {
    scanFile, symbol, activePatternId, sortByPid, sortDesc,
    nodeVisible, selected,
    focusedMatchId, focusedEventId, manualExpandedNodes,     // 内部 ref(export 便于 whitebox 单元测)
    level, selectedEventId, highlightedEventIds, candidateMatchIds, pendingDisambigEventId, hoveredEventId, diag,
    showTrace, expandedNodeIds, markedMatchIds, markedEventIds, // 派生 computed export
    shiftSelectedEvents, activeDetailCard, timeScopeResponse, pairScopeResponse,
    shiftPairPending, shiftSelectedEventIds,
    previewEnabled, preview, previewLoading, previewError,
    patternIds, currentPerStock, pattern, currentAnalysis,
    visiblePatterns, visibleFields, symbolQuery,
    effectivePattern, effectiveAnalysis, effectiveScan,
    unionRows, sortedRows, filteredSortedRows,
    nodeColors, selectedMatchId, selectedMatch, tagMap, isolated, matchedIds, qualifiedIds,
    loadScanFile, clearScanFile, selectSymbol, setActivePattern, setSort,
    toggleNode, toggleExpandedNode,
    focusMatch, focusEvent, clearFocus,
    setLevel, hoverEvent,
    setCandidateMatches, clearCandidates, setPendingDisambig,
    setShiftSelectedEvents, clearShiftSelection, clearDetailCard, triggerTimeQuery, triggerPairQuery,
    // v2 event-debug(2026-07-15)
    debugPending, debugTarget, debugError, triggerEventDebug, cancelDebug,
    currentTimeEventClass,
    setPreviewEnabled, runPreview, clearPreview,
    initVisiblePatterns, togglePattern, setPatternsAllOn, setPatternsAllOff, invertPatterns,
    setSymbolQuery, clearSymbolQuery,
    toggleField, isColumnVisible, effectiveSortKey,
    bandKey, eventTier,
  }
})
