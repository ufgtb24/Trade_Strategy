// 视图状态:mode / scanFile / symbol / activePatternId / node 显隐 / 选中对象;
// 派生 unionRows/sortedRows/pattern/currentAnalysis/effective 三件套。
import { defineStore, acceptHMRUpdate } from 'pinia'

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
  key: 'entry' | 'start' | 'end' | 'confirm'
  bar: number
  label: string
  hint: string
  disabled?: boolean
  disabledReason?: string
}

export function findBoBar(anchorBoIds: string | readonly string[], events: readonly any[]): number | null {
  const anchor: string = Array.isArray(anchorBoIds) ? anchorBoIds[0] ?? '' : anchorBoIds
  if (!anchor) return null
  // anchor_bo_id 恒为 instance_id 形态(后端交错标注后 detect 期写入),纯精确匹配
  const exact = events.find(x => x.instance_id === anchor)
  return exact?.end_idx ?? null
}

// ── tb node_id 塌缩细分:容器 / 子段 / V1 三档 ──────────────────────────
// 引擎 children 声明命名表(方案 A,2026-08-17)已把声明过的段直标子结构 node_id
// (bottom_burst→'tb_seg',anchorsOf 直挂键 start/end,不走此细分)。
// 此细分仅服务 node_id 仍为 'tb' 的事件——未声明 children 的 app 的段 + 全部容器/V1:
//   1. 容器:child_refs 非空(尤其 segments 槽)→ v4 容器,entry/start/end 三锚
//      (start/end 复用后端状态机埋点,端点由子段承担;前端菜单复用不产生后端双埋)
//   2. 子段:child_refs 空,但 instance_id 出现在某容器 child_refs 里 → 历史段 confirm/end 锚
//   3. V1 叶子:child_refs 空 + 未被任何容器引用 → entry/confirm/end 锚
export type TbAnchorProfile = 'tb_v1' | 'tb_container' | 'tb_segment'

export function tbAnchorProfile(e: any, events: readonly any[]): TbAnchorProfile {
  const refs = e.child_refs as Record<string, readonly string[]> | undefined
  if (refs && Object.keys(refs).length > 0) return 'tb_container'
  const isChild = events.some((x: any) => {
    const r = x.child_refs as Record<string, readonly string[]> | undefined
    if (!r) return false
    return Object.values(r).some(ids => ids.includes(e.instance_id))
  })
  return isChild ? 'tb_segment' : 'tb_v1'
}

function tbContainerAnchors(e: any, events: readonly any[]): DebugAnchor[] {
  const boBar = findBoBar(e.anchor_bo_id, events)
  return [
    {
      key: 'entry',
      bar: boBar ?? e.start_idx,   // fallback 避免 null 传导; disabled 阻塞点击
      label: 'entry',
      hint: '停在容器 attempt 入口(每 burst 一次)· 看本 burst 机器锚点(bo/global_bottom)起点',
      disabled: boBar == null,
      disabledReason: boBar == null
        ? `未找到 anchor bo event (id=${String(e.anchor_bo_id ?? '')}), 可改用 tb_seg 段调试`
        : undefined,
    },
    {
      key: 'start',
      bar: e.start_idx,
      label: 'start',
      hint: '容器起点(首段 enter)· 复用状态机 start 埋点(段诞生当根)',
    },
    {
      key: 'end',
      bar: e.end_idx,
      label: 'end',
      hint: '容器终点(末段 exit)· 复用状态机 end 埋点(段收口当根)',
    },
  ]
}

// 历史段锚点(confirm/end):未声明 children 的 app 的段仍埋 confirm/end,词汇未演进,保留
function tbSegmentAnchorsHistoric(e: any): DebugAnchor[] {
  return [
    {
      key: 'confirm',
      bar: e.start_idx,
      label: 'confirm',
      hint: '停在段开处(企稳确认根)· 看企稳条件 / local_trough / troughs(SCB / stop signal / base_min)',
    },
    {
      key: 'end',
      bar: e.end_idx,
      label: 'end',
      hint: '停在段出口 · 看 rise/break/timeout/distribute/oversold(weak)哪条触发',
    },
  ]
}

// v4 段锚点(start/end):tb_seg 确认型事件按锚点档位体系(v4 后端状态机埋点)
function tbSegmentAnchorsV4(e: any): DebugAnchor[] {
  return [
    {
      key: 'start',
      bar: e.start_idx,
      label: 'start',
      hint: '停在段开处(子段确认型 start 档 = 段诞生当根,attempt 归容器)· 看 state/trough/cnt/gbot',
    },
    {
      key: 'end',
      bar: e.end_idx,
      label: 'end',
      hint: '停在段出口 · 看 rise/weak/break/timeout 哪条收段',
    },
  ]
}

function tbV1Anchors(e: any, events: readonly any[]): DebugAnchor[] {
  const boBar = findBoBar(e.anchor_bo_id, events)
  return [
    {
      key: 'entry',
      bar: boBar ?? e.start_idx,
      label: 'entry',
      hint: '停在本 burst 状态机入口(每 burst 一次)· 看 global_bottom(span 内 measure 最小)与 vol 起点',
      disabled: boBar == null,
      disabledReason: boBar == null
        ? `未找到 anchor bo event (id=${String(e.anchor_bo_id ?? '')})`
        : undefined,
    },
    {
      key: 'confirm',
      bar: e.start_idx,
      label: 'confirm',
      hint: '停在入段根(第 K 根不刷新)· 看 state / trough / cnt / peak',
    },
    {
      key: 'end',
      bar: e.end_idx,
      label: 'end',
      hint: '停在段收口根 · 看 rise / weak / break / timeout 哪条收口',
    },
  ]
}

export const anchorsOf: Record<string, (e: any, events: readonly any[]) => DebugAnchor[]> = {
  // 子结构段(children 声明命名表直标 node_id,方案 A):v4 段 start/end 两锚,
  // 断点实际落在物化者(tb 的 ThrowbackDetectorV4)状态机埋点,menu 键按段自身 node_id。
  tb_seg: e => tbSegmentAnchorsV4(e),
  // tb node:容器/段/V1 三档按前端可判信号细分(见 tbAnchorProfile;
  // 未声明 children 的 app 段仍落此键)
  tb: (e, events) => {
    const p = tbAnchorProfile(e, events)
    if (p === 'tb_segment') return tbSegmentAnchorsHistoric(e)
    if (p === 'tb_v1') return tbV1Anchors(e, events)
    return tbContainerAnchors(e, events)
  },
  _default: () => [],  // D7 · 不给未埋点 node 生成菜单项(防"菜单显示但 breakpoint 不 hit"的无声失败)
}

// D8 · DEBUG_ENABLED_NODES 与 anchorsOf 硬耦合(单一 source of truth):
// 后端埋新 detector 时,前端只改 anchorsOf,whitelist 自动同步。
// 实例化后白名单按 node_id 匹配;子结构 node(tb_seg 等)自身无 detector,
// 埋点在其 produced_by detector(段锚断点即容器 detector 的埋点)。
export const DEBUG_ENABLED_NODES = Object.keys(anchorsOf).filter(k => k !== '_default')

import { computed, ref, shallowRef, watch, type ComputedRef } from 'vue'
import type {
  MultiScanResultFile, StockResult, PerPatternResult,
  HitDict, EventDict, Tier, Diagnostics, Level, SerializedPattern, Analysis, ScanMeta,
  TimeScopeResponse, PairScopeResponse, WorkingCopySlot, ViewWindow,
} from '../types'
import { deriveNodeColors } from '../render/colors'
import {
  deriveTagMap, isolatedNodeIds,
  qualifiedIdsOf, inHitIds as inHitIdsOf,
  bandKeyOf, eventTierOf, windowOf, nodeOfEventByBand, isBandVisible,
} from '../render/visible'
import {
  familyKeyOf, foldBand, HIT_FAMILY_PREFIX, type Family,
} from '../render/fold'
import { boundEvents, hitDays, hitOrderOf, landIndex, usingIndex } from '../render/walk'
import { mergedHit, sameSel, step, up, type Axis, type Sel, type SelPath } from '../render/select'
import { bandCells, lineDayOf, makeWorld, type AnchorRow, type WorldCtx } from '../render/selWorld'
import { snapshotOf as selSnapshotOf, type SnapCtx, type Snapshot } from '../render/selSnapshot'
import { feedbackHits } from '../annotate/feedback'
import { getDiagnose, getPreview, getTimeDiagnose, getPairDiagnose, saveWcMirror, clearWcMirror, type PreviewResp } from '../api'
import { useConfigStore } from './config'

// shift+click 累积器条目(入口 D · KlineChart.ts::handleShiftClick 消费/写入)。
// 实例化契约:instance_id/node_id(取代旧的复合身份字段)。
export type ShiftSelectedEvent = { instance_id: string; node_id: string; source: 'main' | 'sub' }
/** 主视图模式(顶栏 mode)。
 *  - annotate:按代码打开的图,只画 K 线、成交量和用户的框与样本,不画任何 app 产物(effectiveAnalysis 恒为 null);
 *  - compare:标注照旧(能接着标),再把当前 pattern 的 app 在这张图上的输出叠上去:event 画在用户框所在的特征轨上,
 *    hit 画在 bracket 轨上(stores/appLink.ts 跑 app、给 mapping);
 *  - app:按 node 分轨画 app 的产物。两种来源(appSource):scan = 扫描结果(加载扫描、从扫描列表选股时进入);
 *    linked = 当前 pattern 的 app 在这只股票上现算的输出(顶栏切过来时)。 */
export type ViewMode = 'annotate' | 'compare' | 'app'

/** user 行(样本那一行)的行键:选中样本时它是当家行。 */
export const SAMPLES_ROW_KEY = 'samples'
/** app 产物从哪来:scan = 扫描结果文件;linked = 当前 pattern 的 app 在这只股票上现算(compare 恒为 linked)。 */
export type AppSource = 'scan' | 'linked'
/** 当前 pattern 的 app 在一只股票上现算的输出(/preview,区间是这只股票截到训练段末日的全部 K 线)。 */
export interface LinkedRun {
  symbol: string
  app: string
  analysis: Analysis
  pattern_spec: SerializedPattern
  scan: PreviewResp['scan']
}


export type Selected =
  | { kind: 'hit'; hitId: string }
  | { kind: 'node'; nodeId: string }
  | null

export type UnionCell = { pid: string; num: number | null; fr: number | null; fd: number | null; hasHit: boolean }
export type UnionRow  = { symbol: string; cells: UnionCell[] }
export type PreviewRowCell = { pid: string; num: number | null; fr: number | null; fd: number | null; filled: boolean }
export type PreviewRow     = { symbol: string; cells: PreviewRowCell[] }

// sortByPid 哨兵值:按 symbol 字典序排序(非 pid)。
// '__symbol__' 双下划线前缀不会与用户 pattern_id 撞(pid 由 dag_spec 注册的人类可读字符串)。
export const SYMBOL_SORT_KEY = '__symbol__'

// 列可见性(field 轴)localStorage 持久化:key 与 value 格式见 view store 说明。
// fd(forward_drawdown)与 fr(forward_return)同层同权;默认可见。
// 老 LS 条目(无 fd)不会被自动补 fd —— 用户可右键字段菜单勾选;新设备/新 LS 默认含 fd。
const LS_KEY_VISIBLE_FIELDS = 'path2_web_ui.visibleFields'
type FieldKey = 'num' | 'fr' | 'fd'
const FIELD_KEYS: readonly FieldKey[] = ['num', 'fr', 'fd']
function loadFieldsFromLS(): Set<FieldKey> {
  try {
    const raw = localStorage.getItem(LS_KEY_VISIBLE_FIELDS)
    if (raw == null) return new Set<FieldKey>(FIELD_KEYS)
    const arr = JSON.parse(raw) as unknown
    if (!Array.isArray(arr)) return new Set<FieldKey>(FIELD_KEYS)
    return new Set(arr.filter((x): x is FieldKey => (FIELD_KEYS as readonly string[]).includes(x)))
  } catch { return new Set<FieldKey>(FIELD_KEYS) }
}
function saveFieldsToLS(s: Set<FieldKey>): void {
  try { localStorage.setItem(LS_KEY_VISIBLE_FIELDS, JSON.stringify([...s])) }
  catch { /* silent */ }
}

const LS_KEY_LEVEL = 'path2_web_ui.level'
const LEVEL_VALUES: readonly Level[] = ['in_hit', 'qualified', 'detected']
function loadLevelFromLS(): Level {
  try {
    const raw = localStorage.getItem(LS_KEY_LEVEL)
    if (raw == null) return 'in_hit'
    return (LEVEL_VALUES as readonly string[]).includes(raw) ? (raw as Level) : 'in_hit'
  } catch { return 'in_hit' }
}
function saveLevelToLS(l: Level): void {
  try { localStorage.setItem(LS_KEY_LEVEL, l) } catch { /* silent */ }
}

export const useViewStore = defineStore('view', () => {
  // ── state ────────────────────────────────────────────────────────
  // shallowRef:scanFile 全程整体替换(loadScanFile/clearScanFile),无内部 mutate,
  // 避免对 4000+ stocks×{events,hits,clauses} 树建深 Proxy 拖慢首屏与排序
  const scanFile = shallowRef<MultiScanResultFile | null>(null)
  const currentScanName = ref<string | null>(null)
  const mode = ref<ViewMode>('annotate')
  const appSource = ref<AppSource>('scan')
  // annotating:用户的框与样本画在图上、可以标注(annotate 与 compare);comparing:compare;
  // linkedView:app 产物来自当前 pattern 的 app 现算(compare,或从顶栏切到的 app)
  const annotating = computed(() => mode.value === 'annotate' || mode.value === 'compare')
  const comparing = computed(() => mode.value === 'compare')
  const linkedView = computed(() => mode.value === 'compare' || (mode.value === 'app' && appSource.value === 'linked'))
  const linkedRun = shallowRef<LinkedRun | null>(null)
  const symbol = ref<string | null>(null)
  // annotate 下打开时图停在哪段(rally / random 进来时给);null = 按默认缩放(整只股票)。
  // 每次 openSymbol 都换一个新对象:同一只股票换一段也能触发重画
  const viewWindow = ref<ViewWindow | null>(null)
  const activePatternId = ref<string | null>(null)
  const sortByPid = ref<string | null>(null)
  const sortDesc = ref(true)
  const visiblePatterns = ref<Set<string>>(new Set())
  const visibleFields = ref<Set<FieldKey>>(loadFieldsFromLS())
  const symbolQuery = ref<string>('')

  const nodeVisible = ref<Record<string, boolean>>({})
  // 选中(由选中的那条路径统一写入,见下文 applyPath):focusedHitId 非空 & 无实例焦点 → 只选 hit,展 trace;
  // selectedInstanceId/focusedInstanceId 任一非空 → 实例焦点,不展 trace:
  //   选中一个 event                → selectedInstanceId 非空
  //   从一个 event 走进它的某次 hit → focusedHitId + focusedInstanceId 非空
  // 聚焦一律不改档位按钮(档位只由用户点)。
  const focusedHitId = ref<string | null>(null)
  const selectedInstanceId = ref<string | null>(null)
  const focusedInstanceId = ref<string | null>(null)
  // sidebar 漏斗手动 toggle 兜底:仅在无实例焦点/pending 时生效
  // sidebar 漏斗手动展开集合(多 node 可同时展开)。语义分层:
  //   手动入口(sidebar 漏斗行 / TopologyControl dblclick)= toggleExpandedNode (add/remove,不折叠其他)
  //   自动入口(focusEvent · marker/candidate/trace node click)= add 焦点 node(不折叠其他)
  //   focusHit(bracket / hit 列表 click)= 清空(trace 独占)
  //   4 处初始化(切数据源)= 清空
  const manualExpandedNodes = ref<Set<string>>(new Set())
  const level = ref<Level>(loadLevelFromLS())
  const hoveredEventId = ref<string | null>(null)
  const diag = ref<Diagnostics | null>(null)
  // 当前日(竖线落点,bar 索引)
  const currentDay = ref<number | null>(null)
  // 图上 K 线的日期(KlineChart 载入 K 线后写入),给侧栏把 bar 下标换成日期
  const barDates = ref<string[]>([])

  // ── 入口 A/D(Task 18):KlineChart brush(scope=time)+ shift+click 跨图(scope=pair) ──
  // shiftSelectedEvents 是唯一跨组件状态载体(同 focusedInstanceRef/candidateHitIds 既有模式;
  // KlineChart 本身零 props/零 emit,靠 store 与 DetailSidebar 通信),故放这里而非组件内 ref。
  const shiftSelectedEvents = ref<ShiftSelectedEvent[]>([])
  const activeDetailCard = ref<'time' | 'pair' | 'debug' | null>(null)

  // v2 event-debug(2026-07-15) · marker 右键触发的精准断点 pending 状态。
  // 单槽位覆盖模型(与 activeDetailCard 单值互斥模式一致): 新 debug 请求 abort 旧 controller。
  const debugPending = ref(false)
  const debugTarget = ref<{ instanceId: string; bar: number; node_id: string; anchor: string } | null>(null)
  // fetch 失败(network/500)态 · 与 debugPending=false 组合区分"断点已释放"(成功)vs"请求失败"
  const debugError = ref<string | null>(null)
  let debugAbortRef: AbortController | null = null
  const timeScopeResponse = ref<TimeScopeResponse | null>(null)
  // 入口 A · FailedAttemptsCard 下拉过滤态 · '' = 全部;提升到 store 让 KlineChart brush handler 可透传给 triggerTimeQuery
  const currentDiagnoseNode = ref<string>('')
  const pairScopeResponse = ref<PairScopeResponse | null>(null)

  // ── Working Copy(2026-07-20 params-consistency,spec=docs/research/2026-07-20_params-profiles-dev-modes)──
  // 浏览态:全 UI 锚 scan file snapshot;探索态:锚 WC dict。localStorage 休眠恢复(不自动激活)。
  const workingCopy = ref<Record<string, WorkingCopySlot | undefined>>({})
  const dormantDrafts = ref<{ pid: string; savedAt: number }[]>([])

  // Task 12 · 全局 toast(scan 完成自动清 WC 等一次性提示)· 3.5s 自清,连续调用互相取消延长展示。
  const toastMsg = ref<string | null>(null)
  let _toastTimer: ReturnType<typeof setTimeout> | null = null
  function showToast(msg: string): void {
    toastMsg.value = msg
    if (_toastTimer) clearTimeout(_toastTimer)
    _toastTimer = setTimeout(() => { toastMsg.value = null }, 3500)
  }

  function _wcKey(pid: string): string {
    return `p2wc:${scanFile.value?.scan.scan_ts ?? ''}:${pid}`
  }
  function snapshotOf(pid: string): Record<string, any> | null {
    return (scanFile.value?.per_pattern[pid] as any)?.params_snapshot ?? null
  }
  const isExploring = computed<boolean>(() => {
    const pid = activePatternId.value
    return !!(pid && workingCopy.value[pid]?.enabled)
  })
  // 三环节一致性核心:浏览态 diagnose/preview 锚 snapshot,探索态锚 WC;legacy(无 snapshot)=null → 后端 fallback 当前 yaml
  const effectiveParamsOverride = computed<Record<string, any> | null>(() => {
    const pid = activePatternId.value
    if (!pid) return null
    const wc = workingCopy.value[pid]
    if (wc?.enabled) return wc.currentDict
    return snapshotOf(pid)
  })
  // WC 镜像落盘(探索态诊断用):修改 WC 的操作调本函数,把当前 WC 镜像到 outputs/path2_web/wc.json。
  // localStorage 行为不变;wc.json 供终端诊断探索态读 WC。fire-and-forget,失败 toast 不阻塞。
  function mirrorWc(pid: string): void {
    const wc = workingCopy.value[pid]
    const sc = scanFile.value?.scan
    if (!wc || !sc) return
    void saveWcMirror(pid, sc.scan_ts, sc.win_start, sc.win_end, sc.start_date, sc.end_date, wc.currentDict, wc.enabled)
      .catch(e => showToast(`WC 镜像落盘失败: ${e?.message ?? e}`))
  }
  function clearWc(pid: string): void {
    void clearWcMirror(pid).catch(e => showToast(`WC 镜像清理失败: ${e?.message ?? e}`))
  }
  function forkWorkingCopy(pid: string): void {
    const snap = snapshotOf(pid)
    if (!snap || workingCopy.value[pid]) {
      if (workingCopy.value[pid]) { workingCopy.value[pid]!.enabled = true; mirrorWc(pid) }
      return
    }
    workingCopy.value = { ...workingCopy.value,
      [pid]: { enabled: true, baseline: JSON.parse(JSON.stringify(snap)),
               currentDict: JSON.parse(JSON.stringify(snap)) } }
    mirrorWc(pid)
  }
  function ensureWorkingCopy(pid: string, baseline: Record<string, any>): void {
    // Write Copy 入口:只保证 WC 存在(内容轴),不碰 enabled——视图轴唯一写者是 setWorkingCopyEnabled(chip)。
    // baseline 由调用方给定(legacy scan 无 snapshot 时用当前 yaml 内容),不依赖 snapshotOf。
    if (workingCopy.value[pid]) return
    workingCopy.value = { ...workingCopy.value,
      [pid]: { enabled: false, baseline: JSON.parse(JSON.stringify(baseline)),
               currentDict: JSON.parse(JSON.stringify(baseline)) } }
    mirrorWc(pid)
  }
  function setWorkingCopyEnabled(pid: string, v: boolean): void {
    const wc = workingCopy.value[pid]
    if (!wc) { if (v) forkWorkingCopy(pid); return }
    wc.enabled = v
    if (v) void runPreview()
    else { preview.value = null; previewError.value = null }
    mirrorWc(pid)
  }
  function updateWorkingCopy(pid: string, dict: Record<string, any>): void {
    const wc = workingCopy.value[pid]
    if (!wc) return
    wc.currentDict = dict
    localStorage.setItem(_wcKey(pid), JSON.stringify(
      { dict, baseline: wc.baseline, savedAt: Date.now() }))
    // F-C:localStorage 已被这次写入覆盖,该 pid 若曾是"休眠草稿"(上次会话遗留、未被本次覆写前的旧内容)
    // 现已不成立——banner 不该再对已被覆盖的 pid 显示「恢复」。restoreDormant 走独立路径(不经本函数)
    // 已自行剔除,这里补上 updateWorkingCopy 直接覆写的那条路径,两处各自剔除、互不冲突。
    dormantDrafts.value = dormantDrafts.value.filter(d => d.pid !== pid)
    if (wc.enabled) void runPreview()
    mirrorWc(pid)
  }
  function resetWorkingCopy(pid: string): void {
    const wc = workingCopy.value[pid]
    if (!wc) return
    updateWorkingCopy(pid, JSON.parse(JSON.stringify(wc.baseline)))
  }
  function discardWorkingCopy(pid: string): void {
    localStorage.removeItem(_wcKey(pid))
    clearWc(pid)
    const { [pid]: _, ...rest } = workingCopy.value
    workingCopy.value = rest
    dormantDrafts.value = dormantDrafts.value.filter(d => d.pid !== pid)
    preview.value = null
  }
  function restoreDormant(pid: string): void {
    // 决策2:恢复=只装回内容轴(enabled=false,chip 灰);看不看由用户点 chip 决定,灰态无 preview。
    const raw = localStorage.getItem(_wcKey(pid))
    if (!raw) return
    try {
      const { dict, baseline } = JSON.parse(raw)
      workingCopy.value = { ...workingCopy.value,
        [pid]: { enabled: false, baseline, currentDict: dict } }
      dormantDrafts.value = dormantDrafts.value.filter(d => d.pid !== pid)
      mirrorWc(pid)
    } catch { localStorage.removeItem(_wcKey(pid)) }
  }
  function wcDirty(pid: string): boolean {
    const wc = workingCopy.value[pid]
    return !!wc && JSON.stringify(wc.currentDict) !== JSON.stringify(wc.baseline)
  }
  function _scanDormantDrafts(): void {
    dormantDrafts.value = []
    const ts = scanFile.value?.scan.scan_ts
    if (!ts) return
    for (const pid of scanFile.value!.pattern_ids) {
      const raw = localStorage.getItem(`p2wc:${ts}:${pid}`)
      if (!raw) continue
      try { dormantDrafts.value.push({ pid, savedAt: JSON.parse(raw).savedAt ?? 0 }) }
      catch { /* 脏数据忽略 */ }
    }
  }

  // previewEnabled 兼容层:保留原名(避免大范围改消费点),改为 isExploring 的 computed 别名。
  const previewEnabled = computed(() => isExploring.value)
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

  // preview-aware effective 三件套。linkedView 下一律取 shownRun:现算的输出,且只认这只股票的
  const shownRun = computed<LinkedRun | null>(() =>
    linkedView.value && linkedRun.value?.symbol === symbol.value ? linkedRun.value : null)
  const _previewApplies = computed(() =>
    !linkedView.value && previewEnabled.value && preview.value
    && preview.value.symbol === symbol.value
    && preview.value.pattern_spec.pattern_id === activePatternId.value)

  const effectivePattern = computed<SerializedPattern | null>(() => {
    if (linkedView.value) return shownRun.value?.pattern_spec ?? null
    return _previewApplies.value ? preview.value!.pattern_spec : pattern.value
  })

  // annotate 模式下恒为 null:图上、侧栏、状态条一律拿不到 app 的产物
  const effectiveAnalysis = computed<Analysis | null>(() => {
    if (mode.value === 'annotate') return null
    if (linkedView.value) return shownRun.value?.analysis ?? null
    return _previewApplies.value ? preview.value!.analysis : currentAnalysis.value
  })

  const effectiveScan = computed<ScanMeta | PreviewResp['scan'] | null>(() => {
    if (linkedView.value) return shownRun.value?.scan ?? null
    if (_previewApplies.value) return preview.value!.scan
    return scanFile.value?.scan ?? null
  })

  // 图上画的是哪个 app 的产物、它的买点 node(eval_meta 的 end_node)
  const appId = computed<string | null>(() => (linkedView.value ? shownRun.value?.app ?? null : activePatternId.value))
  const endNode = computed<string | null>(() => (linkedView.value
    ? shownRun.value?.scan.end_node ?? null
    : (activePatternId.value ? scanFile.value?.per_pattern[activePatternId.value]?.end_node ?? null : null)))
  /** 跑这个 app 用的区间(带缓冲的分析窗口,windowOf):诊断与入口 A/B/D 的查询按同一区间跑;还没有 app 产物为 null。 */
  function appWindowOf(): { start: string; end: string } | null {
    const eff = effectiveScan.value
    return eff && symbol.value && appId.value ? windowOf(eff as any) : null
  }
  // 诊断与入口 A/B/D 的参数覆盖:只有扫描结果的探索态有(linked 一律按 app 的参数文件跑)
  const appParamsOverride = computed<Record<string, any> | undefined>(() =>
    linkedView.value ? undefined : effectiveParamsOverride.value ?? undefined)

  // 探索态列表对照行(dev ↳(UI) parity):从单股 preview 派生出与 unionRows 单行同构的对照行。
  // 只填 active pattern(preview 只现算了它),其余 pattern 留 filled:false(渲染层显空白,非 —)。
  const previewListRow = computed<PreviewRow | null>(() => {
    if (!_previewApplies.value || previewLoading.value) return null
    const pv = preview.value!
    const pid = activePatternId.value!
    const ms = pv.analysis.hits
    const num = ms.length
    // fr 口径须与冻结行 unionRows 消费的 max_forward_return 一致(skip null,取 max);
    // 此处客户端重算是那份后端语义的对手件,后端若改 max 定义,这里需同步。
    // fd 是 fr 的对偶:skip null 取 min(最差下行);与后端 min_forward_drawdown 同口径。
    let fr: number | null = null
    let fd: number | null = null
    for (const m of ms) {
      const r = m.forward_return
      if (r != null && (fr === null || r > fr)) fr = r
      const d = m.forward_drawdown
      if (d != null && (fd === null || d < fd)) fd = d
    }
    const cells: PreviewRowCell[] = patternIds.value.map(p =>
      p === pid
        ? { pid: p, num, fr, fd, filled: true }
        : { pid: p, num: null, fr: null, fd: null, filled: false })
    return { symbol: pv.symbol, cells }
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
          num: pp ? (pp.summary?.hits ?? 0) : null,
          fr:  pp?.max_forward_return ?? null,
          fd:  pp?.min_forward_drawdown ?? null,
          hasHit: (pp?.summary?.hits ?? 0) > 0,
        } as UnionCell
      }),
    }))
  })

  // 每 pattern 的命中股票数(distinct symbol,非 hit 次数)。
  // 源头是 unionRows —— 全量并集、未经 symbolQuery / visiblePatterns 过滤,
  // 因此「固定全量、不随筛选联动」由结构保证,无需额外开关。
  const patternHitStocks = computed<Record<string, number>>(() => {
    const f = scanFile.value
    if (!f) return {}
    const counts: Record<string, number> = {}
    for (const pid of f.pattern_ids) counts[pid] = 0   // 零命中也要有键,显示 0 而非空
    for (const row of unionRows.value) {
      for (const cell of row.cells) {
        if (cell.hasHit) counts[cell.pid] += 1
      }
    }
    return counts
  })

  const sortedRows = computed<UnionRow[]>(() => {
    const rows = unionRows.value
    const pid = effectiveSortKey.value
    if (!pid) return rows
    const dir = sortDesc.value ? -1 : 1
    if (pid === SYMBOL_SORT_KEY) {
      return rows.slice().sort((a, b) => a.symbol.localeCompare(b.symbol) * dir)
    }
    const m = pid.match(/^(.+)_(num|fr|fd)$/)
    if (!m) return rows
    const targetPid = m[1]
    const targetField = m[2] as 'num' | 'fr' | 'fd'
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
      if (!row.cells.some(c => visiblePatterns.value.has(c.pid) && c.hasHit)) return false
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
    currentScanName.value = f?.scan?.name ?? f?.scan?.scan_ts ?? null
    mode.value = 'app'
    appSource.value = 'scan'
    nodeVisible.value = {}
    clearFocus()
    manualExpandedNodes.value = new Set()   // 切数据源清空展开集
    hoveredEventId.value = null
    sortByPid.value = null
    sortDesc.value = true
    symbol.value = f.results[0]?.symbol ?? null
    preview.value = null
    previewError.value = null
    // active 默认值:优先 config.last_selected_pattern 若在 pattern_ids 中
    const cfg = useConfigStore()
    const last = cfg.config?.last_selected_pattern
    activePatternId.value = (last && f.pattern_ids.includes(last))
      ? last : (f.pattern_ids[0] ?? null)
    clearDetailCard()
    symbolQuery.value = ''
    initVisiblePatterns(f.pattern_ids)
    // Task 9 · Working Copy:切数据源清空(不跨 scan 复用) + 扫描本 scan 的休眠草稿(不自动激活)
    workingCopy.value = {}
    _scanDormantDrafts()
  }
  function clearScanFile() {
    scanFile.value = null
    currentScanName.value = null
    // annotate、compare 和现算的 app 下打开的图与扫描无关,不跟着清
    if (mode.value === 'app' && appSource.value === 'scan') {
      symbol.value = null
      mode.value = 'annotate'
    }
    activePatternId.value = null
    sortByPid.value = null
    nodeVisible.value = {}
    clearFocus()
    manualExpandedNodes.value = new Set()   // 切数据源清空展开集
    hoveredEventId.value = null
    preview.value = null
    previewError.value = null
    visiblePatterns.value = new Set()
    symbolQuery.value = ''
    clearDetailCard()
    // Task 9 · Working Copy
    workingCopy.value = {}
    dormantDrafts.value = []
  }
  function setCurrentScanName(name: string | null) {
    currentScanName.value = name
  }
  /** 换图时清掉上一张图上的焦点、展开、预览与候选。 */
  function resetChartState() {
    clearFocus()
    manualExpandedNodes.value = new Set()   // 切数据源清空展开集
    hoveredEventId.value = null
    preview.value = null
    previewError.value = null
    clearDetailCard()
  }
  function selectSymbol(s: string) {
    // 锚-active 解耦:只切股、不动 activePatternId
    // 从扫描列表选股 = 看这只股票的扫描结果
    mode.value = 'app'
    appSource.value = 'scan'
    symbol.value = s
    resetChartState()
    if (previewEnabled.value) void runPreview()
  }
  /** 按代码打开(顶栏 symbol、rally、random,pattern 页的样本卡,链接):不动扫描与 activePatternId。
   *  落点:在 compare 下换图留在 compare(决策票 01:换图不退出 compare),别的模式落在 annotate;
   *  链接跟完一律回到 annotate(stores/directLinks.ts)。
   *  win 给了就让图停在那段上,不给按默认缩放。代码是否存在由调用方先核过。 */
  function openSymbol(s: string, win: ViewWindow | null = null) {
    if (mode.value !== 'compare') mode.value = 'annotate'
    symbol.value = s
    viewWindow.value = win ? { start: win.start, end: win.end } : null
    resetChartState()
  }
  /** 切到 annotate、图不换(直达链接没跟成时落在这里,提示条在 annotate 下);已在 annotate 就什么都不做。 */
  function enterAnnotate() {
    if (mode.value === 'annotate') return
    mode.value = 'annotate'
    resetChartState()
  }
  /** 顶栏切到 compare 或 app:图不换,app 产物取当前 pattern 的 app 现算的输出(linkedRun,stores/appLink.ts 负责跑)。
   *  能不能切由调用方先核过(当前 pattern 有能用的 mapping、已经打开了一只股票)。 */
  function enterLinked(m: 'compare' | 'app') {
    if (mode.value === m && appSource.value === 'linked') return
    mode.value = m
    appSource.value = 'linked'
    resetChartState()
  }
  function setLinkedRun(run: LinkedRun | null) { linkedRun.value = run }
  function setActivePattern(pid: string) {
    activePatternId.value = pid
    useConfigStore().saveLastPattern(pid)
    clearFocus()
    manualExpandedNodes.value = new Set()   // 切数据源清空展开集
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
  function toggleField(f: FieldKey) {
    const s = new Set(visibleFields.value)
    if (s.has(f)) s.delete(f); else s.add(f)
    visibleFields.value = s
    saveFieldsToLS(visibleFields.value)
  }
  function isColumnVisible(pid: string, field: FieldKey): boolean {
    return visiblePatterns.value.has(pid) && visibleFields.value.has(field)
  }
  const effectiveSortKey = computed<string | null>(() => {
    const k = sortByPid.value
    if (k == null || k === SYMBOL_SORT_KEY) return k
    const m = k.match(/^(.+)_(num|fr|fd)$/)
    if (!m) return SYMBOL_SORT_KEY
    return isColumnVisible(m[1], m[2] as FieldKey) ? k : SYMBOL_SORT_KEY
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

  // ── 选中要用的几样查表(spec 5.8「同一天的几次 hit」与显示栏) ─────────────────────────────
  // event / hit 按编号查、hit 的先后、一次 hit 绑定的全部 event、一个 event 被哪些 hit 用到(render/walk.ts)。
  // 选中的 hit / event、当前日放在 focusedHitId / focusedInstanceId / selectedInstanceId / currentDay,
  // 由下文的 applyPath 统一写入,渲染层读它们。
  const byIdMap = computed(() => new Map((effectiveAnalysis.value?.events ?? []).map(e => [e.instance_id, e])))
  const hitsById = computed(() => new Map((effectiveAnalysis.value?.hits ?? []).map(h => [h.hit_id, h])))
  const hitOrder = computed(() => hitOrderOf(effectiveAnalysis.value?.hits ?? []))
  // 每次 hit 绑定的全部 event(落点规则比「像不像」用),按需算、跟着结果换
  const boundCache = computed(() => {
    void hitsById.value
    void byIdMap.value
    return new Map<string, ReadonlySet<string>>()
  })
  function bound(hitId: string): ReadonlySet<string> {
    const cache = boundCache.value
    let b = cache.get(hitId)
    if (!b) {
      const m = hitsById.value.get(hitId)
      b = m ? boundEvents(m, byIdMap.value) : new Set<string>()
      cache.set(hitId, b)
    }
    return b
  }

  const usingOf = computed(() => usingIndex(effectiveAnalysis.value?.hits ?? [], effectiveAnalysis.value?.events ?? []))

  // ── 选中:一条路径(render/select.ts),最外一节 → 当前那一节 ──────────────────────────────
  // 样本、框、反馈在别的 store 里,由它们登记进来(循环依赖,view 不能反过来 import):
  // - samples / boxes:这张图上的样本、框,带那天在场的 hit(配对的排第一);
  // - feedbacks:这张图上当前 pattern 的反馈(已排好序);
  // - onAnchor:按键走到另一个样本 / 框时要做的事(等于点它)。
  interface SelSources {
    samples?: () => AnchorRow[]
    boxes?: () => AnchorRow[]
    feedbacks?: () => { id: string; start: string; end: string; family_start?: string | null }[]
    onAnchor?: (s: Sel) => void
    /** 显示栏 / 选中卡 / 复制行要的名字:band 对到的特征名、反馈、样本、框 */
    featureOfBand?: SnapCtx['featureOfBand']
    feedbackOf?: SnapCtx['feedbackOf']
    sampleOf?: SnapCtx['sampleOf']
    boxOf?: SnapCtx['boxOf']
  }
  const selSources = shallowRef<SelSources>({})
  function setSelSources(part: SelSources): void { selSources.value = { ...selSources.value, ...part } }

  const selPath = shallowRef<SelPath>([])
  /** 每走一步(← / →、↑ / ↓)加一:反馈面板据此判断要不要关(stores/feedback.ts) */
  const moveSeq = ref(0)

  /** 一条 band 上画出来的族:和图上同一套显隐、档位筛选。 */
  function bandFamiliesOf(band: string): Family[] {
    const events = effectiveAnalysis.value?.events ?? []
    const topoNodes = effectivePattern.value?.topology.nodes ?? []
    const node = tagMap.value.tagToNodes[band]?.[0] ?? band
    const spec = topoNodes.find(n => n.node_id === node)
    if (!isBandVisible(band, nodeVisible.value, tagMap.value.tagToNodes)) return []
    return foldBand(events.filter(e => bandKeyOf(e) === band),
      { band, isPoint: spec?.is_point === true, tierOf: eventTier, level: level.value, levelImmune: spec?.solve === false })
  }

  // 一条 band 一个 computed:换档位、显隐、结果变了各自失效(放进 worldCtx 里的普通缓存不会跟着失效)
  const bandFamilyCache = new Map<string, ComputedRef<Family[]>>()
  function bandFamiliesCached(band: string): Family[] {
    let c = bandFamilyCache.get(band)
    if (!c) { c = computed(() => bandFamiliesOf(band)); bandFamilyCache.set(band, c) }
    return c.value
  }

  const worldCtx = computed<WorldCtx>(() => {
    const hits = effectiveAnalysis.value?.hits ?? []
    const events = effectiveAnalysis.value?.events ?? []
    const src = selSources.value
    return {
      hits, hitsById: hitsById.value, byId: byIdMap.value, endNode: endNode.value, hitOrder: hitOrder.value,
      using: usingOf.value, bound, bandOf: bandKeyOf,
      bandFamilies: bandFamiliesCached,
      feedbacks: (src.feedbacks?.() ?? []).map(f => ({
        id: f.id, hitIds: feedbackHits(hits, events, endNode.value, barDates.value, f).map(m => m.hit_id) })),
      samples: src.samples?.() ?? [],
      boxes: src.boxes?.() ?? [],
      lineDay: currentDay.value,
    }
  })
  const world = computed(() => makeWorld(worldCtx.value))

  function expandNodeOf(instanceId: string): void {
    const ev = byIdMap.value.get(instanceId)
    if (!ev) return
    const node = nodeOfEventByBand(ev, tagMap.value.tagToNodes, tagMap.value.tagList)
    if (node && !manualExpandedNodes.value.has(node)) {
      const s = new Set(manualExpandedNodes.value)
      s.add(node)
      manualExpandedNodes.value = s
    }
  }

  /**
   * 换成这条路径,并把它落到渲染层读的那几个量上:
   * - 最后一节是一次 hit(或只有一次 hit 的买点日)→ 选中这次 hit;路径上有 event 时它是实例焦点(不展 trace);
   * - 最后一节是 event → 只选中这个 event;
   * - 其余(一族、买点日、node、反馈、样本、框)→ 不选中任何 hit / event(图上靠路径画「在用」与细框)。
   * 当前日竖线落在最后一节自己的日子上;它不带日子(一族、反馈、node)时竖线不动。
   */
  function applyPath(path: SelPath): void {
    selPath.value = path
    const last = path[path.length - 1]
    const merged = last ? mergedHit(path, world.value) : null
    const hitSel = last?.kind === 'hit' ? last : merged?.sel.kind === 'hit' ? merged.sel : null
    if (hitSel) {
      const anc = [...path].reverse().find((s): s is Extract<Sel, { kind: 'event' }> => s.kind === 'event')
      focusedHitId.value = hitSel.hitId
      selectedInstanceId.value = null
      focusedInstanceId.value = anc?.instanceId ?? null
      if (anc) expandNodeOf(anc.instanceId)
      else manualExpandedNodes.value = new Set()   // 只选 hit:trace 独占视野
    } else {
      focusedHitId.value = null
      focusedInstanceId.value = null
      selectedInstanceId.value = last?.kind === 'event' ? last.instanceId : null
      if (last?.kind === 'event') expandNodeOf(last.instanceId)
    }
    const day = last ? lineDayOf(last, worldCtx.value) : null
    if (day !== null) currentDay.value = day
  }

  /** 外面直接给一条路径(compare 的样本、框、diagnose 的卡片;轨名)。 */
  function setPath(path: SelPath): void { applyPath(path) }

  const familySel = (familyKey: string): Sel => ({ kind: 'hit_family', familyKey })

  /** 点 hits 行的 ▼:选中这一天整体(那一族的这个买点日);这天只有一次 hit 时就是那次 hit。 */
  function clickBuyDay(familyKey: string, day: number): void {
    applyPath([familySel(familyKey), { kind: 'buy', day }])
    currentDay.value = day
  }

  /**
   * 点 hits 行的格:这一列有 ▼(buyDay)时和点 ▼ 一样,选中这一天;没有 ▼(hit 的终点不是买点日)时
   * 选中格里的一次 hit(当前那次在格里就是它,否则和它最像的),竖线落在它的第一个买入日。
   */
  function clickHitCell(familyKey: string, hitIds: readonly string[], buyDay?: number): void {
    if (buyDay !== undefined) { clickBuyDay(familyKey, buyDay); return }
    if (hitIds.length === 0) return
    const cur = focusedHitId.value
    const cands = hitIds.map(id => ({ hitId: id, instanceId: null }))
    const pick = cands[landIndex(cands, cur ? { hitId: cur, instanceId: null } : null, bound)].hitId
    const m = hitsById.value.get(pick)
    if (!m) return
    const day = hitDays(m, byIdMap.value, endNode.value)[0]
    applyPath([familySel(familyKey), { kind: 'buy', day }, { kind: 'hit', hitId: pick, day }])
  }

  /** 点 hits 行的族底线:选中整族(不选其中哪一天、哪一次),竖线留在原处。选着这一族里的东西时点它就退回整族。 */
  function clickFamilyLine(familyKey: string): void {
    applyPath([familySel(familyKey)])
  }

  /**
   * 点 band 上的东西(格、整条、点;记号上可能并着几个成员),侧栏的 trace 行、候选表行也走这里:选中其中一个 event
   * (当前选中的就在里面时不换,否则第一个),它属于它那条 band;竖线落在它的终点。
   */
  function focusMark(memberIds: string[]): void {
    if (memberIds.length === 0) return
    const last = selPath.value[selPath.value.length - 1]
    const keep = last?.kind === 'event' && memberIds.includes(last.instanceId) ? last.instanceId : null
    const id = keep ?? memberIds[0]
    const ev = byIdMap.value.get(id)
    applyPath(ev ? [{ kind: 'node', band: bandKeyOf(ev) }, { kind: 'event', instanceId: id }]
      : [{ kind: 'event', instanceId: id }])
  }

  /** 一个实例(侧栏 trace 行、候选表行):同点 band 上的它。 */
  function focusEvent(instanceId: string): void {
    focusMark([instanceId])
  }

  /** 选中一次 hit(app 侧栏 hits 列表点行):它属于它那一族的一个买点日;竖线落在第一个买入日(给了 day 且它那天也买就落 day)。 */
  function focusHit(hitId: string, opts: { day?: number } = {}): void {
    const m = hitsById.value.get(hitId)
    if (!m) {   // 结果里没有这次 hit(结果还没到):只记下选中
      applyPath([])
      focusedHitId.value = hitId
      currentDay.value = opts.day ?? null
      return
    }
    const days = hitDays(m, byIdMap.value, endNode.value)
    const day = opts.day !== undefined && days.includes(opts.day) ? opts.day : days[0]
    applyPath([familySel(familyKeyOf(HIT_FAMILY_PREFIX, m.start_idx)), { kind: 'buy', day }, { kind: 'hit', hitId, day }])
  }

  /** 点反馈记号:选中这条反馈(它收进来的 hit 画细框),竖线不动。 */
  function clickFeedback(fb: { id: string }): void {
    applyPath([{ kind: 'feedback', id: fb.id }])
  }

  /** 点轨名:选中这条 band(一个 node)。 */
  function selectNode(band: string): void {
    applyPath([{ kind: 'node', band }])
  }

  /**
   * 按一下 ← / →(axis = day)或 ↑ / ↓(axis = stack),照 render/select.ts 的那一个判断走。
   * 走到另一个样本 / 框时通知登记进来的 onAnchor(等于点它)。返回这一下算不算被接下(有选中就算,到头也算)。
   */
  function stepAxis(axis: Axis, dir: -1 | 1): boolean {
    const path = selPath.value
    if (path.length === 0) return false
    const r = step(path, axis, dir, world.value)
    if (!r.moved) return true
    const anchorOf = (p: SelPath) => p.find(s => s.kind === 'sample' || s.kind === 'box') ?? null
    const before = anchorOf(path)
    applyPath(r.path)
    const after = anchorOf(r.path)
    if (after && !sameSel(before, after)) selSources.value.onAnchor?.(after)
    moveSeq.value++
    return true
  }
  function stepPos(dir: -1 | 1): boolean { return stepAxis('day', dir) }
  function stepStack(dir: -1 | 1): boolean { return stepAxis('stack', dir) }

  /** Esc 退一层;退到头清空。没有选中时返回 false(这一下不归它)。 */
  function stepUp(): boolean {
    if (selPath.value.length === 0) return false
    const p = up(selPath.value, world.value)
    if (p.length) applyPath(p)
    else clearFocus()
    return true
  }

  // 结果换了(重跑、换参数):路径上的 hit / event / 一族 / 买点日已经不在新结果里时,从那一节起去掉
  // (不然显示栏写着一个不存在的东西,Shift+C 也会把它复制出去)。结果还没到(null)时不动。
  watch(() => effectiveAnalysis.value, (a) => {
    const path = selPath.value
    if (!a || path.length === 0) return
    const gone = (s: Sel, i: number): boolean =>
      s.kind === 'hit' ? !hitsById.value.has(s.hitId)
        : s.kind === 'event' ? !byIdMap.value.has(s.instanceId)
        : s.kind === 'hit_family' ? world.value.inside(path.slice(0, i + 1), 'day').length === 0
        : s.kind === 'buy' ? world.value.members(path.slice(0, i + 1)).length === 0
        : false
    const i = path.findIndex(gone)
    if (i < 0) return
    if (i === 0) clearFocus()
    else applyPath(path.slice(0, i))
  })

  function setCurrentDay(day: number | null): void { currentDay.value = day }
  function setBarDates(d: string[]): void { barDates.value = d }

  function clearFocus(): void {
    selPath.value = []
    focusedHitId.value = null
    selectedInstanceId.value = null
    focusedInstanceId.value = null
    currentDay.value = null
    clearShiftSelection()
  }

  /** 选中的那一节(路径的最后一节);没有为 null。 */
  const selLast = computed<Sel | null>(() => selPath.value[selPath.value.length - 1] ?? null)

  /** 样本 / 框配对的那一次 hit;配对的 event 没进 hit(或没配上)为 null。 */
  function pairedHitOf(s: Sel): string | null {
    if (s.kind === 'sample') return worldCtx.value.samples.find(r => r.id === s.sampleId)?.pairedHitId ?? null
    if (s.kind === 'box') return worldCtx.value.boxes.find(r => r.id === s.boxId)?.pairedHitId ?? null
    return null
  }

  /** 路径上最外面那一节「牵出的 hit」:一族的、用到那个 event 的、反馈收进来的、样本 / 框配对的那一次(细框、侧栏常标用)。 */
  const selHits = computed<{ ids: ReadonlySet<string>; thin: boolean }>(() => {
    const path = selPath.value
    const none = { ids: new Set<string>(), thin: false }
    for (let i = 0; i < path.length; i++) {
      const s = path[i]
      const sub = path.slice(0, i + 1)
      if (s.kind === 'hit_family') {
        const ids = new Set<string>()
        for (const b of world.value.inside(sub, 'day')) {
          for (const m of world.value.members([...sub, b.sel])) if (m.sel.kind === 'hit') ids.add(m.sel.hitId)
        }
        return { ids, thin: false }
      }
      // event、反馈:只算它们自己牵出的(那个 ▼ 上顺带的别的切法不算)
      if (s.kind === 'event') return { ids: new Set(usingOf.value(s.instanceId).map(m => m.hit_id)), thin: true }
      if (s.kind === 'feedback') {
        return { ids: new Set(worldCtx.value.feedbacks.find(f => f.id === s.id)?.hitIds ?? []), thin: true }
      }
      if (s.kind === 'sample' || s.kind === 'box') {
        // 样本、框:只框配对的那一次(配对的 event 没进 hit 时不框);在场的别的几次要 ↓ 进去才看
        const paired = pairedHitOf(s)
        return { ids: new Set(paired ? [paired] : []), thin: true }
      }
    }
    return none
  })

  /** 选中的是一整天(买点日,且这天不止一次)时,这天叠着的几次 hit;否则为空。 */
  const selDayHitIds = computed<string[]>(() => {
    const last = selLast.value
    if (last?.kind !== 'buy') return []
    return world.value.inside(selPath.value, 'stack').map(m => (m.sel.kind === 'hit' ? m.sel.hitId : ''))
  })

  /** 这个 event 在当前档位、显隐下画没画在它那条 band 上(选中卡的 level 行据此写 hidden)。 */
  function isEventDrawn(instanceId: string): boolean {
    const ev = byIdMap.value.get(instanceId)
    if (!ev) return false
    return bandCells(bandFamiliesCached(bandKeyOf(ev))).some(c => c.members.some(m => m.id === instanceId))
  }
  /** 一次 hit 的全部买点日(结果里没有它为空)。 */
  function buyDaysOfHit(hitId: string): number[] {
    const m = hitsById.value.get(hitId)
    return m ? hitDays(m, byIdMap.value, endNode.value) : []
  }

  /** 显示栏、选中卡、Shift+C 复制共用的那一份(render/selSnapshot.ts);什么都没选为 null。 */
  const selInfo = computed<Snapshot | null>(() => {
    const path = selPath.value
    if (path.length === 0) return null
    const topo = effectivePattern.value?.topology
    const src = selSources.value
    return selSnapshotOf(path, {
      dates: barDates.value, wctx: worldCtx.value, world: world.value,
      nodeOrder: (topo?.nodes ?? []).map(n => n.node_id),
      anchorFields: [...new Set((topo?.edges ?? []).map(e => e.anchor_field).filter((f): f is string => !!f))],
      featureOfBand: src.featureOfBand ?? (() => null),
      feedbackOf: src.feedbackOf ?? (() => null),
      sampleOf: src.sampleOf ?? (() => null),
      boxOf: src.boxOf ?? (() => null),
    })
  })

  function setLevel(l: Level) { level.value = l; saveLevelToLS(l) }
  function hoverEvent(id: string | null) { hoveredEventId.value = id }

  // ── 入口 A(brush)+ 入口 D(shift+click)query actions(Task 18) ──────────────
  function setShiftSelectedEvents(next: ShiftSelectedEvent[]) {
    shiftSelectedEvents.value = next
  }
  function clearShiftSelection(): void {
    shiftSelectedEvents.value = []
  }
  const shiftPairPending = computed<boolean>(() => shiftSelectedEvents.value.length === 1)
  const shiftSelectedEventIds = computed<ReadonlySet<string>>(
    () => new Set(shiftSelectedEvents.value.map(e => e.instance_id))
  )
  /** 清掉当前展示的 time/pair/candidate 查询卡片(DetailSidebar 关闭按钮 · undo-swap · 切股/切
   * pattern 防陈旧残留)。loadScanFile/clearScanFile/selectSymbol/setActivePattern 4 处 reset
   * 均经此单一入口(承 Task 18 前例)。*/
  function clearDetailCard() {
    activeDetailCard.value = null
    timeScopeResponse.value = null
    pairScopeResponse.value = null
    shiftSelectedEvents.value = []
    currentDiagnoseNode.value = ''
    // v2 D9 · 同步清 debug state · abort 挂起的 debug fetch
    if (debugAbortRef) {
      debugAbortRef.abort()
      debugAbortRef = null
    }
    debugTarget.value = null
    debugPending.value = false
    debugError.value = null
  }
  // 入口 A 请求恒不带 node 过滤(过滤是纯前端显示层,重新请求会让后端
  // node 过滤返回子集 → failedNodes 坍缩 → 下拉其他 node 置灰)。
  async function triggerTimeQuery(startBar: number, endBar: number): Promise<void> {
    const w = appWindowOf()
    if (!symbol.value || !appId.value || !w) return
    try {
      timeScopeResponse.value = await getTimeDiagnose(
        appId.value, symbol.value, w.start, w.end, startBar, endBar,
        undefined, 'gate',   // ★ v3 · 入口 A 硬编码 anchorKind='gate'
        appParamsOverride.value)   // Task 9 · 三环节一致性:探索态透传 WC
      activeDetailCard.value = 'time'
    } catch { timeScopeResponse.value = null }
  }
  async function triggerPairQuery(srcInstanceId: string, dstInstanceId: string): Promise<void> {
    const w = appWindowOf()
    if (!symbol.value || !appId.value || !w) return
    try {
      pairScopeResponse.value = await getPairDiagnose(
        appId.value, symbol.value, w.start, w.end, srcInstanceId, dstInstanceId,
        appParamsOverride.value)   // Task 9 · 三环节一致性:探索态透传 WC
      activeDetailCard.value = 'pair'
    } catch { pairScopeResponse.value = null }
  }

  // v2 event-debug(2026-07-15) · marker 右键 → 精准断点触发
  // spec: docs/research/2026-07-15_event-debug-dual-emit-multi-anchor/final_report.md
  async function triggerEventDebug(
    instanceId: string, anchorKey: 'entry' | 'start' | 'end' | 'confirm'
  ): Promise<void> {
    const w = appWindowOf()
    if (!symbol.value || !appId.value || !w) return
    const pid = appId.value
    const events = effectiveAnalysis.value?.events ?? []
    // 实例化契约:参数承载 instance_id;anchorsOf 键按 node_id 反查(debug_enabled 亦按 node)
    const event = events.find(e => e.instance_id === instanceId)
    if (!event) return
    const anchorFn = anchorsOf[event.node_id] ?? anchorsOf._default
    const anchors = anchorFn(event, events)
    const anchor = anchors.find(a => a.key === anchorKey)
    if (!anchor || anchor.disabled) return
    // 单槽位覆盖: abort 旧 controller
    if (debugAbortRef) debugAbortRef.abort()
    const controller = new AbortController()
    debugAbortRef = controller
    debugError.value = null   // 清上一次错误 · 防混叠
    debugTarget.value = {
      instanceId, bar: anchor.bar, node_id: event.node_id, anchor: anchor.key,
    }
    debugPending.value = true
    activeDetailCard.value = 'debug'
    try {
      await getTimeDiagnose(
        pid, symbol.value, w.start, w.end,
        anchor.bar, anchor.bar, controller.signal,
        anchor.key,                                       // ★ v3 · anchor.key 直接透传为 anchorKind
        appParamsOverride.value,                           // Task 9 · 三环节一致性:探索态透传 WC
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
  // Task 9 · setPreviewEnabled 兼容层:委托给 setWorkingCopyEnabled(有 pid 守卫)。
  async function setPreviewEnabled(v: boolean): Promise<void> {
    if (activePatternId.value) setWorkingCopyEnabled(activePatternId.value, v)
  }

  async function runPreview(): Promise<void> {
    if (annotating.value || linkedView.value) return   // annotate、compare 与现算的 app 不跑扫描的探索态预览
    if (!scanFile.value || !symbol.value || !activePatternId.value) return
    // Task 9 · 探索态才跑 preview(浏览态锚 snapshot,无需临时计算)
    if (!workingCopy.value[activePatternId.value!]?.enabled) return
    previewLoading.value = true
    previewError.value = null
    const reqSymbol = symbol.value
    const reqPid = activePatternId.value
    const reqEnabled = previewEnabled.value
    try {
      const baseScan = scanFile.value.scan
      const labelHorizon = baseScan.label_horizon ?? 20
      // Task 9 · 恒传 WC(探索态才可能非 undefined;runPreview 已被上面守卫限定只在探索态执行)
      const ov = workingCopy.value[reqPid]?.enabled ? workingCopy.value[reqPid]!.currentDict : undefined
      const resp = await getPreview(reqPid, reqSymbol,
                                     baseScan.start_date, baseScan.end_date, labelHorizon, ov)
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

  // diag 预取 watch:图上画的那个 app(appId)在同一区间上的诊断;qualified 档靠它判
  watch([symbol, scanFile, appId, linkedRun, preview, previewEnabled], async () => {
    if (!symbol.value || !appId.value) {
      diag.value = null
      return
    }
    const reqSymbol = symbol.value
    const reqPid = appId.value
    try {
      const w = appWindowOf()!
      const d = await getDiagnose(reqPid, symbol.value, w.start, w.end,
                                   appParamsOverride.value)   // Task 9 · 三环节一致性:探索态透传 WC
      if (symbol.value !== reqSymbol || appId.value !== reqPid) return
      diag.value = d
    } catch { if (symbol.value === reqSymbol && appId.value === reqPid) diag.value = null }
  }, { immediate: true })

  // spec §3.1 派生:导出符号保持,内部从 focusedHitId + 实例焦点(selected/focusedInstanceId)派生。
  // selected 从 ref → computed(渲染层零改动 · storeToRefs 拿到的仍是 reactive)。
  const selected = computed<Selected>(() =>
    focusedHitId.value ? { kind: 'hit' as const, hitId: focusedHitId.value } : null)

  const selectedHitId = computed<string | null>(() => focusedHitId.value)
  // 当前聚焦实例(instance_id)的合并引用:selectedInstanceId(0 归属·只聚焦)与
  // focusedInstanceId(1 归属·直选)互斥,合并即「当前聚焦实例」。取代旧的事件级焦点派生。
  const focusedInstanceRef = computed<string | null>(() => selectedInstanceId.value ?? focusedInstanceId.value)

  const selectedHit = computed<HitDict | null>(() => {
    if (!focusedHitId.value || !effectiveAnalysis.value) return null
    return effectiveAnalysis.value.hits.find(m => m.hit_id === focusedHitId.value) ?? null
  })

  // 视觉层:选中一次 hit → 它绑定的 event 亮成一组。选中的不是某一次 hit 时,和它有关的那几次的组成也亮出来
  // (它们不算选中,要进到那一次才是):选中一整天 → 这天叠着的几次;选中样本 / 框 → 配对的那一次。
  // event、反馈牵出的 hit 由 candidateHitIds 画细实线框,不进这里。
  const highlightedEventIds = computed<ReadonlySet<string>>(() => {
    const m = selectedHit.value
    const last = selLast.value
    const related = m ? [m]
      : last?.kind === 'buy' ? selDayHitIds.value.map(id => hitsById.value.get(id)).filter((x): x is HitDict => !!x)
      : last?.kind === 'sample' || last?.kind === 'box'
        ? [hitsById.value.get(pairedHitOf(last) ?? '')].filter((x): x is HitDict => !!x)
        : []
    if (related.length === 0) return new Set<string>()
    return inHitIdsOf(
      related,
      effectiveAnalysis.value?.events ?? [],
      effectivePattern.value?.topology.edges ?? [],
      { expandAnchor: false },
    )
  })

  // hit trace 展开的唯一判据(spec §3.1):有 hit 且无实例焦点(任一实例 ref 为空)才展 trace
  const showTrace = computed<boolean>(() =>
    focusedHitId.value !== null && selectedInstanceId.value === null && focusedInstanceId.value === null)

  // 组成型组「一选全选」:选中的是一个 event(不是某一次 hit)时,它若是组成型容器或其任一段 →
  // 整组(容器+全部段)进视觉选中集,与 hit 组高亮同款 group 边框(选中的那个仍由 focus
  // 条目独家表达,chart group 分支按 focusedInstanceRef 排除)。选中一次 hit 时
  // selectedInstanceId=null → 空集,由 hit 的 inHitIds 闭包覆盖。组成型判别 = topology.nodes[].produced_by 非空
  // (bo→burst 是引用型,公共资源,不在此列)。
  const compositionGroupIds = computed<ReadonlySet<string>>(() => {
    const iid = selectedInstanceId.value
    if (!iid) return new Set()
    const topoNodes = effectivePattern.value?.topology.nodes ?? []
    const structural = topoNodes.filter(n => n.produced_by != null)
    if (structural.length === 0) return new Set()
    const structuralNodes = new Set(structural.map(n => n.node_id))
    const events = effectiveAnalysis.value?.events ?? []
    const ev = events.find(e => e.instance_id === iid)
    if (!ev) return new Set()
    // 组代表容器:点段 → 经 child_refs 逆索引爬到容器(组成段专属单容器);
    // 点容器 → 须持有组成型子槽(某 structural node 的 parent_refs 引用它),
    // 否则(孤立 bo/burst 等引用型/无关 node)空集,维持单点聚焦不变。
    let container = ev
    if (structuralNodes.has(ev.node_id)) {
      const parent = events.find(e =>
        Object.values(e.child_refs ?? {}).some(ids =>
          Array.isArray(ids) && ids.includes(iid)))
      if (!parent) return new Set([iid])   // 孤段(组成型不应出现,防御回落单点)
      container = parent
    } else {
      const hasCompSlot = structural.some(n =>
        (n.parent_refs ?? []).some(([p]) => p === ev.node_id))
      if (!hasCompSlot) return new Set()
    }
    const out = new Set<string>([container.instance_id])
    for (const ids of Object.values(container.child_refs ?? {})) {
      if (Array.isArray(ids)) for (const id of ids) out.add(id)
    }
    return out
  })

  // 漏斗展开集合:单 source = manualExpandedNodes。手动/自动分层写入:
  //   toggleExpandedNode (sidebar 漏斗行 / topology dblclick) = add/remove(不折叠其他)
  //   focusEvent (marker click) = add 焦点 node(不折叠其他)
  //   focusHit (bracket click) = 清空(trace 独占)
  const expandedNodeIds = computed<ReadonlySet<string>>(() => manualExpandedNodes.value)

  // 图上的细框:路径上最外一节是 event、反馈、样本或框时,它牵出的每次 hit 的格加细框(一族靠粗底线认,不加框)。
  const candidateHitIds = computed<ReadonlySet<string>>(() => (selHits.value.thin ? selHits.value.ids : new Set<string>()))

  // 从一个 event 走进它的买点日、停在整天上时:那个 event 不是选中的那一个,但还在用,单独描边
  const pendingDisambigInstanceId = computed<string | null>(() => {
    if (focusedHitId.value || selLast.value?.kind !== 'buy') return null
    const anc = selPath.value.find((x): x is Extract<Sel, { kind: 'event' }> => x.kind === 'event')
    return anc?.instanceId ?? null
  })

  // 侧栏 hits 列表常标的行:路径上最外一节牵出的 hit,加上选中的那次、选中那一天的几次
  const markedHitIds = computed<ReadonlySet<string>>(() => {
    const out = new Set<string>(selHits.value.ids)
    for (const id of selDayHitIds.value) out.add(id)
    if (focusedHitId.value) out.add(focusedHitId.value)
    return out
  })

  // sidebar 候选表"选中"样式判据(spec §3.1 信息层):
  //   实例 focus → {selectedInstanceId ?? focusedInstanceId}
  //   停在整天上、是从一个 event 走进来的 → {它}
  //   都空 → 空集
  const markedEventIds = computed<ReadonlySet<string>>(() => {
    const iid = selectedInstanceId.value ?? focusedInstanceId.value
    if (iid) return new Set([iid])
    if (pendingDisambigInstanceId.value) return new Set([pendingDisambigInstanceId.value])
    return new Set()
  })

  const tagMap = computed(() => effectivePattern.value
    ? deriveTagMap(effectivePattern.value.topology.nodes)
    : { tagToNodes: {} as Record<string, string[]>, tagList: [] as string[] })

  const isolated = computed<Set<string>>(() => effectivePattern.value
    ? isolatedNodeIds(effectivePattern.value.topology) : new Set())

  const inHitIds = computed<Set<string>>(() => inHitIdsOf(
    effectiveAnalysis.value?.hits ?? [], effectiveAnalysis.value?.events ?? [],
    effectivePattern.value?.topology.edges ?? []))

  // 实例化契约下 inHitEventIds ≡ inHitIds(集合元素即 instance_id;身份级判定已消灭,
  // 消费方如 diag AttrRow 按 row.instance_id 判档)。保留导出名避免 Task 10 消费点空引用。
  const inHitEventIds = computed<Set<string>>(() => new Set(inHitIds.value))

  const qualifiedIds = computed<Set<string>>(() => qualifiedIdsOf(diag.value))

  // 给渲染层的当家行键(族行底线加粗):路径上有 hit 的一族时是那一族;最外一节是样本时是样本那一行。
  // event、反馈、框不对应现成的一行,不加粗任何一行(它们牵出的 hit 靠细框认)。
  const activeFamilyKey = computed<string | null>(() => {
    const path = selPath.value
    const fam = path.find((x): x is Extract<Sel, { kind: 'hit_family' }> => x.kind === 'hit_family')
    if (fam) return fam.familyKey
    return path[0]?.kind === 'sample' ? SAMPLES_ROW_KEY : null
  })

  function bandKey(e: EventDict): string { return bandKeyOf(e) }
  function eventTier(e: EventDict): Tier { return eventTierOf(e, inHitIds.value, qualifiedIds.value) }

  return {
    scanFile, symbol, activePatternId, sortByPid, sortDesc,
    nodeVisible, selected,
    focusedHitId, selectedInstanceId, focusedInstanceId, manualExpandedNodes,  // 内部 ref(export 便于 whitebox 单元测)
    level, focusedInstanceRef, highlightedEventIds, candidateHitIds, pendingDisambigInstanceId, hoveredEventId, diag,
    showTrace, expandedNodeIds, markedHitIds, markedEventIds, // 派生 computed export
    compositionGroupIds,   // 组成型组「一选全选」(0 归属非 hit 组)
    shiftSelectedEvents, activeDetailCard, timeScopeResponse, pairScopeResponse,
    shiftPairPending, shiftSelectedEventIds,
    previewEnabled, preview, previewLoading, previewError,
    // Task 9 · Working Copy 探索态状态机(Task 10-13 消费)
    workingCopy, dormantDrafts, snapshotOf, effectiveParamsOverride, isExploring,
    forkWorkingCopy, ensureWorkingCopy, setWorkingCopyEnabled, updateWorkingCopy, resetWorkingCopy,
    discardWorkingCopy, restoreDormant, wcDirty,
    // Task 12 · 全局 toast
    toastMsg, showToast,
    patternIds, currentPerStock, pattern, currentAnalysis,
    visiblePatterns, visibleFields, symbolQuery,
    effectivePattern, effectiveAnalysis, effectiveScan,
    unionRows, sortedRows, filteredSortedRows, previewListRow, patternHitStocks,
    nodeColors, selectedHitId, selectedHit, tagMap, isolated, inHitIds, inHitEventIds, qualifiedIds,
    mode, annotating, comparing, appSource, linkedView, linkedRun, appId, endNode, appWindowOf,
    openSymbol, enterAnnotate, enterLinked, setLinkedRun, viewWindow,
    loadScanFile, clearScanFile, setCurrentScanName, currentScanName, selectSymbol, setActivePattern, setSort,
    toggleNode, toggleExpandedNode,
    focusHit, focusEvent, clearFocus,
    focusMark, clickBuyDay, clickHitCell, clickFamilyLine, clickFeedback, selectNode, setPath, setSelSources,
    stepPos, stepStack, stepUp, setCurrentDay, setBarDates,
    currentDay, activeFamilyKey, barDates, selPath, selLast, selInfo, selHits, selDayHitIds, world, moveSeq,
    isEventDrawn, buyDaysOfHit,
    setLevel, hoverEvent,
    setShiftSelectedEvents, clearShiftSelection, clearDetailCard, triggerTimeQuery, triggerPairQuery,
    // v2 event-debug(2026-07-15)
    debugPending, debugTarget, debugError, triggerEventDebug, cancelDebug,
    currentDiagnoseNode,
    setPreviewEnabled, runPreview, clearPreview,
    initVisiblePatterns, togglePattern, setPatternsAllOn, setPatternsAllOff, invertPatterns,
    setSymbolQuery, clearSymbolQuery,
    toggleField, isColumnVisible, effectiveSortKey,
    bandKey, eventTier,
  }
})

// HMR 热替换 store 实例(pinia 官方样板):不配时 Vue SFC 的 accept 边界会吞掉
// 整页 reload,store 实例留存旧模块闭包——改本文件后出现「模块级 import(如
// anchorsOf)是新、store action 是旧」的半更新(2026-08-17 实证:新锚点菜单项
// 点击毫无反应,find(key) 落在旧表静默 return)。
if (import.meta.hot) {
  import.meta.hot.accept(acceptHMRUpdate(useViewStore, import.meta.hot))
}
