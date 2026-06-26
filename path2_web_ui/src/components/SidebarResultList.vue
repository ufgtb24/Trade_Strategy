<template>
  <div class="list">
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
    <table v-else class="multi">
      <thead>
        <tr>
          <th class="sym">symbol</th>
          <th v-for="pid in patternIds" :key="pid"
              :data-col-pid="pid"
              :title="pid"
              class="col"
              @click="view.setSort(pid)">
            {{ displayNameOf(pid) }}
            <span v-if="sortByPid === pid" class="sort-ind">
              {{ sortDesc ? '▼' : '▲' }}
            </span>
          </th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in sortedRows" :key="row.symbol"
            :class="{ active: row.symbol === symbol }">
          <td class="sym" @click="view.selectSymbol(row.symbol)">{{ row.symbol }}</td>
          <td v-for="cell in row.cells" :key="cell.pid"
              :data-cell-pid="cell.pid"
              :class="['col', { matched: cell.matched }]"
              @click="view.selectSymbol(row.symbol)">
            {{ fmt(cell.max_ret) }}
          </td>
        </tr>
      </tbody>
    </table>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { storeToRefs } from 'pinia'
import { useViewStore } from '../stores/view'
const view = useViewStore()
const { scanFile, symbol, preview, previewEnabled, previewLoading, previewError,
        patternIds, sortedRows, sortByPid, sortDesc } = storeToRefs(view)

const canRefresh = computed(() =>
  previewEnabled.value && !!preview.value && !previewLoading.value
  && preview.value?.symbol === symbol.value)

function displayNameOf(pid: string): string {
  return scanFile.value?.per_pattern[pid]?.pattern_spec.display_name ?? pid
}
function fmt(v: number | null): string {
  if (v == null) return '—'
  const pct = (v * 100).toFixed(1)
  return v >= 0 ? `+${pct}%` : `${pct}%`
}
function onToggle(e: Event) {
  void view.setPreviewEnabled((e.target as HTMLInputElement).checked)
}
function onCloseError() { view.clearPreview() }
</script>

<style scoped>
.list { overflow-y: auto; height: 100%; display: flex; flex-direction: column; }
.preview-bar { padding: 6px 10px; border-bottom: 1px solid #e5e7eb; background: #f8fafc; }
.toggle { display: flex; align-items: center; gap: 6px; cursor: pointer; font-size: 12px; }
.toggle input { cursor: pointer; }
.refresh { margin-left: auto; padding: 1px 6px; font-size: 14px;
           border: 1px solid #cbd5e1; background: #fff; cursor: pointer; }
.refresh:disabled { opacity: 0.4; cursor: not-allowed; }
.status { font-size: 11px; color: #64748b; margin-top: 4px; }
.error { font-size: 11px; color: #ef4444; margin-top: 4px; }
.error a { cursor: pointer; margin-left: 6px; }

.hint { padding: 8px 12px; font-size: 12px; color: #64748b; }
table.multi { width: 100%; border-collapse: collapse; font-size: 12px; }
table.multi th, table.multi td { padding: 4px 6px; border-bottom: 1px solid #f1f5f9; text-align: left; }
table.multi th.col { cursor: pointer; user-select: none; }
table.multi th.col:hover { background: #f1f5f9; }
table.multi .sort-ind { color: #2563eb; margin-left: 2px; }
table.multi td.sym { font-weight: 600; cursor: pointer; }
table.multi td.col { cursor: pointer; text-align: right; background: #fafafa; }
table.multi td.col.matched { background: #dcfce7; }
tr.active { background: #eff6ff; }
</style>
