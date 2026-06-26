import type {
  SerializedPattern, MultiScanResultFile, Ohlc, Diagnostics, AppConfig,
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
