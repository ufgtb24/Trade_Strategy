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
                title="drag a new range on the chart; the note and nodes come along and replace this feedback's range"
                @mousedown.prevent @click="redraw">redraw</button>
        <button type="button" class="ann-btn" data-testid="feedback-delete" title="delete this feedback now"
                @mousedown.prevent @click="fb.remove(p.editingId!)">delete</button>
      </template>
    </div>
    <div v-if="p.editingId" class="fb-line" data-testid="feedback-status-line">
      <span class="ann-k" title="does the current app still buy in this range">status</span>
      <span :class="status ? 'ann-sym' : 'ann-nil'" data-testid="feedback-status"
            :title="statusTip">{{ status?.status ?? 'null' }}</span>
      <span v-if="tag" class="ann-k fb-tag" data-testid="feedback-tag" :title="tagHint(tag)">{{ tag }}</span>
    </div>
    <div v-if="fb.panelPosInside" class="fb-line">
      <span class="ann-sym" data-testid="feedback-pos-inside"
            title="a pos sample of the current pattern on this symbol falls in this range; saving is still allowed">pos sample inside</span>
    </div>
    <div class="ann-kv fb-kv">
      <template v-if="fb.panelIssues.length">
        <span class="ann-k" :title="ISSUES_TITLE">issues</span>
        <div class="fb-issues" data-testid="feedback-issues">
          <button v-for="g in fb.panelIssues" :key="g.key" type="button"
                  :class="['fb-issue', { on: fb.panelIssue?.key === g.key }]"
                  data-testid="feedback-issue" :data-key="g.key" :data-places="g.rows.length" :title="ISSUE_HINT"
                  @mousedown.prevent @click="fb.pickIssue(g.key)">
            <span v-for="n in g.nodes" :key="n" class="ann-sym fb-chip">{{ n }}</span>
            <span v-if="g.note" class="ann-biz fb-issue-note" :title="g.note">{{ g.note }}</span>
            <span class="ann-grow" />
            <span class="ann-sym fb-places" title="places sharing this issue">places {{ g.rows.length }}</span>
          </button>
        </div>
      </template>

      <span class="ann-k" :title="NODES_TITLE">nodes</span>
      <div class="ann-row" data-testid="feedback-nodes">
        <button v-for="n in fb.panelNodes" :key="n" type="button"
                :class="['ann-btn', 'fb-node', { on: picked.includes(n), gone: !known.has(n) }]"
                data-testid="feedback-node" :data-node="n" :title="nodeTitle(n)"
                @mousedown.prevent @click="toggleNode(n)"
                @mouseenter="emit('hover-node', n)" @mouseleave="emit('hover-node', null)">
          <span>{{ n }}</span><span v-if="featureOf(n)" class="ann-biz fb-feat">{{ featureOf(n) }}</span>
        </button>
        <span v-if="!fb.panelNodes.length" class="ann-nil">none</span>
      </div>

      <span class="ann-k" :title="NOTE_TITLE">note</span>
      <textarea ref="noteEl" class="ann-area fb-note" data-testid="feedback-note" rows="1" :value="p.note ?? ''"
                placeholder="required"
                @input="fb.setNote(($event.target as HTMLTextAreaElement).value)" />
    </div>
    <div v-if="shownProblems.length || shownChoice" class="fb-line" data-testid="feedback-problems">
      <span class="ann-k" title="missing before it can be saved">need</span>
      <span v-for="q in shownProblems" :key="q" class="ann-sym" :data-problem="q" :title="PROBLEM_HINT[q]">{{ PROBLEM_TEXT[q] }}</span>
      <span v-if="shownChoice" class="ann-sym" data-problem="choice"
            title="this issue is shared and you changed it: pick all or only this">all | only this</span>
    </div>
    <div v-if="reason" class="fb-line">
      <span class="ann-sym" data-testid="feedback-blocked" :title="REASON_HINT[reason]">{{ reason }}</span>
    </div>
    <!-- 连着的 issue 还有别的处、内容又改了:save 换成二选一,点哪个就按哪个存 -->
    <div v-if="fb.panelNeedsChoice" class="ann-hdr fb-foot" data-testid="feedback-share">
      <span class="ann-sym" data-testid="feedback-share-count" :title="SHARE_HINT">shared by {{ fb.panelPlaces }} places</span>
      <span class="ann-grow" />
      <button type="button" class="ann-btn" data-testid="feedback-share-all"
              title="change every place of this issue to the note and nodes written here"
              @mousedown.prevent @click="trySave('all')">all</button>
      <button type="button" class="ann-btn" data-testid="feedback-share-only"
              title="save only this place, as a new issue of its own; the other places keep what they have"
              @mousedown.prevent @click="trySave('only_this')">only this</button>
    </div>
    <div v-else class="ann-hdr fb-foot">
      <span class="ann-grow" />
      <button type="button" class="ann-btn" data-testid="feedback-save" title="save (Enter); Shift+Enter breaks a line in note; Esc closes without saving"
              @mousedown.prevent @click="trySave(null)">save</button>
    </div>
  </div>
</template>

<script setup lang="ts">
/**
 * 反馈(spec 6.13)的作答面板:compare 下点 ▼ / 点一族 / 点反馈记号 / 用 feedback 工具拖一段后,浮在点击处
 * (拖选时是松开处),越出视口就翻边。挂在 KlineChart.vue,状态全在 stores/feedback.ts 的 panel(这里只是它的样子)。
 *
 * - 页头:股票、日期范围、target(point / family / range);改一条已有的反馈时多 redraw、delete;
 * - 改一条已有的反馈时页头下多一行 status:当前 app 在这段里还买不买(matched / unmatched,还没取到写灰字
 *   null,悬停写取不到的原因),接口给了会话原因标签的后面照着挂(同侧栏 feedback 页,悬停写这个取值的意思)。悬停提示
 *   有的内容面板里都有了,所以面板开着时副图不弹悬停提示(KlineChart.vue);
 * - 范围里有当前 pattern 的正样本时多一行 pos sample inside(不拦);
 * - 一打开就是完整的面板,没有「先选答案」这一步。键值几行从上到下:
 *   · issues:当前 pattern 已有的 issue(几处反馈共享的同一份内容:note 与点出的 node;跨股票),最近用过的在前,
 *     多了在框里滚动(约五条,待验证);每条写点出的 node、note(用户写的,浅灰底,最多两行)与处数 places n。
 *     点一条 = 这一处和它共享:note、node 填成它的,那条加黑边;再点一次不再共享(内容留着)。没有可挑的就不出这一行;
 *   · nodes:node 按钮,可多选,可以一个都不点,意思是「问题落在这一块上」(按钮文字同 band 表头:node 名等宽 +
 *     对到它的用户特征名浅灰底;悬停写 mapping 里这个 node 的原话、并让父组件把对应 band 加亮;记录里有、
 *     当前 app 已没有的排最后、虚线框);没有可点的写灰字 none;
 *   · note:必填(占位字 required);多行文本区,宽度固定,长文字自动换行、随内容长高,到上限
 *     (./feedbackPanel.ts 的 NOTE_MAX_H)后在框里滚动;
 * - 以前存下的带 answer(可能还带 dag)的记录照样打得开:只预填它的 note 与 nodes,answer 与 dag 不显示;
 *   没写 note 的要先补一句才能存;
 * - 连着的 issue 还有别的处、这里又改了 note / node 时,页脚的 save 换成 `shared by n places`(n 含这一处)
 *   与 all / only this 两个按钮:all 各处一起改,only this 只存这一处、另立成新 issue。这时 Enter 不存,
 *   need 一行提示 all | only this;内容没变、或那个 issue 只有这一处时照常 save,不问;
 * - 不抢焦点:打开时不 focus 任何东西,按钮按下不夺焦点(@mousedown.prevent);同一天几个 hit 时 ←/→ 还要用来挑。
 *   点任一 node 按钮(点上或点掉)后把光标放进 note(接着多选不受妨碍);挑 issue 不动焦点(挑完按 Enter 就能存);
 * - 按键:开着时在 window 捕获阶段截下 Enter(保存;焦点在面板按钮上、在 note 里也是保存)与 Esc(只关面板:
 *   不清选中、不熄工具),截下后不再往下传;Shift+Enter 不截(在 note 里换行);输入法组字中不截
 *   (判定见 ./feedbackPanel.ts 的 panelKeyAction);
 * - 点面板外就关(不存):document 上按下鼠标即关。监听在每次打开后 setTimeout(0) 才挂上,打开它的那次点击、
 *   拖选松手后浏览器补派的 click 都碰不到它;点到另一个 ▼ / 族 / 记号时先关旧的、图表的点击再开新的;
 * - 保存不了时标出缺什么(试过保存之后才标);app 还在跑(这只股票的现算结果还没回来)、没跑成等存不进去的原因
 *   随时写在面板里,免得按了 Enter 看不出为什么没存。条件都满足却没存成时兜底写 not saved,草稿一改就撤掉
 *   (否则补齐缺的东西之后它会一直挂着)。
 */
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useFeedbackStore } from '../stores/feedback'
import { useAnnotationStore } from '../stores/annotation'
import { useViewStore } from '../stores/view'
import { useAppLinkStore } from '../stores/appLink'
import type { FeedbackTarget } from '../annotate/model'
import { tagHint, type FeedbackProblem, type IssueChoice } from '../annotate/feedback'
import { UNMAPPED_EDGE } from '../render/annotateLanes'
import { NOTE_MAX_H, noteHeight, panelKeyAction, placePanel, type Anchor, type Pt } from './feedbackPanel'

defineProps<{
  /** node 对到的用户特征名(同 band 表头里写的);没有为 null */
  featureOf: (node: string) => string | null
}>()
const emit = defineEmits<{
  /** 鼠标移到某个 node 按钮上(给出 node),或移开(null):父组件把对应 band 加亮 */
  (e: 'hover-node', node: string | null): void
}>()

const fb = useFeedbackStore()
const ann = useAnnotationStore()
const view = useViewStore()
const appLink = useAppLinkStore()

const NODES_TITLE = "where the problem sits: nodes the app's buys here are bound to, and their child nodes; "
  + 'pick any number, or none if it is not on any one node or you cannot tell'
const NOTE_TITLE = 'what is wrong with buying here, in your own words; required'
const NOTE_MAX_CSS = `${NOTE_MAX_H}px`
const ISSUES_TITLE = 'issues already written under this pattern, across symbols, latest first; '
  + 'pick one to share it here: its nodes and note fill in'
const ISSUE_HINT = 'share this issue here; click again to stop sharing'
const SHARE_HINT = 'places using this issue, this one included; the note or nodes here differ from the other places'
const TARGET_HINT: Record<FeedbackTarget, string> = {
  point: 'one buy day',
  family: 'one family of hits: from its first to its last buy day',
  range: 'a range dragged on the chart',
}
const PROBLEM_TEXT: Record<FeedbackProblem, string> = {
  note: 'note', nodes: 'nodes',
  range: 'range', after_train_end: 'range', point: 'range', family_start: 'family_start',
}
const PROBLEM_HINT: Record<FeedbackProblem, string> = {
  note: 'write a note first',
  nodes: 'nodes must be distinct',
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
/** 正在改的这条反馈在当前 app 下的状态(新拖的还没存,没有) */
const status = computed(() => (p.value?.editingId ? fb.statusById[p.value.editingId] ?? null : null))
const statusTip = computed(() => (status.value ? status.value.reason ?? 'status under the current app' : 'status not read yet'))
/** 会话原因标签:接口给了就挂(挂不挂后端已判过) */
const tag = computed(() => status.value?.tag ?? null)
const picked = computed(() => p.value?.nodes ?? [])
const spanText = computed(() => (p.value ? (p.value.start === p.value.end ? p.value.start
                                                                          : `${p.value.start} – ${p.value.end}`) : ''))
/** 当前拓扑里有的 node(记录里留着、当前 app 已没有的 node 按钮另标) */
const known = computed(() => new Set((view.effectivePattern?.topology.nodes ?? []).map(n => n.node_id)))
function nodeTitle(n: string): string {
  if (!known.value.has(n)) return 'not in the current app'
  return appLink.mapping?.notes?.[n] ?? ''
}

// 试过保存之后才标缺什么;每打开一次清掉
const tried = ref(false)
const failed = ref(false)
const shownProblems = computed<FeedbackProblem[]>(() => (tried.value ? fb.problems : []))
/** 试过保存、别的都不缺、只差在 all / only this 里选一个 */
const shownChoice = computed(() => tried.value && !fb.problems.length && fb.panelNeedsChoice)
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

/** 点一个 node 按钮(点上或点掉),随后把光标放进 note:按钮按下不夺焦点,光标在 note 里不妨碍接着多选。 */
function toggleNode(n: string) {
  fb.toggleNode(n)
  noteEl.value?.focus()
}

/** 保存;choice 是点 all / only this 时给的。只差没选 all / only this 时不算「没存成」(need 一行已经说了)。 */
function trySave(choice: IssueChoice | null = null) {
  tried.value = true
  const waiting = !choice && !fb.problems.length && fb.panelNeedsChoice
  failed.value = !fb.save(choice) && !waiting
}

function redraw() {
  if (fb.startRedraw()) ann.tool = 'feedback'
}

// ── 位置:浮在点击处,越出视口就翻边 ──
const root = ref<HTMLElement | null>(null)
const noteEl = ref<HTMLTextAreaElement | null>(null)
const at = (): Anchor => ({ x: p.value?.x ?? 0, y: p.value?.y ?? 0, yUp: p.value?.yUp })
const viewport = () => ({ w: window.innerWidth, h: window.innerHeight })
const pos = ref<Pt>(placePanel(at(), { w: 0, h: 0 }, viewport()))
function place() {
  const el = root.value
  const r = el?.getBoundingClientRect()
  pos.value = placePanel(at(), { w: r?.width ?? 0, h: r?.height ?? 0 }, viewport())
}
/** note 文本区随内容长高(到上限为止,再多在框里滚动);量不出内容高(还没排版)时不动 */
function growNote() {
  const el = noteEl.value
  if (!el) return
  el.style.height = 'auto'
  if (el.scrollHeight > 0) el.style.height = `${noteHeight(el.scrollHeight, el.offsetHeight - el.clientHeight)}px`
}
/** 面板里的东西变了:note 先长到位,再看要不要翻边 */
function fit() { growNote(); place() }

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
  else trySave(null)
}

// 关旧开新(组件不卸载)时同步重挂外部点击的监听、清掉保存提示、重新定位
watch(() => fb.opens, () => {
  tried.value = false
  failed.value = false
  arm()
  pos.value = placePanel(at(), { w: 0, h: 0 }, viewport())
  void nextTick(fit)
}, { flush: 'sync' })
// 草稿改过了:上一次「试过保存没存成」的兜底提示(not saved)不再作数,等下一次保存再说
watch(() => [p.value?.note, p.value?.nodes, p.value?.link], () => { failed.value = false })
// node 按钮、issues 的条数变了,或 note 换行长高了,面板变高:重新看要不要翻边
watch(() => [fb.panelNodes.length, p.value?.note, fb.panelIssues.length, fb.panelNeedsChoice],
      () => { void nextTick(fit) })

onMounted(() => {
  arm()
  fit()
  window.addEventListener('keydown', onKey, true)
})
onBeforeUnmount(() => {
  disarm()
  window.removeEventListener('keydown', onKey, true)
  emit('hover-node', null)
})
</script>

<style src="./annotationPanel.css"></style>

<style scoped>
/* z-index 压过图上的悬停提示(ECharts 的 tooltip 挂在 body 上,z-index 9999999):点记号打开面板时鼠标还停在
   记号上,提示不压下去就盖住面板 */
.fb-panel {
  position: fixed; z-index: 10000000; min-width: 260px; max-width: 460px; padding: 8px 10px;
  background: #fff; border: 1px solid var(--line-strong); border-radius: 4px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.18); color: var(--ink);
}
.fb-kv { grid-template-columns: 64px 1fr; }
.fb-line { display: flex; align-items: center; gap: 6px; margin: 0 0 6px; }
.fb-foot { margin: 6px 0 0; }
.fb-tag { padding: 0 4px; border: 1.5px solid v-bind(UNMAPPED_EDGE); border-radius: 3px; background: #fff; cursor: help; }
.fb-node { display: inline-flex; align-items: center; gap: 4px; }
.fb-node.gone { border-style: dashed; }
/* 可挑的 issue:一条一行,多了在框里滚动;连着的那条黑边加左侧黑条(同按下的按钮:靠黑边认,不靠颜色) */
.fb-issues { display: flex; flex-direction: column; gap: 3px; max-height: 138px; overflow-y: auto; min-width: 0; }
.fb-issue {
  display: flex; flex-wrap: wrap; align-items: center; gap: 4px; padding: 2px 6px; text-align: left; cursor: pointer;
  border: 1px solid var(--line-strong); border-radius: 3px; background: #fff; color: var(--ink); font: inherit;
}
.fb-issue.on { border-color: var(--ink); box-shadow: inset 4px 0 0 var(--ink); padding-left: 9px; }
.fb-chip { padding: 0 3px; border: 1px solid var(--line-strong); border-radius: 3px; background: #fff; }
.fb-issue-note {
  display: -webkit-box; -webkit-box-orient: vertical; -webkit-line-clamp: 2; overflow: hidden;
  min-width: 0; white-space: pre-wrap;
}
.fb-places { white-space: nowrap; }
/* note:宽度占满这一格(不随文字变宽),高度由脚本随内容调,到上限后滚动 */
.fb-note {
  display: block; box-sizing: border-box; width: 100%; resize: none; overflow-y: auto;
  min-height: 0; max-height: v-bind(NOTE_MAX_CSS); white-space: pre-wrap; overflow-wrap: anywhere;
}
.fb-feat { font-family: system-ui, sans-serif; font-weight: 400; }
</style>
