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
 *   放完自动回到 box 工具。
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
 * 冲突提示一次:读结果里每条冲突以 later.ref 为准,看过的记在浏览器里,之后不再弹出。
 */
import { defineStore } from 'pinia'
import { computed, nextTick, ref, shallowRef } from 'vue'
import { AnnotationSaveError, getAnnotations, postAnnotationBatch } from '../api'
import {
  applyOps, baseOf, boxValue, chartOf, featureByName, featureValue, findBox, findSample, mergePlan, mergeRecords,
  newId, sampleValue, toggleAttr, toggleParent, unmergedBox, type AnnBox, type AnnConflict, type AnnFeature,
  type AnnOp, type AnnRead, type AnnSample, type MergePlan, type MergeRecord, type ParentRow,
} from '../annotate/model'
import { sampleMembers } from '../annotate/membership'
import { memberIds } from '../annotate/samples'
import { sampleWindow } from '../annotate/grouping'
import { useViewStore } from './view'

/** 一个动作:拿到读结果,给出要保存的这一批操作(没什么要改时给空数组)。 */
export type Intent = (r: AnnRead) => AnnOp[]

export type LoadStatus = 'idle' | 'loading' | 'ready' | 'unavailable' | 'load_failed'
export type SidebarTab = 'selection' | 'features' | 'pattern'
export type Tool = 'box' | 'point'
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
  const tool = ref<Tool>('box')
  const renaming = ref(false)                      // 选中框的 feature 一行处在「换特征」状态
  const nameFocus = ref(0)                         // 每加一次,侧栏把光标放进起名框
  const pendingMerge = ref<{ from: string; into: string } | null>(null)
  const daysBySymbol = shallowRef<Record<string, string[]>>({})   // 打开过的图的交易日(算框套框的长短)
  const ack = ref<Set<string>>(loadAck())

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
        const ops = queue.value[0](server.value)
        try {
          if (ops.length) server.value = await postAnnotationBatch(ops)
        } catch (e: any) {
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

  /** 删框:同一批把它从样本的成员里拿掉,把挂在它上面的 attach 也拿掉(后端不许成员框指向不存在的框)。 */
  function deleteBox(id: string): void {
    commit((r) => {
      const hit = findBox(r.state, id)
      if (!hit) return []
      const ops: AnnOp[] = [{ kind: 'box', id, base: baseOf(r, 'box', id), value: null }]
      for (const smp of hit.chart.samples) if (smp.members.includes(id)) {
        ops.push({ kind: 'sample', id: smp.id, base: baseOf(r, 'sample', smp.id),
                   value: { ...smp, symbol: hit.chart.symbol, members: smp.members.filter(m => m !== id) } })
      }
      for (const o of hit.chart.boxes) if (o.attach === id) {
        const { attach: _a, ...rest } = o
        ops.push({ kind: 'box', id: o.id, base: baseOf(r, 'box', o.id), value: boxValue(hit.chart.symbol, rest) })
      }
      return ops
    })
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
   * 两种都会让它成为当前样本,并把工具切回 box。返回样本编号。
   */
  function placeSample(symbol: string, date: string): string | null {
    tool.value = 'box'
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

  /** 删样本;框留在图上。 */
  function deleteSample(sampleId: string): void {
    commit((r) => (findSample(r.state, sampleId) ? [{ kind: 'sample', id: sampleId, base: baseOf(r, 'sample', sampleId), value: null }] : []))
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
   * 样本链接(stores/directLinks.ts)和 pattern 页的样本卡都走这一处。keepTab 同 selectSample;
   * keepCompare:compare 下换图留在 compare(样本卡用;链接一律落在 annotate)。
   */
  async function openSample(id: string, opts: { keepTab?: boolean; keepCompare?: boolean } = {}): Promise<boolean> {
    const hit = state.value ? findSample(state.value, id) : null
    if (!hit) return false
    useViewStore().openSymbol(hit.chart.symbol, sampleWindow(hit), { keepCompare: opts.keepCompare })
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

  function setDays(symbol: string, days: string[]): void {
    daysBySymbol.value = { ...daysBySymbol.value, [symbol]: days }
  }

  return {
    server, view, state, status, loadError, saveError, saving, machine, membership,
    selectedBoxId, selectedBox, selectedSampleId, selectedSample, currentSampleId, currentSample, currentPattern, openCount,
    tab, tool, renaming, nameFocus, merges, pendingMerge, daysBySymbol,
    newConflicts, fingerprint, featureById, nameOf, definitionOf,
    load, commit, flushed, createBox, resizeBox, deleteBox, setBoxFeature, setBoxNote, setAttr, addAttr,
    toggleBoxParent, setDefinition, renameFeature, previewMerge, applyMerge, unmerge, selectBox,
    placeSample, toggleMember, setJudgment, setSampleNote, setSamplePattern, moveSamples, setPatternDefinition,
    deleteSample, setCurrentPattern,
    selectSample, openSample, clearSelection, ackConflicts, setDays,
  }
})
