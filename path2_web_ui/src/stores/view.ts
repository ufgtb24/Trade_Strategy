// 视图状态:scanFile / symbol / activePatternId / role 显隐 / 选中对象;
// 派生 unionRows/sortedRows/pattern/currentAnalysis/effective 三件套。
import { defineStore } from 'pinia'
import { computed, ref, shallowRef, watch } from 'vue'
import type {
  MultiScanResultFile, StockResult, PerPatternResult,
  MatchDict, EventDict, Tier, Diagnostics, Level, SerializedPattern, Analysis, ScanMeta,
} from '../types'
import { deriveRoleColors } from '../render/colors'
import {
  deriveTagMap, isolatedNodeIds,
  qualifiedIdsOf, matchedIds as matchedIdsOf,
  bandKeyOf, eventTierOf, windowOf,
} from '../render/visible'
import { getDiagnose, getPreview, type PreviewResp } from '../api'
import { useConfigStore } from './config'

export type Selected =
  | { kind: 'match'; matchId: string }
  | { kind: 'role'; nodeId: string }
  | null

export type UnionCell = { pid: string; max_ret: number | null; matched: boolean }
export type UnionRow  = { symbol: string; cells: UnionCell[] }

export const useViewStore = defineStore('view', () => {
  // ── state ────────────────────────────────────────────────────────
  const scanFile = ref<MultiScanResultFile | null>(null)
  const symbol = ref<string | null>(null)
  const activePatternId = ref<string | null>(null)
  const sortByPid = ref<string | null>(null)
  const sortDesc = ref(true)

  const roleVisible = ref<Record<string, boolean>>({})
  const selected = ref<Selected>(null)
  const level = ref<Level>('matched')
  const selectedEventId = ref<string | null>(null)
  const hoveredEventId = ref<string | null>(null)
  const diag = ref<Diagnostics | null>(null)

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
          max_ret: pp?.max_forward_return ?? null,
          matched: (pp?.summary?.matches ?? 0) > 0,
        }
      }),
    }))
  })

  const sortedRows = computed<UnionRow[]>(() => {
    const rows = unionRows.value
    const pid = sortByPid.value
    if (!pid) return rows
    const dir = sortDesc.value ? -1 : 1
    return [...rows].sort((a, b) => {
      const av = a.cells.find(c => c.pid === pid)?.max_ret
      const bv = b.cells.find(c => c.pid === pid)?.max_ret
      // null 永远沉底(无论升降)
      if (av == null && bv == null) return 0
      if (av == null) return 1
      if (bv == null) return -1
      return (av - bv) * dir
    })
  })

  // K 线 / 拓扑 等下游派生(同旧)
  const roleColors = computed(() =>
    effectivePattern.value ? deriveRoleColors(effectivePattern.value.topology, effectivePattern.value.event_styles) : {})

  // ── actions ──────────────────────────────────────────────────────
  function loadScanFile(f: MultiScanResultFile) {
    scanFile.value = f
    roleVisible.value = {}
    selected.value = null
    selectedEventId.value = null
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
  }
  function clearScanFile() {
    scanFile.value = null
    symbol.value = null
    activePatternId.value = null
    sortByPid.value = null
    roleVisible.value = {}
    selected.value = null
    selectedEventId.value = null
    hoveredEventId.value = null
    previewEnabled.value = false
    preview.value = null
    previewError.value = null
  }
  function selectSymbol(s: string) {
    // 锚-active 解耦:只切股、不动 activePatternId
    symbol.value = s
    selected.value = null
    selectedEventId.value = null
    hoveredEventId.value = null
    preview.value = null
    previewError.value = null
    if (previewEnabled.value) void runPreview()
  }
  function setActivePattern(pid: string) {
    activePatternId.value = pid
    const cfg = useConfigStore()
    if (cfg.config) cfg.config.last_selected_pattern = pid
    if (previewEnabled.value) void runPreview()
  }
  function setSort(pid: string) {
    if (sortByPid.value === pid) {
      sortDesc.value = !sortDesc.value
    } else {
      sortByPid.value = pid
      sortDesc.value = true
    }
  }
  function toggleRole(nodeId: string) {
    roleVisible.value = { ...roleVisible.value, [nodeId]: roleVisible.value[nodeId] === false }
  }
  function selectMatch(matchId: string) { selected.value = { kind: 'match', matchId } }
  function selectRole(nodeId: string) { selected.value = { kind: 'role', nodeId } }
  function clearSelection() { selected.value = null }
  function setLevel(l: Level) { level.value = l }
  function selectEvent(id: string | null) { selectedEventId.value = id }
  function hoverEvent(id: string | null) { hoveredEventId.value = id }

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

  const selectedMatch = computed<MatchDict | null>(() => {
    const sel = selected.value
    if (sel?.kind !== 'match' || !effectiveAnalysis.value) return null
    return effectiveAnalysis.value.matches.find(m => m.event_id === sel.matchId) ?? null
  })

  const tagMap = computed(() => effectivePattern.value
    ? deriveTagMap(effectivePattern.value.topology.nodes)
    : { tagToNodes: {} as Record<string, string[]>, tagList: [] as string[] })

  const isolated = computed<Set<string>>(() => effectivePattern.value
    ? isolatedNodeIds(effectivePattern.value.topology) : new Set())

  const matchedIds = computed<Set<string>>(() => matchedIdsOf(
    effectiveAnalysis.value?.matches ?? [], effectiveAnalysis.value?.events ?? []))

  const qualifiedIds = computed<Set<string>>(() => qualifiedIdsOf(diag.value))

  function bandKey(e: EventDict): string { return bandKeyOf(e, tagMap.value.tagList) }
  function eventTier(e: EventDict): Tier { return eventTierOf(e, matchedIds.value, qualifiedIds.value) }

  return {
    scanFile, symbol, activePatternId, sortByPid, sortDesc,
    roleVisible, selected,
    level, selectedEventId, hoveredEventId, diag,
    previewEnabled, preview, previewLoading, previewError,
    patternIds, currentPerStock, pattern, currentAnalysis,
    effectivePattern, effectiveAnalysis, effectiveScan,
    unionRows, sortedRows,
    roleColors, selectedMatch, tagMap, isolated, matchedIds, qualifiedIds,
    loadScanFile, clearScanFile, selectSymbol, setActivePattern, setSort,
    toggleRole, selectMatch, selectRole, clearSelection,
    setLevel, selectEvent, hoverEvent,
    setPreviewEnabled, runPreview, clearPreview,
    bandKey, eventTier,
  }
})
