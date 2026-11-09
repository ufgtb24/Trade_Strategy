/**
 * 反馈(feedback,spec 6.13)在 compare 下的状态与作答面板。记录的读写走 stores/annotation.ts(saveFeedback /
 * deleteFeedback,标注的追加写法);取法与保存条件是 annotate/feedback.ts 的纯函数。
 *
 * 状态(statusById):当前 pattern 的全部反馈在当前 app 下是 matched / unmatched / lost,连同会话写的原因标签
 * tag 与画不画朱红 red,都照后端 GET /feedback/status 给的(朱红与否只在后端判一次)。只在 compare 下去取;
 * 重取的时机:
 * - 进入 compare、换当前 pattern;
 * - 反馈存进或删出标注文件之后(后端读结果里反馈的修改记录变了,等还没存完的动作都存完,ann.flushed());
 * - app 重跑之后(view.setLinkedRun 放进新的现算结果:换股票、换 app、切进 compare 都会重跑);
 * - 窗口重新拿到焦点(同 stores/appLink.ts 重读 mapping 的时机:会话改完 app 或会话账本,切回浏览器就生效)。
 * 同一轮里几处同时触发只取一次;连着取时只认最后一次的结果。loading 为真时侧栏显示 loading。
 *
 * 作答面板(panel,同时只开一个,浮在 x、y 处;组件在 components/FeedbackPanel.vue):
 * - open(at, 范围):点 ▼ / 点一族 / 拖选松手时打开。这只股票、当前 pattern 已有范围完全相同的反馈时直接打开
 *   那条(防重复);否则若有 redraw 带过来的答案(carry)且这次是拖出来的 range,用它预填、保存时覆盖原记录
 *   (拖出的范围恰好和 redraw 的那条原来一样时也走 carry;拖选一次就用掉 carry,落在别的已有反馈上时打开那条);
 *   open(at, {id}):点已有的记号,打开那条(预填,editingId 为它的编号)。盲看标记、不属于当前 pattern 的不打开。
 *   面板开着时再 open 就是关旧开新(switchTo 是它的别名),不存;
 * - setAnswer / setNote / toggleSegment 改草稿;切到 neg 时清掉已选分段;
 * - save():保存条件满足才存(存了就关面板),返回存没存;problems 是还缺什么(面板里标出来);
 * - startRedraw():把正在改的那条的答案、理由、分段记进 carry 并关面板,由调用方点亮 feedback 工具;下一次拖选
 *   打开的 range 面板用它预填,存的时候同编号覆盖(target 改为 range、去掉 family_start);clearCarry() 放弃;
 * - close():关掉不存。换股票、换模式、app 重跑时自动关(carry 在换股票、换模式时也放弃);点面板外、平移缩放、
 *   副图滚动由界面调 close()。
 * - opens:每打开一次(含关旧开新)加一。面板组件据此重挂「点面板外就关」的监听、清掉上一次的保存提示。
 * carry 只在 feedback 工具亮着时留着:工具以任何方式熄灭(Esc、再点按钮、换成别的工具、拖完一次)都放弃它。
 * 拖完一次时先熄工具、再在同一段同步代码里 open 用掉 carry,下面的 watch 晚一步才跑,不会抢在 open 之前清掉。
 * selectedId:选中的那条反馈(图上加粗描边;侧栏点行时设);删掉它时清掉。
 * 面板派生量:panelPosInside(范围里有没有当前 pattern 的正样本)、panelSegments(off_pattern 的分段按钮)。
 */
import { defineStore } from 'pinia'
import { computed, onScopeDispose, ref, shallowRef, watch } from 'vue'
import { getFeedbackStatus } from '../api'
import { chartOf, findFeedback, type FeedbackAnswer } from '../annotate/model'
import {
  findSameRange, hitsBuyingIn, posSamplesInside, saveProblems, segmentChoices,
  type FeedbackProblem, type FeedbackRange, type FeedbackStatusOf,
} from '../annotate/feedback'
import { useAnnotationStore } from './annotation'
import { useViewStore } from './view'

/** 面板浮在哪(视口坐标,同点击事件的 clientX / clientY)。 */
export interface PanelAt { x: number; y: number }

/** 作答面板的状态:范围、答案、理由、分段;editingId 是正在改的那条(新建时没有);carry 为真表示是 redraw 拖出来的。 */
export interface FeedbackPanel extends FeedbackRange, PanelAt {
  editingId?: string
  answer?: FeedbackAnswer
  note?: string
  segments?: string[]
  carry?: boolean
}

/** redraw 带进下一次拖选的东西:改的是哪条、答案、理由、分段。 */
export interface FeedbackCarry { editingId: string; answer?: FeedbackAnswer; note?: string; segments?: string[] }

export const useFeedbackStore = defineStore('feedback', () => {
  const view = useViewStore()
  const ann = useAnnotationStore()

  const statusById = shallowRef<Record<string, FeedbackStatusOf>>({})
  const loading = ref(false)
  /** 状态接口失败的原因(503 行情目录不在等);成功后清掉 */
  const error = ref<string | null>(null)
  /** 状态接口说的当前 app、它的版本;找不到 app 时 app 为 null,原因在 reason */
  const app = ref<string | null>(null)
  const appVer = ref<string | null>(null)
  const reason = ref<string | null>(null)

  const panel = ref<FeedbackPanel | null>(null)
  const opens = ref(0)
  const carry = ref<FeedbackCarry | null>(null)
  const selectedId = ref<string | null>(null)

  // ── 状态 ──

  let request = 0                                   // 只认最后一次取的结果
  /** 取当前 pattern 全部反馈的状态;不在 compare 或没有当前 pattern 时什么都不做。 */
  async function refresh(): Promise<void> {
    const pattern = ann.currentPattern
    if (!view.comparing || pattern === null) return
    const mine = ++request
    loading.value = true
    try {
      const r = await getFeedbackStatus(pattern)
      if (mine !== request) return
      statusById.value = Object.fromEntries(r.items.map(({ id, ...rest }) => [id, rest]))
      app.value = r.app
      appVer.value = r.app_ver
      reason.value = r.reason
      error.value = null
    } catch (e: any) {
      if (mine === request) error.value = String(e?.message ?? e)
    } finally {
      if (mine === request) loading.value = false
    }
  }

  let scheduled = false
  /** 同一轮里几处同时要重取只取一次。 */
  function requestRefresh(): void {
    if (scheduled) return
    scheduled = true
    queueMicrotask(() => { scheduled = false; void refresh() })
  }

  /** 后端读结果里每条反馈的最后一次修改(只看已存进文件的,不看还没存完的):它变了说明有反馈存进或删出了。
   *  不按当前 pattern 筛:换 pattern 由下面另一处触发,这里不跟着再取一次。 */
  const savedSig = computed(() => JSON.stringify(ann.server?.revs.feedback ?? {}))

  watch(() => view.comparing, (on) => { if (on) requestRefresh() }, { immediate: true })
  watch(() => ann.currentPattern, () => { if (view.comparing) requestRefresh() })
  watch(() => view.linkedRun, (run) => { if (run && view.comparing) requestRefresh() })
  watch(savedSig, async () => {
    if (!view.comparing) return
    await ann.flushed()
    requestRefresh()
  })
  function onFocus() { if (view.comparing) requestRefresh() }
  window.addEventListener('focus', onFocus)
  onScopeDispose(() => window.removeEventListener('focus', onFocus))

  // ── 作答面板 ──

  /**
   * 打开面板:给范围(点 ▼ / 族 / 拖选)或给已有反馈的编号(点记号)。只在 compare 下;返回开没开
   * (找不到那条、或那条是盲看标记时不开)。面板开着时关旧开新,不存。
   */
  function open(at: PanelAt, what: FeedbackRange | { id: string }): boolean {
    if (!view.comparing || !ann.state) return false
    if ('id' in what) return openRecord(at, what.id)
    const same = findSameRange(chartOf(ann.state, what.symbol), ann.currentPattern, what.start, what.end)
    const c = what.target === 'range' ? carry.value : null
    if (c) carry.value = null                    // 拖选用掉 redraw 带来的东西(落在别的已有反馈上也不再留)
    if (same && same.id !== c?.editingId) return openRecord(at, same.id)
    const base: FeedbackPanel = { x: at.x, y: at.y, symbol: what.symbol, start: what.start, end: what.end, target: what.target }
    if (what.target === 'family' && what.family_start) base.family_start = what.family_start
    if (c) {
      panel.value = { ...base, editingId: c.editingId, answer: c.answer, note: c.note ?? '',
                      segments: [...(c.segments ?? [])], carry: true }
    } else {
      panel.value = { ...base, note: '', segments: [] }
    }
    opens.value++
    return true
  }

  /** 打开一条已有的反馈:盲看标记、不属于当前 pattern 的不开(存不进去,见 annotation.saveFeedback)。 */
  function openRecord(at: PanelAt, id: string): boolean {
    const hit = ann.state ? findFeedback(ann.state, id) : null
    if (!hit || hit.feedback.source !== 'picked' || hit.feedback.pattern !== ann.currentPattern) return false
    const fb = hit.feedback
    const p: FeedbackPanel = {
      x: at.x, y: at.y, symbol: hit.chart.symbol, start: fb.start, end: fb.end, target: fb.target,
      editingId: fb.id, note: fb.note ?? '', segments: [...(fb.segments ?? [])],
    }
    if (fb.answer === 'neg' || fb.answer === 'off_pattern') p.answer = fb.answer
    if (fb.target === 'family' && fb.family_start) p.family_start = fb.family_start
    panel.value = p
    opens.value++
    return true
  }

  /** 关掉面板,不存。 */
  function close(): void { panel.value = null }

  function setAnswer(a: FeedbackAnswer): void {
    if (!panel.value) return
    panel.value = { ...panel.value, answer: a, ...(a === 'neg' ? { segments: [] } : {}) }
  }

  function setNote(note: string): void {
    if (panel.value) panel.value = { ...panel.value, note }
  }

  /** 点一个分段按钮:没选上就选上,选上了就拿掉(可多选)。 */
  function toggleSegment(node: string): void {
    if (!panel.value) return
    const cur = panel.value.segments ?? []
    panel.value = { ...panel.value, segments: cur.includes(node) ? cur.filter(x => x !== node) : [...cur, node] }
  }

  /** 保存条件还缺什么(面板里标出来);没开面板为空。 */
  const problems = computed<FeedbackProblem[]>(() => (panel.value ? saveProblems(panel.value) : []))

  /** 存面板里的这条:条件满足、存得下才关面板;返回存没存。 */
  function save(): boolean {
    const p = panel.value
    if (!p || saveProblems(p).length) return false
    const id = ann.saveFeedback({
      id: p.editingId, symbol: p.symbol, start: p.start, end: p.end, target: p.target,
      family_start: p.family_start, answer: p.answer, note: p.note, segments: p.segments,
    })
    if (!id) return false
    panel.value = null
    return true
  }

  /** 删一条反馈(面板里的 delete、侧栏行上的 delete 都走这里):面板正开着它就关掉,选中的是它就清掉。 */
  function remove(id: string): void {
    ann.deleteFeedback(id)
    if (panel.value?.editingId === id) panel.value = null
    if (selectedId.value === id) selectedId.value = null
  }

  /** redraw:把正在改的那条的答案、理由、分段记进 carry 并关面板;返回成没成(面板没开着一条已有的不成)。
   *  点亮 feedback 工具由调用方做。 */
  function startRedraw(): boolean {
    const p = panel.value
    if (!p?.editingId) return false
    carry.value = { editingId: p.editingId, answer: p.answer, note: p.note ?? '', segments: [...(p.segments ?? [])] }
    panel.value = null
    return true
  }

  function clearCarry(): void { carry.value = null }

  function select(id: string | null): void { selectedId.value = id }

  // 换股票、换模式:关面板、放弃 redraw;app 重跑(含开始重跑时清掉旧结果):关面板
  watch([() => view.symbol, () => view.mode], () => { panel.value = null; carry.value = null })
  watch(() => view.linkedRun, () => { panel.value = null })
  // feedback 工具熄了(不论怎么熄的):redraw 带过来的东西作废,免得留到以后哪次拖选、悄悄覆盖原记录
  watch(() => ann.tool, (t) => { if (t !== 'feedback') carry.value = null })

  // ── 面板派生量 ──

  /** 面板的范围里有没有当前 pattern 的正样本(这只股票的):有就提示 pos sample inside,不拦。 */
  const panelPosInside = computed(() => {
    const p = panel.value
    return !!p && !!ann.state
      && posSamplesInside(chartOf(ann.state, p.symbol), ann.currentPattern, p.start, p.end).length > 0
  })

  /** off_pattern 的分段按钮(node_id,按拓扑顺序):范围里买的那些 hit 绑定的 node 及其子 node;
   *  已选上、当前拓扑里已没有的分段排在最后。面板的股票不是图上这只时只有已选的。 */
  const panelSegments = computed<string[]>(() => {
    const p = panel.value
    if (!p) return []
    const keep = p.segments ?? []
    const a = view.effectiveAnalysis
    if (!a || view.symbol !== p.symbol) return segmentChoices([], null, keep)
    const hits = hitsBuyingIn(a.hits, a.events, view.endNode, view.barDates, p.start, p.end)
    return segmentChoices(hits, view.effectivePattern?.topology, keep)
  })

  return {
    statusById, loading, error, app, appVer, reason, refresh,
    panel, opens, carry, selectedId, problems, panelPosInside, panelSegments,
    open, switchTo: open, close, setAnswer, setNote, toggleSegment, save, remove, startRedraw, clearCarry, select,
  }
})
