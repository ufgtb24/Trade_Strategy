/**
 * 反馈(feedback,spec 6.13)在 compare 下的状态与作答面板。记录的读写走 stores/annotation.ts(saveFeedback /
 * deleteFeedback,标注的追加写法);取法与保存条件是 annotate/feedback.ts 的纯函数。
 *
 * 状态(statusById):当前 pattern 的全部反馈在当前 app 下是 matched / unmatched,连同会话写的原因标签
 * tag 与画不画朱红 red,都照后端 GET /feedback/status 给的(朱红与否只在后端判一次)。只在 compare 下去取;
 * 重取的时机:
 * - 进入 compare、换当前 pattern;
 * - 反馈存进或删出标注文件之后(后端读结果里反馈的修改记录变了,等还没存完的动作都存完,ann.flushed());
 * - app 重跑之后(view.setLinkedRun 放进新的现算结果:换股票、换 app、切进 compare 都会重跑);
 * - 窗口重新拿到焦点(同 stores/appLink.ts 重读 mapping 的时机:会话改完 app 或会话账本,切回浏览器就生效)。
 * 同一轮里几处同时触发只取一次;连着取时只认最后一次的结果。loading 为真时侧栏显示 loading。
 *
 * 作答面板(panel,同时只开一个;组件在 components/FeedbackPanel.vue,落在哪由它和图表组件定,这里不管):
 * - 点图上的东西只选中,不开面板。selTarget 是选中的那一个能作答的对象(买点日或它里面的一次 hit → 那一天;
 *   一族 → 整族;一条反馈 → 那条;别的为 null);openSelected() 对它打开面板(Enter、显示栏的 feedback 按钮);
 * - open(范围):拖选松手、openSelected 时打开。这只股票、当前 pattern 已有范围完全相同的反馈时直接打开
 *   那条(防重复);open({id}):打开已有的那条(预填,editingId 为它的编号)。盲看标记、不属于当前 pattern 的不打开。
 *   面板开着时再 open 就是关旧开新(switchTo 是它的别名),不存;
 * - 面板没有「先选答案」这一步:一打开就能点 node、写 note。setNote / toggleNode 改草稿;
 *   打开一条以前存下的带 answer(可能还带 dag)的记录时只预填它的 note 与 nodes,保存后那条就改写成不带这两个键的形状;
 * - issue(几处反馈共享同一份内容,规则见 annotate/feedback.ts):草稿的 link 记着这一处连着哪个 issue(组键)——
 *   打开已有的一处时是它自己的那个,新标一处时没有,pickIssue(key) 从列表里挑一条就连过去并把 note、nodes
 *   填成它的(再点已连着的那条 = 不连了,内容留着);panelIssue 是 link 指的那一组。
 *   panelIssues 是面板里可挑的(当前 pattern 的全部 issue,一打开就有);panelNeedsChoice 为真表示连着的 issue
 *   还有别的处、内容又改了,得先问 all / only_this;
 * - save(choice):保存条件满足才存(存了就关面板),返回存没存;problems 是还缺什么(面板里标出来)。
 *   要问 all / only_this 而 choice 没给时不存。all 把那个 issue 的各处在同一批里一起改;
 * - resize(id, start, end):改一条已有反馈的起止(点亮 feedback 工具、拖选中那条竖带的左右边;手势在
 *   components/annotateGestures.ts),note、node、所属的 issue 不变,不经面板直接存;说明见函数;
 * - close():关掉不存。换股票、换模式、app 重跑时自动关;点面板外、平移缩放、副图滚动由界面调 close();
 *   按键挪了选中、当前那个出了面板对着的那一块时也关(见下面对 view.moveSeq 的 watch)。
 * - opens:每打开一次(含关旧开新)加一。面板组件据此重挂「点面板外就关」的监听、清掉上一次的保存提示、回到默认位置。
 * selectedId:选中的那条反馈(图上记号描黑粗边、另有一条贯穿主副图的竖带;侧栏点行、点记号时设);删掉它时清掉。
 * editRequest:侧栏卡片的 edit 在落到那段日期之后提的「打开那条的面板」(requestEdit);图上有没有那条记号只有
 *   图表组件知道,所以由 components/KlineChart.vue 接下、打开面板后 takeEditRequest() 消费掉。
 *   换股票、换模式时作废。
 * 面板派生量:panelPosInside(范围里有没有当前 pattern 的正样本)、panelNodes(node 按钮)。
 * placesById:当前 pattern 里每条用户自己挑的反馈所在的 issue 有几处(图上记号的悬停用)。
 */
import { defineStore } from 'pinia'
import { computed, onScopeDispose, ref, shallowRef, watch } from 'vue'
import { getFeedbackStatus } from '../api'
import { chartOf, findFeedback } from '../annotate/model'
import {
  findSameRange, hitsBuyingIn, issueChoices, issueGroups, issueKey, needsIssueChoice, nextIssueValue, planIssueSave,
  posSamplesInside, saveProblems, nodeChoices,
  type FeedbackProblem, type FeedbackRange, type FeedbackStatusOf, type IssueChoice, type IssueGroup,
} from '../annotate/feedback'
import { buyDaysOf } from '../render/fold'
import type { HitDict } from '../types'
import { useAnnotationStore } from './annotation'
import { useViewStore } from './view'

/** 作答面板的状态:范围、理由、点出的 node;editingId 是正在改的那条(新建时没有);
 *  link 是连着的 issue 的组键(没连着就没有这个键)。 */
export interface FeedbackPanel extends FeedbackRange {
  editingId?: string
  note?: string
  nodes?: string[]
  link?: string
}

/** resize 的结果:saved 直接存了;same 已有另一条同范围的、不存;panel 那条没写 note、打开了它的面板。 */
export type ResizeResult = 'saved' | 'same' | 'panel'

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
  /** 面板是对选中的哪一节打开的:那时路径上的反馈编号与族键(openSelected 记下;别的打开法——拖选、侧栏 edit、
   *  改起止补 note——经 open / openRecord 清成 null) */
  let openedFrom: { feedback: string | null; family: string | null } | null = null
  /** 当前路径上的反馈编号与族键(没有为 null) */
  function pathMarks(): { feedback: string | null; family: string | null } {
    let feedback: string | null = null
    let family: string | null = null
    for (const s of view.selPath) {
      if (s.kind === 'feedback') feedback = s.id
      if (s.kind === 'hit_family') family = s.familyKey
    }
    return { feedback, family }
  }
  const selectedId = ref<string | null>(null)
  const editRequest = ref<string | null>(null)

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
   * 打开面板:给范围(选中的一天 / 一族、拖选)或给已有反馈的编号。只在 compare 下;返回开没开
   * (找不到那条、或那条是盲看标记时不开)。面板开着时关旧开新,不存。
   */
  function open(what: FeedbackRange | { id: string }): boolean {
    if (!view.comparing || !ann.state) return false
    openedFrom = null
    if ('id' in what) return openRecord(what.id)
    const same = findSameRange(chartOf(ann.state, what.symbol), ann.currentPattern, what.start, what.end)
    if (same) return openRecord(same.id)
    const base: FeedbackPanel = { symbol: what.symbol, start: what.start, end: what.end, target: what.target }
    if (what.target === 'family' && what.family_start) base.family_start = what.family_start
    panel.value = { ...base, note: '', nodes: [] }
    opens.value++
    return true
  }

  /** 打开一条已有的反馈:盲看标记、不属于当前 pattern 的不开(存不进去,见 annotation.saveFeedback)。
   *  只预填 note 与 nodes:记录上以前存下的 answer、dag 不进面板(保存后那条就不再带它们)。 */
  function openRecord(id: string): boolean {
    openedFrom = null
    const hit = ann.state ? findFeedback(ann.state, id) : null
    if (!hit || hit.feedback.source !== 'picked' || hit.feedback.pattern !== ann.currentPattern) return false
    const fb = hit.feedback
    const p: FeedbackPanel = {
      symbol: hit.chart.symbol, start: fb.start, end: fb.end, target: fb.target,
      editingId: fb.id, note: fb.note ?? '', nodes: [...(fb.nodes ?? [])], link: issueKey(fb),
    }
    if (fb.target === 'family' && fb.family_start) p.family_start = fb.family_start
    panel.value = p
    opens.value++
    return true
  }

  /** 关掉面板,不存。 */
  function close(): void { panel.value = null }

  /** 从列表里挑一条 issue:连过去,note、nodes 填成它的;再点已连着的那条 = 不连了(内容留着)。 */
  function pickIssue(key: string): void {
    const p = panel.value
    const g = groupByKey.value.get(key)
    if (!p || !g) return
    const { link, ...rest } = p
    panel.value = link === key ? rest : { ...rest, note: g.note, nodes: [...g.nodes], link: key }
  }

  function setNote(note: string): void {
    if (panel.value) panel.value = { ...panel.value, note }
  }

  /** 点一个 node 按钮:没选上就选上,选上了就拿掉(可多选)。 */
  function toggleNode(node: string): void {
    if (!panel.value) return
    const cur = panel.value.nodes ?? []
    panel.value = { ...panel.value, nodes: cur.includes(node) ? cur.filter(x => x !== node) : [...cur, node] }
  }

  /** 保存条件还缺什么(面板里标出来);没开面板为空。 */
  const problems = computed<FeedbackProblem[]>(() => (panel.value ? saveProblems(panel.value) : []))

  /**
   * 存面板里的这条:条件满足、存得下才关面板;返回存没存。连着的 issue 还有别的处、内容又改了时要 choice
   * (all 各处一起改 / only_this 只这一处),没给就不存。
   */
  function save(choice: IssueChoice | null = null): boolean {
    const p = panel.value
    if (!p || !ann.state || saveProblems(p).length) return false
    const st = ann.state
    const plan = planIssueSave(p, panelIssue.value, p.editingId ?? null, choice, () =>
      nextIssueValue(st.charts.flatMap(c => (c.feedback ?? []).map(f => f.issue)), st.machine))
    if (plan.ask) return false
    const id = ann.saveFeedback({
      id: p.editingId, symbol: p.symbol, start: p.start, end: p.end, target: p.target,
      family_start: p.family_start, note: p.note, nodes: p.nodes, issue: plan.issue,
    }, plan.others)
    if (!id) return false
    panel.value = null
    return true
  }

  /** 删一条反馈(面板里的 delete、侧栏行上的 delete 都走这里):面板正开着它就关掉,选中的是它就清掉。 */
  function remove(id: string): void {
    ann.deleteFeedback(id)
    if (panel.value?.editingId === id) panel.value = null
    if (selectedId.value === id) selectedId.value = null
    // 图上选中的正是它(或正在它里面走):东西没了,选中一并清掉
    if (view.selPath.some(x => x.kind === 'feedback' && x.id === id)) view.clearFocus()
  }

  /**
   * 改一条已有反馈的起止:note、node、所属的 issue 都不变,target 改为 range、去掉 family_start(点或一族拖过边
   * 就成了一段日期),app_ver 刷新为当前值(同在面板里改)。不经面板,直接存。返回:
   * - 'saved':存了;
   * - 'same':这只股票、当前 pattern 已有另一条范围完全相同的反馈,不存(防重复,同 open);
   * - 'panel':那条是以前存下的、没写 note 的,直接存不了:打开它的面板,范围已换成新的,补上 note 再存;
   * - null:存不了(不在 compare、找不到那条、不是用户自己挑的、不属于当前 pattern、这只股票还没有现算结果)。
   * 范围里有没有 app 的买点由调用方先查(要现算结果,在图表组件里)。面板正开着这一条时关掉,不存面板里的草稿。
   */
  function resize(id: string, start: string, end: string): ResizeResult | null {
    if (!view.comparing || !ann.state) return null
    const hit = findFeedback(ann.state, id)
    if (!hit || hit.feedback.source !== 'picked' || hit.feedback.pattern !== ann.currentPattern) return null
    const same = findSameRange(hit.chart, ann.currentPattern, start, end)
    if (same && same.id !== id) return 'same'
    const f = hit.feedback
    const draft = { id, symbol: hit.chart.symbol, start, end, target: 'range' as const,
                    note: f.note, nodes: f.nodes, issue: f.issue }
    if (saveProblems(draft).includes('note')) {
      if (!openRecord(id)) return null
      const { family_start: _f, ...rest } = panel.value!
      panel.value = { ...rest, start, end, target: 'range' }
      return 'panel'
    }
    if (panel.value?.editingId === id) panel.value = null
    return ann.saveFeedback(draft) ? 'saved' : null
  }

  function select(id: string | null): void {
    selectedId.value = id
    if (!id) return
    // 选中一条反馈 = 图上的选中换成它(显示栏写 feedback、Shift+C 复制它);已经在它里面走着就不动
    if (view.comparing && !view.selPath.some(x => x.kind === 'feedback' && x.id === id)) view.clickFeedback({ id })
  }

  /** 这张图上当前 pattern 里用户自己挑的反馈,按起止排:选中模型里「同一层的反馈」就是它们。 */
  const chartFeedback = computed(() => {
    const sym = view.symbol
    const c = sym && ann.state ? chartOf(ann.state, sym) : null
    return (c?.feedback ?? []).filter(f => f.source === 'picked' && f.pattern === ann.currentPattern)
      .sort((a, b) => (a.start < b.start ? -1 : a.start > b.start ? 1 : a.end < b.end ? -1 : a.end > b.end ? 1 : a.id < b.id ? -1 : 1))
  })
  view.setSelSources({
    feedbacks: () => chartFeedback.value.map(f => ({
      id: f.id, start: f.start, end: f.end, family_start: f.target === 'family' ? f.family_start ?? null : null })),
    feedbackOf: (id) => {
      const f = chartFeedback.value.find(x => x.id === id)
      return f ? { start: f.start, end: f.end, nodes: f.nodes ?? [],
                   familyStart: f.target === 'family' ? f.family_start ?? null : null } : null
    },
  })
  // 粗边与竖带跟着图上的选中走:路径上有一条反馈(点记号、按键换到旁边一条)就是它;
  // 选中换成了别的东西(路径上不再有反馈)就取消。路径清空时不动(侧栏点行后换图的那一下还要留着)。
  watch(() => view.selPath, (path) => {
    const on = path.find((x): x is Extract<typeof x, { kind: 'feedback' }> => x.kind === 'feedback')
    if (on) { if (selectedId.value !== on.id) selectedId.value = on.id }
    else if (selectedId.value && path.length > 0) selectedId.value = null
  })

  /**
   * 选中的那一个能作答的对象(只看路径最里面那一节):
   * - 买点日 → 那一天(point);它里面的一次 hit → 那一天,那天得是这次 hit 的买点日(从样本、框走进去的那次
   *   不在那天买时不能作答);
   * - 一族 → 整族(family):范围是这一族全部买点日的最早到最晚,另存族起点 family_start;一个买点日都没有的族为 null;
   * - 一条反馈 → 那条({id},打开来改);
   * - event、node、样本、框,或没选中:null。
   * 买点日和图上画 ▼ 同一口径(render/fold.ts 的 buyDaysOf,解析不到不退到终点),所以能作答的日子上一定有 ▼。
   * app 跑没跑完由调用方另看(图表组件的 compareReady)。
   */
  const eventsById = computed(() => new Map((view.effectiveAnalysis?.events ?? []).map(e => [e.instance_id, e] as const)))
  const buysOf = (m: HitDict): number[] => buyDaysOf(m, eventsById.value, view.endNode)
  const selTarget = computed<FeedbackRange | { id: string } | null>(() => {
    const sym = view.symbol
    const last = view.selLast
    const hits = view.effectiveAnalysis?.hits ?? []
    if (!view.comparing || !sym || !last) return null
    const date = (i: number): string | null => view.barDates[i] ?? null
    const point = (day: number): FeedbackRange | null => {
      const d = date(day)
      return d ? { symbol: sym, start: d, end: d, target: 'point' } : null
    }
    if (last.kind === 'feedback') return chartFeedback.value.some(f => f.id === last.id) ? { id: last.id } : null
    if (last.kind === 'buy') return hits.some(m => buysOf(m).includes(last.day)) ? point(last.day) : null
    if (last.kind === 'hit') {
      const m = hits.find(h => h.hit_id === last.hitId)
      return m && buysOf(m).includes(last.day) ? point(last.day) : null
    }
    if (last.kind === 'hit_family') {
      const st = Number(last.familyKey.slice(last.familyKey.lastIndexOf('@') + 1))
      const days = hits.filter(m => m.start_idx === st).flatMap(buysOf)
      const start = days.length ? date(Math.min(...days)) : null
      const end = days.length ? date(Math.max(...days)) : null
      const familyStart = date(st)
      return start && end && familyStart ? { symbol: sym, start, end, target: 'family', family_start: familyStart } : null
    }
    return null
  })
  /** 对选中的那一个打开面板(Enter、显示栏的 feedback 按钮);不能作答时不开,返回开没开。
   *  记下打开时路径上的反馈与族(openedFrom),按键走动时据此判断还在不在它里面。 */
  function openSelected(): boolean {
    const what = selTarget.value
    if (!what || !open(what)) return false
    openedFrom = pathMarks()
    return true
  }

  /** 侧栏卡片的 edit:请图表打开那条的面板(图表落定后才提,见 components/FeedbackPage.vue)。 */
  function requestEdit(id: string): void { editRequest.value = id }
  /** 图表接下 edit 的请求:给出编号并消费掉;没有为 null。 */
  function takeEditRequest(): string | null {
    const id = editRequest.value
    editRequest.value = null
    return id
  }

  // 换股票、换模式:关面板、作废还没接下的 edit;app 重跑(含开始重跑时清掉旧结果):关面板
  watch([() => view.symbol, () => view.mode], () => { panel.value = null; editRequest.value = null })
  // 按键挪了选中(← / →、↑ / ↓):面板对着的那一块(point 是那一天;family 是这一族;点记号打开的是那条反馈
  // 收进来的那些 hit;拖出来的一段是那段日期)还包含当前那个就留着,出去了就关(没存的字丢掉,和 Esc、点别处一样)
  watch(() => view.moveSeq, () => {
    const p = panel.value
    if (!p) return
    const day = view.currentDay
    const date = day !== null ? view.barDates[day] ?? null : null
    const hit = view.selectedHit
    const covered = (!!p.editingId && view.selPath.some(x => x.kind === 'feedback' && x.id === p.editingId))
      || (p.target === 'family' && !!p.family_start && !!hit && view.barDates[hit.start_idx] === p.family_start)
      || (date !== null && p.start <= date && date <= p.end)
    // 竖线不动的换法(换到旁边一条反馈、旁边一族):面板对着的还是原来那一块,选中已经是另一个了。
    // 对选中打开的面板按打开时路径上的反馈与族比(同范围防重复打开的是另一条反馈时,路径上的反馈不是 editingId,
    // 不能拿它比);拖选、侧栏 edit 打开的照面板自己的那条反馈 / 那一族比
    const now = pathMarks()
    const famStart = now.family !== null
      ? view.barDates[Number(now.family.slice(now.family.lastIndexOf('@') + 1))] ?? null : null
    const left = openedFrom
      ? now.feedback !== openedFrom.feedback || now.family !== openedFrom.family
      : (!!p.editingId && now.feedback !== null && now.feedback !== p.editingId)
        || (p.target === 'family' && !!p.family_start && famStart !== null && famStart !== p.family_start)
    if (!covered || left) panel.value = null
  })
  watch(() => view.linkedRun, () => { panel.value = null })

  // ── issue ──

  /** 当前 pattern 里用户自己挑的全部反馈(跨股票,含还没存完的)。 */
  const pickedRows = computed(() => ann.feedbackOfPattern().filter(r => r.feedback.source === 'picked'))
  /** 它们按 issue 分的组,按组键查。 */
  const groupByKey = computed(() => new Map(issueGroups(pickedRows.value).map(g => [g.key, g] as const)))
  /** 每条反馈所在的 issue 有几处。 */
  const placesById = computed(() => {
    const out: Record<string, number> = {}
    for (const g of groupByKey.value.values()) for (const r of g.rows) out[r.feedback.id] = g.rows.length
    return out
  })

  /** 面板里可挑的 issue:当前 pattern 的全部(只有正在改的这一处自己的那个除外),最近用过的在前。 */
  const panelIssues = computed<IssueGroup[]>(() => {
    const p = panel.value
    return p ? issueChoices(pickedRows.value, p.editingId ?? null) : []
  })
  /** 这一处眼下连着的 issue:草稿的 link 指的那一组;没有为 null。 */
  const panelIssue = computed<IssueGroup | null>(() => {
    const link = panel.value?.link
    return (link ? groupByKey.value.get(link) : undefined) ?? null
  })
  /** 保存前得先问 all / only_this:连着的 issue 还有别的处,内容又和它不一样。 */
  const panelNeedsChoice = computed(() => {
    const p = panel.value
    return !!p && needsIssueChoice(p, panelIssue.value, p.editingId ?? null)
  })
  /** 连着的 issue 连同这一处一共几处(没连着为 0)。 */
  const panelPlaces = computed(() => {
    const p = panel.value, g = panelIssue.value
    return p && g ? g.rows.filter(r => r.feedback.id !== p.editingId).length + 1 : 0
  })

  // ── 面板派生量 ──

  /** 面板的范围里有没有当前 pattern 的正样本(这只股票的):有就提示 pos sample inside,不拦。 */
  const panelPosInside = computed(() => {
    const p = panel.value
    return !!p && !!ann.state
      && posSamplesInside(chartOf(ann.state, p.symbol), ann.currentPattern, p.start, p.end).length > 0
  })

  /** node 按钮(node_id,按拓扑顺序):范围里买的那些 hit 绑定的 node 及其子 node;
   *  已选上、当前拓扑里已没有的 node 排在最后。面板的股票不是图上这只时只有已选的。 */
  const panelNodes = computed<string[]>(() => {
    const p = panel.value
    if (!p) return []
    const keep = p.nodes ?? []
    const a = view.effectiveAnalysis
    if (!a || view.symbol !== p.symbol) return nodeChoices([], null, keep)
    const hits = hitsBuyingIn(a.hits, a.events, view.endNode, view.barDates, p.start, p.end)
    return nodeChoices(hits, view.effectivePattern?.topology, keep)
  })

  return {
    statusById, loading, error, app, appVer, reason, refresh,
    panel, opens, selectedId, editRequest, problems, panelPosInside, panelNodes,
    panelIssues, panelIssue, panelNeedsChoice, panelPlaces, placesById,
    selTarget, openSelected, open, switchTo: open, close, setNote, toggleNode, pickIssue, save, remove, resize, select,
    requestEdit, takeEditRequest,
  }
})
