<template>
  <section class="rally-list" data-testid="rally-list">
    <span v-if="state !== 'ready'" class="status" data-testid="rally-status"
          :title="STATUS_HINT[state]">{{ state }}</span>
    <table v-else>
      <thead>
        <tr>
          <th v-for="k in RALLY_SORT_KEYS" :key="k" :data-testid="`rally-sort-${k}`"
              :aria-sort="sortKey === k ? (desc ? 'descending' : 'ascending') : 'none'"
              :title="COLUMN_HINT[k]" @click="sortBy(k)">
            {{ k }}<span class="arrow">{{ sortKey === k ? (desc ? '▼' : '▲') : '' }}</span>
          </th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="it in rows" :key="`${it.symbol}@${it.date}`"
            :class="{ current: isCurrent(it) }" data-testid="rally-row"
            :data-symbol="it.symbol" :data-date="it.date"
            :title="`peak_date ${it.peak_date} · rel ${it.rel.toFixed(2)}`"
            @click="open(it)">
          <td><span class="chip">{{ it.symbol }}</span></td>
          <td class="num">{{ it.date }}</td>
          <td class="num">{{ formatRise(it.rise) }}</td>
        </tr>
      </tbody>
    </table>
  </section>
</template>

<script setup lang="ts">
/**
 * 顶栏 rally 打开的大涨段清单:训练段里的大涨段,按 symbol / date / rise 排(点表头切换,再点反向)。
 * 点一行:打开那只股票、落在 annotate,图停在那段涨之前、同时看得见那段涨(图窗取后端给的 view_start..view_end)。
 * 清单第一次打开时向后端要(后端首次整池算一遍约半分钟),之后留在本组件里。
 * 看过哪几行不记:只把当前打开的那一行标出来,换一行就换标记。
 */
import { computed, onMounted, ref } from 'vue'
import { storeToRefs } from 'pinia'
import { getRally } from '../api'
import { useViewStore } from '../stores/view'
import type { RallyItem } from '../types'
import { RALLY_SORT_KEYS, formatRise, sortRally, type RallySortKey } from '../annotate/rallyList'

const emit = defineEmits<{ close: [] }>()
const view = useViewStore()
const { symbol, viewWindow } = storeToRefs(view)

const STATUS_HINT = {
  loading: '正在取大涨段清单(第一次要整池算一遍,约半分钟)',
  load_failed: '没取到大涨段清单',
  empty: '训练段里没有够得上门槛的大涨段',
} as const
const COLUMN_HINT: Record<RallySortKey, string> = {
  symbol: '股票代码',
  date: '涨前那天(收盘后决定、次日开盘买入)',
  rise: '观察期里拿得到的涨幅(跌破止损线就截住)',
}

const items = ref<RallyItem[]>([])
const state = ref<'loading' | 'load_failed' | 'empty' | 'ready'>('loading')
const sortKey = ref<RallySortKey>('rise')
const desc = ref(true)
const rows = computed(() => sortRally(items.value, sortKey.value, desc.value))

onMounted(async () => {
  try {
    items.value = await getRally()
    state.value = items.value.length ? 'ready' : 'empty'
  } catch {
    state.value = 'load_failed'
  }
})

function sortBy(k: RallySortKey) {
  if (sortKey.value === k) desc.value = !desc.value
  else { sortKey.value = k; desc.value = k === 'rise' }
}

function isCurrent(it: RallyItem): boolean {
  return symbol.value === it.symbol && viewWindow.value?.start === it.view_start
    && viewWindow.value?.end === it.view_end
}

function open(it: RallyItem) {
  view.openSymbol(it.symbol, { start: it.view_start, end: it.view_end })
  emit('close')
}
</script>

<style scoped>
/* 字体与色值见 App.vue 的 :root 变量。表头、状态是程序固定文字(等宽);行里是数据(正常字体,代码加浅灰底)。
   悬停底色取比代码浅灰底深一档的 --line-soft,白底上看得出 */
.rally-list {
  max-height: 60vh; overflow: auto; background: #fff; color: var(--ink);
  border: 1px solid var(--line-strong); border-radius: 3px; box-shadow: 0 2px 8px rgb(0 0 0 / 12%);
}
.status { display: block; padding: 8px 12px; font-family: var(--mono); font-size: 12px; }
table { border-collapse: collapse; font-size: 13px; }
th {
  position: sticky; top: 0; padding: 4px 12px; background: var(--bar-bg); border-bottom: 1px solid var(--line);
  font-family: var(--mono); font-size: 12px; font-weight: normal; text-align: left; cursor: pointer; user-select: none;
}
.arrow { display: inline-block; width: 1em; margin-left: 2px; }
td { padding: 2px 12px; white-space: nowrap; }
td.num { font-variant-numeric: tabular-nums; }
tbody tr { cursor: pointer; }
tbody tr:hover { background: var(--line-soft); }
tbody tr.current { outline: 2px solid var(--ink); outline-offset: -2px; }
.chip { padding: 0 4px; border-radius: 2px; background: var(--chip-bg); }
</style>
