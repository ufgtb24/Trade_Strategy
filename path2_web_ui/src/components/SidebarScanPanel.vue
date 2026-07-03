<template>
  <div class="panel">
    <div class="topbar">
      <button :disabled="scan.running" @click="scanDialogOpen = true">扫描 ⚙</button>
      <button @click="historyDialogOpen = true">打开历史 …</button>
    </div>

    <div v-if="scan.running" class="prog">
      {{ progress?.scanned ?? 0 }}/{{ progress?.total ?? 0 }} · 命中 {{ progress?.hits ?? 0 }}
      <button class="btn-stop" @click="onStopClick">停止扫描 ✕</button>
    </div>
    <div v-else-if="lastDone" class="done">
      <template v-if="lastDone.cancelled">扫描已取消</template>
      <template v-else-if="lastDone.error">扫描失败: {{ lastDone.error }}</template>
      <template v-else>完成: 命中 {{ lastDone.hits }} / 错误 {{ lastDone.errors }}</template>
    </div>

    <ScanConfigDialog v-if="scanDialogOpen" @close="scanDialogOpen = false" />
    <ScanResultDialog v-if="historyDialogOpen" @close="historyDialogOpen = false" />
    <StopScanDialog v-if="stopDialogOpen"
                    :hits="progress?.hits ?? 0"
                    @save="onStopSave" @discard="onStopDiscard" @continue="onStopContinue" />
  </div>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import { storeToRefs } from 'pinia'
import { useScanStore } from '../stores/scan'
import ScanConfigDialog from './ScanConfigDialog.vue'
import ScanResultDialog from './ScanResultDialog.vue'
import StopScanDialog from './StopScanDialog.vue'

const scan = useScanStore()
const { progress, lastDone } = storeToRefs(scan)

const scanDialogOpen = ref(false)
const historyDialogOpen = ref(false)
const stopDialogOpen = ref(false)

async function onStopClick() {
  if ((progress.value?.hits ?? 0) > 0) {
    stopDialogOpen.value = true
  } else {
    await scan.cancel(false)
  }
}
async function onStopSave()    { stopDialogOpen.value = false; await scan.cancel(true) }
async function onStopDiscard() { stopDialogOpen.value = false; await scan.cancel(false) }
function onStopContinue()      { stopDialogOpen.value = false }

// dialog 开着时,扫描若自然跑完 → 自动关 dialog
watch(() => scan.running, (r) => { if (!r && stopDialogOpen.value) stopDialogOpen.value = false })
</script>

<style scoped>
.panel { padding: 8px 10px; border-bottom: 1px solid #e5e7eb; background: #f8fafc; }
.topbar { display: flex; gap: 6px; }
.topbar button { padding: 4px 10px; font-size: 12px; border: 1px solid #cbd5e1;
                 background: #fff; cursor: pointer; }
.topbar button:disabled { opacity: 0.4; cursor: not-allowed; }
.prog, .done { font-size: 11px; margin-top: 6px; display: flex; align-items: center; gap: 8px; }
.btn-stop { padding: 2px 8px; font-size: 11px; border: 1px solid #ef4444;
            background: #ef4444; color: #fff; cursor: pointer; margin-left: auto; }
</style>
