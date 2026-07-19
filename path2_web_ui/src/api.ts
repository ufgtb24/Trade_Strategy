import type {
  SerializedPattern, MultiScanResultFile, Ohlc, Diagnostics, AppConfig,
  ScanProgress, ScanDone, ScanHistoryEntry, Analysis, ScanMeta, NodesScopeResponse,
  TimeScopeResponse, PairScopeResponse,
} from './types'

const BASE = (import.meta as any).env?.VITE_API_BASE ?? 'http://localhost:8000'

async function getJson<T>(path: string): Promise<T> {
  const r = await fetch(`${BASE}${path}`)
  if (!r.ok) throw new Error(`GET ${path} → ${r.status}: ${await r.text()}`)
  return r.json() as Promise<T>
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
export function loadScan(scanTs: string): Promise<MultiScanResultFile> {
  return getJson(`/scans/${scanTs}`)
}
export function deleteScan(scanTs: string): Promise<{ok: true}> {
  return fetch(`${BASE}/scans/${scanTs}`, { method: 'DELETE' })
    .then(r => r.ok ? r.json() : Promise.reject(new Error(`HTTP ${r.status}`)))
}
export function cancelScan(scanId: string, save: boolean = false): Promise<{ok: true}> {
  const url = `${BASE}/scan/${scanId}/cancel?save=${save}`
  const ok = navigator.sendBeacon(url)
  return ok ? Promise.resolve({ok: true})
            : Promise.reject(new Error('sendBeacon enqueue failed'))
}
export function getDiagnose(patternId: string, symbol: string, start: string, end: string): Promise<Diagnostics> {
  return getJson(`/diagnose?pattern_id=${patternId}&symbol=${encodeURIComponent(symbol)}&start=${start}&end=${end}`)
}
// 入口 B(拓扑面板降级):点 edge → scope=nodes,只拿这条 node 边的 miss_reasons 分布 +
// example_failed_pairs 样例(≤5),不重取整包 per-node 诊断。legacy getDiagnose 不受影响。
export function getNodesDiagnose(
  patternId: string, symbol: string, start: string, end: string, srcNode: string, dstNode: string,
): Promise<NodesScopeResponse> {
  return getJson(
    `/diagnose?pattern_id=${encodeURIComponent(patternId)}&symbol=${encodeURIComponent(symbol)}`
    + `&start=${start}&end=${end}&scope=nodes`
    + `&src_node=${encodeURIComponent(srcNode)}&dst_node=${encodeURIComponent(dstNode)}`)
}
// 入口 A(KlineChart 主图 brush 框选):scope=time,拿 [start_bar,end_bar] 框内(严格 ⊆)的
// gate 失败样例(GateFailure)。eventClass 可选(按 class_id 二次过滤)。
export function getTimeDiagnose(
  patternId: string, symbol: string, start: string, end: string,
  startBar: number, endBar: number, eventClass?: string,
  signal?: AbortSignal,
  anchorKind?: string,                  // ★ v3 · anchor_kind 门限透传
): Promise<TimeScopeResponse> {
  const url = `${BASE}/diagnose?pattern_id=${encodeURIComponent(patternId)}&symbol=${encodeURIComponent(symbol)}`
    + `&start=${start}&end=${end}&scope=time`
    + `&start_bar=${startBar}&end_bar=${endBar}`
    + (eventClass ? `&event_class=${encodeURIComponent(eventClass)}` : '')
    + (anchorKind ? `&anchor_kind=${encodeURIComponent(anchorKind)}` : '')   // ★ v3 · 空串也 skip · 与后端 handler `if anchor_kind:` 判据对齐
  return fetch(url, { signal }).then(async r => {
    if (!r.ok) throw new Error(`GET ${url} → ${r.status}: ${await r.text()}`)
    return r.json() as Promise<TimeScopeResponse>
  })
}
// 入口 D(KlineChart shift+click 跨图累积):scope=pair,两 marker 的 (src_event_id,dst_event_id)
// 查两 node 间是否有直连 edge · 若有则 4 通道 subcheck 短路(auto swap 见 PairPayload.applied_swap)。
export function getPairDiagnose(
  patternId: string, symbol: string, start: string, end: string,
  srcEventId: string, dstEventId: string,
): Promise<PairScopeResponse> {
  return getJson(
    `/diagnose?pattern_id=${encodeURIComponent(patternId)}&symbol=${encodeURIComponent(symbol)}`
    + `&start=${start}&end=${end}&scope=pair`
    + `&src_event_id=${encodeURIComponent(srcEventId)}&dst_event_id=${encodeURIComponent(dstEventId)}`)
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
}

export async function startScan(req: ScanReq): Promise<string> {
  const r = await fetch(`${BASE}/scan`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(req),
  })
  if (!r.ok) throw new Error(`POST /scan → ${r.status}`)
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
  patternId: string, symbol: string, start: string, end: string, labelHorizon: number
): Promise<PreviewResp> {
  return getJson(
    `/preview?pattern_id=${encodeURIComponent(patternId)}`
    + `&symbol=${encodeURIComponent(symbol)}`
    + `&start=${start}&end=${end}&label_horizon=${labelHorizon}`)
}
