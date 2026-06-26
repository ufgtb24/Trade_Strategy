import { defineStore } from 'pinia'
import { ref } from 'vue'
import type { ScanProgress, ScanDone, ScanHistoryEntry } from '../types'
import { startScan, streamScan, listScans, loadScan, deleteScan, cancelScan, type ScanReq } from '../api'
import { useViewStore } from './view'

export const useScanStore = defineStore('scan', () => {
  const progress = ref<ScanProgress | null>(null)
  const running = ref(false)
  const lastDone = ref<ScanDone | null>(null)
  const history = ref<ScanHistoryEntry[]>([])
  const currentScanId = ref<string | null>(null)
  const cancelling = ref(false)
  let _eventSource: EventSource | null = null
  let _currentPatternId: string | null = null

  async function run(req: ScanReq) {
    running.value = true
    progress.value = null
    lastDone.value = null
    _currentPatternId = req.pattern_id
    const id = await startScan(req)
    currentScanId.value = id
    const es = streamScan(id, (e) => {
      if ((e as ScanDone).type === 'done') {
        const done = e as ScanDone
        lastDone.value = done
        running.value = false
        if (!done.error && !done.cancelled) {
          void refreshHistory(req.pattern_id)
          if (done.scan_ts) void open(req.pattern_id, done.scan_ts)
        }
      } else if (!cancelling.value) {
        progress.value = e as ScanProgress
      }
    }, () => { running.value = false; es.close() })
    _eventSource = es
  }
  async function refreshHistory(patternId: string) {
    history.value = await listScans(patternId)
  }
  async function open(patternId: string, scanTs: string) {
    const f = await loadScan(patternId, scanTs)
    useViewStore().loadScanFile(f)
  }
  async function remove(patternId: string, scanTs: string) {
    await deleteScan(patternId, scanTs)
  }
  async function cancel(save: boolean): Promise<void> {
    if (!currentScanId.value || !running.value || cancelling.value) return
    cancelling.value = true
    const scanId = currentScanId.value
    const patternId = _currentPatternId
    try {
      // ── 修 chrome same-origin socket pool 死锁 ──
      // 现象:点 click 后 page 内 fetch/XHR POST 在 SSE 活动时被 chrome 内部 hold 不
      // 发包(fetch 卡 100+s,XHR send 同步返回但 onload 永不触发)。eval 内的 XHR
      // 立即成功,所以不是 backend 问题,是 chrome page 内 socket pool 调度。
      //
      // 三步修复:
      // 1) cancelScan 用 navigator.sendBeacon — 走 chrome background sync 通道、
      //    不受 page socket pool 限制,POST 立即抵达 backend。
      // 2) 主动 close SSE EventSource — 让 chrome 释放占用的 origin socket slot。
      // 3) delay 300ms 等 chrome 内部 keep-alive cleanup 完成,然后 polling
      //    listScans/loadScan(普通 fetch,此时已不卡),完成后构造 done shape。
      // 不依赖 SSE done event 路径(SSE 已 close,backend 推的 done 进 q 无消费)。
      await cancelScan(scanId, save)              // sendBeacon — 立即返回
      if (_eventSource) {
        _eventSource.close()
        _eventSource = null
      }
      await new Promise(r => setTimeout(r, 300))  // 让 chrome 释放 socket pool
      if (save && patternId) {
        // 轮询历史:backend 写完 partial 文件后该 scan_ts 出现在 list_scans
        for (let i = 0; i < 30; i++) {
          const list = await listScans(patternId)
          const entry = list.find(e => e.scan_ts === scanId)
          if (entry) {
            history.value = list
            await open(patternId, scanId)
            lastDone.value = { type: 'done', hits: entry.hits ?? 0, errors: 0,
                               total: entry.total ?? 0, partial: true,
                               pattern_id: patternId, scan_ts: scanId }
            break
          }
          await new Promise(r => setTimeout(r, 200))
        }
      } else {
        // discard 路径:本地构造 cancelled shape done(SSE 已 close,backend done 不到)
        lastDone.value = { type: 'done', hits: 0, errors: 0, total: 0,
                           cancelled: true, pattern_id: patternId ?? undefined,
                           scan_ts: scanId }
      }
      running.value = false
    } finally {
      cancelling.value = false
    }
  }
  return { progress, running, lastDone, history, currentScanId,
           run, refreshHistory, open, remove, cancel }
})
