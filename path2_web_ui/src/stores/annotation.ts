/**
 * 标注的读写与 annotate 下的界面状态:框、词表、选中、侧栏页、合并记录、冲突提示。
 *
 * 读写:
 * - 读 GET /annotations(全部批次重放出的状态);写 POST /annotations/batch,每次一批操作,后端只新增文件。
 * - 界面上的每个动作是一个「意图」:拿到读结果,给出这一批操作(base 取读结果的 revs)。动作一发生,先把
 *   意图套在当前显示的状态上显示出来;真正保存时按顺序一个个送,每个都对着后端刚回来的读结果重算一遍,
 *   所以连着点几下,base 也都是最新的,不会自己和自己记成冲突。
 * - 新对象的编号在动作发生时就取定(显示与保存用同一个编号):机器名取 state.machine,序号从当前显示的
 *   next_seq 往上取。
 * - 保存没通过(后端校验拒绝、标注目录不在等):这一个意图丢掉,原因放进 saveError(界面上一直显示到点 ok),
 *   并重读一次标注:被拒多半是另一台机器同步来的修改改变了前提,重读后显示的就是后端眼下的状态。
 *
 * 样本与成员框(成员框的规则见 annotate/membership.ts):
 * - point 工具点一根 K 线放样本,归当前 pattern、默认 pos,成员框按推断;同一 pattern 同一天已有样本就是选中它;
 *   放完工具熄灭(工具默认都不亮,点亮一个只用一次)。
 * - 当前样本:这张图上最后一次放下或选中的样本。画框、选中框都不换掉它;选中另一个样本换成它;点空白处、Esc、
 *   换图清掉。它是当前样本期间新画的框(含画完又改了起止的),推断会收的就并进它(只加不踢);换掉时它的成员框
 *   就此冻结,以后补画的框不会并进去。
 * - 手动点进点出(样本页的成员链与 others、框页的 member_of)永远算数:直接改存下的成员框并记 members_edited;
 *   本页还记住点过的,当前样本重算推断时不会把点掉的框又收回来。跨过样本日的框收不进。
 * - 当前 pattern(顶栏 pattern 一格)记在浏览器里,刷新后还在;null 为 unsorted。
 * - 按编号打开样本(openSample):打开它所在的图并选中它,不换当前 pattern。
 *
 * 归组与 pattern 页(派生量见 annotate/grouping.ts):
 * - unsorted 页整行 move:同一批改这一行全部样本的 pattern(名字是新的就同一批新建);
 * - pattern 页的 definition:写进这个 pattern(空着就拿掉定义);
 * - 点开的计数(openCount):pattern 页上同时只点开一个数,换当前 pattern 时收起。
 *
 * 合并与拆回:合并是一批操作(改写涉及的框、删掉被并的词)。还能拆回的合并由后端从标注文件里认出来
 * (读结果的 merges),刷新、换机器后照样能拆回;拆回再写一批,把词用原编号放回、把框改回去。
 *
 * 反馈(spec 6.13,只在 compare 用;面板状态、状态接口在 stores/feedback.ts):
 * - saveFeedback:新建或改一条反馈(都写整条记录)。pattern 取当前 pattern;app_id、app_ver 取这只股票在
 *   compare 下现算的结果(view.linkedRun,app_ver 是单股预览带回的指纹),改的时候也刷新成当前值;
 *   source 恒为 picked。不在 compare、保存条件不满足(annotate/feedback.ts 的 saveProblems)、这只股票还没有
 *   现算结果、要改的那条不是用户自己挑的(盲看标记不可改)或不属于当前 pattern(否则 pattern 与 app 出处会混)
 *   时不存,返回 null;
 * - deleteFeedback:删一条;盲看标记删不得,什么都不做;
 * - feedbackOf / feedbackOfPattern:取当前显示的(含还没存完的)反馈,图上与侧栏用。
 *
 * 删样本与撤销删除(spec 6.14 G4):
 * - deleteSample 可以带上几个框一起删(样本页先问「只服务它的框」要不要一并删,见 annotate/samples.ts 的
 *   boxesOnlyFor);框的删法同 deleteBox,但同一批一起删的框之间不清 attach(对同一个框既删又改,后端按
 *   duplicate_op 整批拒收);
 * - 删框、删样本、删反馈后记下「最近一次删除」(lastDeletion:删前的值,以及这一批顺带从样本成员里拿掉的框、
 *   顺带拿掉的 attach),界面上一行 deleted … undo。undoDeletion 另写一批:被删的对象用原编号写回原值(base 取
 *   当前 rev,同拆回合并);顺带改过的对象只把拿掉的那一项加回它的当前值,不整值覆盖(删之后的修改不被冲掉)。
 *   再删一次就换成新的;撤过、这次删除没保存成(被拒或保存时已没什么可删)或刷新后消失。
 *
 * 冲突提示一次:读结果里每条冲突以 later.ref 为准,看过的记在浏览器里,之后不再弹出。
 */
import { defineStore } from 'pinia'
import { computed, nextTick, ref, shallowRef } from 'vue'
import { AnnotationSaveError, getAnnotations, postAnnotationBatch } from '../api'
import {
  applyOps, baseOf, boxValue, chartOf, featureByName, featureValue, feedbackValue, findBox, findFeedback, findSample,
  mergePlan, mergeRecords, newId, sampleValue, toggleAttr, toggleParent, unmergedBox, type AnnBox, type AnnConflict,
  type AnnFeature, type AnnFeedback, type AnnKind, type AnnOp, type AnnRead, type AnnSample, type AnnState,
  type MergePlan, type MergeRecord, type ParentRow,
} from '../annotate/model'
import { draftToFeedback, saveProblems, type FeedbackDraft } from '../annotate/feedback'
import { sampleMembers } from '../annotate/membership'
import { memberIds, precedence } from '../annotate/samples'
import { sampleWindow } from '../annotate/grouping'
import { useViewStore } from './view'

/** 一个动作:拿到读结果,给出要保存的这一批操作(没什么要改时给空数组)。 */
export type Intent = (r: AnnRead) => AnnOp[]

export type LoadStatus = 'idle' | 'loading' | 'ready' | 'unavailable' | 'load_failed'
/** 侧栏页签;feedback 只在 compare 下有(components/AnnotationSidebar.vue)。 */
export type SidebarTab = 'selection' | 'features' | 'pattern' | 'feedback'
/** 顶栏的工具;feedback 只在 compare 出现(拖一段日期,对这段里 app 的买点作答,spec 6.13)。 */
export type Tool = 'box' | 'point' | 'feedback'
/** 一条保存被拒的原因:code、后端的原话,以及涉及的样本、框编号(有就带)。 */
export interface SaveProblem { code: string; message: string; sample?: string; box?: string }

const ACK_KEY = 'path2_web_ui.annotation.ack_conflicts.v1'
const PATTERN_KEY = 'path2_web_ui.annotation.current_pattern.v1'

function loadPattern(): string | null {
  try {
    const v = JSON.parse(localStorage.getItem(PATTERN_KEY) ?? 'null')
    return typeof v === 'string' ? v : null
  } catch { return null }
}

function savePattern(p: string | null): void {
  try { localStorage.setItem(PATTERN_KEY, JSON.stringify(p)) } catch { /* 存不了就只在本页记住 */ }
}

function loadAck(): Set<string> {
  try {
    const raw = localStorage.getItem(ACK_KEY)
    const arr = raw ? JSON.parse(raw) : []
    return new Set(Array.isArray(arr) ? arr.filter((x: unknown) => typeof x === 'string') : [])
  } catch { return new Set() }
}

function saveAck(s: Set<string>): void {
  try { localStorage.setItem(ACK_KEY, JSON.stringify([...s])) } catch { /* 存不了就只在本页记住 */ }
}

const sameSet = (a: readonly string[], b: readonly string[]) =>
  a.length === b.length && new Set([...a, ...b]).size === a.length

/** 一个样本的改写:找到它就给出这一条操作,找不到(已被删)就什么都不做。 */
function sampleIntent(id: string, change: (s: AnnSample) => AnnSample): Intent {
  return (r) => {
    const hit = findSample(r.state, id)
    if (!hit) return []
    return [{ kind: 'sample', id, base: baseOf(r, 'sample', id), value: sampleValue(hit.chart.symbol, change(hit.sample)) }]
  }
}

/** 当前样本:编号、它当前期间新画的框、本页记住的手动点进点出、这张图的交易日。 */
interface Current { id: string; fresh: ReadonlySet<string>; manual: Record<string, boolean>; days: readonly string[] }

/** 当前样本按推断重算成员框(只加不踢);变了就给出这一条样本操作。r 是已套上这次框改动的读结果。 */
function growCurrent(r: AnnRead, cur: Current): AnnOp[] {
  const hit = findSample(r.state, cur.id)
  if (!hit) return []
  const next = sampleMembers(hit.sample.date, hit.chart.boxes, cur.days,
                             { stored: hit.sample.members, newBoxes: cur.fresh, manual: cur.manual, gap: r.membership.gap })
  if (sameSet(next, hit.sample.members)) return []
  return [{ kind: 'sample', id: cur.id, base: baseOf(r, 'sample', cur.id),
            value: sampleValue(hit.chart.symbol, { ...hit.sample, members: next }) }]
}

/** 一个框的改写:找到它就给出这一条操作,找不到(已被删)就什么都不做。 */
function boxIntent(id: string, change: (b: AnnBox) => AnnBox): Intent {
  return (r) => {
    const hit = findBox(r.state, id)
    if (!hit) return []
    return [{ kind: 'box', id, base: baseOf(r, 'box', id), value: boxValue(hit.chart.symbol, change(hit.box)) }]
  }
}

// ── 删除与撤销 ──

/**
 * 删一个样本和 / 或几个框的那一批操作(在 r 上算;找不到的对象跳过):
 * - 样本(给了的话):删掉;它自己的成员不用清;
 * - 框:删掉;别的样本存下的成员里有它们的,每个样本一条拿掉它们;挂在它们上面、本批不删的框拿掉 attach。
 *   本批一起删的框之间不清 attach:否则对同一个框既删又改,后端按 duplicate_op 整批拒收。
 * 顺序:样本、被删的框、改成员的样本、拿掉 attach 的框。
 */
function deletionOps(r: AnnRead, sampleId: string | null, boxIds: readonly string[]): AnnOp[] {
  const ops: AnnOp[] = []
  if (sampleId && findSample(r.state, sampleId)) {
    ops.push({ kind: 'sample', id: sampleId, base: baseOf(r, 'sample', sampleId), value: null })
  }
  const gone = new Set(boxIds.filter(id => findBox(r.state, id)))
  if (!gone.size) return ops
  for (const c of r.state.charts) {
    if (!c.boxes.some(b => gone.has(b.id))) continue
    for (const b of c.boxes) if (gone.has(b.id)) ops.push({ kind: 'box', id: b.id, base: baseOf(r, 'box', b.id), value: null })
    for (const smp of c.samples) if (smp.id !== sampleId && smp.members.some(m => gone.has(m))) {
      ops.push({ kind: 'sample', id: smp.id, base: baseOf(r, 'sample', smp.id),
                 value: sampleValue(c.symbol, { ...smp, members: smp.members.filter(m => !gone.has(m)) }) })
    }
    for (const o of c.boxes) if (!gone.has(o.id) && o.attach && gone.has(o.attach)) {
      const { attach: _a, ...rest } = o
      ops.push({ kind: 'box', id: o.id, base: baseOf(r, 'box', o.id), value: boxValue(c.symbol, rest) })
    }
  }
  return ops
}

/** 一个框、样本或反馈眼下存进文件的值(带 symbol);不在(已删、从没有过)为 null。 */
function storedValue(s: AnnState, kind: AnnKind, id: string): Record<string, unknown> | null {
  if (kind === 'box') { const h = findBox(s, id); return h ? boxValue(h.chart.symbol, h.box) : null }
  if (kind === 'sample') { const h = findSample(s, id); return h ? sampleValue(h.chart.symbol, h.sample) : null }
  if (kind === 'feedback') { const h = findFeedback(s, id); return h ? feedbackValue(h.chart.symbol, h.feedback) : null }
  return null
}

/**
 * 最近一次删除(界面上一行 deleted … undo):
 * - removed:被删对象删前的值(带 symbol),第一个是用户点删的那个(样本、框或反馈),其后是一并删的框;
 * - members:这一批顺带从别的样本成员里拿掉的框;attach:顺带拿掉 attach 的框和它原来挂的框;
 * - intent:这次删除的动作本身(保存没成时据它把记录撤掉)。
 */
export interface LastDeletion {
  removed: { kind: AnnKind; id: string; value: Record<string, any> }[]
  members: { sample: string; box: string }[]
  attach: { box: string; parent: string }[]
  intent: Intent
}

/** 由删除那一批操作(在 r 上算出的)和删前的状态,记下删前的值与顺带拿掉的那几项;什么都没删为 null。 */
function deletionRecord(r: AnnRead, ops: readonly AnnOp[], intent: Intent): LastDeletion | null {
  const rec: LastDeletion = { removed: [], members: [], attach: [], intent }
  for (const op of ops) {
    if (op.value === null) {
      const before = storedValue(r.state, op.kind, op.id)
      if (before) rec.removed.push({ kind: op.kind, id: op.id, value: before })
    } else if (op.kind === 'sample') {
      const hit = findSample(r.state, op.id)
      for (const m of hit?.sample.members ?? []) if (!op.value.members.includes(m)) rec.members.push({ sample: op.id, box: m })
    } else if (op.kind === 'box') {
      const hit = findBox(r.state, op.id)
      if (hit?.box.attach && !op.value.attach) rec.attach.push({ box: op.id, parent: hit.box.attach })
    }
  }
  return rec.removed.length ? rec : null
}

/**
 * 撤销一次删除的那一批操作(在 r 上算):
 * - 被删的对象眼下不在就用原编号写回原值,base 取当前 rev(还在的不动:删除没保存成,或别处已放回);
 *   写回的样本,成员里眼下已不在这只股票上或越过样本日的框不收回(否则后端拒收整批);
 *   写回的反馈属于某个 issue 且这个 issue 眼下还有别的处时,内容照那些处现在的写;
 * - 顺带拿掉的成员:样本和框都还在、框没越过样本日、眼下不是成员时,加回样本的当前值(一个样本一条,
 *   成员按框的先后排);
 * - 顺带拿掉的 attach:框和原来挂的框都还在、这个框眼下既没 attach 也没 detach 时,加回框的当前值。
 * 删之后对这些对象的别的修改都留着。
 */
function undoOps(r: AnnRead, rec: LastDeletion): AnnOp[] {
  const back: AnnOp[] = rec.removed.filter(x => !storedValue(r.state, x.kind, x.id))
    .map(x => ({ kind: x.kind, id: x.id, base: baseOf(r, x.kind, x.id), value: structuredClone(x.value) }))
  // 写回的反馈若属于某个 issue:这个 issue 眼下还有别的处时,内容照它们现在的写(删之后可能被 all 改过,
  // 照原值写回会和各处不一致、后端拒收整批);没有别的处就照原值。
  // 四个键(answer、note、nodes、dag)整个照抄、那一处没有的键就删掉:它们正是「带不带 answer」两种形状各自的
  // 规则管的全部键,所以写回的那条和照抄的那处形状一致,那处合规写回的就合规。只抄 note、nodes 不行:
  // 那一处若是以前存下的「带 answer、点了 node、没写 note」,写回的会成「不带 answer 又没有 note」而被拒。
  for (const op of back) if (op.kind === 'feedback' && op.value.issue) {
    const now = r.state.charts.flatMap(c => c.feedback ?? []).find(f => f.issue === op.value.issue)
    if (!now) continue
    for (const k of ['answer', 'note', 'nodes', 'dag'] as const) {
      if (now[k] === undefined) delete op.value[k]
      else op.value[k] = structuredClone(now[k])
    }
  }
  const after = applyOps(r, back).state
  const boxOn =(symbol: string, id: string) => chartOf(after, symbol)?.boxes.find(b => b.id === id) ?? null
  for (const op of back) if (op.kind === 'sample') {
    op.value.members = op.value.members.filter((m: string) => {
      const b = boxOn(op.value.symbol, m)
      return b && b.end <= op.value.date
    })
  }
  const ops = [...back]
  const adds = new Map<string, string[]>()
  for (const { sample, box } of rec.members) adds.set(sample, [...(adds.get(sample) ?? []), box])
  for (const [sid, ids] of adds) {
    const hit = findSample(after, sid)
    if (!hit) continue
    const put = ids.filter((id, i) => ids.indexOf(id) === i && !hit.sample.members.includes(id)
      && (boxOn(hit.chart.symbol, id)?.end ?? '￿') <= hit.sample.date)
    if (put.length) {
      // 存下的成员按框的先后排(同 sampleMembers):加回的插回它原来的位置
      const byId = new Map(hit.chart.boxes.map(b => [b.id, b]))
      const members = [...hit.sample.members, ...put].sort((a, b) => {
        const x = byId.get(a), y = byId.get(b)
        return x && y ? precedence(x, y) : x ? -1 : y ? 1 : 0
      })
      ops.push({ kind: 'sample', id: sid, base: baseOf(r, 'sample', sid),
                 value: sampleValue(hit.chart.symbol, { ...hit.sample, members }) })
    }
  }
  for (const { box, parent } of rec.attach) {
    const hit = findBox(after, box)
    if (!hit || hit.box.attach || hit.box.detach || !boxOn(hit.chart.symbol, parent)) continue
    ops.push({ kind: 'box', id: box, base: baseOf(r, 'box', box), value: boxValue(hit.chart.symbol, { ...hit.box, attach: parent }) })
  }
  return ops
}

export const useAnnotationStore = defineStore('annotation', () => {
  const server = shallowRef<AnnRead | null>(null)
  const queue = shallowRef<Intent[]>([])
  const status = ref<LoadStatus>('idle')
  const loadError = ref<string | null>(null)
  const saveError = ref<SaveProblem[] | null>(null)
  const saving = ref(false)

  const selectedBoxId = ref<string | null>(null)
  const selectedSampleId = ref<string | null>(null)
  const currentSampleId = ref<string | null>(null)                  // 当前样本
  const freshBoxes = ref<ReadonlySet<string>>(new Set())             // 当前样本期间新画的框
  const manual = ref<Record<string, Record<string, boolean>>>({})    // 本页记住的手动点进点出:样本 → 框 → 进 / 出
  const currentPattern = ref<string | null>(loadPattern())           // 顶栏的当前 pattern;null = unsorted
  const openCount = ref<string | null>(null)                         // pattern 页上点开的计数(grouping.ts 的 countId)
  const tab = ref<SidebarTab>('selection')
  // 顶栏的工具:默认都不亮(图上拖动是平移),点亮一个只用一次,见 components/annotateGestures.ts
  const tool = ref<Tool | null>(null)
  const renaming = ref(false)                      // 选中框的 feature 一行处在「换特征」状态
  const nameFocus = ref(0)                         // 每加一次,侧栏把光标放进起名框
  const pendingMerge = ref<{ from: string; into: string } | null>(null)
  const daysBySymbol = shallowRef<Record<string, string[]>>({})   // 打开过的图的交易日(算框套框的长短)
  const ack = ref<Set<string>>(loadAck())
  const lastDeletion = shallowRef<LastDeletion | null>(null)       // 最近一次删除(可撤),见模块说明

  /** 当前显示的读结果:后端的读结果,再套上还没保存完的动作。 */
  const view = computed<AnnRead | null>(() => {
    if (!server.value) return null
    let r = server.value
    for (const it of queue.value) r = applyOps(r, it(r))
    return r
  })
  const state = computed(() => view.value?.state ?? null)
  /** 还能拆回的合并(后端从标注文件里认出的),按合并的先后。 */
  const merges = computed<MergeRecord[]>(() => (server.value ? mergeRecords(server.value) : []))
  const machine = computed(() => server.value?.state.machine ?? null)

  const featureById = computed(() => new Map((state.value?.features ?? []).map(f => [f.id, f])))
  function nameOf(fid: string | null): string | null {
    return fid ? featureById.value.get(fid)?.name ?? fid : null
  }
  /** 词的定义(还没写为空串):特征名、属性名的悬停只放它。 */
  function definitionOf(fid: string): string {
    return featureById.value.get(fid)?.definition ?? ''
  }

  const selectedBox = computed(() => (selectedBoxId.value && state.value ? findBox(state.value, selectedBoxId.value) : null))
  const selectedSample = computed(() =>
    (selectedSampleId.value && state.value ? findSample(state.value, selectedSampleId.value) : null))
  const currentSample = computed(() =>
    (currentSampleId.value && state.value ? findSample(state.value, currentSampleId.value) : null))
  /** 成员框推断的默认值(后端读路由带出,和参照实现同一处设定)。 */
  const membership = computed(() => server.value?.membership ?? null)
  /** compare 对照的容差(后端 path2_web/annotation/match.py 唯一设定,读路由带出)。 */
  const match = computed(() => server.value?.match ?? null)

  /** 还没看过的冲突(每条以 later.ref 为准)。 */
  const newConflicts = computed<AnnConflict[]>(() =>
    (server.value?.conflicts ?? []).filter(c => !ack.value.has(c.later.ref)))
  const fingerprint = computed(() => server.value?.fingerprint ?? null)

  async function load(): Promise<void> {
    status.value = 'loading'
    try {
      server.value = await getAnnotations()
      status.value = 'ready'
      loadError.value = null
      if (currentPattern.value !== null && !server.value.state.patterns.some(p => p.name === currentPattern.value)) {
        setCurrentPattern(null)
      }
    } catch (e: any) {
      status.value = e?.status === 503 ? 'unavailable' : 'load_failed'
      loadError.value = String(e?.message ?? e)
    }
  }

  async function pump(): Promise<void> {
    if (saving.value) return
    saving.value = true
    try {
      while (queue.value.length && server.value) {
        const it = queue.value[0]
        const ops = it(server.value)
        // 这次删除保存时已没什么可删(别处已删掉):不留可撤的记录
        if (!ops.length && lastDeletion.value?.intent === it) lastDeletion.value = null
        try {
          if (ops.length) server.value = await postAnnotationBatch(ops)
        } catch (e: any) {
          if (lastDeletion.value?.intent === it) lastDeletion.value = null     // 删除没保存成:没什么可撤
          saveError.value = e instanceof AnnotationSaveError ? e.reasons
            : [{ code: 'save_failed', message: String(e?.message ?? e) }]
          if (e?.status === 503) status.value = 'unavailable'
          else if (e?.status === 400) await reread()
        }
        queue.value = queue.value.slice(1)
      }
    } finally {
      saving.value = false
    }
  }

  /** 保存被拒后重读一次:显示后端眼下的状态(比如另一台机器同步来的修改)。读不到就留着原来的。 */
  async function reread(): Promise<void> {
    try { server.value = await getAnnotations() } catch { /* 读不到:留着原来的读结果 */ }
  }

  /** 记下一个动作:马上显示,按顺序保存。 */
  function commit(it: Intent): void {
    if (!server.value) return
    saveError.value = null
    queue.value = [...queue.value, it]
    void pump()
  }

  /** 等全部动作保存完(测试与换图前用)。 */
  async function flushed(): Promise<void> {
    while (saving.value || queue.value.length) await new Promise(r => setTimeout(r, 10))
  }

  /** 从当前显示的 next_seq 往上取 n 个新序号。 */
  function takeSeqs(n: number): number[] {
    const start = view.value?.next_seq ?? 1
    return Array.from({ length: n }, (_, i) => start + i)
  }

  /** 按名字找词;没有就新起一个(编号此刻取定)。返回词编号和要新建的词(已有时为 null)。 */
  function wordFor(name: string): { id: string; create: AnnFeature | null } {
    const hit = state.value ? featureByName(state.value, name) : null
    if (hit) return { id: hit.id, create: null }
    const id = newId('w', machine.value!, takeSeqs(1)[0])
    return { id, create: { id, name: name.trim() } }
  }

  /** 新词还不在读结果里时,给出新建它的操作(同一批里先建词、再让框用它)。 */
  function createIfMissing(r: AnnRead, create: AnnFeature | null): AnnOp[] {
    return create && !r.state.features.some(f => f.id === create.id)
      ? [{ kind: 'feature', id: create.id, base: null, value: featureValue(create) }] : []
  }

  // ── 框 ──

  /**
   * 这张图上的当前样本(没有为 null)。drawn:这次新画的框,记进「当前样本期间新画的框」;改起止时不给。
   * 返回的是此刻的快照,意图保存时照它重算。
   */
  function currentOn(symbol: string, drawn: string | null): Current | null {
    const cur = currentSample.value
    if (!cur || cur.chart.symbol !== symbol) return null
    if (drawn) freshBoxes.value = new Set([...freshBoxes.value, drawn])
    return { id: cur.sample.id, fresh: freshBoxes.value, manual: { ...(manual.value[cur.sample.id] ?? {}) },
             days: daysBySymbol.value[symbol] ?? [] }
  }

  /** 一次框的改写,连同当前样本按推断重算出的成员框(同一批)。 */
  function withCurrent(ops: (r: AnnRead) => AnnOp[], cur: Current | null): Intent {
    return (r) => {
      const first = ops(r)
      return cur && first.length ? [...first, ...growCurrent(applyOps(r, first), cur)] : first
    }
  }

  /** 画一个新框;feature 给了就直接带这个特征(在特征轨上拖出来的)。新框被选中;推断会收它的话并进当前样本。 */
  function createBox(symbol: string, start: string, end: string, feature: string | null): string | null {
    if (!machine.value) return null
    const [seq] = takeSeqs(1)
    const id = newId('b', machine.value, seq)
    const box: AnnBox = { id, feature, start, end }
    commit(withCurrent(() => [{ kind: 'box', id, base: null, value: boxValue(symbol, box) }], currentOn(symbol, id)))
    selectBox(id)
    renaming.value = false
    if (!feature) nameFocus.value++
    return id
  }

  /**
   * 改框的起止。当前样本期间新画的框改完进了推断范围,也并进当前样本;别的框不并(只有新画的框会自动并进,
   * 手动点掉的旧框不会因为拖了一下又被收回来)。越过样本日的限制由拖动时的界面守,保存时后端再查。
   */
  function resizeBox(id: string, start: string, end: string): void {
    const hit = state.value ? findBox(state.value, id) : null
    const cur = hit ? currentOn(hit.chart.symbol, null) : null
    commit(withCurrent(boxIntent(id, b => ({ ...b, start, end })), cur))
  }

  /** 删框:同一批把它从样本的成员里拿掉,把挂在它上面的 attach 也拿掉(后端不许成员框指向不存在的框)。可撤。 */
  function deleteBox(id: string): void {
    commitDeletion((r) => deletionOps(r, null, [id]))
    if (selectedBoxId.value === id) selectBox(null)
  }

  /** 给框定特征:选已有的词(给编号),或输入一个名字(有同名的就用它,没有就新起)。 */
  function setBoxFeature(boxId: string, pick: { id: string } | { name: string }): void {
    if ('name' in pick && !pick.name.trim()) return
    const { id: fid, create } = 'id' in pick ? { id: pick.id, create: null } : wordFor(pick.name)
    commit((r) => [...createIfMissing(r, create), ...boxIntent(boxId, b => ({ ...b, feature: fid }))(r)])
    renaming.value = false
  }

  function setBoxNote(boxId: string, note: string): void {
    commit(boxIntent(boxId, b => {
      const next = { ...b }
      if (note.trim()) next.note = note
      else delete next.note
      return next
    }))
  }

  /** 属性三态:点 true / false;已按下的再点一下回到 null。 */
  function setAttr(boxId: string, fid: string, clicked: boolean): void {
    commit(boxIntent(boxId, b => ({ ...b, attrs: toggleAttr(b.attrs, fid, clicked) })))
  }

  /** 挂一条新属性(词表里的词;没有就新起),先判成 true。 */
  function addAttr(boxId: string, name: string): void {
    if (!name.trim()) return
    const w = wordFor(name)
    commit((r) => [...createIfMissing(r, w.create),
      ...boxIntent(boxId, b => (b.attrs && w.id in b.attrs ? b : { ...b, attrs: { ...(b.attrs ?? {}), [w.id]: true } }))(r)])
  }

  /** 点 parent 一行的 ⊂(detach / attach,规则见 annotate/model.ts 的 parentRow)。 */
  function toggleBoxParent(boxId: string, row: ParentRow): void {
    commit(boxIntent(boxId, b => toggleParent(b, row)))
  }

  // ── 样本与成员框 ──

  /**
   * point 工具点在某天:同一张图上当前 pattern 这天已有样本就选中它,否则放一个新样本(pos,成员框按推断)。
   * 两种都会让它成为当前样本,并熄灭工具(point 只用一次)。返回样本编号。
   */
  function placeSample(symbol: string, date: string): string | null {
    tool.value = null
    if (!machine.value || !state.value) return null
    const pattern = currentPattern.value
    const same = chartOf(state.value, symbol)?.samples.find(x => x.date === date && x.pattern === pattern)
    if (same) { selectSample(same.id); return same.id }
    const id = newId('s', machine.value, takeSeqs(1)[0])
    const days = daysBySymbol.value[symbol] ?? []
    commit((r) => {
      const boxes = chartOf(r.state, symbol)?.boxes ?? []
      const members = sampleMembers(date, boxes, days, { gap: r.membership.gap })
      return [{ kind: 'sample', id, base: null,
                value: sampleValue(symbol, { id, date, pattern, judgment: 'pos', members }) }]
    })
    selectSample(id)
    return id
  }

  /** 手动把框收进样本或拿掉(永远算数,记 members_edited);跨过样本日的框收不进。 */
  function toggleMember(sampleId: string, boxId: string): void {
    const hit = state.value ? findSample(state.value, sampleId) : null
    const box = hit?.chart.boxes.find(b => b.id === boxId)
    if (!hit || !box) return
    const on = memberIds(hit.sample, hit.chart).has(boxId)
    if (!on && box.end > hit.sample.date) return
    manual.value = { ...manual.value, [sampleId]: { ...(manual.value[sampleId] ?? {}), [boxId]: !on } }
    const days = daysBySymbol.value[hit.chart.symbol] ?? []
    commit((r) => {
      const h = findSample(r.state, sampleId)
      if (!h) return []
      const members = sampleMembers(h.sample.date, h.chart.boxes, days,
                                    { stored: h.sample.members, manual: { [boxId]: !on }, gap: r.membership.gap })
      return sampleIntent(sampleId, x => ({ ...x, members, members_edited: true }))(r)
    })
  }

  function setJudgment(sampleId: string, judgment: AnnSample['judgment']): void {
    commit(sampleIntent(sampleId, x => ({ ...x, judgment })))
  }

  function setSampleNote(sampleId: string, note: string): void {
    commit(sampleIntent(sampleId, x => {
      const next = { ...x }
      if (note.trim()) next.note = note
      else delete next.note
      return next
    }))
  }

  /** pattern 名还不在读结果里时,给出新建它的操作(同一批里先建 pattern、再让样本用它)。 */
  function patternIfMissing(r: AnnRead, name: string | null): AnnOp[] {
    return name !== null && !r.state.patterns.some(p => p.name === name)
      ? [{ kind: 'pattern', id: name, base: null, value: { name } }] : []
  }

  /** 改样本的 pattern(null = unsorted);名字是新的就同一批新建这个 pattern。 */
  function setSamplePattern(sampleId: string, name: string | null): void {
    moveSamples([sampleId], name)
  }

  /** 把几个样本(unsorted 页的一整行)挪进一个 pattern(null = unsorted):同一批改它们的 pattern;
   *  名字是新的就同一批新建这个 pattern。 */
  function moveSamples(ids: readonly string[], name: string | null): void {
    const p = name === null ? null : name.trim()
    if (p === '' || !ids.length) return
    commit((r) => {
      const ops: AnnOp[] = []
      for (const id of ids) ops.push(...sampleIntent(id, x => ({ ...x, pattern: p }))(r))
      return ops.length ? [...patternIfMissing(r, p), ...ops] : []
    })
  }

  /** pattern 的定义:写进这个 pattern;空着就拿掉定义。其余字段(flags)照旧。 */
  function setPatternDefinition(name: string, text: string): void {
    const t = text.trim()
    commit((r) => {
      const p = r.state.patterns.find(x => x.name === name)
      if (!p || (p.definition ?? '') === t) return []
      const { definition: _d, ...rest } = p
      return [{ kind: 'pattern', id: name, base: baseOf(r, 'pattern', name), value: t ? { ...rest, definition: t } : rest }]
    })
  }

  /**
   * 删样本;boxIds 给了就同一批把这几个框也删掉(样本页问过「只服务它的框」要不要一并删),删法同 deleteBox,
   * 一起删的框之间不清 attach。没给的框留在图上。可撤。
   */
  function deleteSample(sampleId: string, boxIds: readonly string[] = []): void {
    const ids = [...boxIds]
    commitDeletion((r) => deletionOps(r, sampleId, ids))
    if (selectedBoxId.value && ids.includes(selectedBoxId.value)) selectBox(null)
    if (selectedSampleId.value === sampleId) selectedSampleId.value = null
    if (currentSampleId.value === sampleId) makeCurrent(null)
  }

  /** 顶栏换当前 pattern(新放的样本归它);名字是新的就新建这个 pattern。 */
  function setCurrentPattern(name: string | null): void {
    const p = name === null ? null : name.trim()
    if (p === '') return
    if (p !== null && state.value && !state.value.patterns.some(x => x.name === p)) commit(r => patternIfMissing(r, p))
    if (currentPattern.value !== p) openCount.value = null
    currentPattern.value = p
    savePattern(p)
  }

  // ── 反馈 ──

  /**
   * 存一条反馈:draft.id 给了是改那一条(整条重写,同编号),没给是新建(编号此刻取定)。返回编号;不存时返回 null
   * (不在 compare、保存条件不满足、这只股票还没有现算结果、要改的那条找不到 / 不是用户自己挑的 / 不属于当前
   * pattern、还没有当前 pattern)。
   * 改 redraw 出来的范围时 draft 的 target 是 range、不带 family_start,整条重写后原来的 family_start 随之拿掉。
   * 记录和原来一模一样(连 app_ver 也没变)时不写。
   * draft.issue 是这一处要带的 issue 值(没有即不带)。others 是同一批里一起改的别的处(同一个 issue 的其余成员,
   * 可在别的股票上):它们的 note、nodes、issue 换成这一处的,记录上以前存下的 answer、dag 一并拿掉(和这一处
   * 一样改写成不带这两个键的形状),其余字段(日期、app_ver 等)保持原值,各用各的
   * 修改记录作 base。后端要求带同一个 issue 值的各处内容相同,所以必须和这一处放在同一批里;保存时已不在、
   * 不是用户自己挑的、不属于当前 pattern 的成员跳过。
   */
  function saveFeedback(draft: FeedbackDraft & { id?: string }, others: readonly string[] = []): string | null {
    if (!machine.value || !state.value || saveProblems(draft).length) return null
    const v = useViewStore()
    const run = v.comparing && v.symbol === draft.symbol && v.linkedRun?.symbol === draft.symbol ? v.linkedRun : null
    const appVer = run?.scan.app_ver
    if (!run || !appVer) return null
    let id = draft.id ?? null
    const pattern = currentPattern.value
    if (pattern === null) return null
    if (id) {
      const old = findFeedback(state.value, id)
      if (!old || old.chart.symbol !== draft.symbol || old.feedback.source !== 'picked'
          || old.feedback.pattern !== pattern) return null
    }
    if (!id) id = newId('f', machine.value, takeSeqs(1)[0])
    const fid = id
    const fb = draftToFeedback(draft, { id: fid, pattern, app_id: run.app, app_ver: appVer })
    const value = feedbackValue(draft.symbol, fb)
    const editing = !!draft.id
    commit((r) => {
      const hit = findFeedback(r.state, fid)
      if (editing && (!hit || hit.feedback.source !== 'picked')) return []      // 保存前已被删(或换成了盲看标记)
      const ops: AnnOp[] = []
      if (!hit || JSON.stringify(feedbackValue(hit.chart.symbol, hit.feedback)) !== JSON.stringify(value)) {
        ops.push({ kind: 'feedback', id: fid, base: baseOf(r, 'feedback', fid), value })
      }
      for (const oid of others) {
        const o = oid === fid ? null : findFeedback(r.state, oid)
        if (!o || o.feedback.source !== 'picked' || o.feedback.pattern !== pattern) continue
        const { note: _n, nodes: _s, dag: _d, issue: _i, answer: _a, ...rest } = o.feedback
        const next: AnnFeedback = { ...rest }
        if (fb.note) next.note = fb.note
        if (fb.nodes?.length) next.nodes = [...fb.nodes]
        if (fb.issue) next.issue = fb.issue
        const v2 = feedbackValue(o.chart.symbol, next)
        if (JSON.stringify(feedbackValue(o.chart.symbol, o.feedback)) !== JSON.stringify(v2)) {
          ops.push({ kind: 'feedback', id: oid, base: baseOf(r, 'feedback', oid), value: v2 })
        }
      }
      return ops
    })
    return fid
  }

  /** 删一条反馈;盲看标记(source 不是 picked)删不得,什么都不做。可撤。 */
  function deleteFeedback(id: string): void {
    commitDeletion((r) => {
      const hit = findFeedback(r.state, id)
      return hit && hit.feedback.source === 'picked'
        ? [{ kind: 'feedback', id, base: baseOf(r, 'feedback', id), value: null }] : []
    })
  }

  // ── 删除的撤销 ──

  /** 记下一次删除:按当前显示的状态记下删前的值(换掉上一次的记录),再照常保存。显示的状态里没什么可删就不记。 */
  function commitDeletion(it: Intent): void {
    const r = view.value
    if (!r) return
    lastDeletion.value = deletionRecord(r, it(r), it) ?? lastDeletion.value
    commit(it)
  }

  /** 撤销最近一次删除(规则见 undoOps);撤过就不能再撤。 */
  function undoDeletion(): void {
    const rec = lastDeletion.value
    if (!rec) return
    lastDeletion.value = null
    commit((r) => undoOps(r, rec))
  }

  /** 这只股票上某个 pattern(缺省为当前 pattern)的反馈,按(start、end、编号);含盲看标记,看 source 分。 */
  function feedbackOf(symbol: string | null, pattern: string | null = currentPattern.value): AnnFeedback[] {
    if (!state.value || pattern === null) return []
    return (chartOf(state.value, symbol)?.feedback ?? []).filter(f => f.pattern === pattern)
  }

  /** 某个 pattern(缺省为当前 pattern)跨股票的全部反馈,按股票、再按(start、end、编号);含盲看标记。 */
  function feedbackOfPattern(pattern: string | null = currentPattern.value): { symbol: string; feedback: AnnFeedback }[] {
    if (!state.value || pattern === null) return []
    return state.value.charts.flatMap(c => (c.feedback ?? []).filter(f => f.pattern === pattern)
      .map(feedback => ({ symbol: c.symbol, feedback })))
  }

  // ── 词表 ──

  /** 写定义:只在这个词还没有定义时写得进去(定义定下就不改,意思变了另起一个词)。 */
  function setDefinition(fid: string, text: string): void {
    const t = text.trim()
    if (!t) return
    commit((r) => {
      const f = r.state.features.find(x => x.id === fid)
      if (!f || f.definition) return []
      return [{ kind: 'feature', id: fid, base: baseOf(r, 'feature', fid), value: featureValue({ ...f, definition: t }) }]
    })
  }

  /** 改名:改一处,用到它的框处处跟着变。重名不改,返回 name_taken。 */
  function renameFeature(fid: string, name: string): 'ok' | 'empty' | 'name_taken' {
    const t = name.trim()
    if (!t) return 'empty'
    const other = state.value ? featureByName(state.value, t) : null
    if (other && other.id !== fid) return 'name_taken'
    if (other) return 'ok'
    commit((r) => {
      const f = r.state.features.find(x => x.id === fid)
      if (!f) return []
      return [{ kind: 'feature', id: fid, base: baseOf(r, 'feature', fid), value: featureValue({ ...f, name: t }) }]
    })
    return 'ok'
  }

  function previewMerge(from: string, into: string): MergePlan | null {
    return state.value ? mergePlan(state.value, from, into) : null
  }

  /** 把 from 并进 into:同一批改写涉及的框、删掉 from(后端据这一批认出合并,拆回时用)。 */
  function applyMerge(from: string, into: string): void {
    if (!state.value?.features.some(f => f.id === from) || from === into) return
    pendingMerge.value = null
    commit((r) => {
      const plan = mergePlan(r.state, from, into)
      return [
        ...plan.changes.map(c => ({ kind: 'box' as const, id: c.after.id, base: baseOf(r, 'box', c.after.id),
                                    value: boxValue(c.symbol, c.after) })),
        { kind: 'feature', id: from, base: baseOf(r, 'feature', from), value: null },
      ]
    })
  }

  /** 拆回一次合并:被并的词用原编号放回词表,当时改过的框改回去(之后又动过的框只改回特征和属性)。 */
  function unmerge(i: number): void {
    const rec = merges.value[i]
    if (!rec) return
    commit((r) => {
      const ops: AnnOp[] = []
      if (!r.state.features.some(f => f.id === rec.from.id)) {
        ops.push({ kind: 'feature', id: rec.from.id, base: baseOf(r, 'feature', rec.from.id), value: featureValue(rec.from) })
      }
      for (const c of rec.changes) {
        const hit = findBox(r.state, c.after.id)
        const next = hit ? unmergedBox(c, hit.box, rec.from.id, rec.into) : null
        if (hit && next) ops.push({ kind: 'box', id: next.id, base: baseOf(r, 'box', next.id), value: boxValue(hit.chart.symbol, next) })
      }
      return ops
    })
  }

  // ── 选中、提示 ──

  /** 选中一个框(null:只取消选中框)。当前样本不换。 */
  function selectBox(id: string | null): void {
    selectedBoxId.value = id
    renaming.value = false
    if (id) {
      selectedSampleId.value = null
      tab.value = 'selection'
    }
  }

  /** 换当前样本:旧的就此冻结(以后新画的框不再并进它),新的从此刻起记「期间新画的框」。 */
  function makeCurrent(id: string | null): void {
    if (currentSampleId.value === id) return
    currentSampleId.value = id
    freshBoxes.value = new Set()
  }

  /** 选中一个样本,它成为当前样本。keepTab:侧栏留在当前页(从 pattern 页打开样本时),否则翻到 selection。 */
  function selectSample(id: string | null, opts: { keepTab?: boolean } = {}): void {
    selectedSampleId.value = id
    selectedBoxId.value = null
    renaming.value = false
    if (id) {
      if (!opts.keepTab) tab.value = 'selection'
      makeCurrent(id)
    }
  }

  /**
   * 按编号找样本,打开它所在的图(图窗停在样本的跨度上)并选中它;找不到返回 false。
   * 样本链接(stores/directLinks.ts)和 pattern 页的样本卡都走这一处。keepTab 同 selectSample。
   */
  async function openSample(id: string, opts: { keepTab?: boolean } = {}): Promise<boolean> {
    const hit = state.value ? findSample(state.value, id) : null
    if (!hit) return false
    useViewStore().openSymbol(hit.chart.symbol, sampleWindow(hit))
    await nextTick()               // 换图会清掉选中(KlineChart 的 symbol 监听),等它跑完再选中
    selectSample(id, opts)
    return true
  }

  /** 点空白处、Esc、换图:什么都不选,当前样本也清掉(冻结)。 */
  function clearSelection(): void {
    selectBox(null)
    selectedSampleId.value = null
    makeCurrent(null)
  }

  function ackConflicts(): void {
    const next = new Set(ack.value)
    for (const c of server.value?.conflicts ?? []) next.add(c.later.ref)
    ack.value = next
    saveAck(next)
  }

  /** 点工具按钮(或按快捷键):亮着就熄,没亮就点亮它(另一个随之熄灭)。 */
  function toggleTool(t: Tool): void {
    tool.value = tool.value === t ? null : t
  }

  function setDays(symbol: string, days: string[]): void {
    daysBySymbol.value = { ...daysBySymbol.value, [symbol]: days }
  }

  return {
    server, view, state, status, loadError, saveError, saving, machine, membership, match,
    selectedBoxId, selectedBox, selectedSampleId, selectedSample, currentSampleId, currentSample, currentPattern, openCount,
    tab, tool, toggleTool, renaming, nameFocus, merges, pendingMerge, daysBySymbol,
    newConflicts, fingerprint, featureById, nameOf, definitionOf,
    load, commit, flushed, createBox, resizeBox, deleteBox, setBoxFeature, setBoxNote, setAttr, addAttr,
    toggleBoxParent, setDefinition, renameFeature, previewMerge, applyMerge, unmerge, selectBox,
    placeSample, toggleMember, setJudgment, setSampleNote, setSamplePattern, moveSamples, setPatternDefinition,
    deleteSample, setCurrentPattern, saveFeedback, deleteFeedback, feedbackOf, feedbackOfPattern,
    lastDeletion, undoDeletion, selectSample, openSample, clearSelection, ackConflicts, setDays,
  }
})
