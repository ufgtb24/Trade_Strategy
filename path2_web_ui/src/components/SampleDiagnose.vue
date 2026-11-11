<template>
  <div v-if="d" class="sample-diagnose" data-testid="sample-diagnose">
    <!-- 头:键值四行 —— 买没买、看的是哪个 node、哪一天、那天在场几个 event(按档位分) -->
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
      <span class="ann-k" :title="EVENTS_TIP">events</span>
      <div class="ann-row" data-testid="diagnose-count">
        <span class="ann-sym">{{ d.rows.length }}</span>
        <template v-if="d.rows.length">
          <span v-for="t in TIERS" :key="t" class="ann-sym tier-n" :title="TIER_TIP[t]">· {{ t }} {{ count[t] }}</span>
        </template>
      </div>
    </div>

    <!-- 每个 event 一块:块头是它是谁(配对的那个标 paired),块里键值排 start / member / level / failed -->
    <div v-for="r in shown" :key="r.instanceId" data-testid="diagnose-row"
         :class="['ev', { cur: r.instanceId === currentId }]"
         :data-instance="r.instanceId" :data-paired="r.paired ? 1 : 0"
         title="click to select this event on the chart" @click="pick(r.instanceId)">
      <div class="ann-kv ev-kv">
        <span class="ann-k" title="start of the event: different starts are different families">start</span>
        <div class="ann-row">
          <span class="ann-sym">{{ dates[r.start] }}</span>
          <span class="ann-grow" />
          <span v-if="r.paired" class="ann-sym paired" data-testid="diagnose-paired" :title="PAIRED_TIP">paired</span>
        </div>
        <template v-if="r.member">
          <span class="ann-k" :title="FIRST_DIFF_TIP">first_diff</span>
          <span class="ann-sym">{{ r.member }}</span>
        </template>
        <span class="ann-k" title="how far this event got: in_hit / qualified / detected">level</span>
        <div class="ann-row">
          <span class="ann-sym" data-testid="diagnose-level" :title="TIER_TIP[r.level]">{{ r.level }}</span>
          <span v-if="belowLevel(r.level)" class="ann-nil" data-testid="diagnose-hidden"
                :title="`not drawn at level ${view.level}; switch the level buttons to see it`">hidden</span>
        </div>
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
    <button v-if="hidden > 0" type="button" class="ann-btn more" data-testid="diagnose-more"
            title="list them one by one" @click="expanded = true">+ {{ hidden }} detected</button>
  </div>
</template>

<script setup lang="ts">
/**
 * selection 页样本下面的 diagnose 块(只在 compare、当前 pattern 有 app 时出)。两层,都是键值排:
 * - 头(四行):match —— app 的买点离样本日在容差内算 matched(stores/compare.ts → annotate/compareRead.ts 的
 *   matchOf),后面的 ✓ / ✗ 是「app 和这个样本的判断一致与否」,和图上 ▲ 字母后的记号同一个;node —— 下面列的是
 *   哪个 node 的 event(买点 node 所在的那个),后跟 mapping notes 里它的用户原话;date —— 样本日;events ——
 *   那天这个 node 在场的 event 几个,按档位各几个;
 * - 每个 event 一块(配对的在最前,块头右侧标 paired):start 起点、first_diff(同起点同跨度有几个 event 时才有:
 *   它们内部第一处不一样的子段、以及这个 event 里那一段的终点,如 `step → 2024-11-21`;不是事件的类型)、
 *   level 档位、failed 没过的 where(一行一条:where 名 + mapping notes 里的用户原话)。只给类别,不给实测值与
 *   门槛(spec 1.4);
 * - 配对那块和档位不低于 qualified 的照列,其余 detected 折成「+ n detected」,点开逐块;
 * - 当前选中的 event(图上或这里点的、←/→ 走到的)那一块描黑粗边;点一块 = 选中它,当前日仍在样本日;
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
const TIERS: readonly Tier[] = ['in_hit', 'qualified', 'detected']
const TIER_TIP: Record<Tier, string> = {
  in_hit: 'in_hit: the event is part of a hit (the app buys with it)',
  qualified: 'qualified: passed every where clause of its node, but is in no hit',
  detected: 'detected: found by the detector, but failed a where clause of its node',
}
const EVENTS_TIP = 'events of this node present on the sample date (their span covers the day and they are confirmed by then), counted by level'
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

const shown = computed(() => {
  const rows = d.value?.rows ?? []
  if (expanded.value) return rows
  return rows.filter(r => r.paired || r.level !== 'detected' || r.instanceId === currentId.value)
})
const hidden = computed(() => (d.value?.rows.length ?? 0) - shown.value.length)

const RANK: Record<string, number> = { detected: 0, qualified: 1, in_hit: 2 }
/** 这一档在当前档位下画不出来(档位按钮不因聚焦样本自动改)。 */
function belowLevel(tier: string): boolean { return RANK[tier] < RANK[view.level] }

function noteOf(where: string): string | null {
  return cmp.notes[`${node.value}.${where}`] ?? null
}

function pick(id: string): void {
  const r = d.value?.read
  if (!r) return
  view.focusEvent(id, { day: r.day, family: cmp.samplesRow })
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
.ev { margin-top: 6px; padding: 5px 7px; border: 1px solid var(--line-strong); border-radius: 4px; background: #fff; cursor: pointer; }
.ev.cur { border: 2px solid var(--ink); padding: 4px 6px; }
.ev-kv { gap: 3px 8px; }
.paired { padding: 0 4px; border: 1.5px solid var(--ink); border-radius: 3px; font-weight: 700; cursor: help; }
/* failed:两列小表,左 where 名(等宽),右用户原话 */
.failed { display: grid; grid-template-columns: max-content 1fr; gap: 2px 8px; align-items: start; min-width: 0; }
.more { margin-top: 6px; }
</style>
