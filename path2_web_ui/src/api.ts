import type {
  SerializedPattern, MultiScanResultFile, Ohlc, Diagnostics, AppConfig,
  ScanProgress, ScanDone, ScanHistoryEntry, Analysis, ScanMeta, NodesScopeResponse,
  TimeScopeResponse, PairScopeResponse, ParamsDiffResp,
} from './types'
// Task 10 · ParamsChip(及 Task 11 抽屉)按 `from '../api'` 消费 diff 响应类型,故随 getParamsDiff 一并重导出。
export type { ParamsDiffResp }

const BASE = (import.meta as any).env?.VITE_API_BASE ?? 'http://localhost:8000'

async function getJson<T>(path: string): Promise<T> {
  const r = await fetch(`${BASE}${path}`)
  if (!r.ok) throw new Error(`GET ${path} → ${r.status}: ${await r.text()}`)
  return r.json() as Promise<T>
}

// Task 8:统一 params_override query 拼接 helper。有值才拼(不回归既有无 override 调用点的 URL)。
function ovQuery(o?: Record<string, any>): string {
  return o ? `&params_override=${encodeURIComponent(JSON.stringify(o))}` : ''
}

export function getPatterns(): Promise<SerializedPattern[]> {
  return getJson('/patterns')
}
export function getOhlc(symbol: string, start: string, end: string): Promise<Ohlc> {
  return getJson(`/ohlc?symbol=${encodeURIComponent(symbol)}&start=${start}&end=${end}`)
}
export function listScans(): Promise<ScanHistoryEntry[]> {
  return getJson('/scans/')
}
export function loadScan(name: string): Promise<MultiScanResultFile> {
  return getJson(`/scans/${encodeURIComponent(name)}`)
}
export function deleteScan(name: string): Promise<{ok: true}> {
  return fetch(`${BASE}/scans/${encodeURIComponent(name)}`, { method: 'DELETE' })
    .then(r => r.ok ? r.json() : Promise.reject(new Error(`HTTP ${r.status}`)))
}
export function renameScan(oldName: string, newName: string): Promise<{name: string}> {
  return fetch(`${BASE}/scans/${encodeURIComponent(oldName)}/rename`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name: newName }),
  }).then(r => r.ok ? r.json() : Promise.reject(new Error(`HTTP ${r.status}`)))
}
export function cancelScan(scanId: string, save: boolean = false): Promise<{ok: true}> {
  const url = `${BASE}/scan/${scanId}/cancel?save=${save}`
  const ok = navigator.sendBeacon(url)
  return ok ? Promise.resolve({ok: true})
            : Promise.reject(new Error('sendBeacon enqueue failed'))
}
export function getDiagnose(
  patternId: string, symbol: string, start: string, end: string,
  paramsOverride?: Record<string, any>,          // ★ Task 8 · Working Copy 参数覆盖透传
): Promise<Diagnostics> {
  return getJson(
    `/diagnose?pattern_id=${patternId}&symbol=${encodeURIComponent(symbol)}&start=${start}&end=${end}`
    + ovQuery(paramsOverride))
}
// 入口 B(拓扑面板降级):点 edge → scope=nodes,只拿这条 node 边的 miss_reasons 分布 +
// example_failed_pairs 样例(≤5),不重取整包 per-node 诊断。legacy getDiagnose 不受影响。
export function getNodesDiagnose(
  patternId: string, symbol: string, start: string, end: string, srcNode: string, dstNode: string,
  paramsOverride?: Record<string, any>,          // ★ Task 8 · Working Copy 参数覆盖透传
): Promise<NodesScopeResponse> {
  return getJson(
    `/diagnose?pattern_id=${encodeURIComponent(patternId)}&symbol=${encodeURIComponent(symbol)}`
    + `&start=${start}&end=${end}&scope=nodes`
    + `&src_node=${encodeURIComponent(srcNode)}&dst_node=${encodeURIComponent(dstNode)}`
    + ovQuery(paramsOverride))
}
// 入口 A(KlineChart 主图 brush 框选):scope=time,拿 [start_bar,end_bar] 框内(严格 ⊆)的
// gate 失败样例(GateFailure)。
export function getTimeDiagnose(
  patternId: string, symbol: string, start: string, end: string,
  startBar: number, endBar: number,
  signal?: AbortSignal,
  anchorKind?: string,                  // ★ v3 · anchor_kind 门限透传
  paramsOverride?: Record<string, any>, // ★ Task 8 · Working Copy 参数覆盖透传
): Promise<TimeScopeResponse> {
  const url = `${BASE}/diagnose?pattern_id=${encodeURIComponent(patternId)}&symbol=${encodeURIComponent(symbol)}`
    + `&start=${start}&end=${end}&scope=time`
    + `&start_bar=${startBar}&end_bar=${endBar}`
    + (anchorKind ? `&anchor_kind=${encodeURIComponent(anchorKind)}` : '')   // ★ v3 · 空串也 skip · 与后端 handler `if anchor_kind:` 判据对齐
    + ovQuery(paramsOverride)
  return fetch(url, { signal }).then(async r => {
    if (!r.ok) throw new Error(`GET ${url} → ${r.status}: ${await r.text()}`)
    return r.json() as Promise<TimeScopeResponse>
  })
}
// 入口 D(KlineChart shift+click 跨图累积):scope=pair,两 marker 的 instance_id
// 查两 node 间是否有直连 edge · 若有则 4 通道 subcheck 短路(auto swap 见 PairPayload.applied_swap)。
// ★ wire 契约:后端 query 参数名沿用旧名(值已是 instance_id),TS 参数名按语义改为 instanceId。
export function getPairDiagnose(
  patternId: string, symbol: string, start: string, end: string,
  srcInstanceId: string, dstInstanceId: string,
  paramsOverride?: Record<string, any>,          // ★ Task 8 · Working Copy 参数覆盖透传
): Promise<PairScopeResponse> {
  return getJson(
    `/diagnose?pattern_id=${encodeURIComponent(patternId)}&symbol=${encodeURIComponent(symbol)}`
    + `&start=${start}&end=${end}&scope=pair`
    + `&src_event_id=${encodeURIComponent(srcInstanceId)}&dst_event_id=${encodeURIComponent(dstInstanceId)}`
    + ovQuery(paramsOverride))
}
export function getConfig(): Promise<AppConfig> {
  return getJson('/config')
}
export async function putConfig(cfg: AppConfig): Promise<void> {
  const r = await fetch(`${BASE}/config`, {
    method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(cfg),
  })
  if (!r.ok) throw new Error(`PUT /config → ${r.status}`)
}

export interface ScanReq {
  pattern_ids: string[]
  start_date: string
  end_date: string
  workers: number
  ticker_regex: string | null
  label_horizon: number
  first_passage_k: number                              // 几何对称阈值倍数 k(波动率标准化:上行 P(1+kM)、下行 P/(1+kM))
  params_overrides?: Record<string, Record<string, any>>   // ★ Task 8 · pid → params dict(Working Copy 直扫)
  params_files?: Record<string, string>                     // pid → app 目录下的 yaml 文件名(与 params_overrides 互斥)
  note?: string                                             // ★ Task 8 · 扫描备注(命名实验)
  price_min?: number | null                                 // match 级:end_node 事件日收盘价下限(闭区间)
  price_max?: number | null                                 // match 级:end_node 事件日收盘价上限(闭区间)
  volume_min?: number | null                                // 股票级预筛:扫描区间内日均成交量下限(严格大于)
}

export async function startScan(req: ScanReq): Promise<string> {
  const r = await fetch(`${BASE}/scan`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(req),
  })
  if (!r.ok) {
    // 后端把参数源错误(文件不存在/字段非法/两通道互斥)写在 detail 里;丢掉它 = UI 只剩状态码
    // detail 只在是非空字符串时可信;FastAPI 422 的 detail 是对象数组,`??` 兜不住,
    // 不加类型守卫会让 alert 退化成 "[object Object]"(比改动前的状态码文案还差)
    const detail = (await r.json().catch(() => null))?.detail
    throw new Error(typeof detail === 'string' && detail ? detail : `POST /scan → ${r.status}`)
  }
  return (await r.json()).scan_id
}

export function streamScan(
  scanId: string, onEvent: (e: ScanProgress | ScanDone) => void, onError: (e: unknown) => void,
): EventSource {
  const es = new EventSource(`${BASE}/scan/${scanId}/stream`)
  es.onmessage = (ev: MessageEvent) => {
    const data = JSON.parse(ev.data)
    onEvent(data)
    if (data.type === 'done') es.close()
  }
  es.onerror = (e) => onError(e)
  return es
}

export interface PreviewResp {
  analysis: Analysis
  summary: Record<string, number>
  pattern_spec: SerializedPattern
  scan: ScanMeta
}

export function getPreview(
  patternId: string, symbol: string, start: string, end: string, labelHorizon: number,
  paramsOverride?: Record<string, any>,          // ★ Task 8 · Working Copy 参数覆盖透传
): Promise<PreviewResp> {
  return getJson(
    `/preview?pattern_id=${encodeURIComponent(patternId)}`
    + `&symbol=${encodeURIComponent(symbol)}`
    + `&start=${start}&end=${end}&label_horizon=${labelHorizon}`
    + ovQuery(paramsOverride))
}

// ─── Task 6/7:params_diff 前端 wire 层 ───────────────────────────────────────
export function getParamsDiff(patternId: string, scanTs: string): Promise<ParamsDiffResp> {
  return getJson(`/params_diff?pattern_id=${encodeURIComponent(patternId)}&scan_ts=${encodeURIComponent(scanTs)}`)
}

// ─── 参数文件层(dev 式 File 层):列目录 / 读文件 / 写文件(含晋升) ─────────────
export async function listParamFiles(patternId: string): Promise<string[]> {
  const r = await getJson<{ files: string[] }>(
    `/params/files?pattern_id=${encodeURIComponent(patternId)}`)
  return r.files
}
export async function readParamFile(patternId: string, name: string): Promise<Record<string, any>> {
  const r = await getJson<{ params: Record<string, any> }>(
    `/params/file?pattern_id=${encodeURIComponent(patternId)}&name=${encodeURIComponent(name)}`)
  return r.params
}
export async function saveParamFile(
  patternId: string, name: string, params: Record<string, any>,
): Promise<{ ok: true; path: string }> {
  const r = await fetch(`${BASE}/params/save`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ pattern_id: patternId, name, params }),
  })
  if (!r.ok) throw new Error(`POST /params/save → ${r.status}: ${await r.text()}`)
  return r.json()
}

export function deleteParamFile(patternId: string, name: string): Promise<{ok: true}> {
  return fetch(`${BASE}/params/file?pattern_id=${encodeURIComponent(patternId)}&name=${encodeURIComponent(name)}`,
    { method: 'DELETE' })
    .then(r => r.ok ? r.json() : Promise.reject(new Error(`HTTP ${r.status}`)))
}

/** WC 镜像落盘(探索态诊断用):前端修改 WC 时把当前 WC(currentDict+enabled)写到后端 wc.json。
 *  localStorage 行为不变,这是额外镜像,供终端诊断探索态读 WC。调用方 fire-and-forget。*/
export async function saveWcMirror(
  pid: string, scanTs: string, winStart: string, winEnd: string,
  startDate: string, endDate: string,
  wc: Record<string, any>, enabled: boolean,
): Promise<{ ok: true; path: string }> {
  const r = await fetch(`${BASE}/params/wc-mirror`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ pid, scan_ts: scanTs, win_start: winStart, win_end: winEnd, start_date: startDate, end_date: endDate, wc, enabled }),
  })
  if (!r.ok) throw new Error(`POST /params/wc-mirror → ${r.status}: ${await r.text()}`)
  return r.json()
}

/** WC 镜像清理:discardWorkingCopy 触发,删 wc.json。 */
export async function clearWcMirror(pid: string): Promise<{ ok: true }> {
  const r = await fetch(`${BASE}/params/wc-clear`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ pid }),
  })
  if (!r.ok) throw new Error(`POST /params/wc-clear → ${r.status}: ${await r.text()}`)
  return r.json()
}
