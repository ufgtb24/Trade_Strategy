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
 * - 保存条件(saveProblems):与后端校验一致(path2_web/annotation/store.py 模块说明「反馈」),不满足的不送;
 *   note 按去掉首尾空白后判空(比后端略严:全是空格的理由不算写了);
 * - off_pattern 的分段按钮(segmentChoices):范围里买的那些 hit 绑定的 node(hit 的 node_index 的键),加它们在
 *   拓扑里的子 node(由 TopoNode.parent_refs 认父,递归取),按拓扑顺序(即 band 的顺序),根 node 保留。
 *   只读拓扑,不认任何具体事件类型;
 * - 侧栏排序(sortFeedbackRows):朱红在前、lost 其次、其余在后,同档按股票、start、end、编号(同后端状态接口)。
 *   朱红与否只照后端给的 red,前端不自己判。
 */
import type { EventDict, FeedbackStatusItem, HitDict, Topology } from '../types'
import { buyDaysOf } from '../render/fold'
import { TRAIN_END } from './directLinks'
import type { AnnChart, AnnFeedback, AnnSample, FeedbackAnswer, FeedbackTarget } from './model'

/** 反馈落成的那段日期(还没作答):股票、起止、从哪来;family 另带这一族的起点日期。 */
export interface FeedbackRange {
  symbol: string
  start: string
  end: string
  target: FeedbackTarget
  family_start?: string
}

/** 面板里正在写的一条反馈:范围加答案、理由、分段(都可能还没填)。 */
export interface FeedbackDraft extends FeedbackRange {
  answer?: FeedbackAnswer | null
  note?: string
  segments?: string[]
}

/** 后端状态接口给的一条去掉编号(stores/feedback.ts 按编号存):status 读不到行情时为 null。 */
export type FeedbackStatusOf = Omit<FeedbackStatusItem, 'id'>

/** 侧栏一行:反馈连同它所在的股票。 */
export interface FeedbackRow { symbol: string; feedback: AnnFeedback }

/**
 * 保存条件没满足的地方(面板里标出缺什么):
 * - answer:还没选 neg / off_pattern;
 * - note:neg 没写理由;
 * - segments_or_note:off_pattern 分段与理由一样都没有;
 * - segments:分段有重复或空的;
 * - range:日期写法不对或 start 晚于 end;after_train_end:end 晚于训练段末日;
 * - point:point 的 start 与 end 不是同一天;
 * - family_start:family 没有起点或起点晚于 start,或不是 family 却带了起点。
 * 后四种由图上取范围的代码保证,正常不会出现;列出来是为了和后端校验逐条对上。
 */
export type FeedbackProblem =
  | 'answer' | 'note' | 'segments_or_note' | 'segments' | 'range' | 'after_train_end' | 'point' | 'family_start'

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
 * off_pattern 的分段按钮:hits(范围里买的那些)绑定的 node,加它们的子 node(递归;子 node 由
 * parent_refs 认父),按拓扑里 node 的先后。keep 是已经选上的分段(改一条已有反馈时):当前拓扑里已没有的
 * 也留着,排在最后,好让用户看得见、点得掉。拓扑为 null 时只有 keep。
 */
export function segmentChoices(hits: readonly Pick<HitDict, 'node_index'>[], topology: Topology | null | undefined,
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
  const note = (d.note ?? '').trim()
  const segs = d.segments ?? []
  if (d.answer !== 'neg' && d.answer !== 'off_pattern') out.push('answer')
  else if (d.answer === 'neg' && !note) out.push('note')
  else if (d.answer === 'off_pattern' && !note && !segs.length) out.push('segments_or_note')
  if (segs.some(s => typeof s !== 'string' || s === '') || new Set(segs).size !== segs.length) out.push('segments')
  const datesOk = DATE_RE.test(d.start) && DATE_RE.test(d.end)
  if (!datesOk || d.start > d.end) out.push('range')
  if (datesOk && d.end > TRAIN_END) out.push('after_train_end')
  if (d.target === 'point' && d.start !== d.end) out.push('point')
  const fs = d.family_start ?? null
  if (d.target === 'family' ? !fs || !DATE_RE.test(fs) || fs > d.start : fs !== null) out.push('family_start')
  return out
}

/**
 * 面板里的草稿 → 要存的反馈(保存条件已满足时调用):理由去掉首尾空白,空的不写;neg 不带分段(切到 neg 时
 * 面板已清掉,这里再保一次);family_start 只在 family 时带;source 恒为 picked。
 * 记录的出处(编号、pattern、app、app 版本)由调用方给。
 */
export function draftToFeedback(d: FeedbackDraft, origin: { id: string; pattern: string; app_id: string; app_ver: string }): AnnFeedback {
  const fb: AnnFeedback = {
    id: origin.id, pattern: origin.pattern, app_id: origin.app_id, app_ver: origin.app_ver,
    start: d.start, end: d.end, target: d.target, source: 'picked', answer: d.answer as FeedbackAnswer,
  }
  const note = (d.note ?? '').trim()
  if (note) fb.note = note
  if (d.answer === 'off_pattern' && d.segments?.length) fb.segments = [...d.segments]
  if (d.target === 'family' && d.family_start) fb.family_start = d.family_start
  return fb
}

/** 侧栏里的档:0 朱红、1 lost、2 其余(状态还没取到的算其余)。 */
export function feedbackRank(st: FeedbackStatusOf | null | undefined): 0 | 1 | 2 {
  return st?.red ? 0 : st?.status === 'lost' ? 1 : 2
}

/** 侧栏排序:朱红在前、lost 其次、其余在后;同档按股票、start、end、编号。不改入参。 */
export function sortFeedbackRows(rows: readonly FeedbackRow[],
                                 statusById: Readonly<Record<string, FeedbackStatusOf | undefined>>): FeedbackRow[] {
  const cmp = (a: string, b: string) => (a < b ? -1 : a > b ? 1 : 0)
  return [...rows].sort((a, b) =>
    feedbackRank(statusById[a.feedback.id]) - feedbackRank(statusById[b.feedback.id])
    || cmp(a.symbol, b.symbol) || cmp(a.feedback.start, b.feedback.start)
    || cmp(a.feedback.end, b.feedback.end) || cmp(a.feedback.id, b.feedback.id))
}
