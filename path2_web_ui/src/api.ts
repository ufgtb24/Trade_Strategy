// 后端 REST + SSE 封装。BASE 默认 localhost:8000,可经 VITE_API_BASE 覆盖。
import type {
  SerializedPattern, ScanResultFile, Ohlc, Diagnostics, AppConfig,
  ScanProgress, ScanDone, ScanHistoryEntry, Analysis, ScanMeta,
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
export function listScans(patternId: string): Promise<ScanHistoryEntry[]> {
  return getJson(`/scans/${patternId}`)
}
export function loadScan(patternId: string, scanTs: string): Promise<ScanResultFile> {
  return getJson(`/scans/${patternId}/${scanTs}`)
}
export function deleteScan(patternId: string, scanTs: string): Promise<{ok: true}> {
  return fetch(`${BASE}/scans/${patternId}/${scanTs}`, { method: 'DELETE' })
    .then(r => r.ok ? r.json() : Promise.reject(new Error(`HTTP ${r.status}`)))
}
export function cancelScan(scanId: string, save: boolean = false): Promise<{ok: true}> {
  // 用 navigator.sendBeacon 而非 fetch/XHR:实测 page 内的 fetch/XHR POST 在
  // SSE EventSource 同源活动时,被 chrome 内部 hold 不真发 packet — fetch 卡
  // 100+s 等 SSE 自然关闭,XHR 即使 send() 同步返回也 onload 永不触发。chrome
  // 把 sendBeacon 走独立调度路径(背景:为页面 unload 时刻 fire-and-forget 设计),
  // 不受 page 主 socket pool 排队影响,在 active SSE 期间也能立即发包(实测 ~10ms)。
  // 不需要 response — cancel 的反馈通过 SSE done event 经现有 onmessage 路径回来。
  const url = `${BASE}/scan/${scanId}/cancel?save=${save}`
  const ok = navigator.sendBeacon(url)
  return ok ? Promise.resolve({ok: true})
            : Promise.reject(new Error('sendBeacon enqueue failed'))
}
export function getDiagnose(patternId: string, symbol: string, start: string, end: string): Promise<Diagnostics> {
  return getJson(`/diagnose?pattern_id=${patternId}&symbol=${encodeURIComponent(symbol)}&start=${start}&end=${end}`)
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

export interface ScanReq { pattern_id: string; start_date: string; end_date: string; workers: number; ticker_regex: string | null; label_horizon: number }

export async function startScan(req: ScanReq): Promise<string> {
  const r = await fetch(`${BASE}/scan`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(req),
  })
  if (!r.ok) throw new Error(`POST /scan → ${r.status}`)
  return (await r.json()).scan_id
}

/** 订阅扫描进度 SSE。onEvent 收 ScanProgress|ScanDone;done 后自动 close。返回 EventSource(可手动 close)。 */
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

// ── 单股临时计算(spec §3:GET /preview)──
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
