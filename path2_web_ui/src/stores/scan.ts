import { defineStore } from 'pinia'
import { ref } from 'vue'
import type { ScanProgress, ScanDone, ScanHistoryEntry } from '../types'
import { startScan, streamScan, listScans, loadScan, deleteScan, cancelScan, renameScan, type ScanReq } from '../api'
import { useViewStore } from './view'

export const useScanStore = defineStore('scan', () => {
  const progress = ref<ScanProgress | null>(null)
  const running = ref(false)
  const lastDone = ref<ScanDone | null>(null)
  const history = ref<ScanHistoryEntry[]>([])
  const currentScanId = ref<string | null>(null)
  const cancelling = ref(false)
  let _eventSource: EventSource | null = null

  // Task 12 · WC 发起扫描的 hash 守卫:发起时记参与 pid 的 dict 快照,done 时字节等价才清
  // (防异步扫描期间用户继续编辑被误清;partial 不清;per-pid 只清参与本次的槽位)。
  // 闭包私有(不进 return,pinia setup store 不可 serialize 出去的普通变量)。
  let _wcLaunch: Record<string, string> = {}
  function markWcLaunch(pids: string[]): void {
    const v = useViewStore()
    _wcLaunch = {}
    for (const pid of pids) {
      const wc = v.workingCopy[pid]
      if (wc) _wcLaunch[pid] = JSON.stringify(wc.currentDict)
    }
  }
  function settleWcAfterDone(opts: { partial: boolean }): void {
    const v = useViewStore()
    if (opts.partial) { _wcLaunch = {}; return }
    for (const [pid, launched] of Object.entries(_wcLaunch)) {
      const wc = v.workingCopy[pid]
      if (wc && JSON.stringify(wc.currentDict) === launched) {
        v.discardWorkingCopy(pid)
        v.showToast(`${pid} 工作副本已固化为本次扫描的 snapshot,回到浏览态`)
      }
    }
    _wcLaunch = {}
  }

  async function run(req: ScanReq) {
    running.value = true
    progress.value = null
    lastDone.value = null
    let id: string
    try {
      id = await startScan(req)
    } catch (e) {
      running.value = false   // 不复位 = 按钮永久 disabled、对话框不关,用户只能刷页面
      throw e                 // 交给调用方展示;store 不弹 UI
    }
    currentScanId.value = id
    const es = streamScan(id, (e) => {
      if ((e as ScanDone).type === 'done') {
        const done = e as ScanDone
        lastDone.value = done
        running.value = false
        if (!done.error && !done.cancelled) {
          settleWcAfterDone({ partial: !!done.partial })   // Task 12 · 先 settle 再 open(open 会重置 workingCopy)
          void refreshHistory()
          if (done.name) void open(done.name)
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

  async function open(name: string) {
    const f = await loadScan(name)
    useViewStore().loadScanFile(f)
  }

  async function remove(name: string) {
    await deleteScan(name)
  }

  async function rename(oldName: string, newName: string) {
    await renameScan(oldName, newName)
    await refreshHistory()
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
           run, refreshHistory, open, remove, rename, cancel,
           markWcLaunch, settleWcAfterDone }
})
