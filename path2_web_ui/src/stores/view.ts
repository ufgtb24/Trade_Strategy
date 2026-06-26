// 视图状态:当前结果文件 / 选中股票 / role 显隐 / 选中对象;派生 roleColors/level 门控。
import { defineStore } from 'pinia'
import { computed, ref, shallowRef, watch } from 'vue'
import type { ScanResultFile, StockResult, MatchDict, EventDict, Tier, Diagnostics, Level } from '../types'
import { deriveRoleColors } from '../render/colors'
import {
  deriveTagMap, isolatedNodeIds,
  qualifiedIdsOf, matchedIds as matchedIdsOf,
  bandKeyOf, eventTierOf, windowOf,
} from '../render/visible'
import { getDiagnose, getPreview, type PreviewResp } from '../api'

export type Selected =
  | { kind: 'match'; matchId: string }
  | { kind: 'role'; nodeId: string }
  | null

export const useViewStore = defineStore('view', () => {
  const scanFile = ref<ScanResultFile | null>(null)
  const symbol = ref<string | null>(null)
  const roleVisible = ref<Record<string, boolean>>({})
  const selected = ref<Selected>(null)

  // ─── 新增 state ───────────────────────────────────────────────────────────
  const level = ref<Level>('matched')
  const selectedEventId = ref<string | null>(null)
  const hoveredEventId = ref<string | null>(null)
  const diag = ref<Diagnostics | null>(null)

  // ─── preview state(spec §4.1)─────────────────────────────────────────────
  const previewEnabled = ref(false)
  const preview = shallowRef<{
    symbol: string
    analysis: PreviewResp['analysis']
    pattern_spec: PreviewResp['pattern_spec']
    scan: PreviewResp['scan']
  } | null>(null)
  const previewLoading = ref(false)
  const previewError = ref<string | null>(null)

  // ─── 现有 computed ────────────────────────────────────────────────────────
  const pattern = computed(() => scanFile.value?.pattern_spec ?? null)
  const currentResult = computed<StockResult | null>(() =>
    scanFile.value?.results.find((r) => r.symbol === symbol.value) ?? null)
  const currentAnalysis = computed(() => currentResult.value?.analysis ?? null)

  const roleColors = computed(() =>
    effectivePattern.value ? deriveRoleColors(effectivePattern.value.topology, effectivePattern.value.event_styles) : {})

  // ─── preview computed(三处统一 guard)──────────────────────────────────────
  const effectiveAnalysis = computed(() => {
    if (previewEnabled.value && preview.value && preview.value.symbol === symbol.value)
      return preview.value.analysis
    return currentResult.value?.analysis ?? null
  })
  const effectivePattern = computed(() => {
    if (previewEnabled.value && preview.value && preview.value.symbol === symbol.value)
      return preview.value.pattern_spec
    return scanFile.value?.pattern_spec ?? null
  })
  const effectiveScan = computed(() => {
    if (previewEnabled.value && preview.value && preview.value.symbol === symbol.value)
      return preview.value.scan
    return scanFile.value?.scan ?? null
  })

  // ─── 现有 actions ─────────────────────────────────────────────────────────
  function loadScanFile(f: ScanResultFile) {
    scanFile.value = f
    roleVisible.value = {}
    selected.value = null
    selectedEventId.value = null
    hoveredEventId.value = null
    symbol.value = f.results[0]?.symbol ?? null
  }
  function clearScanFile() {
    scanFile.value = null
    symbol.value = null
    roleVisible.value = {}
    selected.value = null
    selectedEventId.value = null
    hoveredEventId.value = null
    // ─ preview:切 pattern 时全复位 ─
    previewEnabled.value = false
    preview.value = null
    previewError.value = null
    // diag 由 watch([symbol, scanFile, pattern, preview, previewEnabled]) 自动清:symbol → null 时
  }
  function selectSymbol(s: string) {
    symbol.value = s
    selected.value = null
    selectedEventId.value = null
    hoveredEventId.value = null
    // ─ preview:切股票清旧股临时结果;若仍勾选 → 自动 fetch 新股 ─
    preview.value = null
    previewError.value = null
    if (previewEnabled.value) void runPreview()
  }
  function toggleRole(nodeId: string) {
    roleVisible.value = { ...roleVisible.value, [nodeId]: roleVisible.value[nodeId] === false }
  }
  function selectMatch(matchId: string) { selected.value = { kind: 'match', matchId } }
  function selectRole(nodeId: string) { selected.value = { kind: 'role', nodeId } }
  function clearSelection() { selected.value = null }

  // ─── 新增 actions ─────────────────────────────────────────────────────────
  function setLevel(l: Level) { level.value = l }
  function selectEvent(id: string | null) { selectedEventId.value = id }
  function hoverEvent(id: string | null) { hoveredEventId.value = id }

  // ─── preview actions(spec §4.1)───────────────────────────────────────────
  async function setPreviewEnabled(v: boolean): Promise<void> {
    previewEnabled.value = v
    if (v) {
      await runPreview()
    } else {
      preview.value = null
      previewError.value = null
    }
  }

  async function runPreview(): Promise<void> {
    if (!scanFile.value || !symbol.value || !pattern.value) return
    previewLoading.value = true
    previewError.value = null
    const reqSymbol = symbol.value
    const reqEnabled = previewEnabled.value
    try {
      // C1 fix: always use the original strict window from scanFile (never the buffered preview.scan)
      const baseScan = scanFile.value.scan
      const start = baseScan.start_date
      const end = baseScan.end_date
      const labelHorizon = baseScan.label_horizon ?? 20
      const resp = await getPreview(pattern.value.pattern_id, reqSymbol,
                                     start, end, labelHorizon)
      if (symbol.value !== reqSymbol || previewEnabled.value !== reqEnabled) return
      preview.value = { symbol: reqSymbol, analysis: resp.analysis,
                        pattern_spec: resp.pattern_spec, scan: resp.scan }
    } catch (e: any) {
      if (symbol.value !== reqSymbol || previewEnabled.value !== reqEnabled) return
      previewError.value = String(e?.message ?? e)
    } finally {
      // loading token guard:防并发场景旧响应错误清 loading
      if (symbol.value === reqSymbol && previewEnabled.value === reqEnabled)
        previewLoading.value = false
    }
  }

  function clearPreview(): void {
    preview.value = null
    previewError.value = null
  }

  // ─── diag 预取 watch(带 stale-token guard,防快速切 symbol 时旧响应覆盖新 diag) ─
  watch([symbol, scanFile, pattern, preview, previewEnabled], async () => {
    if (!symbol.value || !scanFile.value || !pattern.value) { diag.value = null; return }
    const reqSymbol = symbol.value
    try {
      const w = windowOf(effectiveScan.value ?? scanFile.value.scan)
      const d = await getDiagnose(pattern.value.pattern_id, symbol.value, w.start, w.end)
      if (symbol.value !== reqSymbol) return            // 陈旧响应,丢弃
      diag.value = d
    } catch { if (symbol.value === reqSymbol) diag.value = null }
  }, { immediate: true })

  // ─── 现有 computed (selectedMatch) ───────────────────────────────────────
  const selectedMatch = computed<MatchDict | null>(() => {
    const sel = selected.value
    if (sel?.kind !== 'match' || !currentAnalysis.value) return null
    return currentAnalysis.value.matches.find((m) => m.event_id === sel.matchId) ?? null
  })

  // ─── 新增 computed (单一真相源) ───────────────────────────────────────────
  const tagMap = computed(() => effectivePattern.value
    ? deriveTagMap(effectivePattern.value.topology.nodes)
    : { tagToNodes: {} as Record<string, string[]>, tagList: [] as string[] })

  const isolated = computed<Set<string>>(() => effectivePattern.value
    ? isolatedNodeIds(effectivePattern.value.topology) : new Set())

  const matchedIds = computed<Set<string>>(() => matchedIdsOf(
    currentAnalysis.value?.matches ?? [], currentAnalysis.value?.events ?? []))

  const qualifiedIds = computed<Set<string>>(() => qualifiedIdsOf(diag.value))

  function bandKey(e: EventDict): string { return bandKeyOf(e, tagMap.value.tagList) }
  function eventTier(e: EventDict): Tier { return eventTierOf(e, matchedIds.value, qualifiedIds.value) }

  return {
    // 现有 state
    scanFile, symbol, roleVisible, selected,
    // 新增 state
    level, selectedEventId, hoveredEventId, diag,
    // preview state(新)
    previewEnabled, preview, previewLoading, previewError,
    // 现有 computed
    pattern, currentResult, currentAnalysis, roleColors, selectedMatch,
    // preview computed(新)
    effectiveAnalysis, effectivePattern, effectiveScan,
    // 新增 computed
    tagMap, isolated, matchedIds, qualifiedIds,
    // 现有 actions
    loadScanFile, clearScanFile, selectSymbol, toggleRole, selectMatch, selectRole, clearSelection,
    // 新增 actions
    setLevel, selectEvent, hoverEvent,
    // preview actions(新)
    setPreviewEnabled, runPreview, clearPreview,
    // 新增 computed 函数
    bandKey, eventTier,
  }
})
