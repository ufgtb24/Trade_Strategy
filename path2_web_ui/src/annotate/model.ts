/**
 * 标注的数据形状与纯函数:读结果的类型、把一批操作套到状态上、属性三态、词表用量、起名候选、
 * 特征轨的排法、合并的波及面。不碰网络和界面,stores/annotation.ts 和侧栏、图都用它。
 *
 * 形状与后端 path2_web/annotation/store.py 的读结果一致(GET /annotations):
 *   {state: {machine, data_fingerprint, features, patterns, charts}, conflicts, unsynced, violations,
 *    fingerprint, merges, revs, next_seq, ignored_files, membership}
 * membership 是成员框推断的默认值 {gap, near},和会话用的参照实现读同一处设定。
 * 一条操作把一个对象改成新值 {kind, id, base, value};value 为 null 表示删除;框和样本的 value 带 symbol。
 *
 * 属性三态:attrs 是特征编号 → true / false,键不在就是 null(没看过)。null 不算「没有」:
 * 后加的属性在旧框上是没看过,不能被当成 false 算进「没有」里。
 */
import { canAttach, parents, rankOf, type NestBox } from './membership'

export type AnnKind = 'feature' | 'pattern' | 'box' | 'sample'

export interface AnnFeature { id: string; name: string; definition?: string }
export interface AnnBox {
  id: string
  feature: string | null
  start: string
  end: string
  attrs?: Record<string, boolean>
  note?: string
  detach?: true
  attach?: string
}
export interface AnnSample {
  id: string
  date: string
  pattern: string | null
  judgment: 'pos' | 'neg'
  members: string[]
  members_edited?: boolean
  note?: string
}
export interface AnnPattern { name: string; definition?: string; flags?: { feature: string; mapping_row: number }[] }
export interface AnnChart { symbol: string; boxes: AnnBox[]; samples: AnnSample[] }
export interface AnnState {
  machine: string
  data_fingerprint: string | null
  features: AnnFeature[]
  patterns: AnnPattern[]
  charts: AnnChart[]
}
export interface AnnEdit { ref: string; machine: string; ts: string }
export interface AnnConflict { kind: AnnKind; id: string; base: string | null; later: AnnEdit; earlier: AnnEdit | null }
export interface AnnFingerprint {
  local: string | null
  local_error: string | null
  recorded: { fingerprint: string | null; batches: number }[]
  consistent: boolean
}
/** 成员框推断的默认值:gap(前后两段空几根以内算连着)、near(画了没收的范围)。 */
export interface MembershipDefaults { gap: number; near: number }
export interface AnnRead {
  state: AnnState
  conflicts: AnnConflict[]
  unsynced: { kind: AnnKind; id: string; base: string; ref: string }[]
  violations: { code: string; message: string }[]
  fingerprint: AnnFingerprint
  merges: AnnMerge[]
  revs: Record<AnnKind, Record<string, string>>
  next_seq: number
  ignored_files: string[]
  membership: MembershipDefaults
}
export interface AnnOp { kind: AnnKind; id: string; base: string | null; value: any }
/** 存进文件的框:状态里的框再带上它所在的股票。 */
export type StoredBox = AnnBox & { symbol: string }
/** 读结果里一条还能拆回的合并:被删的词(删之前的值)、并进的词、那些框在合并那一批改前改后的值。 */
export interface AnnMerge {
  ref: string
  machine: string
  ts: string
  feature: AnnFeature
  into: string
  boxes: { id: string; before: StoredBox; after: StoredBox }[]
}

/** 带机器名的新编号:词 w、框 b、样本 s。 */
export function newId(letter: 'w' | 'b' | 's', machine: string, seq: number): string {
  return `${letter}-${machine}-${seq}`
}

/** 写操作时的 base:这个对象的最后一次修改(含已删的);新建为 null。 */
export function baseOf(r: AnnRead, kind: AnnKind, id: string): string | null {
  return r.revs[kind]?.[id] ?? null
}

/** 框存进操作的值:带 symbol;空的 attrs、note 不写,detach 只写 true,attach 只写编号。 */
export function boxValue(symbol: string, b: AnnBox): Record<string, unknown> {
  const v: Record<string, unknown> = { id: b.id, symbol, feature: b.feature, start: b.start, end: b.end }
  if (b.attrs && Object.keys(b.attrs).length) v.attrs = { ...b.attrs }
  if (b.note) v.note = b.note
  if (b.detach) v.detach = true
  else if (b.attach) v.attach = b.attach
  return v
}

/** 样本存进操作的值:带 symbol;members_edited 只写 true,空的 note 不写。 */
export function sampleValue(symbol: string, smp: AnnSample): Record<string, unknown> {
  const v: Record<string, unknown> = {
    id: smp.id, symbol, date: smp.date, pattern: smp.pattern, judgment: smp.judgment, members: [...smp.members],
  }
  if (smp.members_edited) v.members_edited = true
  if (smp.note) v.note = smp.note
  return v
}

/** 词存进操作的值:定义为空就不写。 */
export function featureValue(f: AnnFeature): Record<string, unknown> {
  return f.definition ? { id: f.id, name: f.name, definition: f.definition } : { id: f.id, name: f.name }
}

export function findBox(s: AnnState, id: string): { chart: AnnChart; box: AnnBox } | null {
  for (const chart of s.charts) {
    const box = chart.boxes.find(b => b.id === id)
    if (box) return { chart, box }
  }
  return null
}

export function findSample(s: AnnState, id: string): { chart: AnnChart; sample: AnnSample } | null {
  for (const chart of s.charts) {
    const sample = chart.samples.find(x => x.id === id)
    if (sample) return { chart, sample }
  }
  return null
}

export function chartOf(s: AnnState, symbol: string | null): AnnChart | null {
  return symbol ? s.charts.find(c => c.symbol === symbol) ?? null : null
}

const ID_SEQ = /^[wbs]-[A-Za-z0-9_]+-([1-9]\d*)$/

function stripSymbol(v: any): any {
  const { symbol: _s, ...rest } = v
  return rest
}

const boxOrder = (a: AnnBox, b: AnnBox) =>
  a.start < b.start ? -1 : a.start > b.start ? 1 : a.end < b.end ? -1 : a.end > b.end ? 1 : a.id < b.id ? -1 : 1
/** 样本的先后:样本日早的在前,再按编号。 */
export const sampleOrder = (a: AnnSample, b: AnnSample) =>
  a.date < b.date ? -1 : a.date > b.date ? 1 : a.id < b.id ? -1 : 1

/**
 * 把一批操作套到读结果上,返回新的读结果(不改入参):界面保存时先这样显示,后端回来的结果再整个换上。
 * next_seq 接到用过的最大号之后;revs、冲突等不动(真正保存时 base 取后端回来的 revs)。
 */
export function applyOps(r: AnnRead, ops: readonly AnnOp[]): AnnRead {
  const s: AnnState = {
    ...r.state,
    features: [...r.state.features],
    patterns: [...r.state.patterns],
    charts: r.state.charts.map(c => ({ ...c, boxes: [...c.boxes], samples: [...c.samples] })),
  }
  let seq = r.next_seq
  const chartFor = (symbol: string): AnnChart => {
    let c = s.charts.find(x => x.symbol === symbol)
    if (!c) {
      c = { symbol, boxes: [], samples: [] }
      s.charts.push(c)
      s.charts.sort((a, b) => (a.symbol < b.symbol ? -1 : 1))
    }
    return c
  }
  for (const op of ops) {
    const m = ID_SEQ.exec(op.id)
    if (m) seq = Math.max(seq, Number(m[1]) + 1)
    if (op.kind === 'feature' || op.kind === 'pattern') {
      const list: any[] = op.kind === 'feature' ? s.features : s.patterns
      const key = op.kind === 'feature' ? 'id' : 'name'
      const i = list.findIndex(x => x[key] === op.id)
      if (op.value === null) { if (i >= 0) list.splice(i, 1) }
      else if (i >= 0) list[i] = { ...op.value }
      else list.push({ ...op.value })
      continue
    }
    const field = op.kind === 'box' ? 'boxes' : 'samples'
    for (const c of s.charts) {
      const i = (c[field] as any[]).findIndex(x => x.id === op.id)
      if (i >= 0) c[field].splice(i, 1)
    }
    if (op.value !== null) {
      const c = chartFor(op.value.symbol)
      if (op.kind === 'box') { c.boxes.push(stripSymbol(op.value)); c.boxes.sort(boxOrder) }
      else { c.samples.push(stripSymbol(op.value)); c.samples.sort(sampleOrder) }
    }
  }
  s.charts = s.charts.filter(c => c.boxes.length || c.samples.length)
  return { ...r, state: s, next_seq: seq }
}

// ── 属性三态 ──────────────────────────────────────────────────────────

export type AttrState = 'true' | 'false' | 'null'

/** 框上某个属性的状态:键不在就是 null(没看过),不是 false。 */
export function attrState(b: Pick<AnnBox, 'attrs'>, fid: string): AttrState {
  const v = b.attrs?.[fid]
  return v === true ? 'true' : v === false ? 'false' : 'null'
}

/** 点一下 true 或 false:已按下的再点一下回到 null(把键拿掉),否则设成点的那个值。返回新的 attrs。 */
export function toggleAttr(attrs: Record<string, boolean> | undefined, fid: string, clicked: boolean): Record<string, boolean> {
  const out = { ...(attrs ?? {}) }
  if (out[fid] === clicked) delete out[fid]
  else out[fid] = clicked
  return out
}

/** 一组框上某个属性三种状态各有几个:null 单独数,不并进 false。 */
export function attrCounts(boxes: readonly AnnBox[], fid: string): Record<AttrState, number> {
  const out: Record<AttrState, number> = { true: 0, false: 0, null: 0 }
  for (const b of boxes) out[attrState(b, fid)]++
  return out
}

// ── 词表 ──────────────────────────────────────────────────────────────

export interface Usage { box: number; attr: number }

/** 每个词跨全部图的用量:box = 当特征用的框数,attr = 当属性判过(true 或 false)的框数。 */
export function featureUsage(s: AnnState): Map<string, Usage> {
  const out = new Map<string, Usage>(s.features.map(f => [f.id, { box: 0, attr: 0 }]))
  const get = (id: string) => {
    if (!out.has(id)) out.set(id, { box: 0, attr: 0 })
    return out.get(id)!
  }
  for (const c of s.charts) for (const b of c.boxes) {
    if (b.feature) get(b.feature).box++
    for (const k of Object.keys(b.attrs ?? {})) get(k).attr++
  }
  return out
}

/** 按名字找词(去掉首尾空白后完全相同)。 */
export function featureByName(s: AnnState, name: string): AnnFeature | null {
  const t = name.trim()
  return s.features.find(f => f.name === t) ?? null
}

export interface Suggestion { feature: AnnFeature; near: boolean; score: number }

/**
 * 起名时列哪些已有的词、怎么排:和输入有共同字(在词名或定义里)的算「相近」,排最前、按共同字数从多到少;
 * 其余只列当过框的特征的词,按用量从多到少。只当过属性或还没用过的词,相近时才列出来。
 */
export function rankSuggestions(query: string, features: readonly AnnFeature[], usage: Map<string, Usage>): Suggestion[] {
  const chars = [...new Set([...query.trim()].filter(c => c.trim() !== ''))]
  const out: Suggestion[] = []
  for (const f of features) {
    const hay = f.name + (f.definition ?? '')
    const score = chars.filter(c => hay.includes(c)).length
    const used = (usage.get(f.id)?.box ?? 0) > 0
    if (score > 0 || used) out.push({ feature: f, near: score > 0, score })
  }
  const boxN = (f: AnnFeature) => usage.get(f.id)?.box ?? 0
  return out.sort((a, b) => b.score - a.score || boxN(b.feature) - boxN(a.feature)
    || (a.feature.name < b.feature.name ? -1 : a.feature.name > b.feature.name ? 1 : 0))
}

/** 同一特征的框(全部图)用过的属性,按第一次出现的先后。 */
export function attrWordsOf(fid: string, charts: readonly AnnChart[]): string[] {
  const out: string[] = []
  for (const c of charts) for (const b of c.boxes) if (b.feature === fid) {
    for (const k of Object.keys(b.attrs ?? {})) if (!out.includes(k)) out.push(k)
  }
  return out
}

/**
 * 只为算框套框而用的交易日:这张图的 K 线在手时用它;别的图用周一到周五的日子代替
 * (只差节假日,包住与否不受影响,只在长短几乎一样的情形下可能换个所属的框)。
 */
export function weekdaysCovering(boxes: readonly { start: string; end: string }[]): string[] {
  if (!boxes.length) return []
  let lo = boxes[0].start, hi = boxes[0].end
  for (const b of boxes) { if (b.start < lo) lo = b.start; if (b.end > hi) hi = b.end }
  const out: string[] = []
  const d = new Date(`${lo}T00:00:00Z`), last = new Date(`${hi}T00:00:00Z`)
  for (; d <= last; d.setUTCDate(d.getUTCDate() + 1)) {
    const wd = d.getUTCDay()
    if (wd !== 0 && wd !== 6) out.push(d.toISOString().slice(0, 10))
  }
  return out
}

function nestOf(b: AnnBox): NestBox {
  return { id: b.id, feature: b.feature, start: b.start, end: b.end, detach: !!b.detach, attach: b.attach ?? null }
}

/** 算框套框用的交易日:这张图的 K 线日期在手(非空)就用它,否则用周一到周五代替(见 weekdaysCovering)。 */
export function daysFor(boxes: readonly AnnBox[], days?: readonly string[] | null): readonly string[] {
  return days && days.length ? days : weekdaysCovering(boxes)
}

/** 一张图上框套框的结果(框编号 → 所属框编号);days 缺省或为空时用周一到周五代替。 */
export function chartParents(boxes: readonly AnnBox[], days?: readonly string[] | null): Record<string, string | null> {
  return parents(boxes.map(nestOf), daysFor(boxes, days))
}

/**
 * 在这个特征的框里画成过子框的特征(全部图),按第一次出现的先后:界面上这些词写「⊂ 词」,不给 true。
 * daysOf(symbol) 给得出这张图的交易日就用它,给不出用周一到周五代替。
 */
export function kidWordsOf(fid: string, charts: readonly AnnChart[],
                           daysOf: (symbol: string) => readonly string[] | null = () => null): string[] {
  const out: string[] = []
  for (const c of charts) {
    if (!c.boxes.some(b => b.feature === fid)) continue
    const par = chartParents(c.boxes, daysOf(c.symbol))
    const byId = new Map(c.boxes.map(b => [b.id, b]))
    for (const b of c.boxes) {
      const p = par[b.id]
      if (p && byId.get(p)?.feature === fid && b.feature && b.feature !== fid && !out.includes(b.feature)) out.push(b.feature)
    }
  }
  return out
}

// ── 框套框:选中框时的 parent 一行 ──────────────────────────────────────

/**
 * 选中框时 parent 下面列的几行,每行一个别的框,点它的 ⊂ 会怎样:
 * - default:被这个框包住,默认属于它(⊂ 亮);点掉 = detach;
 * - attach:手动挂在这个交叠、更长的框上(⊂ 亮);点掉 = 拿掉 attach,回到默认;
 * - detached:被这个框包住、但点掉过(⊂ 灭);再点 = 拿掉 detach;
 * - candidate:和它交叠、比它长、可以手动挂上的框(⊂ 灭);点上 = attach 到它。
 * 第一行是它现在属于(或点掉前属于)的框,其后是其余能挂上的框,按长短排。都没有为空数组。
 * detach 与 attach 互斥:改其中一个时另一个一并拿掉。
 */
export interface ParentRow { other: AnnBox; on: boolean; via: 'default' | 'attach' | 'detached' | 'candidate' }

export function parentRows(b: AnnBox, boxes: readonly AnnBox[], days: readonly string[]): ParentRow[] {
  const d = daysFor(boxes, days)
  const byId = new Map(boxes.map(x => [x.id, x]))
  const rows: ParentRow[] = []
  const eff = chartParents(boxes, d)[b.id]
  if (eff) rows.push({ other: byId.get(eff)!, on: true, via: b.attach === eff ? 'attach' : 'default' })
  else if (b.detach) {
    const plain = chartParents(boxes.map(x => (x.id === b.id ? { ...x, detach: undefined } : x)), d)[b.id]
    if (plain) rows.push({ other: byId.get(plain)!, on: false, via: 'detached' })
  }
  const length = (x: AnnBox) => rankOf(d, x.end) - rankOf(d, x.start)
  const cands = boxes.filter(o => !rows.some(r => r.other.id === o.id) && canAttach(nestOf(b), nestOf(o), d))
    .sort((p, q) => length(p) - length(q) || (p.start < q.start ? -1 : p.start > q.start ? 1 : p.id < q.id ? -1 : 1))
  return [...rows, ...cands.map(o => ({ other: o, on: false, via: 'candidate' as const }))]
}

/** 点一下 parent 某一行的 ⊂ 之后的框(规则见 parentRows)。 */
export function toggleParent(b: AnnBox, row: ParentRow): AnnBox {
  const next: AnnBox = { ...b }
  delete next.detach
  delete next.attach
  if (row.via === 'default') next.detach = true
  else if (row.via === 'candidate') next.attach = row.other.id
  return next
}

// ── 特征轨 ────────────────────────────────────────────────────────────

export interface LaneBox { box: AnnBox; row: number }
export interface Lane {
  key: string | null           // 特征编号;null = 还没起名的框
  parent: string | null        // 轨标题写成「key ⊂ parent」时的 parent 特征编号
  rows: number                 // 轨里叠了几行(同一轨里交叠的框分行画)
  boxes: LaneBox[]
}

/**
 * annotate 下一张图的特征轨:一个特征一条轨。
 * - 轨序:rankOfFeature 给了就先按它(当前 pattern 里各段的先后,见 annotate/grouping.ts 的 featureOrder),
 *   不在其中的特征排在后面;其余按特征在这张图上首次出现的先后(最早的起点;一样早按名字);
 * - 子框轨:这个特征的框全都属于同一个别的特征的框时,它是那个特征的子框轨,紧跟在那条轨后面,标题写成
 *   「缩量 ⊂ 横盘」;
 * - 还没起名的框单独一条轨,放最后;
 * - 同一条轨里交叠的框分行,一行里不交叠。
 * days 是这张图的交易日(算框套框的长短用)。
 */
export function computeLanes(boxes: readonly AnnBox[], nameOf: (fid: string) => string,
                             days: readonly string[], rankOfFeature?: ReadonlyMap<string, number> | null): Lane[] {
  const par = chartParents(boxes, days)
  const byId = new Map(boxes.map(b => [b.id, b]))
  const groups = new Map<string | null, AnnBox[]>()
  for (const b of boxes) {
    if (!groups.has(b.feature)) groups.set(b.feature, [])
    groups.get(b.feature)!.push(b)
  }
  const first = (fid: string) => groups.get(fid)!.reduce((m, b) => (b.start < m ? b.start : m), '9999-99-99')
  const rank = (fid: string) => rankOfFeature?.get(fid) ?? Number.POSITIVE_INFINITY
  const named = [...groups.keys()].filter((k): k is string => k !== null)
    .sort((a, b) => (rank(a) !== rank(b) ? (rank(a) < rank(b) ? -1 : 1)
      : first(a) < first(b) ? -1 : first(a) > first(b) ? 1 : nameOf(a) < nameOf(b) ? -1 : 1))
  const laneParent = new Map<string, string | null>()
  for (const fid of named) {
    const ps = groups.get(fid)!.map(b => { const p = par[b.id]; return p ? byId.get(p)?.feature ?? null : null })
    const p0 = ps[0]
    laneParent.set(fid, p0 && p0 !== fid && ps.every(p => p === p0) ? p0 : null)
  }
  const order: string[] = []
  const put = (fid: string) => {
    if (order.includes(fid)) return
    order.push(fid)
    for (const k of named) if (laneParent.get(k) === fid) put(k)
  }
  for (const fid of named) if (!laneParent.get(fid)) put(fid)
  for (const fid of named) put(fid)          // 所属的框一定更长,轨的从属不会绕成环;这一行只是兜底
  const keys: (string | null)[] = [...order]
  if (groups.has(null)) keys.push(null)
  return keys.map(key => {
    const { rows, boxes: lb } = packRows(groups.get(key)!, days)
    return { key, parent: key ? laneParent.get(key) ?? null : null, rows, boxes: lb }
  })
}

function packRows(boxes: readonly AnnBox[], days: readonly string[]): { rows: number; boxes: LaneBox[] } {
  const r = (d: string) => (days.length ? rankOf(days, d) : d)
  const sorted = [...boxes].sort((a, b) => (a.start < b.start ? -1 : a.start > b.start ? 1 : a.end > b.end ? -1 : 1))
  const ends: (number | string)[] = []
  const out: LaneBox[] = []
  for (const b of sorted) {
    let row = ends.findIndex(e => e < r(b.start))
    if (row < 0) { row = ends.length; ends.push(r(b.end)) } else ends[row] = r(b.end)
    out.push({ box: b, row })
  }
  return { rows: Math.max(1, ends.length), boxes: out }
}

// ── 合并 ──────────────────────────────────────────────────────────────

export interface MergeChange { symbol: string; before: AnnBox; after: AnnBox }
export interface MergePlan { from: string; into: string; changes: MergeChange[]; box: number; attr: number }

/**
 * 把词 from 并进 into 会改哪些框:当特征用 from 的框改成 into(box 计数);属性里有 from 的框,
 * 那个判断挪到 into 上(into 已判过的保留 into 的判断),from 的键拿掉(attr 计数)。
 */
export function mergePlan(s: AnnState, from: string, into: string): MergePlan {
  const changes: MergeChange[] = []
  let box = 0, attr = 0
  for (const c of s.charts) for (const b of c.boxes) {
    const asFeature = b.feature === from
    const asAttr = !!b.attrs && from in b.attrs
    if (!asFeature && !asAttr) continue
    const after: AnnBox = { ...b, attrs: { ...(b.attrs ?? {}) } }
    if (asFeature) { after.feature = into; box++ }
    if (asAttr) {
      if (!(into in after.attrs!)) after.attrs![into] = after.attrs![from]
      delete after.attrs![from]
      attr++
    }
    if (!Object.keys(after.attrs!).length) delete after.attrs
    changes.push({ symbol: c.symbol, before: b, after })
  }
  return { from, into, changes, box, attr }
}

/** 界面上的一条合并记录(由读结果的 merges 来):被并的词、并进的词、改过的框,以及当特征、当属性各改了几个框。 */
export interface MergeRecord { from: AnnFeature; into: string; changes: MergeChange[]; box: number; attr: number }

export function mergeRecords(r: AnnRead): MergeRecord[] {
  return (r.merges ?? []).map(m => {
    const changes = m.boxes.map(b => ({ symbol: b.before.symbol, before: b.before, after: b.after }))
    return {
      from: m.feature, into: m.into, changes,
      box: changes.filter(c => c.before.feature === m.feature.id).length,
      attr: changes.filter(c => !!c.before.attrs && m.feature.id in c.before.attrs).length,
    }
  })
}

/**
 * 拆回时一个框该改成什么:合并后没再动过的框整个改回合并前;动过的(比如改了起止)只把特征和属性里
 * 合并改掉的部分改回去,别的改动留着。返回 null 表示这个框不用改。
 */
export function unmergedBox(change: MergeChange, current: AnnBox, from: string, into: string): AnnBox | null {
  if (sameBox(current, change.after)) return change.before
  const next: AnnBox = { ...current, attrs: { ...(current.attrs ?? {}) } }
  if (change.before.feature === from && current.feature === into) next.feature = from
  const was = change.before.attrs ?? {}
  if (from in was) {
    next.attrs![from] = was[from]
    if (!(into in was) && next.attrs![into] === change.after.attrs?.[into]) delete next.attrs![into]
  }
  if (!Object.keys(next.attrs!).length) delete next.attrs
  return sameBox(next, current) ? null : next
}

/** 两个框的存储值是否相同(attrs 不看键的先后)。 */
export function sameBox(a: AnnBox, b: AnnBox): boolean {
  const canon = (x: AnnBox) => {
    const v = boxValue('', x)
    if (v.attrs) v.attrs = Object.fromEntries(Object.entries(v.attrs as object).sort(([p], [q]) => (p < q ? -1 : 1)))
    return JSON.stringify(v)
  }
  return canon(a) === canon(b)
}
