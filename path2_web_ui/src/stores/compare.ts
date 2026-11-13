/**
 * compare 的读数(store):把 annotate/compareRead.ts 的纯函数接到当前图、当前 pattern 的 app 产物与标注上。
 * 图上 ▲ 旁的 ✓ / ✗、样本与框 → 当前日(KlineChart.vue),selection 页的 diagnose(SampleDiagnose.vue)
 * 与框的 node 行(BoxPanel.vue)读的都是这一份,不各算各的。
 *
 * - 配对在哪个 node 上:样本按 app 的买点 node 所在的那个 node(eval_meta 的 end_node 点号前那段,如
 *   plateau.today → plateau);框按 mapping 里它的特征对的 node。都不认具体事件类型;
 * - 子框:样本的成员框、框里套的框里,特征对到「配对 node 的某个子 node」(拓扑 produced_by)的那个,
 *   带上它在父 children 里的槽名(拓扑 child_slot)交给配对;
 * - 日子:样本按样本日,框按框终点;都按这张图的 K 线逐根精确取(K 线是这只股票截到训练段末日的全部,
 *   和 app 的下标逐根对齐,见 stores/appLink.ts);
 * - 聚焦样本:点 ▲(选中样本)或进 compare 时的默认样本(没有选中的就取离图窗中心最近的,不动标注的选中、
 *   侧栏不翻页)。聚焦 = 选中的就是这个样本、当前日落在样本日(见 focusSample;配对的那次 hit 按 ↓ 进去才算选中);
 *   ← / → 在样本间走(当家行 samples)。
 */
import { defineStore } from 'pinia'
import { computed, ref, watch } from 'vue'
import { useViewStore, SAMPLES_ROW_KEY } from './view'
import { useAnnotationStore } from './annotation'
import { useAppLinkStore } from './appLink'
import { chartOf, chartParents, type AnnBox, type AnnSample } from '../annotate/model'
import {
  diagnoseRows, matchMark, matchOf, pairOn,
  type DiagnoseRow, type MatchResult, type Pairing,
} from '../annotate/compareRead'
import { hitOrderOf } from '../render/walk'
import type { AnchorRow } from '../render/selWorld'
import { sampleLetters } from '../annotate/samples'
import { buyDaysOf, formatMemberLabel, memberLabels } from '../render/fold'
import type { EventDict, HitDict, Tier } from '../types'

/** 选中样本(或它里面的东西)时的当家行键(副图里没有叫这个的族,user 那一行由 KlineChart 自己加粗)。 */
export const SAMPLES_ROW = SAMPLES_ROW_KEY

export interface SampleRead {
  id: string
  day: number
  judgment: 'pos' | 'neg'
  match: MatchResult
  mark: '✓' | '✗'
  pairing: Pairing
}

export interface BoxRead {
  node: string
  day: number
  pairing: Pairing
}

export const useCompareStore = defineStore('compare', () => {
  const view = useViewStore()
  const ann = useAnnotationStore()
  const appLink = useAppLinkStore()

  const analysis = computed(() => (view.comparing ? view.effectiveAnalysis : null))
  const events = computed<EventDict[]>(() => analysis.value?.events ?? [])
  const hits = computed<HitDict[]>(() => analysis.value?.hits ?? [])
  const byId = computed(() => new Map(events.value.map(e => [e.instance_id, e])))
  const topoNodes = computed(() => (view.comparing ? view.effectivePattern?.topology.nodes ?? [] : []))
  const anchorFields = computed(() => [...new Set((view.effectivePattern?.topology.edges ?? [])
    .map(ed => ed.anchor_field).filter((f): f is string => !!f))])
  const dayIdx = computed(() => new Map(view.barDates.map((d, i) => [d, i])))
  const features = computed<Record<string, string>>(() => appLink.mapping?.features ?? {})
  /** 特征 → 它对的 node(特征在词表里、node 在拓扑里才算)。 */
  function nodeOfFeature(fid: string | null): string | null {
    if (!fid || !ann.featureById.has(fid)) return null
    const n = features.value[fid]
    return n && topoNodes.value.some(t => t.node_id === n) ? n : null
  }
  const pairNode = computed(() => view.endNode?.split('.')[0] ?? null)
  const ready = computed(() => !!analysis.value && !!appLink.mapping && !!ann.match && !!pairNode.value)

  const chart = computed(() => (ann.state ? chartOf(ann.state, view.symbol) : null))
  const tierOf = (e: EventDict): Tier => view.eventTier(e)

  /** 框里(样本的成员框、框里套的框)特征对到 node 的子 node 的那个,作子框。 */
  function subBoxOf(node: string, boxes: readonly AnnBox[]): { box: { start: number; end: number; slot: string }; tol: number } | null {
    const tol = ann.match?.sub
    if (tol === undefined) return null
    for (const b of boxes) {
      const child = nodeOfFeature(b.feature)
      const spec = child ? topoNodes.value.find(t => t.node_id === child) : null
      if (!spec || spec.produced_by !== node || !spec.child_slot) continue
      const s = dayIdx.value.get(b.start), e = dayIdx.value.get(b.end)
      if (s === undefined || e === undefined) continue
      return { box: { start: s, end: e, slot: spec.child_slot }, tol }
    }
    return null
  }

  /** 这张图上当前 pattern 的样本(样本日在 K 线里的),按样本日。 */
  const samples = computed<AnnSample[]>(() => (chart.value?.samples ?? [])
    .filter(s => s.pattern === ann.currentPattern && dayIdx.value.has(s.date)))
  const sampleDays = computed(() => samples.value.map(s => ({ id: s.id, day: dayIdx.value.get(s.date)! })))

  const sampleReads = computed<Map<string, SampleRead>>(() => {
    const out = new Map<string, SampleRead>()
    const node = pairNode.value
    const c = chart.value
    if (!ready.value || !node || !c) return out
    const boxById = new Map(c.boxes.map(b => [b.id, b]))
    const buys = (h: HitDict) => buyDaysOf(h, byId.value, view.endNode)
    for (const s of samples.value) {
      const day = dayIdx.value.get(s.date)!
      const members = s.members.map(id => boxById.get(id)).filter((b): b is AnnBox => !!b)
      const pairing = pairOn(day, node, events.value, hits.value, tierOf, { subBox: subBoxOf(node, members) })
      const match = matchOf(day, s.judgment, hits.value, buys, ann.match!)
      out.set(s.id, { id: s.id, day, judgment: s.judgment, match, mark: matchMark(s.judgment, match), pairing })
    }
    return out
  })

  const boxReads = computed<Map<string, BoxRead>>(() => {
    const out = new Map<string, BoxRead>()
    const c = chart.value
    if (!ready.value || !c) return out
    const par = chartParents(c.boxes, c.samples, view.barDates)
    for (const b of c.boxes) {
      const node = nodeOfFeature(b.feature)
      const day = dayIdx.value.get(b.end)
      if (!node || day === undefined) continue
      const kids = c.boxes.filter(k => par[k.id] === b.id)
      const pairing = pairOn(day, node, events.value, hits.value, tierOf, { subBox: subBoxOf(node, kids) })
      out.set(b.id, { node, day, pairing })
    }
    return out
  })

  // ── 样本日在场的 hit(diagnose 的 hits 组,也是选中模型里样本、框「装着」的那几次) ──
  const hitOrder = computed(() => hitOrderOf(hits.value))

  /**
   * 一天在场、进了 hit 的 event(一块一个 event)与用到它的 hit,按块排好:配对的那块在前,其余按块里最早的那次 hit
   * 的先后(render/walk.ts 的 hitOrderOf);块里配对的那次在前,其余按 hit 的先后。diagnose 的卡片顺序与
   * ↑ / ↓ 在样本日在场的 hit 间走的先后都用它,所以两边一致。
   */
  function stackCards(p: Pairing, node: string): { instanceId: string; hitIds: string[] }[] {
    const rank = (id: string) => hitOrder.value.get(id) ?? Number.MAX_SAFE_INTEGER
    const cards = p.present.map(e => ({
      instanceId: e.instance_id,
      hitIds: hits.value.filter(h => h.node_index?.[node] === e.instance_id).map(h => h.hit_id)
        .sort((a, b) => Number(b === p.hitId) - Number(a === p.hitId) || rank(a) - rank(b)),
    })).filter(c => c.hitIds.length > 0)
    const paired = p.event?.instance_id ?? null
    return cards.sort((a, b) => Number(b.instanceId === paired) - Number(a.instanceId === paired)
      || rank(a.hitIds[0]) - rank(b.hitIds[0]))
  }

  /** 一天在场的几次 hit:配对的那次在前,其余照 diagnose 的 hits 组的顺序。 */
  function presentHitIds(p: Pairing, node: string): string[] {
    return stackCards(p, node).flatMap(c => c.hitIds)
  }

  /** 这张图上当前 pattern 的样本(按样本日),各带样本日在场的 hit:选中模型里样本「装着」的就是它们。 */
  const sampleRows = computed<AnchorRow[]>(() => {
    const node = pairNode.value
    if (!ready.value || !node) return []
    const out: AnchorRow[] = []
    for (const s of [...sampleDays.value].sort((a, b) => a.day - b.day || (a.id < b.id ? -1 : 1))) {
      const r = sampleReads.value.get(s.id)
      if (r) out.push({ id: s.id, day: s.day, hitIds: presentHitIds(r.pairing, node), pairedHitId: r.pairing.hitId ?? null })
    }
    return out
  })

  /** 这张图上对得到 node 的框(按终点),各带框终点在场的 hit。 */
  const boxRows = computed<AnchorRow[]>(() => {
    const out: AnchorRow[] = []
    for (const [id, r] of boxReads.value) {
      out.push({ id, day: r.day, hitIds: presentHitIds(r.pairing, r.node), pairedHitId: r.pairing.hitId ?? null })
    }
    return out.sort((a, b) => a.day - b.day || (a.id < b.id ? -1 : 1))
  })

  // ── 聚焦 ──
  /** 当前聚焦的样本(选中的,或进 compare 时默认聚焦的);为 null 时没有聚焦样本。 */
  const focusedSampleId = ref<string | null>(null)

  /**
   * 聚焦一个样本:选中的就是这个样本(显示栏写 `sample`),当前日落在样本日;配对的那次 hit 不算选中,按 ↓ 进去才是。
   * 已经停在这个样本里面(它在场的某次 hit、它的某个 event)时不动——按键走到它、标注那边的选中跟过来都走这条;
   * 用户亲手点它(reset)时一律回到只选中样本。聚焦不改档位:配对的 event 在当前档位下画不出来时,diagnose 那一行写 hidden。
   */
  function focusSample(id: string, opts: { reset?: boolean } = {}): boolean {
    if (!sampleReads.value.get(id)) return false
    focusedSampleId.value = id
    const first = view.selPath[0]
    const inside = first?.kind === 'sample' && first.sampleId === id
    if (opts.reset ? view.selPath.length !== 1 || !inside : !inside) view.setPath([{ kind: 'sample', sampleId: id }])
    return true
  }

  /** 聚焦一个框:选中的就是这个框,当前日落在框终点。reset 同 focusSample。 */
  function focusBox(id: string, opts: { reset?: boolean } = {}): boolean {
    if (!boxReads.value.get(id)) return false
    focusedSampleId.value = null
    const first = view.selPath[0]
    const inside = first?.kind === 'box' && first.boxId === id
    if (opts.reset ? view.selPath.length !== 1 || !inside : !inside) view.setPath([{ kind: 'box', boxId: id }])
    return true
  }

  /**
   * diagnose 里点一张卡片:hits 组的卡片选中它的第一次 hit(它属于这个样本;写 × k 的卡片随后能用 ↑ / ↓ 走过它那 k 次);
   * not_in_hit 组的卡片选中那个 event(也属于这个样本),竖线不动。
   */
  function pickCard(sampleId: string, instanceId: string): void {
    const r = sampleReads.value.get(sampleId)
    if (!r) return
    focusedSampleId.value = sampleId
    const node = pairNode.value
    const card = node ? stackCards(r.pairing, node).find(c => c.instanceId === instanceId) : undefined
    const anchor = { kind: 'sample' as const, sampleId }
    if (card?.hitIds.length) view.setPath([anchor, { kind: 'hit', hitId: card.hitIds[0], day: r.day }])
    else { view.setPath([anchor, { kind: 'event', instanceId }]); view.setCurrentDay(r.day) }
  }

  // 选中模型要的东西登记给 view(view 不能反过来 import 这里):样本与框、走到另一个样本 / 框时等于点它、各自的叫法
  view.setSelSources({
    samples: () => sampleRows.value,
    boxes: () => boxRows.value,
    onAnchor: (s) => {
      if (s.kind === 'sample') { focusedSampleId.value = s.sampleId; ann.selectSample(s.sampleId) }
      else if (s.kind === 'box') ann.selectBox(s.boxId)
    },
    featureOfBand: (band) => {
      const fid = Object.entries(features.value).find(([, node]) => node === band)?.[0] ?? null
      return fid ? ann.nameOf(fid) ?? null : null
    },
    sampleOf: (id) => {
      const s = chart.value?.samples.find(x => x.id === id)
      return s ? { letter: sampleLetters(chart.value, s.pattern).get(s.id) ?? null, judgment: s.judgment, date: s.date } : null
    },
    boxOf: (id) => {
      const b = chart.value?.boxes.find(x => x.id === id)
      return b ? { feature: ann.nameOf(b.feature) ?? null, start: b.start, end: b.end, node: nodeOfFeature(b.feature) } : null
    },
  })

  function clearSampleFocus(): void { focusedSampleId.value = null }
  // 换图、离开 compare:聚焦的样本作废;选中的不再是样本或它里面的东西(Esc 清掉、点了 app 的格或框)时也作废,
  // 免得 selection 页还写着「focus a」而竖线已经不在它的样本日上
  watch(() => [view.symbol, view.comparing] as const, () => { focusedSampleId.value = null })
  watch(() => view.activeFamilyKey, (k) => { if (k !== SAMPLES_ROW) focusedSampleId.value = null })
  // 换了标注的当前 pattern:样本、框的对照、反馈都是按 pattern 的,原来选中的那一个不再属于这张图
  watch(() => ann.currentPattern, () => {
    const k = view.selPath[0]?.kind
    if (k !== 'sample' && k !== 'box' && k !== 'feedback') return
    focusedSampleId.value = null
    view.clearFocus()
  })
  // 选中的样本 / 框被删掉了(或撤销掉了):东西没了,图上的选中一并清掉
  watch(() => [chart.value?.samples, chart.value?.boxes] as const, ([samples, boxes]) => {
    if (!ann.state) return   // 标注还没读到(或正在重读):不算没了
    const first = view.selPath[0]
    const gone = first?.kind === 'sample' ? !samples?.some(x => x.id === first.sampleId)
      : first?.kind === 'box' ? !boxes?.some(x => x.id === first.boxId) : false
    if (!gone) return
    focusedSampleId.value = null
    view.clearFocus()
  })

  // ── selection 页 ──
  /** 聚焦的样本:选中的,没选中时是进 compare 时默认聚焦的那个。 */
  const shownSampleId = computed(() => ann.selectedSampleId ?? focusedSampleId.value)
  const focusedSample = computed(() =>
    (!ann.selectedSampleId && focusedSampleId.value ? samples.value.find(s => s.id === focusedSampleId.value) ?? null : null))
  /** 聚焦样本的 diagnose 行(只给档位与没过的 where 名);不在 compare、或没有配对数据时为 null。 */
  const diagnose = computed<{ read: SampleRead; rows: DiagnoseRow[] } | null>(() => {
    const id = shownSampleId.value
    const read = id ? sampleReads.value.get(id) : undefined
    if (!read) return null
    const dates = view.barDates
    const label = (e: EventDict, same: readonly EventDict[]) => {
      const ls = memberLabels(same.map(x => x.instance_id), byId.value, anchorFields.value)
      const k = same.findIndex(x => x.instance_id === e.instance_id)
      return k >= 0 && ls[k] ? formatMemberLabel(ls[k], dates) : null
    }
    return { read, rows: diagnoseRows(read.pairing, view.diag, tierOf, label) }
  })
  /** mapping 的 notes:键 node 或 node.where,值是用户原话。 */
  const notes = computed<Record<string, string>>(() => appLink.mapping?.notes ?? {})

  return {
    ready, pairNode, samples, sampleDays, sampleReads, boxReads, focusedSampleId, focusedSample,
    focusSample, focusBox, pickCard, stackCards, clearSampleFocus, diagnose, notes, nodeOfFeature,
  }
})
