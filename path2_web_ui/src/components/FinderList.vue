<template>
  <section class="finder-list" data-testid="finder-list">
    <nav class="tabs" role="tablist">
      <button v-for="t in FINDER_TABS" :key="t" type="button" role="tab"
              :class="['tab', { on: finder.tab === t }]" :aria-selected="finder.tab === t"
              :data-testid="`finder-tab-${t}`" :title="TAB_HINT[t]" @click="finder.setTab(t)">{{ t }}</button>
    </nav>

    <!-- 三页叠在同一格里,各是一个滚动区;没选上的只是看不见(visibility),照样撑宽度:左栏宽度按最宽的一页定,
         切页签时图不跟着变宽变窄。切页签、切到 scan 档都只藏不拆:滚动位置、rally 的排序都留着 -->
    <div class="pages">
      <div :style="shown('rally')" ref="rallyEl" class="page" data-testid="finder-page-rally">
        <span v-if="finder.rallyStatus !== 'ready'" class="status" data-testid="rally-status"
              :title="RALLY_HINT[finder.rallyStatus]">{{ rallyStatusText }}</span>
        <table v-else>
          <thead>
            <tr>
              <th v-for="k in RALLY_SORT_KEYS" :key="k" class="sortable" :data-testid="`rally-sort-${k}`"
                  :aria-sort="sortKey === k ? (desc ? 'descending' : 'ascending') : 'none'"
                  :title="RALLY_COLUMN_HINT[k]" @click="sortBy(k)">
                {{ k }}<span class="arrow">{{ sortKey === k ? (desc ? '▼' : '▲') : '' }}</span>
              </th>
              <th :title="MARK_HINT.patterns">patterns</th>
              <th :title="MARK_HINT.boxes">boxes</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(r, i) in rallyRows" :key="`${r.item.symbol}@${r.item.date}`"
                :class="{ current: i === rallyCur }" data-testid="rally-row"
                :data-symbol="r.item.symbol" :data-date="r.item.date" @click="openRally(r.item)">
              <td><span class="chip">{{ r.item.symbol }}</span></td>
              <td class="num" :title="`peak_date ${r.item.peak_date} · rel ${r.item.rel.toFixed(2)}`">{{ r.item.date }}</td>
              <td class="num">{{ formatRise(r.item.rise) }}</td>
              <td class="pats" data-testid="row-patterns" @mouseenter="showSamples($event, r.marks)" @mouseleave="hideSamples">
                <template v-for="p in r.marks.patterns" :key="p ?? ''">
                  <span v-if="p !== null" class="chip">{{ p }}</span><span v-else class="key">unsorted</span>
                </template>
              </td>
              <td class="num" data-testid="row-boxes">{{ r.marks.boxes || '' }}</td>
            </tr>
          </tbody>
        </table>
      </div>

      <div :style="shown('random')" ref="randomEl" class="page" data-testid="finder-page-random">
        <span v-if="!randomRows.length" class="status empty" data-testid="random-status" :title="RANDOM_EMPTY_HINT">empty</span>
        <table v-else>
          <thead>
            <tr>
              <th title="抽的先后">#</th>
              <th title="股票代码">symbol</th>
              <th title="抽到的这段图从哪天起">start</th>
              <th title="抽到的这段图到哪天止">end</th>
              <th :title="MARK_HINT.patterns">patterns</th>
              <th :title="MARK_HINT.boxes">boxes</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(r, i) in randomRows" :key="i" :class="{ current: i === randomCur }" data-testid="random-row"
                :data-symbol="r.draw.symbol" :data-start="r.draw.start" :data-end="r.draw.end" @click="openRandom(r.draw)">
              <td class="num">{{ i + 1 }}</td>
              <td><span class="chip">{{ r.draw.symbol }}</span></td>
              <td class="num">{{ r.draw.start }}</td>
              <td class="num">{{ r.draw.end }}</td>
              <td class="pats" data-testid="row-patterns" @mouseenter="showSamples($event, r.marks)" @mouseleave="hideSamples">
                <template v-for="p in r.marks.patterns" :key="p ?? ''">
                  <span v-if="p !== null" class="chip">{{ p }}</span><span v-else class="key">unsorted</span>
                </template>
              </td>
              <td class="num" data-testid="row-boxes">{{ r.marks.boxes || '' }}</td>
            </tr>
          </tbody>
        </table>
      </div>

      <div :style="shown('charts')" ref="chartsEl" class="page" data-testid="finder-page-charts">
        <span v-if="!ann.state" class="status" data-testid="charts-status">{{ ann.status }}</span>
        <span v-else-if="!chartRows.length" class="status empty" data-testid="charts-status"
              title="还没有标过的股票(画了框或放了样本的才算)">empty</span>
        <table v-else>
          <thead>
            <tr>
              <th title="股票代码">symbol</th>
              <th title="这只股票上的样本归哪些 pattern;悬停列出样本">patterns</th>
              <th title="正样本数">pos</th>
              <th title="负样本数">neg</th>
              <th title="这只股票上画的框数">boxes</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(r, i) in chartRows" :key="r.symbol" :class="{ current: i === chartsCur }" data-testid="charts-row"
                :data-symbol="r.symbol" @click="view.openFromFinder(r.symbol)">
              <td><span class="chip">{{ r.symbol }}</span></td>
              <td class="pats" data-testid="row-patterns" @mouseenter="showSamples($event, r)" @mouseleave="hideSamples">
                <template v-for="p in r.patterns" :key="p ?? ''">
                  <span v-if="p !== null" class="chip">{{ p }}</span><span v-else class="key">unsorted</span>
                </template>
              </td>
              <td class="num" data-testid="row-pos">{{ r.pos || '' }}</td>
              <td class="num" data-testid="row-neg">{{ r.neg || '' }}</td>
              <td class="num" data-testid="row-boxes">{{ r.boxes || '' }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- 悬停 patterns 一格:列出算进来的样本 -->
    <div v-if="hovered" class="samples-pop" data-testid="finder-samples"
         :style="{ right: `${hovered.right}px`, top: `${hovered.top}px` }">
      <table>
        <tr v-for="s in hovered.samples" :key="s.id" data-testid="finder-sample">
          <td class="num">{{ s.date }}</td>
          <td class="key">{{ s.judgment }}</td>
          <td><span v-if="s.pattern !== null" class="chip">{{ s.pattern }}</span><span v-else class="key">unsorted</span></td>
        </tr>
      </table>
    </div>
  </section>
</template>

<script setup lang="ts">
/**
 * 标注三档(annotate / compare / app)的左栏:找图清单,三页 rally / random / charts(状态在 stores/finder.ts,
 * 每行标过什么在 annotate/finderList.ts)。
 * - rally:训练段里的大涨段清单,按 symbol / date / rise 排(点表头切换,再点反向);每行写这张图窗里标过的
 *   pattern 名和框数,悬停 pattern 名一格列出算进来的样本;
 * - random:这次用顶栏 random 抽过的图,按抽的先后;每行同样写标过什么;
 * - charts:全部标过的股票,一只一行,写 pattern 名、正负样本数、框数。
 * 点一行,或在当前页签上按 PageUp / PageDown 挨个翻,换到那张图;换图不换档(view.openFromFinder)。
 * 焦点在任何输入框(单行、多行)、下拉框里时翻页键不切(守卫同 Delete 删框);scan 档里左栏换成扫描列表,
 * 这里的翻页键不接。不带「敲字母搜股票」,搜股票用顶栏 symbol。
 * 只把当前打开的那一行标出来,看过哪几行不记。
 */
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useViewStore } from '../stores/view'
import { useAnnotationStore } from '../stores/annotation'
import { FINDER_TABS, useFinderStore, type FinderTab, type RallyStatus } from '../stores/finder'
import { chartsBySymbol, chartsRows, marksInWindow, stepIndex, type Marks } from '../annotate/finderList'
import { RALLY_SORT_KEYS, formatRise, sortRally, type RallySortKey } from '../annotate/rallyList'
import type { RallyItem, RandomWindow, ViewWindow } from '../types'

const view = useViewStore()
const ann = useAnnotationStore()
const finder = useFinderStore()

const TAB_HINT: Record<FinderTab, string> = {
  rally: '训练段里的大涨段清单,点一行打开那段涨之前的图',
  random: '这次用顶栏 random 抽过的图,按抽的先后;刷新就清空',
  charts: '全部标过的股票(画了框或放了样本)',
}
const RALLY_HINT: Record<RallyStatus, string> = {
  idle: '还没取大涨段清单',
  loading: '正在取大涨段清单(第一次要整池算一遍,约半分钟)',
  load_failed: '没取到大涨段清单',
  empty: '训练段里没有够得上门槛的大涨段',
  ready: '',
}
const RALLY_COLUMN_HINT: Record<RallySortKey, string> = {
  symbol: '股票代码',
  date: '涨前那天(收盘后决定、次日开盘买入);悬停看最高点那天与相对涨幅',
  rise: '观察期里拿得到的涨幅(跌破止损线就截住)',
}
const MARK_HINT = {
  patterns: '这张图窗里的样本归哪些 pattern(样本日在图窗里才算);悬停列出样本',
  boxes: '和这张图窗有重叠的框数',
} as const
const RANDOM_EMPTY_HINT = '这次还没抽过图:按顶栏 random 抽一张(只记在本页,刷新就清空)'

/** 没选上的页:看不见、不接鼠标,但照样占位撑宽度。 */
function shown(t: FinderTab) {
  return finder.tab === t ? undefined : { visibility: 'hidden' as const }
}

const rallyStatusText = computed(() => (finder.rallyStatus === 'idle' ? 'loading' : finder.rallyStatus))

const byChart = computed(() => chartsBySymbol(ann.state))
const sortKey = ref<RallySortKey>('rise')
const desc = ref(true)
const rallyRows = computed(() => sortRally(finder.rally, sortKey.value, desc.value).map(item => ({
  item, marks: marksInWindow(byChart.value.get(item.symbol), { start: item.view_start, end: item.view_end }),
})))
const randomRows = computed(() => finder.draws.map(draw => ({
  draw, marks: marksInWindow(byChart.value.get(draw.symbol), draw),
})))
const chartRows = computed(() => chartsRows(ann.state))

function sortBy(k: RallySortKey) {
  if (sortKey.value === k) desc.value = !desc.value
  else { sortKey.value = k; desc.value = k === 'rise' }
}

/** 当前打开的是不是这只股票的这段图窗。 */
function isOpen(symbol: string, win: ViewWindow): boolean {
  return view.symbol === symbol && view.viewWindow?.start === win.start && view.viewWindow?.end === win.end
}
const rallyCur = computed(() => rallyRows.value.findIndex(r =>
  isOpen(r.item.symbol, { start: r.item.view_start, end: r.item.view_end })))
const randomCur = computed(() => randomRows.value.findIndex(r => isOpen(r.draw.symbol, r.draw)))
const chartsCur = computed(() => chartRows.value.findIndex(r => r.symbol === view.symbol))

function openRally(it: RallyItem) { view.openFromFinder(it.symbol, { start: it.view_start, end: it.view_end }) }
function openRandom(d: RandomWindow) { view.openFromFinder(d.symbol, d) }

// ── 悬停列出样本 ──
// 浮层右缘对齐这一格的右缘、挂在它下面:往左展开,留在左栏里,不盖住图
const hovered = ref<{ samples: Marks['samples']; right: number; top: number } | null>(null)
function showSamples(e: MouseEvent, m: Marks) {
  const cell = e.currentTarget as HTMLElement | null
  if (!cell || !m.samples.length) { hovered.value = null; return }
  const r = cell.getBoundingClientRect()
  hovered.value = { samples: m.samples, right: Math.max(0, window.innerWidth - r.right), top: r.bottom + 2 }
}
function hideSamples() { hovered.value = null }

// ── PageUp / PageDown 在当前页签里挨个翻 ──
const rallyEl = ref<HTMLElement | null>(null)
const randomEl = ref<HTMLElement | null>(null)
const chartsEl = ref<HTMLElement | null>(null)

/** 当前页签的行数、当前行、换到第 i 行、它的滚动区。 */
function currentPage(): { n: number; cur: number; open: (i: number) => void; el: HTMLElement | null } {
  if (finder.tab === 'rally') {
    return { n: finder.rallyStatus === 'ready' ? rallyRows.value.length : 0, cur: rallyCur.value,
             open: i => openRally(rallyRows.value[i].item), el: rallyEl.value }
  }
  if (finder.tab === 'random') {
    return { n: randomRows.value.length, cur: randomCur.value, open: i => openRandom(randomRows.value[i].draw),
             el: randomEl.value }
  }
  return { n: chartRows.value.length, cur: chartsCur.value, open: i => view.openFromFinder(chartRows.value[i].symbol),
           el: chartsEl.value }
}

/** 把第 i 行滚进视野(不被吸顶的表头盖住)。 */
function revealRow(page: HTMLElement | null, i: number) {
  const row = page?.querySelectorAll('tbody tr')[i] as HTMLElement | undefined
  if (!page || !row) return
  const head = page.querySelector('thead')?.getBoundingClientRect().height ?? 0
  const pr = page.getBoundingClientRect()
  const rr = row.getBoundingClientRect()
  if (rr.top < pr.top + head) page.scrollTop -= pr.top + head - rr.top
  else if (rr.bottom > pr.bottom) page.scrollTop += rr.bottom - pr.bottom
}

const EDITABLE = 'input, textarea, select, [contenteditable=""], [contenteditable="true"]'
function onPageKey(e: KeyboardEvent) {
  if (view.scanView) return
  if (e.key !== 'PageUp' && e.key !== 'PageDown') return
  if (e.ctrlKey || e.metaKey || e.altKey || e.shiftKey || e.isComposing) return
  const ae = document.activeElement as HTMLElement | null
  if (ae && ae.closest(EDITABLE)) return
  const page = currentPage()
  if (!page.n) return
  e.preventDefault()
  const next = stepIndex(page.n, page.cur, e.key)
  if (next === null) return
  page.open(next)
  revealRow(page.el, next)
}

onMounted(() => {
  void finder.loadRally()
  document.addEventListener('keydown', onPageKey)
})
onBeforeUnmount(() => document.removeEventListener('keydown', onPageKey))
</script>

<style scoped>
/* 字体与色值见 App.vue 的 :root 变量。页签、表头、状态是程序固定文字(等宽);行里是数据(正常字体),
   股票代码与用户起的 pattern 名加浅灰底;unsorted 是程序的词,等宽、不加底。
   悬停底色取比浅灰底深一档的 --line-soft,白底上看得出;当前打开的那行加黑框 */
.finder-list { display: flex; flex-direction: column; flex: 1; min-height: 0; background: #fff; color: var(--ink); }
.tabs {
  display: flex; gap: 12px; padding: 6px 8px 0; flex: none;
  background: #fff; border-bottom: 1px solid var(--line-soft);
}
/* 没选上的页签按「没选上的状态」用灰字,选中的加黑色下划线(同侧栏页签) */
.tab {
  padding: 2px 2px 4px; border: none; border-bottom: 2px solid transparent;
  background: none; color: var(--ink-off); cursor: pointer; font-family: var(--mono); font-size: 12px;
}
.tab.on { color: var(--ink); border-bottom-color: var(--ink); }
.pages { flex: 1; min-height: 0; display: grid; grid-template: minmax(0, 1fr) / auto; }
.page { grid-area: 1 / 1; min-height: 0; overflow: auto; }
.status { display: block; padding: 8px 12px; font-family: var(--mono); font-size: 12px; }
.status.empty { color: var(--ink-empty); }
table { border-collapse: collapse; font-size: 13px; }
th {
  position: sticky; top: 0; padding: 4px 8px; background: var(--bar-bg); border-bottom: 1px solid var(--line);
  font-family: var(--mono); font-size: 12px; font-weight: normal; text-align: left; white-space: nowrap;
}
th.sortable { cursor: pointer; user-select: none; }
.arrow { display: inline-block; width: 1em; margin-left: 2px; }
td { padding: 2px 8px; white-space: nowrap; }
td.num { font-variant-numeric: tabular-nums; }
td.pats > * + * { margin-left: 4px; }
tbody tr { cursor: pointer; }
tbody tr:hover { background: var(--line-soft); }
tbody tr.current { outline: 2px solid var(--ink); outline-offset: -2px; }
.chip { padding: 0 4px; border-radius: 2px; background: var(--chip-bg); }
.key { font-family: var(--mono); font-size: 12px; }
.samples-pop {
  position: fixed; z-index: 60; padding: 4px 6px; background: #fff; color: var(--ink);
  border: 1px solid var(--line-strong); border-radius: 3px; box-shadow: 0 2px 8px rgb(0 0 0 / 12%);
  font-size: 13px; pointer-events: none;
}
.samples-pop td { padding: 1px 6px; }
</style>
