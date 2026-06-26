<template>
  <div class="list">
    <!-- preview 工具栏(spec §4.4)-->
    <div class="preview-bar">
      <label class="toggle">
        <input type="checkbox" :checked="previewEnabled"
               :disabled="!scanFile"
               @change="onToggle($event)" />
        <span>用 yaml 临时计算</span>
        <button class="refresh" title="重算当前股(yaml 改过后用)"
                :disabled="!canRefresh" @click="view.runPreview">↻</button>
      </label>
      <div v-if="previewLoading" class="status">计算中…</div>
      <div v-if="previewError" class="error">
        临时计算失败: {{ previewError }}
        <a @click="onCloseError">×</a>
      </div>
    </div>

    <div v-if="!scanFile" class="hint">未加载扫描结果</div>
    <div
      v-for="r in scanFile?.results ?? []" :key="r.symbol"
      :data-symbol="r.symbol" class="row" :class="{ active: r.symbol === symbol }"
      @click="view.selectSymbol(r.symbol)"
    >
      <span class="sym">{{ r.symbol }}</span>
      <span class="badges">
        <span v-for="(n, k) in r.summary" :key="k" class="badge">{{ k }}:{{ n }}</span>
      </span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { storeToRefs } from 'pinia'
import { useViewStore } from '../stores/view'
const view = useViewStore()
const { scanFile, symbol, preview, previewEnabled, previewLoading, previewError }
  = storeToRefs(view)

const canRefresh = computed(() =>
  previewEnabled.value && !!preview.value && !previewLoading.value
  && preview.value?.symbol === symbol.value)

function onToggle(e: Event) {
  void view.setPreviewEnabled((e.target as HTMLInputElement).checked)
}
function onCloseError() { view.clearPreview() }
</script>

<style scoped>
.list { overflow-y: auto; }

.preview-bar { padding: 6px 10px; border-bottom: 1px solid #e5e7eb;
               background: #f8fafc; }
.toggle { display: flex; align-items: center; gap: 6px; cursor: pointer;
          font-size: 12px; }
.toggle input { cursor: pointer; }
.refresh { margin-left: auto; padding: 1px 6px; font-size: 14px;
           border: 1px solid #cbd5e1; background: #fff; cursor: pointer; }
.refresh:disabled { opacity: 0.4; cursor: not-allowed; }
.status { font-size: 11px; color: #64748b; margin-top: 4px; }
.error { font-size: 11px; color: #ef4444; margin-top: 4px; }
.error a { cursor: pointer; margin-left: 6px; }

.row { padding: 6px 10px; cursor: pointer; border-bottom: 1px solid #f1f5f9; }
.row.active { background: #eff6ff; }
.sym { font-weight: 600; }
.badges { display: block; font-size: 10px; color: #64748b; }
.badge { margin-right: 6px; }
</style>
