<template>
  <div class="backdrop" @click.self="onCancel">
      <div class="card" tabindex="-1" ref="cardEl"
           @keydown.esc.stop="onCancel"
           @keydown.enter.stop="onEnter"
           @keydown.stop="onKeydown">
        <header><h3>Scan Results</h3></header>

        <div v-if="loading" class="state">Loading…</div>
        <div v-else-if="error" class="state error">
          {{ error }} <button @click="reload">Retry</button>
        </div>
        <div v-else-if="!rows.length" class="state">No scan history.</div>
        <table v-else class="file-list" tabindex="0" ref="listEl">
          <thead><tr><th>Time</th><th>Hits</th><th>Size</th></tr></thead>
          <tbody>
            <tr v-for="(r, i) in rows" :key="r.scan_ts"
                :class="{ active: selected.has(r.scan_ts), current: r.scan_ts === currentScanTs }"
                @click.exact.prevent="selectSingle(i)"
                @click.ctrl.prevent="toggle(i)"
                @click.meta.prevent="toggle(i)"
                @click.shift.prevent="extendTo(i)"
                @dblclick="openOne(r.scan_ts)">
              <td>
                {{ formatTs(r.scan_ts) }}
                <span v-if="r.partial" class="partial-badge">未完成</span>
                <span v-for="pid in r.pattern_ids" :key="pid" class="chip">{{ pid }}</span>
              </td>
              <td>{{ r.hits === null ? '—' : `${r.hits} / ${r.total}` }}</td>
              <td>{{ formatSize(r.size) }}</td>
            </tr>
          </tbody>
        </table>

        <footer>
          <span class="hint">{{ selected.size }} selected · ↑↓ / Enter / Delete / Esc</span>
          <button @click="onCancel">Cancel</button>
          <button :disabled="selected.size !== 1" @click="onOpen">Open</button>
        </footer>

        <div v-if="confirming" class="confirm-backdrop">
          <div class="confirm-card">
            <p>{{ confirmMessage }}</p>
            <p v-if="confirmIncludesCurrent" class="warn">
              Note: includes the currently loaded scan; main view will be cleared.
            </p>
            <button @click="confirming = false">Keep</button>
            <button class="btn-stop" @click="performDelete">Delete</button>
          </div>
        </div>
      </div>
  </div>
</template>

<script setup lang="ts">
/*
 * 注:测试约束导致未用 Teleport;当前 codebase 无 transform/filter/perspective 祖先,
 * position: fixed 能正确覆盖视口。若未来父级加入此类属性,需补回 <Teleport to="body">
 * 并改测试 helper 为 document.body.querySelector。
 */
import { ref, computed, onMounted, nextTick } from 'vue'
import { storeToRefs } from 'pinia'
import { useScanStore } from '../stores/scan'
import { useViewStore } from '../stores/view'
import type { ScanHistoryEntry } from '../types'

const emit = defineEmits<{ (e: 'close'): void }>()

const view = useViewStore()
const scan = useScanStore()
const { scanFile } = storeToRefs(view)

const rows = ref<ScanHistoryEntry[]>([])
const selected = ref(new Set<string>())
const anchor = ref<number>(-1)
const loading = ref(false)
const error = ref<string | null>(null)
const confirming = ref(false)
const confirmMessage = ref('')
const confirmIncludesCurrent = ref(false)
const cardEl = ref<HTMLElement | null>(null)
const listEl = ref<HTMLElement | null>(null)

const currentScanTs = computed(() => scanFile.value?.scan?.scan_ts ?? null)

async function reload() {
  loading.value = true; error.value = null
  try {
    await scan.refreshHistory()
    rows.value = [...scan.history]
  }
  catch (e: any) { error.value = `Failed to load history: ${e.message ?? e}` }
  finally { loading.value = false }
}

onMounted(async () => {
  await reload()
  await nextTick()
  ;(listEl.value ?? cardEl.value)?.focus()
})

function selectSingle(i: number) {
  selected.value = new Set([rows.value[i].scan_ts])
  anchor.value = i
}
function toggle(i: number) {
  const ts = rows.value[i].scan_ts
  const next = new Set(selected.value)
  next.has(ts) ? next.delete(ts) : next.add(ts)
  selected.value = next
  anchor.value = i
}
function extendTo(i: number) {
  if (anchor.value < 0) return selectSingle(i)
  const [lo, hi] = anchor.value < i ? [anchor.value, i] : [i, anchor.value]
  selected.value = new Set(rows.value.slice(lo, hi + 1).map(r => r.scan_ts))
}

function onEnter() {
  if (selected.value.size === 1) onOpen()
}
function onKeydown(e: KeyboardEvent) {
  if (e.key === 'Delete') onDeleteKey()
}
function onDeleteKey() {
  // 注:confirmMessage 在按 Delete 那一刻 snapshot;confirm 层打开期间无法改选(键盘只在 .card 监听 esc/enter,无 selection 操作)。若未来加键盘可改选,需改 computed。
  if (!selected.value.size) return
  const sel = Array.from(selected.value)
  confirmMessage.value = sel.length === 1
    ? `Delete ${formatTs(sel[0])}?`
    : buildMultiMessage(sel)
  confirmIncludesCurrent.value = currentScanTs.value !== null && sel.includes(currentScanTs.value)
  confirming.value = true
}
function buildMultiMessage(sel: string[]): string {
  const head = sel.slice(0, 3).map(formatTs).map(s => `• ${s}`).join('\n')
  const tail = sel.length > 3 ? `\n…and ${sel.length - 3} more` : ''
  return `Delete ${sel.length} scan results?\n${head}${tail}`
}

async function performDelete() {
  const targets = Array.from(selected.value)
  const failures: string[] = []
  for (const ts of targets) {
    try { await scan.remove(ts) } catch { failures.push(ts) }
  }
  await scan.refreshHistory()
  rows.value = [...scan.history]
  if (currentScanTs.value !== null && targets.includes(currentScanTs.value)) {
    view.clearScanFile()
  }
  selected.value.clear()
  confirming.value = false
  if (failures.length) error.value = `Failed to delete: ${failures.join(', ')}`
}

async function onOpen() {
  if (selected.value.size !== 1) return
  const ts = Array.from(selected.value)[0]
  await scan.open(ts)
  emit('close')
}
function openOne(ts: string) {
  scan.open(ts).then(() => emit('close'))
}
function onCancel() { emit('close') }

function formatTs(ts: string): string {
  const m = ts.match(/^(\d{4})(\d{2})(\d{2})T(\d{2})(\d{2})(\d{2})$/)
  return m ? `${m[1]}-${m[2]}-${m[3]} ${m[4]}:${m[5]}:${m[6]}` : ts
}
function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 ** 2) return `${(bytes / 1024).toFixed(1)} KB`
  if (bytes < 1024 ** 3) return `${(bytes / 1024 / 1024).toFixed(1)} MB`
  return `${(bytes / 1024 ** 3).toFixed(2)} GB`
}
</script>

<style scoped>
.backdrop {
  position: fixed; inset: 0;
  background: rgba(0, 0, 0, 0.4);
  display: flex; align-items: center; justify-content: center;
  z-index: 1000;
}
.card {
  background: #fff;
  border-radius: 8px;
  padding: 16px;
  min-width: 480px;
  max-width: 80vw;
  max-height: 70vh;
  display: flex; flex-direction: column;
  position: relative;
  outline: none;
}
header h3 { margin: 0 0 12px; font-size: 14px; }
.state { padding: 24px; text-align: center; color: #64748b; }
.state.error { color: #b91c1c; }
.file-list {
  width: 100%; border-collapse: collapse;
  overflow-y: auto; max-height: 50vh; display: block;
  font-size: 12px;
}
.file-list thead, .file-list tbody, .file-list tr { display: table; width: 100%; table-layout: fixed; }
.file-list th, .file-list td { padding: 4px 8px; text-align: left; }
.file-list tr.active { background: #eff6ff; }
.file-list tr.current { font-weight: 600; }
.file-list tr { cursor: pointer; }
footer { display: flex; align-items: center; gap: 10px; margin-top: 12px; }
.hint { flex: 1; font-size: 11px; color: #64748b; white-space: pre-line; }
.confirm-backdrop {
  position: absolute; inset: 0;
  background: rgba(255, 255, 255, 0.85);
  display: flex; align-items: center; justify-content: center;
}
.confirm-card {
  background: #fff;
  border: 1px solid #cbd5e1;
  padding: 16px;
  border-radius: 6px;
  max-width: 360px;
}
.confirm-card p { white-space: pre-line; margin: 0 0 12px; font-size: 12px; }
.warn { color: #b91c1c; font-size: 11px; }
button.btn-stop { background: #ef4444; color: #fff; }
.chip { display: inline-block; padding: 1px 6px; background: #e5e7eb;
        border-radius: 8px; font-size: 10px; margin-right: 4px; }
.partial-badge {
  display: inline-block;
  margin-left: 6px;
  padding: 1px 6px;
  font-size: 10px;
  background: #fef3c7;
  color: #92400e;
  border-radius: 3px;
  vertical-align: middle;
}
</style>
