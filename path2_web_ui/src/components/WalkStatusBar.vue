<template>
  <div class="walk-bar" data-testid="walk-bar">
    <span class="cell c-kind" data-testid="sel-kind" title="what is selected"><span class="lb">{{ L.kind }}</span>
      <span v-if="info" class="kind">{{ info.kind }}</span><span v-else class="na">{{ NA }}</span></span>
    <span class="cell c-node" data-testid="sel-node" :title="tip('the node it belongs to', info?.node)">
      <span class="lb">{{ L.node }}</span><span :class="{ na: !info?.node }">{{ info?.node ?? NA }}</span></span>
    <span class="cell c-date" data-testid="sel-date" :title="tip('its day, or its start→end', info?.date)">
      <span class="lb">{{ L.date }}</span><span :class="{ na: !info?.date }">{{ info?.date ?? NA }}</span></span>
    <span class="cell c-name" data-testid="sel-name" :title="tip('its name: sample letter and judgment, or feature name', info?.name)">
      <span class="lb">{{ L.name }}</span><span :class="{ na: !info?.name, user: !!info?.name && userNamed }">{{ info?.name ?? NA }}</span></span>
    <span class="cell c-diff" data-testid="sel-diff"
          :title="tip('how it differs from the others on the same day: the first part that differs, and where it ends', info?.diff)">
      <span class="lb">{{ L.diff }}</span><span :class="{ na: !info?.diff }">{{ info?.diff ?? NA }}</span></span>
    <span ref="inEl" class="cell c-in" data-testid="sel-in"
          :title="tip('what it belongs to, outermost first; the last one is where Esc goes back to', inFull)">
      <span class="lb">{{ L.in }}</span><span :class="{ na: !inFull }">{{ inShown ?? NA }}</span></span>
    <span class="cell c-day" data-testid="sel-day" :title="dayTip">
      <kbd :class="{ off: !dayText }">{{ KEY.pos }}</kbd><span :class="{ na: !dayText }">{{ dayText ?? NA }}</span></span>
    <span class="cell c-stack" data-testid="sel-stack" :title="stackTip">
      <kbd :class="{ off: !stackText }">{{ KEY.stack }}</kbd><span :class="{ na: !stackText }">{{ stackText ?? NA }}</span></span>
    <span v-if="view.shiftPairPending" class="cell c-pair" data-testid="walk-pair"
          title="pair query: 1 of 2 events picked; Shift+click a second event">pair 1/2</span>
    <span class="cell c-esc" data-testid="sel-esc" :title="escTip"><kbd :class="{ off: !escActive }">Esc</kbd></span>
    <span v-if="feedback" class="cell c-fb">
      <button type="button" class="fb-open" data-testid="sel-feedback" data-feedback-opener
              :class="{ off: feedback === 'off', on: feedback === 'open' }" :disabled="feedback === 'off'"
              :aria-pressed="feedback === 'open'" :title="FB_TIP[feedback]"
              @mousedown.prevent @click="emit('feedback')">feedback</button>
    </span>
  </div>
</template>

<script setup lang="ts">
// 副图上方的显示栏:选中的那一个(stores/view.ts 的 selInfo)按维度拆成九格,位置和写法永远不变——
//   kind(选中的是什么)、node、date、name、diff(是哪一个)、in(属于什么,最后一节就是 Esc 退到的地方)、
//   ← / → 与 ↑ / ↓ 两个键槽(按了会去哪:`into buys ×11` 是进去,`buys 1/11` 是在同一层的第几个)、Esc。
// 不适用的格照占位置,写灰色 `—`,键帽画灰;进行到一半的 Shift 配对另占一格 `pair 1/2`。
// compare 下最右多一个 feedback 按钮:对选中的那一个打开反馈面板(同 Enter),面板开着时再点是关;
// 选中的东西不能作答(或没选中、app 没跑完)时灰、点不了。开关由图表组件(KlineChart.vue)接。
// 在 compare / app 下常驻(不常驻的话每点一下主图伸缩一次)。窄的时候先省 in 最外面的几节(悬停看全)。
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useViewStore } from '../stores/view'
import { useAnnotationStore } from '../stores/annotation'
import { useFeedbackStore } from '../stores/feedback'
import { WALK_KEY_LABEL as KEY, type WalkFeedbackState } from './walkKey'
import { BAR_LABELS as L, PATH_SEP, SEL_NA as NA, SEL_NONE as NONE, slotText } from '../render/selSnapshot'

defineProps<{ feedback?: WalkFeedbackState }>()
const emit = defineEmits<{ (e: 'feedback'): void }>()
const FB_TIP: Record<WalkFeedbackState, string> = {
  on: 'give feedback on what is selected (Enter)',
  off: 'select a buy day, a hit on it, a family of hits, or a feedback to give feedback on it',
  open: 'close the feedback panel (Esc)',
}

const view = useViewStore()
const ann = useAnnotationStore()
const fb = useFeedbackStore()

const info = computed(() => view.selInfo)
/** name 那格是用户起的名字(框、node 的特征名)时,按「用户内容」的样子写;样本的字母与判断、空值 none 是程序固定词 */
const userNamed = computed(() => (info.value?.kind === 'box' || info.value?.kind === 'node') && info.value.name !== NONE)
const dayText = computed(() => (info.value ? slotText(info.value.day) : null))
const stackText = computed(() => (info.value ? slotText(info.value.stack) : null))

// in:由外到内;放不下时从最外一节起省成 `…›`
const inEl = ref<HTMLElement | null>(null)
const inChars = ref(400)
const widthOf = (s: string): number => [...s].reduce((n, ch) => n + (ch.charCodeAt(0) > 0x2e7f ? 2 : 1), 0)
const inFull = computed(() => (info.value?.in.length ? info.value.in.join(PATH_SEP) : null))
const inShown = computed(() => {
  const segs = info.value?.in ?? []
  if (segs.length === 0) return null
  const avail = inChars.value - (L.in.length + 2)
  let parts = segs
  let text = parts.join(PATH_SEP)
  while (widthOf(text) > avail && parts.length > 1) {
    parts = parts.slice(1)
    text = `…›${PATH_SEP.slice(2)}${parts.join(PATH_SEP)}`
  }
  return text
})
let ro: ResizeObserver | null = null
onMounted(() => {
  const el = inEl.value
  if (!el || typeof ResizeObserver === 'undefined') return
  const probe = document.createElement('span')
  probe.textContent = '0000000000'
  probe.style.cssText = 'position:absolute;visibility:hidden;white-space:pre'
  el.appendChild(probe)
  const cw = probe.getBoundingClientRect().width / 10
  el.removeChild(probe)
  const measure = () => { if (cw > 0) inChars.value = Math.floor(el.clientWidth / cw) }
  ro = new ResizeObserver(measure)
  ro.observe(el)
  measure()
})
onBeforeUnmount(() => { ro?.disconnect(); ro = null })

const tip = (what: string, value: string | null | undefined): string => (value ? `${what}: ${value}` : `${what} (not applicable)`)
function slotTip(key: string, text: string | null, moves: string): string {
  if (!text) return `${key}: nothing to go to from here`
  return text.startsWith('into ')
    ? `${key} goes into them (${text.slice(5)}); ${moves}`
    : `${key} goes to the previous / next one on this level (${text}); ${moves}`
}
const dayTip = computed(() => slotTip(KEY.pos, dayText.value, 'the vertical line moves'))
const stackTip = computed(() => slotTip(KEY.stack, stackText.value, 'the vertical line stays on the same day'))
const escActive = computed(() => !!info.value || !!fb.panel || (view.annotating && !!ann.tool) || view.shiftPairPending)
const escTip = computed(() => {
  if (fb.panel) return 'Esc: close the feedback panel'
  if (view.annotating && ann.tool) return 'Esc: turn off the tool'
  if (view.shiftPairPending) return 'Esc: cancel the pair query'
  if (info.value) return `Esc: ${info.value.esc}`
  return 'Esc: nothing to go back from'
})
</script>

<style scoped>
/* 滚动容器外的独立条件行,位于 divider 与 sub-outer 之间;compare / app 下常驻,高度固定,canvas 内容绝对位置不动。
   九格固定宽度、固定顺序(in 占余下的宽度),格之间一道细竖线。程序固定文字:等宽、黑字;不适用:灰;键名用细边小键帽。 */
.walk-bar {
  display: flex;
  height: 18px;
  line-height: 18px;
  padding: 0 4px;
  font-size: 12px;
  font-family: ui-monospace, "JetBrains Mono", "DejaVu Sans Mono", Consolas, monospace;
  color: #111111;
  background: #eef0f3;
  border-radius: 3px;
  user-select: none;
  flex-shrink: 0;
  white-space: nowrap;
  overflow: hidden;
}
.cell {
  position: relative;
  flex: 0 0 auto;
  box-sizing: content-box;
  padding: 0 6px;
  overflow: hidden;
  text-overflow: ellipsis;
  cursor: default;
}
.cell + .cell { border-left: 1px solid #b9bfc8; }
.c-kind { width: 18ch; }
.c-node { width: 15ch; }
.c-date { width: 28ch; }
.c-name { width: 17ch; }
.c-diff { width: 24ch; }
.c-in { flex: 1 1 20ch; min-width: 20ch; }
.c-day { width: 21ch; }
.c-stack { width: 22ch; }
.c-pair { width: 9ch; }
.c-esc { width: 5ch; }
.c-fb { padding: 0 2px 0 6px; }
.fb-open {
  font: inherit;
  line-height: 14px;
  padding: 0 5px;
  border: 1px solid #9aa1ab;
  border-radius: 3px;
  background: #ffffff;
  color: #111111;
  cursor: pointer;
}
.fb-open.on { border: 1px solid #111111; box-shadow: inset 0 0 0 1px #111111; font-weight: 700; }
.fb-open.off { color: #6b7078; border-color: #c3c8d0; background: #eef0f3; cursor: default; }
.lb { margin-right: 1ch; }
.na { color: #6b7078; }
.kind {
  display: inline-block;
  line-height: 12px;
  padding: 0 4px;
  background: #ffffff;
  border: 2px solid #111111;
  border-radius: 2px;
  font-weight: 700;
}
.user {
  font-family: system-ui, "Noto Sans CJK SC", sans-serif;
  background: #dde1e7;
  padding: 0 3px;
  border-radius: 2px;
}
kbd {
  font-family: inherit;
  font-size: 11px;
  line-height: 13px;
  padding: 0 3px;
  margin-right: 1ch;
  border: 1px solid #9aa1ab;
  border-radius: 3px;
  background: #ffffff;
  color: #111111;
}
kbd.off { color: #6b7078; border-color: #c3c8d0; background: #eef0f3; }
</style>
