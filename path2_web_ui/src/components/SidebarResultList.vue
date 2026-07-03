<template>
  <div class="list" ref="listEl">
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
    <div v-else class="table-wrap" ref="tableWrapEl" @scroll.passive="recalc">
      <table class="multi" ref="tableEl">
        <thead>
          <tr class="hdr-pattern">
            <th class="sym" rowspan="2" data-cell-field="sym"
                @click="view.setSort(SYMBOL_SORT_KEY)"
                @contextmenu.prevent="openFieldsMenu($event)">
              symbol
              <span v-if="sortByPid === SYMBOL_SORT_KEY" class="sort-ind">
                {{ sortDesc ? '▼' : '▲' }}
              </span>
            </th>
            <template v-for="pid in visiblePatterns" :key="pid">
              <th v-if="fieldCountFor(pid) > 0"
                  class="col-pattern"
                  :colspan="fieldCountFor(pid)"
                  :data-pattern-pid="pid">
                {{ pid }}
              </th>
            </template>
          </tr>
          <tr class="hdr-field">
            <template v-for="pid in visiblePatterns" :key="pid">
              <th v-if="visibleFields.has('num')"
                  :data-col-pid="pid" data-col-field="num"
                  class="col col-num"
                  @click="view.setSort(`${pid}_num`)"
                  @contextmenu.prevent="openFieldsMenu($event)">
                num
                <span v-if="sortByPid === `${pid}_num`" class="sort-ind">
                  {{ sortDesc ? '▼' : '▲' }}
                </span>
              </th>
              <th v-if="visibleFields.has('fr')"
                  :data-col-pid="pid" data-col-field="fr"
                  class="col col-fr"
                  @click="view.setSort(`${pid}_fr`)"
                  @contextmenu.prevent="openFieldsMenu($event)">
                fr
                <span v-if="sortByPid === `${pid}_fr`" class="sort-ind">
                  {{ sortDesc ? '▼' : '▲' }}
                </span>
              </th>
            </template>
          </tr>
        </thead>
        <tbody ref="tbodyEl">
          <tr v-if="topPad > 0" class="vpad" :style="{ height: topPad + 'px' }">
            <td colspan="99"></td>
          </tr>
          <tr v-for="row in visibleRows" :key="row.symbol"
              :class="{ active: row.symbol === symbol }">
            <td class="sym" :data-symbol="row.symbol"
                @click="view.selectSymbol(row.symbol)">{{ row.symbol }}</td>
            <template v-for="cell in row.cells" :key="cell.pid">
              <td v-if="view.isColumnVisible(cell.pid, 'num')"
                  :data-cell-pid="cell.pid" data-cell-field="num"
                  :data-symbol="row.symbol"
                  :class="['col col-num', { matched: cell.matched }]"
                  @click="view.selectSymbol(row.symbol)">
                {{ cell.num == null ? '—' : cell.num }}
              </td>
              <td v-if="view.isColumnVisible(cell.pid, 'fr')"
                  :data-cell-pid="cell.pid" data-cell-field="fr"
                  :data-symbol="row.symbol"
                  :class="['col col-fr', { matched: cell.matched }]"
                  @click="view.selectSymbol(row.symbol)">
                {{ cell.fr == null ? '—' : fmt(cell.fr) }}
              </td>
            </template>
          </tr>
          <tr v-if="botPad > 0" class="vpad" :style="{ height: botPad + 'px' }">
            <td colspan="99"></td>
          </tr>
        </tbody>
      </table>
    </div>

    <div v-if="fieldsMenu.open" class="field-menu"
         :style="{ left: fieldsMenu.x + 'px', top: fieldsMenu.y + 'px' }"
         @click.stop>
      <label>
        <input type="checkbox" data-field="num"
               :checked="visibleFields.has('num')"
               @change="view.toggleField('num')" />
        num
      </label>
      <label>
        <input type="checkbox" data-field="fr"
               :checked="visibleFields.has('fr')"
               @change="view.toggleField('fr')" />
        fr
      </label>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, onBeforeUnmount, reactive, ref, watch, nextTick } from 'vue'
import { storeToRefs } from 'pinia'
import { useViewStore, SYMBOL_SORT_KEY } from '../stores/view'
const view = useViewStore()
const { scanFile, symbol, preview, previewEnabled, previewLoading, previewError,
        patternIds, sortedRows, filteredSortedRows, sortByPid, sortDesc,
        visiblePatterns, visibleFields } = storeToRefs(view)

const canRefresh = computed(() =>
  previewEnabled.value && !!preview.value && !previewLoading.value
  && preview.value?.symbol === symbol.value)

function fmt(v: number | null): string {
  if (v == null) return '—'
  const pct = (v * 100).toFixed(1)
  return v >= 0 ? `+${pct}%` : `${pct}%`
}
function onToggle(e: Event) {
  void view.setPreviewEnabled((e.target as HTMLInputElement).checked)
}
function onCloseError() { view.clearPreview() }

// ── field menu ─────────────────────────────────────────────────────
const fieldsMenu = reactive({ open: false, x: 0, y: 0 })
function openFieldsMenu(evt: MouseEvent) {
  const MENU_W = 100
  const MENU_H = 64
  const x = Math.min(evt.clientX, window.innerWidth - MENU_W - 8)
  const y = Math.min(evt.clientY, window.innerHeight - MENU_H - 8)
  fieldsMenu.open = true
  fieldsMenu.x = x
  fieldsMenu.y = y
}
function onDocClick(e: MouseEvent) {
  if (!fieldsMenu.open) return
  const t = e.target as HTMLElement
  if (!t.closest('.field-menu')) fieldsMenu.open = false
}
function onDocKey(e: KeyboardEvent) {
  if (e.key === 'Escape') fieldsMenu.open = false
}

// ── 虚拟滚动 ───────────────────────────────────────────────────────
const ROW_H = 26
const OVERSCAN = 8
const listEl  = ref<HTMLElement | null>(null)
const tableWrapEl = ref<HTMLElement | null>(null)
const tableEl = ref<HTMLElement | null>(null)
const tbodyEl = ref<HTMLElement | null>(null)
const startIdx = ref(0)
const endIdx   = ref(50)

const visibleRows = computed(() => filteredSortedRows.value.slice(startIdx.value, endIdx.value))
const topPad = computed(() => startIdx.value * ROW_H)
const botPad = computed(() => Math.max(0, (filteredSortedRows.value.length - endIdx.value) * ROW_H))

// 每 pid 的 sub-cell 数(colspan 用):所有 pid 同 shape,忽略参数,返回全局 visibleFields 数
const fieldCountFor = (_pid: string) => visibleFields.value.size

function recalc() {
  const ct = tableWrapEl.value, tb = tbodyEl.value
  if (!ct || !tb) return
  const N = filteredSortedRows.value.length
  if (N === 0) { startIdx.value = 0; endIdx.value = 0; return }
  const lr = ct.getBoundingClientRect()
  const tr = tb.getBoundingClientRect()
  const hiddenAbove = Math.max(0, lr.top - tr.top)
  const viewportH = ct.clientHeight
  const first = Math.floor(hiddenAbove / ROW_H)
  const last  = Math.ceil((hiddenAbove + viewportH) / ROW_H)
  startIdx.value = Math.max(0, first - OVERSCAN)
  endIdx.value   = Math.min(N, last + OVERSCAN)
}

let ro: ResizeObserver | null = null
onMounted(() => {
  recalc()
  if (typeof ResizeObserver !== 'undefined') {
    ro = new ResizeObserver(() => recalc())
    if (tableWrapEl.value) ro.observe(tableWrapEl.value)
  }
  document.addEventListener('click', onDocClick, true)
  document.addEventListener('keydown', onDocKey, true)
})
onBeforeUnmount(() => {
  ro?.disconnect()
  document.removeEventListener('click', onDocClick, true)
  document.removeEventListener('keydown', onDocKey, true)
})

watch([filteredSortedRows, scanFile], () => { void nextTick(recalc) })
</script>

<style scoped>
.list { overflow: hidden; height: 100%; display: flex; flex-direction: column; position: relative;
        --hdr-row-h: 24px; }
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
.table-wrap { flex: 1; overflow: auto; }
table.multi { width: max-content; border-collapse: collapse; font-size: 12px; table-layout: fixed; }
table.multi th, table.multi td { padding: 4px 6px; border-bottom: 1px solid #f1f5f9; text-align: left;
                                  vertical-align: top; box-sizing: border-box; }
table.multi thead tr.hdr-pattern th {
  position: sticky; top: 0; background: #fff; z-index: 3;
}
table.multi thead tr.hdr-field th {
  position: sticky; top: var(--hdr-row-h); background: #fff; z-index: 3;
}
table.multi thead tr.hdr-pattern th.sym {
  position: sticky; top: 0; left: 0; background: #fff; z-index: 4;
}
table.multi thead tr.hdr-pattern th.col-pattern {
  text-align: center;
  font-weight: 600;
  border-bottom: 1px solid #e5e7eb;
  white-space: nowrap;
  padding: 2px 4px;
}
table.multi th.sym, table.multi td.sym { width: 60px; position: sticky; left: 0; z-index: 2; background: #fff; }
table.multi th.col-num, table.multi td.col-num { width: 46px; text-align: right; }
table.multi th.col-fr,  table.multi td.col-fr  { width: 64px; text-align: right; }
table.multi th.sym, table.multi th.col { cursor: pointer; user-select: none; word-break: break-all; overflow-wrap: anywhere; }
table.multi th.sym:hover, table.multi th.col:hover { background: #f1f5f9; }
table.multi .sort-ind { color: #2563eb; margin-left: 2px; }
table.multi tbody td { height: 26px; line-height: 18px;
                       white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
table.multi tbody tr.vpad td { padding: 0; border: 0; height: inherit; }
table.multi td.sym { font-weight: 600; cursor: pointer; }
table.multi td.col { cursor: pointer; background: #fafafa; }
table.multi td.col.matched { background: #dcfce7; }
table.multi tr.active td { background: #1d4ed8; color: #fff; }
table.multi tr.active td.col.matched { background: #1d4ed8; }

.field-menu {
  position: fixed;
  z-index: 100;
  min-width: 100px;
  background: #fff;
  border: 1px solid #cbd5e1;
  box-shadow: 0 4px 12px rgba(0,0,0,0.1);
  padding: 6px 8px;
  font-size: 12px;
}
.field-menu label { display: flex; align-items: center; gap: 6px; cursor: pointer; padding: 3px 0; }
.field-menu input { cursor: pointer; }
</style>
