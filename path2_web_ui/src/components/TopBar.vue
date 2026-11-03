<template>
  <header class="top-bar" data-testid="top-bar">
    <label class="grp">
      <span class="key">symbol</span>
      <input
        v-model="draft"
        class="symbol-input"
        data-testid="symbol-input"
        list="symbol-list"
        spellcheck="false" autocomplete="off"
        title="输入代码回车打开(训练段副本里的股票,图画到 2025-12-31)"
        @input="status = null"
        @keydown.enter.prevent="onEnter"
        @keydown.up.stop
        @keydown.down.stop
      />
      <datalist id="symbol-list">
        <option v-for="s in symbols" :key="s" :value="s" />
      </datalist>
    </label>
    <div class="grp">
      <button type="button" :class="['entry', { on: rallyOpen }]" data-testid="rally-button"
              :aria-expanded="rallyOpen" title="训练段里的大涨段清单,点一行打开那段涨之前的图"
              @click="rallyOpen = !rallyOpen">rally</button>
      <button type="button" class="entry" data-testid="random-button"
              title="从股票池 × 训练段随机给一段图" :disabled="randomStatus === 'loading'"
              @click="onRandom">random</button>
      <span v-if="randomStatus" class="status" data-testid="random-status"
            :title="RANDOM_HINT[randomStatus]">{{ randomStatus }}</span>
    </div>
    <div v-if="annotating" class="grp" data-testid="tool-group">
      <span class="key" title="what dragging on the chart does">tool</span>
      <button type="button" :class="['entry', { on: ann.tool === 'box' }]" data-testid="tool-box"
              title="drag on the chart to draw a box; drag a box edge on its lane to change it; click to select"
              @click="ann.tool = 'box'">box</button>
      <button type="button" :class="['entry', { on: ann.tool === 'point' }]" data-testid="tool-point"
              title="click a bar to place a sample there (current pattern, pos); switches back to box"
              @click="ann.tool = 'point'">point</button>
    </div>
    <div v-if="annotating" class="grp" data-testid="pattern-group">
      <span class="key" title="the current pattern: new samples go to it">pattern</span>
      <PatternPicker :value="ann.currentPattern" tid="top-pattern" title="the current pattern: new samples go to it"
                     @pick="ann.setCurrentPattern($event)" />
    </div>
    <div class="grp" data-testid="ref-group">
      <span class="key" title="reference layers computed by the system; off by default, off again when the symbol changes">ref</span>
      <label :class="['chk', { off: !refs.available }]"
             :title="refs.available ? 'peaks found by bo detection, as horizontal lines up to the bar that first breaks them'
                                    : 'only in annotate / compare, with a symbol open'">
        <input type="checkbox" data-testid="ref-peaks" :checked="refs.peaks" :disabled="!refs.available"
               @change="refs.setPeaks(($event.target as HTMLInputElement).checked)" />peaks
      </label>
      <span v-if="refs.status" class="status" data-testid="ref-status"
            :title="PEAKS_HINT[refs.status]">{{ refs.status }}</span>
    </div>
    <span v-if="status" class="status" data-testid="symbol-status"
          title="训练段副本里没有这只股票(2026 年才上市的不在列表里)">{{ status }}</span>
    <!-- v-show:关上再打开时,清单、排序与滚动位置都还在 -->
    <RallyList v-if="rallyMounted" v-show="rallyOpen" class="rally-pop" @close="rallyOpen = false" />
  </header>
</template>

<script setup lang="ts">
/**
 * 主视图顶栏:
 * - symbol:输入代码回车,不经扫描直接打开那只股票的图,落在 annotate。代码先对股票列表
 *   (训练段副本里有的股票)核一遍,不在列表里就报 not_found、不动当前的图。输入框平时显示当前打开的股票。
 * - rally:展开 / 收起大涨段清单(RallyList),点一行打开那段涨之前的图,落在 annotate。
 * - random:从股票池 × 训练段随机给一段图,落在 annotate,图停在那一段上。
 * - tool(annotate 下):box = 在图上拖出框;point = 点一根 K 线放样本,放完自动回到 box。
 * - pattern(annotate 下):当前 pattern,新放的样本归它;下拉里有 unsorted · n 和 + new。
 * - ref:参照层,先只有 peaks(stores/refLayers.ts)。只在 annotate / compare 下可用,别的模式下变灰;默认关,换股票自动关。
 * 看过什么一律不记。
 */
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { storeToRefs } from 'pinia'
import { getRandom, getSymbols } from '../api'
import { useViewStore } from '../stores/view'
import { useAnnotationStore } from '../stores/annotation'
import { useRefLayerStore, type PeaksStatus } from '../stores/refLayers'
import { resolveSymbolInput } from '../annotate/symbolInput'
import RallyList from './RallyList.vue'
import PatternPicker from './PatternPicker.vue'

const view = useViewStore()
const { symbol, annotating } = storeToRefs(view)
const ann = useAnnotationStore()
const refs = useRefLayerStore()
const PEAKS_HINT: Record<PeaksStatus, string> = {
  loading: 'loading the peaks of this symbol',
  load_failed: 'could not load the peaks',
  empty: 'bo detection found no peak in the training range of this symbol',
}

type RandomStatus = 'loading' | 'load_failed' | 'empty'
const RANDOM_HINT: Record<RandomStatus, string> = {
  loading: '正在取随机的一段图(第一次要整池算一遍,约半分钟)',
  load_failed: '没取到随机的一段图',
  empty: '股票池是空的',
}

const symbols = ref<string[] | null>(null)        // null:还没拿到或拿失败(此时交给后端判)
const symbolSet = computed(() => symbols.value ? new Set(symbols.value) : null)
const draft = ref(symbol.value ?? '')
const status = ref<'not_found' | null>(null)          // symbol 输入框的状态
const randomStatus = ref<RandomStatus | null>(null)
const rallyOpen = ref(false)
const rallyMounted = ref(false)                   // 第一次展开才向后端要清单

watch(symbol, (s) => { draft.value = s ?? ''; status.value = null; randomStatus.value = null })
watch(rallyOpen, (v) => { if (v) rallyMounted.value = true })

function onKeyDown(e: KeyboardEvent) {
  if (e.key === 'Escape' && rallyOpen.value) rallyOpen.value = false
}

onMounted(async () => {
  window.addEventListener('keydown', onKeyDown)
  try { symbols.value = await getSymbols() } catch { symbols.value = null }
})
onBeforeUnmount(() => window.removeEventListener('keydown', onKeyDown))

function onEnter() {
  const r = resolveSymbolInput(draft.value, symbolSet.value)
  if (r.kind === 'empty') return
  if (r.kind === 'not_found') { status.value = 'not_found'; return }
  status.value = null
  draft.value = r.symbol
  view.openSymbol(r.symbol)
}

async function onRandom() {
  rallyOpen.value = false
  randomStatus.value = 'loading'
  try {
    const w = await getRandom()
    randomStatus.value = null
    view.openSymbol(w.symbol, { start: w.start, end: w.end })
  } catch (e: any) {
    randomStatus.value = e?.status === 404 ? 'empty' : 'load_failed'
  }
}
</script>

<style scoped>
/* 字体与色值见 App.vue 的 :root 变量 */
.top-bar {
  position: relative;
  display: flex; align-items: center; gap: 6px 16px; flex-wrap: wrap;
  padding: 4px 10px; background: var(--bar-bg); border-bottom: 1px solid var(--line); color: var(--ink);
}
.grp { display: flex; align-items: center; gap: 6px; }
.key, .status, .entry { font-family: var(--mono); font-size: 12px; color: var(--ink); }
.status { padding: 0 6px; border: 1px solid var(--ink); border-radius: 3px; }
.symbol-input {
  width: 110px; padding: 2px 6px; font-size: 13px; color: var(--ink);
  border: 1px solid var(--line-strong); border-radius: 3px; background: #fff;
}
.entry {
  padding: 1px 8px; border: 1px solid var(--line-strong); border-radius: 3px; background: #fff; cursor: pointer;
}
.entry.on { border-color: var(--ink); box-shadow: inset 0 -2px 0 var(--ink); }
.entry:disabled { cursor: progress; }
.chk { display: flex; align-items: center; gap: 3px; font-family: var(--mono); font-size: 12px; color: var(--ink); cursor: pointer; }
.chk input { margin: 0; accent-color: var(--ink); }   /* 勾上是黑的:浏览器默认的蓝会被读成会话蓝 */
.chk.off { color: var(--ink-off); cursor: default; }
.rally-pop { position: absolute; top: 100%; left: 10px; z-index: 50; margin-top: 2px; }
</style>
