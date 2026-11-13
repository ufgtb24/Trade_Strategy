<template>
  <div v-if="info" class="sel-card" data-testid="sel-card">
    <div v-for="r in rows" :key="r.name" class="row" :data-testid="`sel-card-${r.name}`">
      <span class="lb">{{ r.name }}</span>
      <span class="val">
        <template v-if="r.lines === null"><span class="na">{{ NA }}</span></template>
        <template v-else>
          <span v-for="(l, i) in r.lines" :key="i" class="line">{{ l }}</span>
        </template>
      </span>
    </div>
  </div>
</template>

<script setup lang="ts">
// 选中卡:选中的那一个(stores/view.ts 的 selInfo)在右侧栏的细节,十一行、行序固定,每行「标签 值」——
//   buys、hits(牵出的买点日与 hit)、nodes(一次 hit 的组成)、family(结构上的那一族)、
//   feedback、sample(盖住它的反馈、相关的样本:「买得对不对」)、paired(配对的另一方)、
//   level、failed(event 的档位与没过的 where)、id(内部编号)、copy(Shift+C 会复制的那一行)。
// 不适用的行照占位置,写灰色 `—`;适用但是空的写黑字 `none`。只给类别,不给数字。
import { computed } from 'vue'
import { useViewStore } from '../stores/view'
import { useAnnotationStore } from '../stores/annotation'
import { useCompareStore } from '../stores/compare'
import { useFeedbackStore } from '../stores/feedback'
import { useCopyRefStore } from '../stores/copyRef'
import { chartOf } from '../annotate/model'
import { sampleLetters } from '../annotate/samples'
import { CARD_ROWS, SEL_NA as NA, SEL_NONE as NONE } from '../render/selSnapshot'
import type { EventDict } from '../types'

const view = useViewStore()
const ann = useAnnotationStore()
const cmp = useCompareStore()
const fb = useFeedbackStore()
const copyRef = useCopyRefStore()

const info = computed(() => view.selInfo)
const dates = computed(() => view.barDates)
const d = (i: number): string => dates.value[i] ?? String(i)
const span = (a: string, b: string): string => (a === b ? a : `${a}→${b}`)
const listOrNone = (ls: string[]): string[] => (ls.length ? ls : [NONE])

const chart = computed(() => (view.symbol && ann.state ? chartOf(ann.state, view.symbol) : null))
/** 这一个牵出的 hit:选中的那次、选中那一天的几次、或路径上最外一节牵出的 */
const ownHitIds = computed<ReadonlySet<string>>(() => {
  const i = info.value
  if (i?.hitId) return new Set([i.hitId])
  if (view.selDayHitIds.length) return new Set(view.selDayHitIds)
  return view.selHits.ids
})
/** 这一个牵出的买点日(日期):选中一整天就是那一天;否则是它牵出的 hit 的全部买点日 */
const ownDates = computed<Set<string>>(() => {
  const out = new Set<string>()
  const last = view.selLast
  if (last?.kind === 'buy' && !info.value?.hitId) { out.add(d(last.day)); return out }
  for (const id of ownHitIds.value) for (const day of view.buyDaysOfHit(id)) out.add(d(day))
  return out
})

const feedbackLines = computed<string[] | null>(() => {
  const i = info.value
  if (!i || !view.comparing || i.kind === 'node' || i.kind === 'sample' || i.kind === 'box' || i.kind === 'event') return null
  const all = (chart.value?.feedback ?? []).filter(f => f.source === 'picked' && f.pattern === ann.currentPattern)
  const mine = i.kind === 'feedback' ? all.filter(f => f.id === i.id)
    : all.filter(f => [...ownDates.value].some(x => f.start <= x && x <= f.end)
        || (f.target === 'family' && !!f.family_start && f.family_start === (i.kind === 'hit_family' ? i.date : i.family)))
  return listOrNone(mine.map(f => [span(f.start, f.end), fb.statusById[f.id]?.status ?? null].filter(Boolean).join(' ')))
})

function sampleLine(id: string): string | null {
  const s = chart.value?.samples.find(x => x.id === id)
  if (!s) return null
  const letter = sampleLetters(chart.value, s.pattern).get(s.id) ?? null
  return [letter, s.judgment, s.date, cmp.sampleReads.get(id)?.mark ?? null].filter(Boolean).join(' ')
}
const sampleLines = computed<string[] | null>(() => {
  const i = info.value
  if (!i || !view.comparing || i.kind === 'node') return null
  if (i.kind === 'sample') return listOrNone([sampleLine(i.id ?? '')].filter((x): x is string => !!x))
  if (i.kind === 'box') {
    return listOrNone(cmp.samples.filter(s => s.members.includes(i.id ?? '')).map(s => sampleLine(s.id))
      .filter((x): x is string => !!x))
  }
  // app 的东西:样本日在场的 hit 里有它牵出的 hit(event 没进 hit 时看配对的是不是它)
  const out: string[] = []
  for (const s of cmp.samples) {
    const r = cmp.sampleReads.get(s.id)
    if (!r) continue
    const present = r.pairing.present.map(e => e.instance_id)
    const hitIn = view.effectiveAnalysis?.hits.some(h => ownHitIds.value.has(h.hit_id)
      && present.some(p => Object.values(h.node_index ?? {}).includes(p)))
    if (hitIn || (i.instanceId && present.includes(i.instanceId))) { const l = sampleLine(s.id); if (l) out.push(l) }
  }
  return listOrNone(out)
})

const eventText = (e: EventDict): string => `event ${e.node_id} ${e.start_idx === e.end_idx ? d(e.start_idx) : `${d(e.start_idx)}→${d(e.end_idx)}`}`
const pairedLines = computed<string[] | null>(() => {
  const i = info.value
  if (!i || !view.comparing) return null
  if (i.kind === 'sample') { const e = cmp.sampleReads.get(i.id ?? '')?.pairing.event; return [e ? eventText(e) : NONE] }
  if (i.kind === 'box') { const e = cmp.boxReads.get(i.id ?? '')?.pairing.event; return [e ? eventText(e) : NONE] }
  if (i.kind !== 'event' && i.kind !== 'hit') return null
  const out: string[] = []
  for (const s of cmp.samples) {
    const p = cmp.sampleReads.get(s.id)?.pairing
    if (!p) continue
    if ((i.instanceId && p.event?.instance_id === i.instanceId) || (i.hitId && p.hitId === i.hitId)) {
      const l = sampleLine(s.id)
      if (l) out.push(`sample ${l}`)
    }
  }
  return listOrNone(out)
})

const eventOf = computed<EventDict | null>(() => {
  const id = info.value?.instanceId
  return id ? view.effectiveAnalysis?.events.find(e => e.instance_id === id) ?? null : null
})
const levelLines = computed<string[] | null>(() => {
  const e = eventOf.value
  if (!e) return null
  return [[view.eventTier(e), view.isEventDrawn(e.instance_id) ? null : 'hidden'].filter(Boolean).join(' ')]
})
const failedLines = computed<string[] | null>(() => {
  const e = eventOf.value
  if (!e) return null
  const row = view.diag?.nodes[e.node_id]?.attr.find(r => r.instance_id === e.instance_id)
  if (!row) return [NONE]
  return listOrNone(Object.entries(row.clauses).filter(([, c]) => !c.satisfied).map(([name]) => name))
})

const rows = computed(() => {
  const i = info.value
  if (!i) return []
  const one = (v: string | null): string[] | null => (v === null ? null : [v])
  const by: Record<(typeof CARD_ROWS)[number], string[] | null> = {
    buys: one(i.buys),
    hits: i.hits ? [i.hits.head, ...i.hits.lines] : null,
    nodes: i.nodes,
    family: one(i.family),
    feedback: feedbackLines.value,
    sample: sampleLines.value,
    paired: pairedLines.value,
    level: levelLines.value,
    failed: failedLines.value,
    id: one(i.id),
    copy: one(copyRef.line()),
  }
  return CARD_ROWS.map(name => ({ name, lines: by[name] }))
})
</script>

<style scoped>
/* 程序固定文字:等宽、黑字;不适用:灰。行序固定,标签列等宽对齐。 */
.sel-card {
  margin: 0 0 8px;
  padding: 6px 8px;
  background: #eef0f3;
  border-radius: 3px;
  font-size: 12px;
  line-height: 17px;
  font-family: ui-monospace, "JetBrains Mono", "DejaVu Sans Mono", Consolas, monospace;
  color: #111111;
}
.row { display: flex; align-items: baseline; }
.lb { flex: 0 0 9ch; }
.val { flex: 1 1 auto; min-width: 0; }
.line { display: block; overflow-wrap: anywhere; }
.na { color: #6b7078; }
</style>
