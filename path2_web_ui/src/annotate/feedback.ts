/**
 * 反馈(feedback,spec 6.13)界面侧的纯函数:图上(▼ / 族 / 拖选)、作答面板、侧栏 feedback 页共用。
 * 不碰网络和界面;记录形状见 annotate/model.ts 的 AnnFeedback,读写与面板状态见 stores/feedback.ts。
 *
 * - 同范围查重(findSameRange):这只股票、这个 pattern 已有 start、end 完全相同的反馈时,面板直接打开那条;
 *   只认用户自己挑的(source = picked),盲看标记创建后不可改,不拿来打开;
 * - 范围里的正样本(posSamplesInside):这只股票上当前 pattern 的 pos 样本,样本日落在 [start, end] 里。
 *   面板与记号悬停提示 `pos sample inside`,不拦;
 * - 买点日(buyDatesIn / hitsBuyingIn):hit 的买点日按 eval_meta 的买点 node 取(render/fold.ts 的 buyDaysOf,
 *   与图上 ▼、后端判反馈状态同一口径),K 线下标经这只股票的交易日换成日期;
 * - 保存条件(saveProblems):与后端对不带 answer 的反馈的校验一致(path2_web/annotation/store.py 模块说明
 *   「反馈」),不满足的不送:note 必须写(去掉首尾空白后判空,比后端略严:全是空格的理由不算写了);
 *   node 可点可不点(一个都不点 = 问题不在某一块上或说不清,由 note 说);
 * - 面板写出的反馈一律是不带 answer、不带 dag 的形状(draftToFeedback)。以前存下的带 answer(可能还带 dag)的
 *   记录照样读得出、打得开,经面板保存后就改写成这种形状;
 * - node 按钮(nodeChoices):范围里买的那些 hit 绑定的 node(hit 的 node_index 的键),加它们在
 *   拓扑里的子 node(由 TopoNode.parent_refs 认父,递归取),按拓扑顺序(即 band 的顺序),根 node 保留。
 *   只读拓扑,不认任何具体事件类型;
 * - issue(几处反馈共享同一份内容:pattern、note、nodes;各处只有股票和日期范围不同):
 *   · 分组(issueGroups):组键 = 记录上的 issue 值,不带的用自己的编号(自成一个只有一处的 issue);只有用户自己
 *     挑的参与共享,盲看标记各自一组;
 *   · 面板里可挑的 issue(issueChoices):当前 pattern 里除了「只有正在改的这一处自己」以外的各组,
 *     最近用过的在前——没有时间戳可用,按组内各处编号里序号的最大值从大到小排(待验证);
 *   · 内容改没改(sameContent):note 去首尾空白后比、nodes 按集合比。旧记录上的 answer、dag 不属于内容,不比;
 *   · 新的 issue 值(nextIssueValue):`i-<机器名>-<n>`,n = 眼下全部股票、全部 pattern 已有 issue 值里同机器名的
 *     最大序号加一。不走对象编号的序列(那个序列只按对象编号推进,issue 值不是对象编号);
 *   · 一次保存要动哪些记录(planIssueSave):这一处带不带 issue 值、同一批里还要改哪些别的处。后端要求带同一个
 *     issue 值的各处内容相同,所以改共享内容必须一批改完;
 *   · 侧栏分组的次序(sortIssueGroups):有朱红的组在前、其次有不买了却还挂着原因标签的,其余在后;同档按组里排第一的那一处
 *     (sortFeedbackRows 的次序),组内各处也按它排。
 * - 侧栏排序(sortFeedbackRows):朱红在前、不买了却还挂着原因标签的其次、其余在后,同档按股票、start、end、编号(同后端状态接口)。
 *   朱红与否只照后端给的 red,前端不自己判。
 */
import type { EventDict, FeedbackStatusItem, HitDict, Topology } from '../types'
import { buyDaysOf } from '../render/fold'
import { TRAIN_END } from './directLinks'
import type { AnnChart, AnnFeedback, AnnSample, FeedbackTarget } from './model'

/** 反馈落成的那段日期(还没作答):股票、起止、从哪来;family 另带这一族的起点日期。 */
export interface FeedbackRange {
  symbol: string
  start: string
  end: string
  target: FeedbackTarget
  family_start?: string
}

/** 面板里正在写的一条反馈:范围加理由、点出的 node(都可能还没填);issue 是这一处要带的
 *  issue 值(没有即不带,由 planIssueSave 定)。 */
export interface FeedbackDraft extends FeedbackRange {
  note?: string
  nodes?: string[]
  issue?: string | null
}

/** 后端状态接口给的一条去掉编号(stores/feedback.ts 按编号存):status 读不到行情时为 null。 */
export type FeedbackStatusOf = Omit<FeedbackStatusItem, 'id'>

/** 侧栏一行:反馈连同它所在的股票。 */
export interface FeedbackRow { symbol: string; feedback: AnnFeedback }

/**
 * 保存条件没满足的地方(面板里标出缺什么):
 * - note:没写理由(去掉首尾空白后为空);
 * - nodes:点出的 node 有重复或空的;
 * - range:日期写法不对或 start 晚于 end;after_train_end:end 晚于训练段末日;
 * - point:point 的 start 与 end 不是同一天;
 * - family_start:family 没有起点或起点晚于 start,或不是 family 却带了起点。
 * 后四种由图上取范围的代码保证,正常不会出现;列出来是为了和后端校验逐条对上。
 */
export type FeedbackProblem =
  | 'note' | 'nodes' | 'range' | 'after_train_end' | 'point' | 'family_start'

const DATE_RE = /^\d{4}-\d{2}-\d{2}$/

/** 同范围查重:这只股票上这个 pattern 已有 start、end 完全相同、用户自己挑的反馈就给出它,没有为 null。 */
export function findSameRange(chart: AnnChart | null | undefined, pattern: string | null,
                              start: string, end: string): AnnFeedback | null {
  if (!chart || pattern === null) return null
  return chart.feedback?.find(f => f.source === 'picked' && f.pattern === pattern
                                   && f.start === start && f.end === end) ?? null
}

/** 范围里当前 pattern 的正样本(这只股票的,样本日落在 [start, end] 里),按样本日。 */
export function posSamplesInside(chart: AnnChart | null | undefined, pattern: string | null,
                                 start: string, end: string): AnnSample[] {
  if (!chart || pattern === null) return []
  return chart.samples.filter(s => s.pattern === pattern && s.judgment === 'pos' && start <= s.date && s.date <= end)
}

/** 一次 hit 的买点日(日期,升序);下标超出交易日的丢掉。 */
function hitBuyDates(h: HitDict, byId: ReadonlyMap<string, EventDict>, endNode: string | null | undefined,
                     dates: readonly string[]): string[] {
  return buyDaysOf(h, byId, endNode).map(i => dates[i]).filter((d): d is string => d !== undefined)
}

/** 买点日落在 [start, end] 里的那些 hit(按结果里的先后)。dates 是这只股票的交易日(K 线下标 → 日期)。 */
export function hitsBuyingIn(hits: readonly HitDict[], events: readonly EventDict[], endNode: string | null | undefined,
                             dates: readonly string[], start: string, end: string): HitDict[] {
  const byId = new Map(events.map(e => [e.instance_id, e]))
  return hits.filter(h => hitBuyDates(h, byId, endNode, dates).some(d => start <= d && d <= end))
}

/** [start, end] 里 app 的买点日(日期,升序去重);没有为空数组(拖选范围里没有 ▼ 时不弹面板)。 */
export function buyDatesIn(hits: readonly HitDict[], events: readonly EventDict[], endNode: string | null | undefined,
                           dates: readonly string[], start: string, end: string): string[] {
  const byId = new Map(events.map(e => [e.instance_id, e]))
  const out = new Set<string>()
  for (const h of hits) for (const d of hitBuyDates(h, byId, endNode, dates)) if (start <= d && d <= end) out.add(d)
  return [...out].sort()
}

/**
 * node 按钮:hits(范围里买的那些)绑定的 node,加它们的子 node(递归;子 node 由
 * parent_refs 认父),按拓扑里 node 的先后。keep 是已经选上的 node(改一条已有反馈时):当前拓扑里已没有的
 * 也留着,排在最后,好让用户看得见、点得掉。拓扑为 null 时只有 keep。
 */
export function nodeChoices(hits: readonly Pick<HitDict, 'node_index'>[], topology: Topology | null | undefined,
                            keep: readonly string[] = []): string[] {
  const nodes = topology?.nodes ?? []
  const kids = new Map<string, string[]>()
  for (const n of nodes) for (const [p] of n.parent_refs ?? []) {
    if (p === n.node_id) continue
    const list = kids.get(p)
    if (list) list.push(n.node_id)
    else kids.set(p, [n.node_id])
  }
  const picked = new Set<string>()
  const walk = (id: string) => {
    if (picked.has(id)) return
    picked.add(id)
    for (const k of kids.get(id) ?? []) walk(k)
  }
  for (const h of hits) for (const id of Object.keys(h.node_index ?? {})) walk(id)
  const ordered = nodes.map(n => n.node_id).filter(id => picked.has(id))
  const known = new Set(ordered)
  return [...ordered, ...keep.filter((id, i) => !known.has(id) && keep.indexOf(id) === i)]
}

/** 保存条件(同后端校验):返回没满足的地方,空数组即可以存。 */
export function saveProblems(d: FeedbackDraft): FeedbackProblem[] {
  const out: FeedbackProblem[] = []
  const picked = d.nodes ?? []
  if (!(d.note ?? '').trim()) out.push('note')
  if (picked.some(s => typeof s !== 'string' || s === '') || new Set(picked).size !== picked.length) out.push('nodes')
  const datesOk = DATE_RE.test(d.start) && DATE_RE.test(d.end)
  if (!datesOk || d.start > d.end) out.push('range')
  if (datesOk && d.end > TRAIN_END) out.push('after_train_end')
  if (d.target === 'point' && d.start !== d.end) out.push('point')
  const fs = d.family_start ?? null
  if (d.target === 'family' ? !fs || !DATE_RE.test(fs) || fs > d.start : fs !== null) out.push('family_start')
  return out
}

/**
 * 面板里的草稿 → 要存的反馈(保存条件已满足时调用):不带 answer、不带 dag;理由去掉首尾空白(保存条件保证
 * 非空);nodes 点了才带;issue 有才带;family_start 只在 family 时带;source 恒为 picked。
 * 记录的出处(编号、pattern、app、app 版本)由调用方给。
 */
export function draftToFeedback(d: FeedbackDraft, origin: { id: string; pattern: string; app_id: string; app_ver: string }): AnnFeedback {
  const fb: AnnFeedback = {
    id: origin.id, pattern: origin.pattern, app_id: origin.app_id, app_ver: origin.app_ver,
    start: d.start, end: d.end, target: d.target, source: 'picked',
  }
  const note = (d.note ?? '').trim()
  if (note) fb.note = note
  if (d.nodes?.length) fb.nodes = [...d.nodes]
  if (d.issue) fb.issue = d.issue
  if (d.target === 'family' && d.family_start) fb.family_start = d.family_start
  return fb
}

/** 侧栏里的档:0 朱红、1 不买了却还挂着会话原因标签(认法变了、毛病还在)、2 其余(状态还没取到的算其余)。 */
export function feedbackRank(st: FeedbackStatusOf | null | undefined): 0 | 1 | 2 {
  return st?.red ? 0 : st?.status === 'unmatched' && st.tag ? 1 : 2
}

/**
 * 会话原因标签各个取值的悬停说明(取值在后端 path2_web/mapping.py 的 SESSION_TAGS;这里没列的照样显示,
 * 悬停写通用的一句)。标签挂不挂由后端判(match.py 的 shown_tag),页面三处照接口给的写。
 */
const TAG_HINT: Record<string, string> = {
  unhandled: 'the session has not dealt with this feedback yet',
  for_tuning: 'the condition is already there, only its threshold is off; left for parameter tuning',
  not_worth: 'measured: a condition for it would not be worth adding',
  hindsight: 'the reason cannot be seen on the buy day, only afterwards, so no condition can catch it',
  accepted: 'you said buys like this are fine',
  redefined: 'you changed the pattern definition; this buy fits the new wording, so it is not counted against the app',
}
export function tagHint(tag: string): string {
  return TAG_HINT[tag] ?? 'reason the session gave for this feedback'
}

/** 侧栏排序:朱红在前、不买了却还挂着原因标签的其次、其余在后;同档按股票、start、end、编号。不改入参。 */
export function sortFeedbackRows(rows: readonly FeedbackRow[],
                                 statusById: Readonly<Record<string, FeedbackStatusOf | undefined>>): FeedbackRow[] {
  const cmp = (a: string, b: string) => (a < b ? -1 : a > b ? 1 : 0)
  return [...rows].sort((a, b) =>
    feedbackRank(statusById[a.feedback.id]) - feedbackRank(statusById[b.feedback.id])
    || cmp(a.symbol, b.symbol) || cmp(a.feedback.start, b.feedback.start)
    || cmp(a.feedback.end, b.feedback.end) || cmp(a.feedback.id, b.feedback.id))
}

// ── issue:几处反馈共享同一份内容 ──

/** 一个 issue 的内容(issue 之间比的就是它):理由、点出的 node。 */
export interface IssueContent { note?: string; nodes?: readonly string[] }

/** 一个 issue:组键、记录上的 issue 值(各处都不带时为 null,即只有一处、还没和谁共享过)、内容、它的各处。 */
export interface IssueGroup {
  key: string
  issue: string | null
  note: string
  nodes: string[]
  rows: FeedbackRow[]
}

/** 一条反馈属于哪个 issue:记录上的 issue 值;不带的(以及盲看标记)用自己的编号,自成一组。 */
export function issueKey(fb: Pick<AnnFeedback, 'id' | 'issue' | 'source'>): string {
  return fb.source === 'picked' && fb.issue ? fb.issue : fb.id
}

/** 按 issue 分组:组的先后照各组第一处在 rows 里的先后,组内各处照 rows 里的先后;内容取组里第一处的。 */
export function issueGroups(rows: readonly FeedbackRow[]): IssueGroup[] {
  const byKey = new Map<string, IssueGroup>()
  for (const r of rows) {
    const f = r.feedback
    const key = issueKey(f)
    const g = byKey.get(key)
    if (g) g.rows.push(r)
    else byKey.set(key, { key, issue: f.source === 'picked' ? f.issue ?? null : null,
                          note: f.note ?? '', nodes: [...(f.nodes ?? [])], rows: [r] })
  }
  return [...byKey.values()]
}

/** 编号末尾的序号(`f-<机器名>-<n>` 的 n);认不出为 0。 */
function idSeq(id: string): number {
  const m = /-(\d+)$/.exec(id)
  return m ? Number(m[1]) : 0
}

/**
 * 面板里可挑的 issue:rows 是当前 pattern 的全部反馈(跨股票);只取用户自己挑的各组,
 * 去掉「只有 selfId 这一处自己」的那一组(没有别的处可共享)。最近用过的在前:按组内各处编号序号的最大值
 * 从大到小(待验证),同值按组键。
 */
export function issueChoices(rows: readonly FeedbackRow[], selfId: string | null = null): IssueGroup[] {
  const groups = issueGroups(rows.filter(r => r.feedback.source === 'picked'))
    .filter(g => g.rows.some(r => r.feedback.id !== selfId))
  const recent = (g: IssueGroup) => Math.max(...g.rows.map(r => idSeq(r.feedback.id)))
  return groups.sort((a, b) => recent(b) - recent(a) || (a.key < b.key ? -1 : a.key > b.key ? 1 : 0))
}

/** 两份内容一样不一样:note 去首尾空白后比,nodes 按集合比(不论顺序)。 */
export function sameContent(a: IssueContent, b: IssueContent): boolean {
  if ((a.note ?? '').trim() !== (b.note ?? '').trim()) return false
  const x = new Set(a.nodes ?? []), y = new Set(b.nodes ?? [])
  return x.size === y.size && [...x].every(n => y.has(n))
}

/** 新的 issue 值:`i-<机器名>-<n>`,n = used(眼下全部 issue 值)里同机器名的最大序号加一,没有则 1。 */
export function nextIssueValue(used: Iterable<string | null | undefined>, machine: string): string {
  const head = `i-${machine}-`
  let max = 0
  for (const v of used) {
    if (!v || !v.startsWith(head)) continue
    const rest = v.slice(head.length)
    if (/^[1-9]\d*$/.test(rest)) max = Math.max(max, Number(rest))
  }
  return `${head}${max + 1}`
}

/** 改了共享的内容时用户的二选一:all 各处一起改;only_this 只这一处,另立成新 issue。 */
export type IssueChoice = 'all' | 'only_this'

/**
 * 一次保存的安排:issue 是这一处要带的 issue 值(null 即不带);others 是同一批里还要改的别的处(编号),
 * 它们的 note、nodes 换成这一处的、issue 换成同一个值(并改写成不带 answer、不带 dag 的形状),其余不动;ask 为真表示还得先问 all / only_this,这次不存。
 */
export interface IssueSavePlan { ask: boolean; issue: string | null; others: string[] }

/**
 * 这一处保存时怎么带 issue(规则):
 * - 没连着哪个 issue(新写的、点掉不再共享的):不带 issue 值,别的处不动;
 * - 连着的 issue 只有这一处自己:照存,原来带的 issue 值留着,不问;
 * - 连着的 issue 还有别的处、内容没变:这一处带上它的 issue 值;那个 issue 还没有值(只有一处、头一回被共享)时
 *   现取一个,同一批里给原来那一处补上;
 * - 连着的 issue 还有别的处、内容变了:要先问。all = 各处一起改成这一处的内容(一批);only_this = 这一处不带
 *   issue 值、另立,别的处不动。
 * @param draft   这一处的内容
 * @param group   连着的 issue(没连着为 null)
 * @param selfId  正在改的那一处的编号(新标一处为 null)
 * @param choice  用户选的 all / only_this(还没选为 null)
 * @param newIssue 现取一个新的 issue 值
 */
export function planIssueSave(draft: IssueContent, group: IssueGroup | null, selfId: string | null,
                              choice: IssueChoice | null, newIssue: () => string): IssueSavePlan {
  if (!group) return { ask: false, issue: null, others: [] }
  const others = group.rows.map(r => r.feedback.id).filter(id => id !== selfId)
  if (!others.length) return { ask: false, issue: group.issue, others: [] }
  if (sameContent(draft, group)) {
    return group.issue ? { ask: false, issue: group.issue, others: [] }
                       : { ask: false, issue: newIssue(), others }
  }
  if (choice === 'only_this') return { ask: false, issue: null, others: [] }
  if (choice === 'all') return { ask: false, issue: group.issue ?? newIssue(), others }
  return { ask: true, issue: null, others: [] }
}

/** 连着的 issue 还有别的处、而这一处的内容和它不一样:保存前得先问 all / only_this。 */
export function needsIssueChoice(draft: IssueContent, group: IssueGroup | null, selfId: string | null): boolean {
  return planIssueSave(draft, group, selfId, null, () => '').ask
}

/**
 * 侧栏的分组与次序:rows 先按 sortFeedbackRows 排(组内各处、同档的组都照它),再按 issue 分组;
 * 有朱红的组在前、其次有「不买了却还挂着原因标签」的,其余在后。不改入参。
 */
export function sortIssueGroups(rows: readonly FeedbackRow[],
                                statusById: Readonly<Record<string, FeedbackStatusOf | undefined>>): IssueGroup[] {
  const rank = (g: IssueGroup) => Math.min(...g.rows.map(r => feedbackRank(statusById[r.feedback.id])))
  const groups = issueGroups(sortFeedbackRows(rows, statusById))
  return groups.map((g, i) => ({ g, i })).sort((a, b) => rank(a.g) - rank(b.g) || a.i - b.i).map(x => x.g)
}
