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
    <div class="grp" data-testid="mode-group">
      <span class="key" title="pressed = your choice; grayed = unavailable now">mode</span>
      <button type="button" :class="['entry', { on: mode === 'annotate' }]" data-testid="mode-annotate"
              title="your annotation only" @click="appLink.setMode('annotate')">annotate</button>
      <button type="button" :class="['entry', { on: mode === 'compare', off: !appLink.available }]"
              data-testid="mode-compare" :disabled="!appLink.available" :title="modeTitle('compare')"
              @click="appLink.setMode('compare')">compare</button>
      <button type="button" :class="['entry', { on: mode === 'app', off: !appLink.available && mode !== 'app' }]"
              data-testid="mode-app" :disabled="!appLink.available && mode !== 'app'" :title="modeTitle('app')"
              @click="mode !== 'app' && appLink.setMode('app')">app</button>
      <span v-if="linkedView && appLink.mapping" class="app-id" data-testid="linked-app"
            title="the app of the current pattern">{{ appLink.mapping.app }}</span>
      <span v-if="linkedView && appLink.runStatus" class="status" data-testid="app-status"
            :title="RUN_HINT[appLink.runStatus]">{{ appLink.runStatus }}</span>
    </div>
    <div class="grp" data-testid="tiers-group">
      <label :class="['chk', { off: !tiersOn }]"
             :title="tiersOn ? 'tier tags at the right end of gray event bars: qualified_only (dark gray), detected_only (light gray)'
                             : 'only in app / compare'">
        <input type="checkbox" data-testid="tiers" :checked="view.tiers" :disabled="!tiersOn"
               @change="view.setTiers(($event.target as HTMLInputElement).checked)" />tiers
      </label>
    </div>
    <div v-if="annotating" class="grp" data-testid="tool-group">
      <span class="key" title="what dragging on the chart does; none on: drag pans, click selects">tool</span>
      <button type="button" :class="['entry', { on: ann.tool === 'box' }]" data-testid="tool-box"
              title="on: drag on the chart to draw a box, or drag a box edge on its lane to change it; off after one use. Shift+B toggles, Esc turns off"
              @click="ann.toggleTool('box')">box</button>
      <button type="button" :class="['entry', { on: ann.tool === 'point' }]" data-testid="tool-point"
              title="on: click a bar to place a sample there (current pattern, pos); off after one use. Esc turns off"
              @click="ann.toggleTool('point')">point</button>
      <button v-if="mode === 'compare'" type="button" :class="['entry', { on: ann.tool === 'feedback' }]"
              data-testid="tool-feedback"
              title="on: drag across the chart to give feedback on the app's buys in that range; off after one use. Shift+F toggles, Esc turns off"
              @click="ann.toggleTool('feedback')">feedback</button>
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
 * - mode:annotate / compare / app。compare、app 只在当前 pattern 有 app(有一个能用的 mapping,stores/appLink.ts)
 *   且已经打开一只股票时可用,否则变灰;从扫描列表选股时是 app(扫描结果)。compare、现算的 app 下旁边写 app 的名字
 *   (不显示 mapping)。
 * - tiers:app、compare 下 event 灰条右端 qualified_only / detected_only 两种 tier tag 的开关,默认开;别的模式下变灰。
 * - symbol:输入代码回车,不经扫描直接打开那只股票的图,落在 annotate(compare 下留在 compare,rally、random 同)。代码先对股票列表
 *   (训练段副本里有的股票)核一遍,不在列表里就报 not_found、不动当前的图。输入框平时显示当前打开的股票。
 * - rally:展开 / 收起大涨段清单(RallyList),点一行打开那段涨之前的图,落在 annotate。
 * - random:从股票池 × 训练段随机给一段图,落在 annotate,图停在那一段上。
 * - tool(annotate、compare 下):默认都不亮,图上拖动是平移;box = 点亮后在图上拖出一个框或改一次框的起止;
 *   point = 点亮后点一根 K 线放样本;feedback(只在 compare 出现)= 点亮后在图上拖一段,对这段里 app 的买点作答
 *   (spec 6.13)。点亮一个只用一次,用完自动熄灭;再点一下、Esc 也熄灭;Shift+B 点亮 / 熄灭 box,Shift+F 点亮 / 熄灭 feedback。
 * - pattern(annotate 下):当前 pattern,新放的样本归它;下拉里有 unsorted · n 和 + new。
 * - ref:参照层,目前只有 peaks(stores/refLayers.ts)。只在 annotate / compare 下可用,别的模式下变灰;默认关,换股票自动关。
 * 看过什么一律不记。
 */
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { storeToRefs } from 'pinia'
import { getRandom, getSymbols } from '../api'
import { useViewStore } from '../stores/view'
import { useAnnotationStore } from '../stores/annotation'
import { useRefLayerStore, type PeaksStatus } from '../stores/refLayers'
import { useAppLinkStore, type RunStatus } from '../stores/appLink'
import { resolveSymbolInput } from '../annotate/symbolInput'
import RallyList from './RallyList.vue'
import PatternPicker from './PatternPicker.vue'

const view = useViewStore()
const { symbol, annotating, mode, linkedView } = storeToRefs(view)
const ann = useAnnotationStore()
const refs = useRefLayerStore()
const appLink = useAppLinkStore()
const tiersOn = computed(() => mode.value === 'app' || mode.value === 'compare')
const RUN_HINT: Record<RunStatus, string> = {
  loading: 'running the app of the current pattern on this symbol',
  load_failed: 'could not run the app of the current pattern on this symbol',
}
/** compare / app 按钮的悬停:能用时说这一档是什么;用不了时说为什么。 */
function modeTitle(m: 'compare' | 'app'): string {
  if (appLink.available) {
    return m === 'compare' ? `annotation with the output of app ${appLink.mapping!.app} overlaid; still editable`
      : `output of app ${appLink.mapping!.app} only, lanes by node`
  }
  if (m === 'app' && mode.value === 'app') return 'scan results'
  if (appLink.problem) return `the mapping of the current pattern cannot be used:\n${appLink.problem}`
  if (!appLink.mapping) return 'the current pattern has no app (no path2_apps/<app>/mapping.yaml names it)'
  return 'open a symbol first'
}
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
.entry.off { color: var(--ink-off); cursor: default; }   /* 变灰 = 现在用不了 */
.app-id { font-family: var(--mono); font-size: 12px; color: var(--ink); padding: 0 4px; }
.chk { display: flex; align-items: center; gap: 3px; font-family: var(--mono); font-size: 12px; color: var(--ink); cursor: pointer; }
.chk input { margin: 0; accent-color: var(--ink); }   /* 勾上是黑的:浏览器默认的蓝会被读成会话蓝 */
.chk.off { color: var(--ink-off); cursor: default; }
.rally-pop { position: absolute; top: 100%; left: 10px; z-index: 50; margin-top: 2px; }
</style>
