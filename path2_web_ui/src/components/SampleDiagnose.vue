<template>
  <div v-if="d" class="sample-diagnose" data-testid="sample-diagnose">
    <!-- 头:键值三行 —— 买没买、看的是哪个 node、哪一天 -->
    <div class="ann-kv">
      <span class="ann-k" :title="MATCH_TIP">match</span>
      <div class="ann-row">
        <span class="ann-sym" data-testid="diagnose-match" :data-state="d.read.match.state"
              :title="matchTip">{{ d.read.match.state }}</span>
        <span :class="['ann-sym', 'mark', { off: d.read.mark === '✗' }]" data-testid="diagnose-mark"
              :title="d.read.mark === '✓' ? 'app agrees with the judgment' : 'app disagrees with the judgment'">{{ d.read.mark }}</span>
      </div>
      <span class="ann-k" title="the node whose events are listed below: the node the app buys on">node</span>
      <div class="ann-row">
        <span class="ann-sym" data-testid="diagnose-node">{{ node }}</span>
        <span v-if="cmp.notes[node]" class="ann-biz note" data-testid="diagnose-node-note">{{ cmp.notes[node] }}</span>
      </div>
      <span class="ann-k" title="the sample date: events present on this day are listed">date</span>
      <span class="ann-sym" data-testid="diagnose-date">{{ dates[d.read.day] }}</span>
    </div>

    <!-- 两组,组头各带个数:hits —— 样本日在场、进了 hit 的(一块一次 hit);not_in_hit —— 在场但没进 hit 的 event -->
    <template v-for="g in groups" :key="g.key">
      <div class="grp" :data-testid="`diagnose-group-${g.key}`">
        <span class="ann-k" :title="g.tip">{{ g.key }}</span>
        <span class="ann-sym" data-testid="diagnose-count">{{ g.count }}</span>
        <template v-if="g.key === 'not_in_hit' && g.count">
          <span v-for="t in LOW_TIERS" :key="t" class="ann-sym tier-n" :title="TIER_TIP[t]">· {{ t }} {{ count[t] }}</span>
        </template>
      </div>
      <div v-for="r in g.rows" :key="r.instanceId" data-testid="diagnose-row"
           :class="['ev', { cur: r.instanceId === currentId }]"
           :data-instance="r.instanceId" :data-paired="r.paired ? 1 : 0" :data-group="g.key"
           :title="g.key === 'hits' ? 'click to select this hit on the chart; ↑/↓ walks the hits of this group in this order' : 'click to select this event on the chart'"
           @click="pick(r.instanceId)">
        <div class="ann-kv ev-kv">
          <span class="ann-k" :title="g.key === 'hits' ? 'start of the hit: different starts are different families'
                                                       : 'start of the event: different starts are different families'">start</span>
          <div class="ann-row">
            <span class="ann-sym">{{ dates[r.start] }}</span>
            <span v-if="hitCount(r.instanceId) >= 2" class="ann-sym" data-testid="diagnose-shared"
                  title="this many hits share this event (they differ in other nodes)">× {{ hitCount(r.instanceId) }}</span>
            <span class="ann-grow" />
            <span v-if="r.paired" class="ann-sym paired" data-testid="diagnose-paired" :title="PAIRED_TIP">paired</span>
          </div>
          <template v-if="r.member">
            <span class="ann-k" :title="g.key === 'hits' ? FIRST_DIFF_HIT_TIP : FIRST_DIFF_TIP">first_diff</span>
            <span class="ann-sym">{{ r.member }}</span>
          </template>
          <template v-if="g.key === 'not_in_hit'">
            <span class="ann-k" title="how far this event got: qualified / detected">level</span>
            <div class="ann-row">
              <span class="ann-sym" data-testid="diagnose-level" :title="TIER_TIP[r.level]">{{ r.level }}</span>
              <span v-if="belowLevel(r.level)" class="ann-nil" data-testid="diagnose-hidden"
                    :title="`not drawn at level ${view.level}; switch the level buttons to see it`">hidden</span>
            </div>
          </template>
          <template v-if="r.failed.length">
            <span class="ann-k" title="where clauses this event failed (names only, no values)">failed</span>
            <div class="failed">
              <template v-for="w in r.failed" :key="w">
                <span class="ann-sym" data-testid="diagnose-failed" :data-where="w">{{ w }}</span>
                <span v-if="noteOf(w)" class="ann-biz note" data-testid="diagnose-note">{{ noteOf(w) }}</span>
                <span v-else />
              </template>
            </div>
          </template>
        </div>
      </div>
      <button v-if="g.key === 'not_in_hit' && hidden > 0" type="button" class="ann-btn more" data-testid="diagnose-more"
              title="list them one by one" @click="expanded = true">+ {{ hidden }} detected</button>
    </template>
  </div>
</template>

<script setup lang="ts">
/**
 * selection 页样本下面的 diagnose 块(只在 compare、当前 pattern 有 app 时出)。都是键值排:
 * - 头(三行):match —— app 的买点离样本日在容差内算 matched(stores/compare.ts → annotate/compareRead.ts 的
 *   matchOf),后面的 ✓ / ✗ 是「app 和这个样本的判断一致与否」,和图上 ▲ 字母后的记号同一个;node —— 下面列的是
 *   哪个 node 的 event(买点 node 所在的那个),后跟 mapping notes 里它的用户原话;date —— 样本日;
 * - 下面按「进没进 hit」分两组,组头各带个数(图上一个买入日 ▼ 可能并了几次 hit,这里一次一块地分开):
 *   - hits n:样本日在场的 hit,一块一次(块的身份仍是它在这个 node 上的 event;同一个 event 被几次 hit 共用时
 *     块头写 × k,个数照 hit 数算)。块里:start 起点、first_diff(同起点同跨度有几块时才有:它们内部第一处
 *     不一样的子段、以及这一块里那一段的终点,如 `step → 2024-11-21`;不是类型)。配对的在最前(块头右侧标
 *     paired),其余按块里最早那次 hit 的先后——和 ↑ / ↓ 在样本日在场的 hit 间走的先后一致(同一份排序,
 *     stores/compare.ts 的 stackCards);
 *   - not_in_hit n:在场但没进 hit 的 event,组头另写 qualified / detected 各几个。块里多 level 档位、failed
 *     没过的 where(一行一条:where 名 + mapping notes 里的用户原话;只给类别,不给实测值与门槛,spec 1.4)。
 *     配对那块和 qualified 的照列,其余 detected 折成「+ n detected」,点开逐块;
 * - 当前选中的那一块(图上或这里点的、↑ / ↓ 走到的)描黑粗边;点一块 = 选中它,当前日仍在样本日;
 * - 聚焦样本不动档位按钮:那一块的档位低于当前档位、图上画不出来时,档位后写灰字 hidden(悬停说明);
 * - 读的是聚焦的样本:选中的,没选中时是进 compare 时默认聚焦的那个(FocusedSamplePanel 里显示)。
 */
import { computed, ref, watch } from 'vue'
import { useCompareStore } from '../stores/compare'
import { useViewStore } from '../stores/view'
import { useAnnotationStore } from '../stores/annotation'
import type { Tier } from '../types'

const cmp = useCompareStore()
const view = useViewStore()
const ann = useAnnotationStore()
const LOW_TIERS: readonly Tier[] = ['qualified', 'detected']
const TIER_TIP: Record<Tier, string> = {
  in_hit: 'in_hit: the event is part of a hit (the app buys with it)',
  qualified: 'qualified: passed every where clause of its node, but is in no hit',
  detected: 'detected: found by the detector, but failed a where clause of its node',
}
const HITS_TIP = 'hits present on the sample date (the event of this node in each hit covers the day and is confirmed by then); one card per hit'
const NOT_IN_HIT_TIP = 'events of this node present on the sample date that are in no hit, counted by level'
const FIRST_DIFF_HIT_TIP = 'these hits have the same start and end; this is the first part inside them that differs, and where that part ends in this hit (it is not a type)'
const FIRST_DIFF_TIP = 'these events have the same start and end; this is the first part inside them that differs, and where that part ends in this event (it is not the event\'s type)'
const PAIRED_TIP = 'the event matched to this sample: the one in a hit that day; if none, the one that got furthest, then the latest start'
/** 容差只读后端标注路由带回的那一份(path2_web/annotation/match.py),这里不另写数。 */
const MATCH_TIP = computed(() => {
  const t = ann.match
  return t
    ? `matched: an app buy day is within ${bars(t.pos)} (pos sample) / ${bars(t.neg)} (neg sample) of the sample date`
    : 'matched: an app buy day is within the tolerance of the sample date'
})
const d = computed(() => cmp.diagnose)
const node = computed(() => cmp.pairNode ?? '')
const dates = computed(() => view.barDates)
const expanded = ref(false)
watch(() => d.value?.read.id, () => { expanded.value = false })

const count = computed<Record<Tier, number>>(() => {
  const out: Record<Tier, number> = { in_hit: 0, qualified: 0, detected: 0 }
  for (const r of d.value?.rows ?? []) out[r.level] += 1
  return out
})

const matchTip = computed(() => {
  const m = d.value?.read.match
  if (!m) return ''
  return m.state === 'matched'
    ? `buy day ${m.offset! >= 0 ? '+' : ''}${bars(m.offset!)} from the sample date`
    : `no app buy day within ${tolOf(d.value!.read.judgment) ?? 'the tolerance'} of the sample date`
})
function tolOf(j: 'pos' | 'neg'): string | null {
  const t = ann.match
  return t ? bars(j === 'pos' ? t.pos : t.neg) : null
}
function bars(n: number): string { return `${n} bar${Math.abs(n) === 1 ? '' : 's'}` }

/** 当前选中的那一块:选中的 event,或选中 hit 绑定在这个 node 上的实例。 */
const currentId = computed<string | null>(() => {
  const ids = new Set(d.value?.rows.map(r => r.instanceId) ?? [])
  const hitInst = view.selectedHitId
    ? (view.effectiveAnalysis?.hits ?? []).find(h => h.hit_id === view.selectedHitId)?.node_index?.[node.value] ?? null
    : null
  for (const id of [view.focusedInstanceRef, hitInst]) if (id && ids.has(id)) return id
  return null
})

/** 这个 node 的 event → 用到它的 hit(按 hit 在结果里的先后,即图上 ←/→ 走的先后)。 */
const hitsOfEvent = computed(() => {
  const out = new Map<string, string[]>()
  for (const h of view.effectiveAnalysis?.hits ?? []) {
    const inst = h.node_index?.[node.value]
    if (typeof inst !== 'string') continue
    const ids = out.get(inst)
    if (ids) ids.push(h.hit_id)
    else out.set(inst, [h.hit_id])
  }
  return out
})
function hitCount(instanceId: string): number { return hitsOfEvent.value.get(instanceId)?.length ?? 0 }

/** 进了 hit 的:和 ↑ / ↓ 走的先后同一份(配对的在最前,其余按块里最早那次 hit 的先后)。 */
const hitRows = computed(() => {
  const read = d.value?.read
  const order = new Map<string, number>()
  if (read && cmp.pairNode) cmp.stackCards(read.pairing, cmp.pairNode).forEach((c, k) => order.set(c.instanceId, k))
  return (d.value?.rows ?? []).filter(r => r.level === 'in_hit')
    .sort((a, b) => (order.get(a.instanceId) ?? Infinity) - (order.get(b.instanceId) ?? Infinity))
})
const lowRows = computed(() => (d.value?.rows ?? []).filter(r => r.level !== 'in_hit'))
const lowShown = computed(() => expanded.value
  ? lowRows.value
  : lowRows.value.filter(r => r.paired || r.level !== 'detected' || r.instanceId === currentId.value))
const hidden = computed(() => lowRows.value.length - lowShown.value.length)

const groups = computed(() => [
  { key: 'hits' as const, tip: HITS_TIP, rows: hitRows.value,
    count: hitRows.value.reduce((n, r) => n + Math.max(1, hitCount(r.instanceId)), 0) },
  { key: 'not_in_hit' as const, tip: NOT_IN_HIT_TIP, rows: lowShown.value, count: lowRows.value.length },
])

const RANK: Record<string, number> = { detected: 0, qualified: 1, in_hit: 2 }
/** 这一档在当前档位下画不出来(档位按钮不因聚焦样本自动改)。 */
function belowLevel(tier: string): boolean { return RANK[tier] < RANK[view.level] }

function noteOf(where: string): string | null {
  return cmp.notes[`${node.value}.${where}`] ?? null
}

/** 点一块:选中的仍在这个样本下面,hits 组的跳到它的第一次(× k 的随后用 ↑ / ↓ 走过它那 k 次),not_in_hit 组的只选中那个 event。 */
function pick(id: string): void {
  const r = d.value?.read
  if (r) cmp.pickCard(r.id, id)
}
</script>

<style src="./annotationPanel.css"></style>
<style scoped>
.sample-diagnose { margin-top: 10px; }
.mark { font-weight: 700; padding: 0 3px; border-radius: 2px; }
.mark.off { background: #E8875A; }   /* 朱红:只表示「app 的判断和你相反」(spec 5.8);字照规范用黑 */
.tier-n { cursor: help; white-space: nowrap; }   /* 只是计数,不描边:描了边会被当成按钮 */
.note { font-size: 12px; }
/* 一个 event 一块:细边;当前选中的那块黑粗边(靠黑边认,不靠颜色) */
/* 组头:一行,键 + 个数;和上面隔开一点 */
.grp { display: flex; flex-wrap: wrap; align-items: baseline; gap: 4px 8px; margin-top: 10px; }
.ev { margin-top: 6px; padding: 5px 7px; border: 1px solid var(--line-strong); border-radius: 4px; background: #fff; cursor: pointer; }
.ev.cur { border: 2px solid var(--ink); padding: 4px 6px; }
.ev-kv { gap: 3px 8px; }
.paired { padding: 0 4px; border: 1.5px solid var(--ink); border-radius: 3px; font-weight: 700; cursor: help; }
/* failed:两列小表,左 where 名(等宽),右用户原话 */
.failed { display: grid; grid-template-columns: max-content 1fr; gap: 2px 8px; align-items: start; min-width: 0; }
.more { margin-top: 6px; }
</style>
