<template>
  <div class="list" ref="listEl">
    <div v-if="scanFile" class="search-bar">
      <input ref="searchInputEl" type="text"
             data-testid="symbol-search"
             :value="symbolQuery"
             @input="onSearchInput"
             placeholder="搜索 symbol…"
             spellcheck="false" autocomplete="off" />
      <span class="count" data-testid="symbol-search-count">
        {{ filteredSortedRows.length }} / {{ sortedRows.length }}
      </span>
      <button v-if="symbolQuery" class="clear"
              data-testid="symbol-search-clear"
              @click="onClearSearch">×</button>
    </div>
    <div v-if="!scanFile" class="hint">未加载扫描结果</div>
    <div v-else class="table-wrap" ref="tableWrapEl" @scroll.passive="recalc">
      <table class="multi" ref="tableEl">
        <thead>
          <tr class="hdr-pattern" ref="hdrPatternEl">
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
                  :data-pattern-pid="pid"
                  @mouseenter="onPatternHover(pid, $event)"
                  @mouseleave="onPatternLeave">
                {{ pid }}
                <span class="hit-count" data-testid="pattern-hit-count">{{ patternHitCounts[pid] ?? 0 }}</span>
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
                r{{ scanFile?.scan.label_horizon }}
                <span v-if="sortByPid === `${pid}_fr`" class="sort-ind">
                  {{ sortDesc ? '▼' : '▲' }}
                </span>
              </th>
              <th v-if="visibleFields.has('fd')"
                  :data-col-pid="pid" data-col-field="fd"
                  class="col col-fd"
                  @click="view.setSort(`${pid}_fd`)"
                  @contextmenu.prevent="openFieldsMenu($event)">
                d{{ scanFile?.scan.label_horizon }}
                <span v-if="sortByPid === `${pid}_fd`" class="sort-ind">
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
          <template v-for="row in visibleRows" :key="row.symbol">
          <tr :class="{ active: row.symbol === symbol }">
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
              <td v-if="view.isColumnVisible(cell.pid, 'fd')"
                  :data-cell-pid="cell.pid" data-cell-field="fd"
                  :data-symbol="row.symbol"
                  :class="['col col-fd', { matched: cell.matched }]"
                  @click="view.selectSymbol(row.symbol)">
                {{ cell.fd == null ? '—' : fmt(cell.fd) }}
              </td>
            </template>
          </tr>
          <tr v-if="previewListRow && row.symbol === symbol"
              class="preview-row" data-testid="preview-list-row">
            <td class="sym preview-label">↳ 探索</td>
            <template v-for="cell in previewListRow.cells" :key="cell.pid">
              <td v-if="view.isColumnVisible(cell.pid, 'num')"
                  :data-cell-pid="cell.pid" data-cell-field="num"
                  class="col col-num">
                <template v-if="cell.filled">{{ cell.num == null ? '—' : cell.num }}</template>
              </td>
              <td v-if="view.isColumnVisible(cell.pid, 'fr')"
                  :data-cell-pid="cell.pid" data-cell-field="fr"
                  class="col col-fr">
                <template v-if="cell.filled">{{ cell.fr == null ? '—' : fmt(cell.fr) }}</template>
              </td>
              <td v-if="view.isColumnVisible(cell.pid, 'fd')"
                  :data-cell-pid="cell.pid" data-cell-field="fd"
                  class="col col-fd">
                <template v-if="cell.filled">{{ cell.fd == null ? '—' : fmt(cell.fd) }}</template>
              </td>
            </template>
          </tr>
          </template>
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
        r{{ scanFile?.scan.label_horizon }}
      </label>
      <label>
        <input type="checkbox" data-field="fd"
               :checked="visibleFields.has('fd')"
               @change="view.toggleField('fd')" />
        d{{ scanFile?.scan.label_horizon }}
      </label>
    </div>

    <PatternStatsTooltip v-if="hoveredStats"
                         :stats="hoveredStats"
                         :stats-drawdown="hoveredStatsDrawdown ?? undefined"
                         :first-passage-stats="hoveredFpStats ?? undefined"
                         class="hover-tooltip"
                         :style="{ left: tooltipX + 'px', top: tooltipY + 'px' }" />
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, onBeforeUnmount, reactive, ref, watch, nextTick } from 'vue'
import { storeToRefs } from 'pinia'
import { useViewStore, SYMBOL_SORT_KEY } from '../stores/view'
import PatternStatsTooltip from './PatternStatsTooltip.vue'
const view = useViewStore()
const { scanFile, symbol,
        patternIds, sortedRows, filteredSortedRows, sortByPid, sortDesc,
        visiblePatterns, visibleFields, symbolQuery, previewListRow,
        patternHitCounts } = storeToRefs(view)

const searchInputEl = ref<HTMLInputElement | null>(null)
function onSearchInput(e: Event) {
  view.setSymbolQuery((e.target as HTMLInputElement).value)
}
function onClearSearch() {
  view.clearSymbolQuery()
  searchInputEl.value?.focus()
}

function fmt(v: number | null): string {
  if (v == null) return '—'
  const pct = (v * 100).toFixed(1)
  return v >= 0 ? `+${pct}%` : `${pct}%`
}
// ── hdr-pattern hover → stats tooltip ─────────────────────────────
const hoveredPid = ref<string | null>(null)
const tooltipX = ref(0)
const tooltipY = ref(0)

const hoveredStats = computed(() => {
  if (!hoveredPid.value || !scanFile.value) return null
  return scanFile.value.per_pattern[hoveredPid.value]?.stats ?? null
})

// drawdown 分布与 forward_return stats 同 shape(T1 注入);老 scan file 无此字段 → null,
// PatternStatsTooltip 收到 undefined 不渲染 drawdown 块。
const hoveredStatsDrawdown = computed(() => {
  if (!hoveredPid.value || !scanFile.value) return null
  return scanFile.value.per_pattern[hoveredPid.value]?.stats_drawdown ?? null
})

// 首次穿越集合级统计(T3 注入);老 scan file 或 first_passage_enabled=False → null,
// PatternStatsTooltip 收到 undefined 不渲染首次穿越块。
const hoveredFpStats = computed(() => {
  if (!hoveredPid.value || !scanFile.value) return null
  return scanFile.value.per_pattern[hoveredPid.value]?.first_passage_stats ?? null
})

function onPatternHover(pid: string, evt: MouseEvent) {
  const th = evt.currentTarget as HTMLElement | null
  if (!th) return
  if (!scanFile.value?.per_pattern[pid]?.stats) return  // 无 stats 不挂
  const thRect = th.getBoundingClientRect()
  const TOOLTIP_W = 140
  const MARGIN = 8
  // viewport 坐标(position:fixed)· 溢出右边界则向左翻转对齐 th.right
  let x = thRect.left
  if (x + TOOLTIP_W + MARGIN > window.innerWidth) {
    x = Math.max(MARGIN, thRect.right - TOOLTIP_W)
  }
  tooltipX.value = x
  tooltipY.value = thRect.bottom + 2
  hoveredPid.value = pid
}

function onPatternLeave() {
  hoveredPid.value = null
}

// ── field menu ─────────────────────────────────────────────────────
const fieldsMenu = reactive({ open: false, x: 0, y: 0 })
function openFieldsMenu(evt: MouseEvent) {
  const MENU_W = 100
  const MENU_H = 90   // num/fr/fd 三项 + 上下 padding
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
  if (e.key !== 'Escape') return
  // 搜索框内的 Esc:非空清 query;已空 blur。优先级高于关字段菜单。
  if (document.activeElement === searchInputEl.value) {
    if (symbolQuery.value !== '') {
      view.clearSymbolQuery()
    } else {
      searchInputEl.value?.blur()
    }
    return
  }
  if (fieldsMenu.open) fieldsMenu.open = false
}

const CHAR_RE = /^[a-zA-Z0-9.\-]$/

function onGlobalCharKey(e: KeyboardEvent) {
  if (!scanFile.value) return
  if (e.ctrlKey || e.metaKey || e.altKey || e.shiftKey) return
  if (e.isComposing) return
  const ae = document.activeElement as HTMLElement | null
  // 活动元素守卫:焦点在 body 或列表面板内才劫持;对话框 / 其他面板一律放行
  if (ae !== null && ae !== document.body && !(listEl.value?.contains(ae))) return
  if (e.key.length !== 1 || !CHAR_RE.test(e.key)) return
  const input = searchInputEl.value
  if (!input) return
  if (ae === input) return  // 已 focus 在搜索框,让浏览器默认输入生效
  input.focus()
  view.setSymbolQuery(view.symbolQuery + e.key)
  e.preventDefault()
}

// ── 上/下 键切换股票 ────────────────────────────────────────────────
function scrollRowIntoView(index: number) {
  const wrap = tableWrapEl.value
  if (!wrap) return
  const stickyH = wrap.querySelector('thead')?.getBoundingClientRect().height ?? 0
  const rowTopInContent = stickyH + index * ROW_H
  const rowBotInContent = rowTopInContent + ROW_H
  if (wrap.scrollTop > rowTopInContent - stickyH) {
    wrap.scrollTop = rowTopInContent - stickyH
  } else if (wrap.scrollTop < rowBotInContent - wrap.clientHeight) {
    wrap.scrollTop = rowBotInContent - wrap.clientHeight
  }
}
function onArrowKey(e: KeyboardEvent) {
  if (e.key !== 'ArrowUp' && e.key !== 'ArrowDown') return
  if (e.ctrlKey || e.metaKey || e.altKey || e.shiftKey) return
  if (e.isComposing) return
  if (fieldsMenu.open) return
  // 搜索框 focus 时 ArrowUp/Down 仍切股(input 内光标已在末尾无意义)
  // 只保留 IME 守卫(顶部已有 e.isComposing)
  const rows = filteredSortedRows.value
  if (rows.length === 0) return

  e.preventDefault()

  const cur = rows.findIndex(r => r.symbol === symbol.value)
  const next = cur < 0
    ? 0
    : e.key === 'ArrowDown'
      ? Math.min(cur + 1, rows.length - 1)
      : Math.max(cur - 1, 0)
  if (rows[next].symbol === symbol.value) return
  view.selectSymbol(rows[next].symbol)
  scrollRowIntoView(next)
}

// ── 虚拟滚动 ───────────────────────────────────────────────────────
const ROW_H = 26
const OVERSCAN = 8
const listEl  = ref<HTMLElement | null>(null)
const tableWrapEl = ref<HTMLElement | null>(null)
const tableEl = ref<HTMLElement | null>(null)
const tbodyEl = ref<HTMLElement | null>(null)
const hdrPatternEl = ref<HTMLTableRowElement | null>(null)
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

// 把第一级表头(hdr-pattern)的实际高度写进 --hdr-row-h,让第二级 sticky 精确贴住其下沿。
// 硬编码 24px 与真实高度(padding+line-height+border)不符,滚动时会露出 1-3px 缝(数据行透过)。
// ⚠ 必须 Math.floor 而非 ceil:真实高度是子像素(如 28.7),ceil→29 让第二级 top=29 起画、
// 第一级底沿在 28.7 → 缝 0.3px(数据行透过) ← 反而制造缝隙。floor→28 让第二级 top=28 起画,
// 视觉上第二级顶部微微覆盖第一级底部 border,无缝、无可见 overlap。
// h===0 时(SSR/jsdom/首帧未测)保留 CSS 里 --hdr-row-h: 24px 的 fallback,不覆盖。
function syncHdrRowH() {
  const el = hdrPatternEl.value
  const host = listEl.value
  if (!el || !host) return
  const h = Math.floor(el.getBoundingClientRect().height)
  if (h > 0) host.style.setProperty('--hdr-row-h', h + 'px')
}

let ro: ResizeObserver | null = null
onMounted(() => {
  recalc()
  nextTick(syncHdrRowH)   // 初次同步(RO 也会立即触发一次,双保险防竞态)
  if (typeof ResizeObserver !== 'undefined') {
    ro = new ResizeObserver(() => { recalc(); syncHdrRowH() })
    if (tableWrapEl.value) ro.observe(tableWrapEl.value)
  }
  document.addEventListener('click', onDocClick, true)
  document.addEventListener('keydown', onDocKey, true)
  document.addEventListener('keydown', onArrowKey)
  document.addEventListener('keydown', onGlobalCharKey, true)   // capture 阶段,先于组件级 window keydown
})
// hdr-pattern tr 挂在 v-else(有 scanFile 时)分支下,mount 时可能不在 DOM;
// 一旦 scanFile 载入让 tr 出现,补:同步一次 + 让 RO 也观察它(字号/列宽变化跟随)。
watch(hdrPatternEl, (el) => {
  if (!el) return
  syncHdrRowH()
  ro?.observe(el)
})
onBeforeUnmount(() => {
  ro?.disconnect()
  document.removeEventListener('click', onDocClick, true)
  document.removeEventListener('keydown', onDocKey, true)
  document.removeEventListener('keydown', onArrowKey)
  document.removeEventListener('keydown', onGlobalCharKey, true)
})

watch([filteredSortedRows, scanFile], () => { void nextTick(recalc) })
</script>

<style scoped>
.list { overflow: hidden; height: 100%; display: flex; flex-direction: column; position: relative;
        --hdr-row-h: 24px; }
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
/* 命中股票数:11px 灰色常规字重,与 pid(12px/600/深色)分层,
   读起来是 pid 的附注而非名字的一部分。
   display:block 让它落到 pid 正下方独占一行 —— 数字不再计入行内宽度,
   列宽只由 pid 决定,这正是竖排要省的横向空间。
   外层 th 的 white-space:nowrap 保持不动:它保证两行各自不再内部折行。 */
table.multi thead tr.hdr-pattern th.col-pattern .hit-count {
  display: block;
  font-size: 11px;
  color: #64748b;
  font-weight: 400;
  line-height: 1.1;
}
table.multi th.sym, table.multi td.sym { width: 60px; position: sticky; left: 0; z-index: 2; background: #fff; }
table.multi th.col-num, table.multi td.col-num { width: 46px; text-align: right; }
table.multi th.col-fr,  table.multi td.col-fr  { width: 64px; text-align: right; }
table.multi th.col-fd,  table.multi td.col-fd  { width: 64px; text-align: right; }
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
/* 探索态现算对照行:淡黄底,区别于绿 matched / 蓝 active */
/* 探索态现算对照行:整行取 chip「探索 · Working Copy」的绿(ParamsChip .mode-explore:
   #10b981 底 / 白字 / 600)。与冻结行的浅绿(#dcfce7,matched)靠饱和度+白字区分,
   不靠色相 —— 色盲友好(浅黄 vs 浅绿会混,深绿满字白字不会)。border 呼应 chip 轮廓。 */
table.multi tr.preview-row td { background: #10b981; color: #ffffff; font-weight: 600; cursor: default; }
table.multi tr.preview-row td:first-child { border-left: 2px solid #047857; }
table.multi tr.preview-row td.sym.preview-label { color: #ffffff; font-weight: 600; }

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

.hover-tooltip {
  position: fixed;
  z-index: 100;
  pointer-events: none;
}

.search-bar { display: flex; align-items: center; gap: 6px;
              padding: 6px 10px; border-bottom: 1px solid #e5e7eb;
              background: #fff; }
.search-bar input { flex: 1; min-width: 0; padding: 3px 6px;
                    font-size: 12px; border: 1px solid #cbd5e1;
                    border-radius: 3px; }
.search-bar .count { font-size: 11px; color: #64748b; white-space: nowrap; }
.search-bar .clear { padding: 0 6px; font-size: 14px; line-height: 1;
                     border: 1px solid #cbd5e1; background: #fff;
                     cursor: pointer; border-radius: 3px; }
.search-bar .clear:hover { background: #f1f5f9; }
</style>
