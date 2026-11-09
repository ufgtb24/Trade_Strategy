<template>
  <div v-if="p" ref="root" class="fb-panel" data-testid="feedback-panel" :data-target="p.target"
       :data-editing="p.editingId ?? ''" :style="{ left: `${pos.x}px`, top: `${pos.y}px` }">
    <div class="ann-hdr">
      <span class="ann-biz" data-testid="feedback-symbol" title="symbol">{{ p.symbol }}</span>
      <span class="ann-sym" data-testid="feedback-span"
            title="start – end: the app's buys in this range are what this feedback is about">{{ spanText }}</span>
      <span class="ann-sym" data-testid="feedback-target" :title="TARGET_HINT[p.target]">{{ p.target }}</span>
      <span class="ann-grow" />
      <template v-if="p.editingId">
        <button type="button" class="ann-btn" data-testid="feedback-redraw"
                title="drag a new range on the chart; the answer, note and segments come along and replace this feedback's range"
                @mousedown.prevent @click="redraw">redraw</button>
        <button type="button" class="ann-btn" data-testid="feedback-delete" title="delete this feedback now"
                @mousedown.prevent @click="fb.remove(p.editingId!)">delete</button>
      </template>
    </div>
    <div v-if="fb.panelPosInside" class="fb-line">
      <span class="ann-sym" data-testid="feedback-pos-inside"
            title="a pos sample of the current pattern on this symbol falls in this range; saving is still allowed">pos sample inside</span>
    </div>
    <div class="ann-kv fb-kv">
      <span class="ann-k" title="neg: the app should not buy here (say why in note); off_pattern: it buys, but some parts do not look like the pattern (pick them, or say why)">answer</span>
      <div class="ann-row">
        <button v-for="a in ANSWERS" :key="a" type="button" :class="['ann-btn', { on: p.answer === a }]"
                :data-testid="`feedback-answer-${a}`" :title="ANSWER_HINT[a]"
                @mousedown.prevent @click="pick(a)">{{ a }}</button>
      </div>

      <template v-if="p.answer === 'off_pattern'">
        <span class="ann-k" title="the parts that do not look like the pattern: nodes the app's buys here are bound to, and their child nodes; pick any number">segments</span>
        <div class="ann-row" data-testid="feedback-segments">
          <button v-for="n in fb.panelSegments" :key="n" type="button"
                  :class="['ann-btn', 'fb-seg', { on: segs.includes(n), gone: !known.has(n) }]"
                  data-testid="feedback-segment" :data-node="n" :title="segTitle(n)"
                  @mousedown.prevent @click="fb.toggleSegment(n)"
                  @mouseenter="emit('hover-segment', n)" @mouseleave="emit('hover-segment', null)">
            <span>{{ n }}</span><span v-if="featureOf(n)" class="ann-biz fb-feat">{{ featureOf(n) }}</span>
          </button>
          <span v-if="!fb.panelSegments.length" class="ann-nil">none</span>
        </div>
      </template>

      <template v-if="p.answer">
        <span class="ann-k" :title="p.answer === 'neg' ? 'why the app should not buy here; required' : 'why it does not look like the pattern; optional when segments are picked'">note</span>
        <input ref="noteEl" class="ann-input" data-testid="feedback-note" :value="p.note ?? ''"
               :placeholder="p.answer === 'neg' ? 'required' : 'optional'"
               @input="fb.setNote(($event.target as HTMLInputElement).value)" />
      </template>
    </div>
    <div v-if="shownProblems.length" class="fb-line" data-testid="feedback-problems">
      <span class="ann-k" title="missing before it can be saved">need</span>
      <span v-for="q in shownProblems" :key="q" class="ann-sym" :data-problem="q" :title="PROBLEM_HINT[q]">{{ PROBLEM_TEXT[q] }}</span>
    </div>
    <div v-if="reason" class="fb-line">
      <span class="ann-sym" data-testid="feedback-blocked" :title="REASON_HINT[reason]">{{ reason }}</span>
    </div>
    <div v-if="p.answer" class="ann-hdr fb-foot">
      <span class="ann-grow" />
      <button type="button" class="ann-btn" data-testid="feedback-save" title="save (Enter); Esc closes without saving"
              @mousedown.prevent @click="trySave">save</button>
    </div>
  </div>
</template>

<script setup lang="ts">
/**
 * 反馈(spec 6.13)的作答面板:compare 下点 ▼ / 点一族 / 点反馈记号 / 用 feedback 工具拖一段后,浮在点击处
 * (拖选时是松开处),越出视口就翻边。挂在 KlineChart.vue,状态全在 stores/feedback.ts 的 panel(这里只是它的样子)。
 *
 * - 页头:股票、日期范围、target(point / family / range);改一条已有的反馈时多 redraw、delete;
 * - 范围里有当前 pattern 的正样本时多一行 pos sample inside(不拦);
 * - 初始只有 neg / off_pattern 两个按钮。点 neg 展开 note 并把光标放进去;点 off_pattern 展开分段按钮
 *   (按钮文字同 band 表头:node 名等宽 + 对到它的用户特征名浅灰底;悬停写 mapping 里这个 node 的原话、
 *   并让父组件把对应 band 加亮)与可选的 note;
 * - 不抢焦点:打开时不 focus 任何东西,按钮按下不夺焦点(@mousedown.prevent),只有点 neg 才把光标放进 note;
 *   同一天几个 hit 时 ←/→ 还要用来挑;
 * - 按键:开着时在 window 捕获阶段截下 Enter(保存;焦点在面板按钮上也是保存)与 Esc(只关面板:不清选中、不熄工具),
 *   截下后不再往下传;输入法组字中不截(判定见 ./feedbackPanel.ts 的 panelKeyAction);
 * - 点面板外就关(不存):document 上按下鼠标即关。监听在每次打开后 setTimeout(0) 才挂上,打开它的那次点击、
 *   拖选松手后浏览器补派的 click 都碰不到它;点到另一个 ▼ / 族 / 记号时先关旧的、图表的点击再开新的;
 * - 保存不了时标出缺什么(试过保存之后才标);app 还在跑(这只股票的现算结果还没回来)、没跑成等存不进去的原因
 *   随时写在面板里,免得按了 Enter 看不出为什么没存。
 */
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useFeedbackStore } from '../stores/feedback'
import { useAnnotationStore } from '../stores/annotation'
import { useViewStore } from '../stores/view'
import { useAppLinkStore } from '../stores/appLink'
import type { FeedbackAnswer, FeedbackTarget } from '../annotate/model'
import type { FeedbackProblem } from '../annotate/feedback'
import { panelKeyAction, placePanel, type Pt } from './feedbackPanel'

defineProps<{
  /** node 对到的用户特征名(同 band 表头里写的);没有为 null */
  featureOf: (node: string) => string | null
}>()
const emit = defineEmits<{
  /** 鼠标移到某个分段按钮上(node),或移开(null):父组件把对应 band 加亮 */
  (e: 'hover-segment', node: string | null): void
}>()

const fb = useFeedbackStore()
const ann = useAnnotationStore()
const view = useViewStore()
const appLink = useAppLinkStore()

const ANSWERS: FeedbackAnswer[] = ['neg', 'off_pattern']
const ANSWER_HINT: Record<FeedbackAnswer, string> = {
  neg: 'the app should not buy here; say why in note',
  off_pattern: 'it buys, but some parts do not look like the pattern; pick them below or say why',
}
const TARGET_HINT: Record<FeedbackTarget, string> = {
  point: 'one buy day',
  family: 'one family of hits: from its first to its last buy day',
  range: 'a range dragged on the chart',
}
const PROBLEM_TEXT: Record<FeedbackProblem, string> = {
  answer: 'answer', note: 'note', segments_or_note: 'segments | note', segments: 'segments',
  range: 'range', after_train_end: 'range', point: 'range', family_start: 'family_start',
}
const PROBLEM_HINT: Record<FeedbackProblem, string> = {
  answer: 'pick neg or off_pattern',
  note: 'neg needs a note',
  segments_or_note: 'off_pattern needs segments or a note',
  segments: 'segments must be distinct',
  range: 'start must not be after end',
  after_train_end: 'end must not be after the end of the training range',
  point: 'a point is a single day',
  family_start: 'a family needs its start date',
}
type Reason = 'app running' | 'app failed' | 'no app_ver' | 'no pattern' | 'not saved'
const REASON_HINT: Record<Reason, string> = {
  'app running': 'the app is still running on this symbol; save after it finishes',
  'app failed': 'could not run the app on this symbol, so this feedback cannot be saved',
  'no app_ver': 'the app run did not report its version, so this feedback cannot be saved',
  'no pattern': 'pick a current pattern first',
  'not saved': 'not saved; reload the page and try again',
}

const p = computed(() => fb.panel)
const segs = computed(() => p.value?.segments ?? [])
const spanText = computed(() => (p.value ? (p.value.start === p.value.end ? p.value.start
                                                                          : `${p.value.start} – ${p.value.end}`) : ''))
/** 当前拓扑里有的 node(记录里留着、当前 app 已没有的分段按钮另标) */
const known = computed(() => new Set((view.effectivePattern?.topology.nodes ?? []).map(n => n.node_id)))
function segTitle(n: string): string {
  if (!known.value.has(n)) return 'not in the current app'
  return appLink.mapping?.notes?.[n] ?? ''
}

// 试过保存之后才标缺什么;每打开一次清掉
const tried = ref(false)
const failed = ref(false)
const shownProblems = computed<FeedbackProblem[]>(() => (tried.value ? fb.problems : []))
/** 存不进去、又不是面板里缺东西的原因:随时写出来(app 还在跑等),试过保存仍没存时兜底写 not saved。 */
const reason = computed<Reason | null>(() => {
  const cur = p.value
  if (!cur) return null
  const run = view.linkedRun
  if (!run || run.symbol !== cur.symbol) return appLink.runStatus === 'load_failed' ? 'app failed' : 'app running'
  if (!run.scan?.app_ver) return 'no app_ver'
  if (ann.currentPattern === null) return 'no pattern'
  return failed.value && !fb.problems.length ? 'not saved' : null
})

async function pick(a: FeedbackAnswer) {
  fb.setAnswer(a)
  failed.value = false
  if (a !== 'neg') return
  await nextTick()
  noteEl.value?.focus()
}

function trySave() {
  tried.value = true
  failed.value = !fb.save()
}

function redraw() {
  if (fb.startRedraw()) ann.tool = 'feedback'
}

// ── 位置:浮在点击处,越出视口就翻边 ──
const root = ref<HTMLElement | null>(null)
const noteEl = ref<HTMLInputElement | null>(null)
const at = (): Pt => ({ x: p.value?.x ?? 0, y: p.value?.y ?? 0 })
const viewport = () => ({ w: window.innerWidth, h: window.innerHeight })
const pos = ref<Pt>(placePanel(at(), { w: 0, h: 0 }, viewport()))
function place() {
  const el = root.value
  const r = el?.getBoundingClientRect()
  pos.value = placePanel(at(), { w: r?.width ?? 0, h: r?.height ?? 0 }, viewport())
}

// ── 点面板外就关:每次打开后隔一轮才挂上 ──
let armTimer: ReturnType<typeof setTimeout> | null = null
function onDocDown(e: MouseEvent) {
  const t = e.target as Node | null
  if (root.value && t && root.value.contains(t)) return
  fb.close()
}
function disarm() {
  if (armTimer) { clearTimeout(armTimer); armTimer = null }
  document.removeEventListener('mousedown', onDocDown, true)
}
function arm() {
  disarm()
  armTimer = setTimeout(() => {
    armTimer = null
    document.addEventListener('mousedown', onDocDown, true)
  }, 0)
}

// ── 按键:Enter 保存、Esc 关面板 ──
function editable(el: HTMLElement | null): boolean {
  return !!el && (el.tagName === 'INPUT' || el.tagName === 'TEXTAREA' || el.tagName === 'SELECT' || el.isContentEditable)
}
function onKey(e: KeyboardEvent) {
  const t = e.target instanceof HTMLElement ? e.target : null
  const act = panelKeyAction(e, editable(t) && !(root.value?.contains(t) ?? false))
  if (!act) return
  e.preventDefault()
  e.stopPropagation()
  if (act === 'close') fb.close()
  else trySave()
}

// 关旧开新(组件不卸载)时同步重挂外部点击的监听、清掉保存提示、重新定位
watch(() => fb.opens, () => {
  tried.value = false
  failed.value = false
  arm()
  pos.value = placePanel(at(), { w: 0, h: 0 }, viewport())
  void nextTick(place)
}, { flush: 'sync' })
// 展开了 note、分段按钮,面板变高:重新看要不要翻边
watch(() => [p.value?.answer, fb.panelSegments.length], () => { void nextTick(place) })

onMounted(() => {
  arm()
  place()
  window.addEventListener('keydown', onKey, true)
})
onBeforeUnmount(() => {
  disarm()
  window.removeEventListener('keydown', onKey, true)
  emit('hover-segment', null)
})
</script>

<style src="./annotationPanel.css"></style>

<style scoped>
.fb-panel {
  position: fixed; z-index: 1000; min-width: 260px; max-width: 460px; padding: 8px 10px;
  background: #fff; border: 1px solid var(--line-strong); border-radius: 4px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.18); color: var(--ink);
}
.fb-kv { grid-template-columns: 64px 1fr; }
.fb-line { display: flex; align-items: center; gap: 6px; margin: 0 0 6px; }
.fb-foot { margin: 6px 0 0; }
.fb-seg { display: inline-flex; align-items: center; gap: 4px; }
.fb-seg.gone { border-style: dashed; }
.fb-feat { font-family: system-ui, sans-serif; font-weight: 400; }
</style>
