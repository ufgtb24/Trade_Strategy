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
 *   侧栏不翻页)。聚焦 = 当前日落在样本日 + 选中配对的 hit / event(见 focusSample);←/→ 在样本间走
 *   (当家行 samples)。
 */
import { defineStore } from 'pinia'
import { computed, ref, watch } from 'vue'
import { useViewStore, type ActiveFamily } from './view'
import { useAnnotationStore } from './annotation'
import { useAppLinkStore } from './appLink'
import { chartOf, chartParents, type AnnBox, type AnnSample } from '../annotate/model'
import {
  diagnoseRows, matchMark, matchOf, pairOn, stepSample,
  type DiagnoseRow, type MatchResult, type Pairing,
} from '../annotate/compareRead'
import { buyDaysOf, formatMemberLabel, memberLabels } from '../render/fold'
import type { EventDict, HitDict, Tier } from '../types'

/** ←/→ 在样本间走时当家行的键(副图里没有叫这个的族,user 那一行由 KlineChart 自己加粗)。 */
export const SAMPLES_ROW = 'samples'

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

  // ── 聚焦 ──
  /** 当前聚焦的样本(选中的,或进 compare 时默认聚焦的);为 null 时没有聚焦样本。 */
  const focusedSampleId = ref<string | null>(null)

  const samplesRow: ActiveFamily = {
    kind: 'external', key: SAMPLES_ROW,
    step: (dir) => {
      const next = stepSample(sampleDays.value, focusedSampleId.value, dir)
      if (next && next !== focusedSampleId.value) ann.selectSample(next)   // 等于点它
    },
  }

  /**
   * 当前日落在 day,选中配对的 hit(那天有 hit)或 event;一个都没有时只设当前日。family:当家行。
   * 聚焦不改档位(view 的聚焦一律如此):配对的 event 在当前档位下画不出来时,diagnose 那一行写 hidden。
   */
  function focusPairing(p: Pairing, family: ActiveFamily | null): void {
    if (p.hitId) view.focusHit(p.hitId, { day: p.day, family })
    else if (p.event) view.focusEvent(p.event.instance_id, { day: p.day, family })
    else {
      view.clearFocus()
      view.setCurrentDay(p.day)
      view.setActiveFamily(family)
    }
  }

  /** 聚焦一个样本(当家行设成 samples,←/→ 在样本间走)。 */
  function focusSample(id: string): boolean {
    const r = sampleReads.value.get(id)
    if (!r) return false
    focusedSampleId.value = id
    focusPairing(r.pairing, samplesRow)
    return true
  }

  /** 聚焦一个框:当前日落在框终点,选中配对的那个;当家行不动(框不在任何族行里)。 */
  function focusBox(id: string): boolean {
    const r = boxReads.value.get(id)
    if (!r) return false
    focusedSampleId.value = null
    focusPairing(r.pairing, null)
    return true
  }

  function clearSampleFocus(): void { focusedSampleId.value = null }
  // 换图、离开 compare:聚焦的样本作废;当家行不再是样本(Esc 清掉、点了 app 的格或框)时也作废,
  // 免得 selection 页还写着「focus a」而竖线已经不在它的样本日上
  watch(() => [view.symbol, view.comparing] as const, () => { focusedSampleId.value = null })
  watch(() => view.activeFamilyKey, (k) => { if (k !== SAMPLES_ROW) focusedSampleId.value = null })

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
    ready, pairNode, samples, sampleDays, sampleReads, boxReads, focusedSampleId, focusedSample, samplesRow,
    focusSample, focusBox, clearSampleFocus, diagnose, notes, nodeOfFeature,
  }
})
