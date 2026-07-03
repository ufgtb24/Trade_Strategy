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

  async function run(req: ScanReq) {
    running.value = true
    progress.value = null
    lastDone.value = null
    const id = await startScan(req)
    currentScanId.value = id
    const es = streamScan(id, (e) => {
      if ((e as ScanDone).type === 'done') {
        const done = e as ScanDone
        lastDone.value = done
        running.value = false
        if (!done.error && !done.cancelled) {
          void refreshHistory()
          if (done.scan_ts) void open(done.scan_ts)
        }
      } else if (!cancelling.value) {
        progress.value = e as ScanProgress
      }
    }, () => { running.value = false; es.close() })
    _eventSource = es
  }

  async function refreshHistory() {
    history.value = await listScans()
  }

  async function open(scanTs: string) {
    const f = await loadScan(scanTs)
    useViewStore().loadScanFile(f)
  }

  async function remove(scanTs: string) {
    await deleteScan(scanTs)
  }

  async function cancel(save: boolean): Promise<void> {
    if (!currentScanId.value || !running.value || cancelling.value) return
    cancelling.value = true
    const scanId = currentScanId.value
    try {
      await cancelScan(scanId, save)
      if (_eventSource) {
        _eventSource.close()
        _eventSource = null
      }
      await new Promise(r => setTimeout(r, 300))
      if (save) {
        for (let i = 0; i < 30; i++) {
          const list = await listScans()
          const entry = list.find(e => e.scan_ts === scanId)
          if (entry) {
            history.value = list
            await open(scanId)
            lastDone.value = { type: 'done', hits: entry.hits ?? 0, errors: 0,
                               total: entry.total ?? 0, partial: true,
                               scan_ts: scanId }
            break
          }
          await new Promise(r => setTimeout(r, 200))
        }
      } else {
        lastDone.value = { type: 'done', hits: 0, errors: 0, total: 0,
                           cancelled: true, scan_ts: scanId }
      }
      running.value = false
    } finally {
      cancelling.value = false
    }
  }

  return { progress, running, lastDone, history, currentScanId,
           run, refreshHistory, open, remove, cancel }
})
