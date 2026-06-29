<template>
  <div class="panel">
    <label>区间</label>
    <input v-model="start" /> ~ <input v-model="end" />
    <label>workers</label>
    <input v-model.number="workers" type="number" min="1" />
    <label>label horizon (days)</label>
    <input v-model.number="labelHorizon" type="number" min="1" />

    <button
      :disabled="selectedArray.length === 0"
      :class="{ 'btn-stop': running }"
      @click="onPrimary"
    >
      {{ running ? '停止扫描' : '开始扫描' }}
    </button>

    <button
      :disabled="running"
      @click="dialogOpen = true"
    >
      打开历史…
    </button>

    <div v-if="progress" class="prog">{{ progress.scanned }}/{{ progress.total }} · 命中 {{ progress.hits }}</div>
    <div v-if="lastDone" class="done">
      <template v-if="lastDone.cancelled">扫描已取消</template>
      <template v-else-if="lastDone.error">扫描失败: {{ lastDone.error }}</template>
      <template v-else>完成: 命中 {{ lastDone.hits }} / 错误 {{ lastDone.errors }}</template>
    </div>

    <ScanResultDialog
      v-if="dialogOpen"
      @close="dialogOpen = false"
    />

    <StopScanDialog
      v-if="stopDialogOpen"
      :hits="progress?.hits ?? 0"
      @save="onStopSave"
      @discard="onStopDiscard"
      @continue="onStopContinue"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, watch } from 'vue'
import { storeToRefs } from 'pinia'
import { usePatternsStore } from '../stores/patterns'
import { useScanStore } from '../stores/scan'
import { useConfigStore } from '../stores/config'
import ScanResultDialog from './ScanResultDialog.vue'
import StopScanDialog from './StopScanDialog.vue'

const patterns = usePatternsStore()
const scan = useScanStore()
const cfg = useConfigStore()
const { selectedArray } = storeToRefs(patterns)
const { running, progress, lastDone } = storeToRefs(scan)

const start = ref('2025-01-01')
const end = ref('2025-12-31')
const workers = ref(8)
const tickerRegex = ref<string | null>(null)
const labelHorizon = ref(20)
const dialogOpen = ref(false)
const stopDialogOpen = ref(false)

onMounted(async () => {
  try {
    await cfg.load()
    const s = cfg.config?.scan
    if (s) {
      start.value = s.start_date; end.value = s.end_date
      workers.value = s.workers; tickerRegex.value = s.ticker_regex
      labelHorizon.value = s.label_horizon ?? 20
    }
  } catch { /* 后端不可用:保留默认 */ }
})

async function onPrimary() {
  if (selectedArray.value.length === 0) return
  if (running.value) {
    // 正在扫:已命中数 > 0 → 弹 StopScanDialog 让用户选;= 0 → 直接 cancel(false)
    if ((progress.value?.hits ?? 0) > 0) {
      stopDialogOpen.value = true
    } else {
      await scan.cancel(false)
    }
  } else {
    await onScan()
  }
}

async function onScan() {
  if (selectedArray.value.length === 0) return
  const s = {
    start_date: start.value, end_date: end.value,
    workers: workers.value, ticker_regex: tickerRegex.value,
    label_horizon: labelHorizon.value,
  }
  if (cfg.config) await cfg.save({ ...cfg.config, scan: s })
  scan.run({ pattern_ids: selectedArray.value, ...s })
}

async function onStopSave()    { stopDialogOpen.value = false; await scan.cancel(true) }
async function onStopDiscard() { stopDialogOpen.value = false; await scan.cancel(false) }
function onStopContinue()      { stopDialogOpen.value = false }

// dialog 开着时,扫描若自然跑完 → 自动关 dialog
watch(running, (r) => { if (!r && stopDialogOpen.value) stopDialogOpen.value = false })
</script>

<style scoped>
.panel { padding: 10px; border-top: 1px solid #e5e7eb; }
label { font-size: 11px; color: #64748b; display: block; margin-top: 6px; }
input { padding: 3px; width: 90px; }
button { margin-top: 8px; width: 100%; padding: 6px; }
button.btn-stop { background: #ef4444; color: #fff; }
.prog, .done { font-size: 11px; margin-top: 6px; }
</style>
