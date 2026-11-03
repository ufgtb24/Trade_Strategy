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
 * - 保存没通过(后端校验拒绝、标注目录不在等):这一个意图丢掉,原因放进 saveError,显示回到后端的状态。
 *
 * 合并与拆回:合并是一批操作(改写涉及的框、删掉被并的词)。还能拆回的合并由后端从标注文件里认出来
 * (读结果的 merges),刷新、换机器后照样能拆回;拆回再写一批,把词用原编号放回、把框改回去。
 *
 * 冲突提示一次:读结果里每条冲突以 later.ref 为准,看过的记在浏览器里,之后不再弹出。
 */
import { defineStore } from 'pinia'
import { computed, ref, shallowRef } from 'vue'
import { AnnotationSaveError, getAnnotations, postAnnotationBatch } from '../api'
import {
  applyOps, baseOf, boxValue, featureByName, featureValue, findBox, mergePlan, mergeRecords, newId, toggleAttr,
  toggleParent, unmergedBox, type AnnBox, type AnnConflict, type AnnFeature, type AnnOp, type AnnRead,
  type MergePlan, type MergeRecord, type ParentRow,
} from '../annotate/model'

/** 一个动作:拿到读结果,给出要保存的这一批操作(没什么要改时给空数组)。 */
export type Intent = (r: AnnRead) => AnnOp[]

export type LoadStatus = 'idle' | 'loading' | 'ready' | 'unavailable' | 'load_failed'
export type SidebarTab = 'selection' | 'features' | 'pattern'
export type Tool = 'box'
export interface SaveProblem { code: string; message: string }

const ACK_KEY = 'path2_web_ui.annotation.ack_conflicts.v1'

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

  const selectedBox = computed(() => (selectedBoxId.value && state.value ? findBox(state.value, selectedBoxId.value) : null))

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
        }
        queue.value = queue.value.slice(1)
      }
    } finally {
      saving.value = false
    }
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

  /** 画一个新框;feature 给了就直接带这个特征(在特征轨上拖出来的)。新框被选中。 */
  function createBox(symbol: string, start: string, end: string, feature: string | null): string | null {
    if (!machine.value) return null
    const [seq] = takeSeqs(1)
    const id = newId('b', machine.value, seq)
    const box: AnnBox = { id, feature, start, end }
    commit(() => [{ kind: 'box', id, base: null, value: boxValue(symbol, box) }])
    selectBox(id)
    renaming.value = false
    if (!feature) nameFocus.value++
    return id
  }

  function resizeBox(id: string, start: string, end: string): void {
    commit(boxIntent(id, b => ({ ...b, start, end })))
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

  function selectBox(id: string | null): void {
    selectedBoxId.value = id
    renaming.value = false
    if (id) tab.value = 'selection'
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
    server, view, state, status, loadError, saveError, saving, machine,
    selectedBoxId, selectedBox, tab, tool, renaming, nameFocus, merges, pendingMerge, daysBySymbol,
    newConflicts, fingerprint, featureById, nameOf,
    load, commit, flushed, createBox, resizeBox, deleteBox, setBoxFeature, setBoxNote, setAttr, addAttr,
    toggleBoxParent, setDefinition, renameFeature, previewMerge, applyMerge, unmerge, selectBox,
    ackConflicts, setDays,
  }
})
