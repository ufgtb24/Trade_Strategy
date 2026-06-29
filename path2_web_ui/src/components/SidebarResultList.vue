<template>
  <div class="list" ref="listEl" @scroll.passive="recalc">
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
    <table v-else class="multi" ref="tableEl">
      <thead>
        <tr>
          <th class="sym" @click="view.setSort(SYMBOL_SORT_KEY)">
            symbol
            <span v-if="sortByPid === SYMBOL_SORT_KEY" class="sort-ind">
              {{ sortDesc ? '▼' : '▲' }}
            </span>
          </th>
          <th v-for="pid in patternIds" :key="pid"
              :data-col-pid="pid"
              class="col"
              @click="view.setSort(pid)">
            {{ pid }}
            <span v-if="sortByPid === pid" class="sort-ind">
              {{ sortDesc ? '▼' : '▲' }}
            </span>
          </th>
        </tr>
      </thead>
      <tbody ref="tbodyEl">
        <!-- 上 spacer:撑出 startIdx 行高度,代替真实 DOM -->
        <tr v-if="topPad > 0" class="vpad" :style="{ height: topPad + 'px' }">
          <td :colspan="totalCols"></td>
        </tr>
        <tr v-for="row in visibleRows" :key="row.symbol"
            :class="{ active: row.symbol === symbol }">
          <td class="sym" @click="view.selectSymbol(row.symbol)">{{ row.symbol }}</td>
          <td v-for="cell in row.cells" :key="cell.pid"
              :data-cell-pid="cell.pid"
              :class="['col', { matched: cell.matched }]"
              @click="view.selectSymbol(row.symbol)">
            {{ fmt(cell.max_ret) }}
          </td>
        </tr>
        <!-- 下 spacer -->
        <tr v-if="botPad > 0" class="vpad" :style="{ height: botPad + 'px' }">
          <td :colspan="totalCols"></td>
        </tr>
      </tbody>
    </table>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, onBeforeUnmount, ref, watch, nextTick } from 'vue'
import { storeToRefs } from 'pinia'
import { useViewStore, SYMBOL_SORT_KEY } from '../stores/view'
const view = useViewStore()
const { scanFile, symbol, preview, previewEnabled, previewLoading, previewError,
        patternIds, sortedRows, sortByPid, sortDesc } = storeToRefs(view)

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

// ── 虚拟滚动 ───────────────────────────────────────────────────────
// 4825+ 行场景下,只渲染视口内 ~30 行 + 两端各 OVERSCAN 行,排序 reorder 只动可见 DOM
const ROW_H = 26          // 固定行高,与 CSS .multi tbody td 一致
const OVERSCAN = 8        // 上下各预留几行,缓冲滚动
const listEl  = ref<HTMLElement | null>(null)
const tableEl = ref<HTMLElement | null>(null)
const tbodyEl = ref<HTMLElement | null>(null)
const startIdx = ref(0)
const endIdx   = ref(50)

const totalCols = computed(() => 1 + patternIds.value.length)
const visibleRows = computed(() => sortedRows.value.slice(startIdx.value, endIdx.value))
const topPad = computed(() => startIdx.value * ROW_H)
const botPad = computed(() => Math.max(0, (sortedRows.value.length - endIdx.value) * ROW_H))

function recalc() {
  const ct = listEl.value, tb = tbodyEl.value
  if (!ct || !tb) return
  const N = sortedRows.value.length
  if (N === 0) { startIdx.value = 0; endIdx.value = 0; return }
  // tbody 相对滚动容器视口顶部的偏移:正=tbody 尚未滚出顶部;负=已有内容滚出
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
  // jsdom 测试环境无 ResizeObserver,实运行环境有
  if (typeof ResizeObserver !== 'undefined') {
    ro = new ResizeObserver(() => recalc())
    if (listEl.value) ro.observe(listEl.value)
  }
})
onBeforeUnmount(() => { ro?.disconnect() })

// 数据变化(加载/排序/preview 切换)后重算窗口,clamp endIdx
watch([sortedRows, scanFile], () => { void nextTick(recalc) })
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
/* 列宽:sym 固定 60px,其余按 pattern 数等分剩余空间 — 长 pattern_id 折行不截断 */
table.multi { width: 100%; border-collapse: collapse; font-size: 12px; table-layout: fixed; }
table.multi th, table.multi td { padding: 4px 6px; border-bottom: 1px solid #f1f5f9; text-align: left;
                                  vertical-align: top; }
table.multi th.sym, table.multi td.sym { width: 60px; }
table.multi th.sym { cursor: pointer; user-select: none; }
table.multi th.sym:hover { background: #f1f5f9; }
table.multi th.col { cursor: pointer; user-select: none;
                     /* pattern_id 是唯一命名源,长 id 在列宽不足时按字符断行,不截断 */
                     word-break: break-all; overflow-wrap: anywhere; }
table.multi th.col:hover { background: #f1f5f9; }
table.multi .sort-ind { color: #2563eb; margin-left: 2px; }
/* 虚拟滚动:body 行强制固定行高,与 ROW_H 一致;单行不换行 */
table.multi tbody td { height: 26px; line-height: 18px; box-sizing: border-box;
                       white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
table.multi tbody tr.vpad td { padding: 0; border: 0; height: inherit; }
table.multi td.sym { font-weight: 600; cursor: pointer; }
table.multi td.col { cursor: pointer; text-align: right; background: #fafafa; }
table.multi td.col.matched { background: #dcfce7; }
tr.active { background: #eff6ff; }
</style>
