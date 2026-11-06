<template>
  <div v-if="d" class="sample-diagnose" data-testid="sample-diagnose">
    <div class="ann-kv">
      <span class="ann-k" :title="MATCH_TIP">match</span>
      <div class="ann-row">
        <span class="ann-sym" data-testid="diagnose-match" :data-state="d.read.match.state"
              :title="matchTip">{{ d.read.match.state }}</span>
        <span :class="['ann-sym', 'mark', { off: d.read.mark === '✗' }]" data-testid="diagnose-mark"
              :title="d.read.mark === '✓' ? 'app agrees with the judgment' : 'app disagrees with the judgment'">{{ d.read.mark }}</span>
      </div>
      <span class="ann-k" :title="`events of node ${node} present on the sample date; the paired one first`">diagnose</span>
      <div class="ann-row">
        <span class="ann-sym" data-testid="diagnose-head">{{ node }} @ {{ dates[d.read.day] }}</span>
        <span v-if="cmp.notes[node]" class="ann-biz note" data-testid="diagnose-node-note">{{ cmp.notes[node] }}</span>
        <span class="ann-grow" />
        <span class="ann-sym" data-testid="diagnose-count">{{ d.rows.length ? `${d.rows.length} event${d.rows.length > 1 ? 's' : ''}` : 'none' }}</span>
      </div>
    </div>
    <table v-if="d.rows.length" class="diag-table" data-testid="diagnose-rows">
      <thead>
        <tr>
          <th />
          <th title="start of the event: different starts are different families">start</th>
          <th title="tells apart events with the same span">member</th>
          <th title="in_hit / qualified / detected">level</th>
        </tr>
      </thead>
      <tbody v-for="r in shown" :key="r.instanceId" :class="{ cur: r.instanceId === currentId }" data-testid="diagnose-row"
             :data-instance="r.instanceId" :data-paired="r.paired ? 1 : 0" @click="pick(r.instanceId)">
        <tr>
          <td class="ann-sym">{{ r.instanceId === currentId ? '▶' : '' }}</td>
          <td class="ann-sym" :title="dates[r.start]">{{ short(dates[r.start]) }}</td>
          <td class="ann-sym">{{ r.member ? shortLabel(r.member) : '' }}</td>
          <td class="ann-sym" data-testid="diagnose-level">{{ r.level }}<span v-if="belowLevel(r.level)" class="hidden-tag"
              data-testid="diagnose-hidden" :title="`not drawn at level ${view.level}; switch the level buttons to see it`"> hidden</span></td>
        </tr>
        <tr v-if="r.failed.length">
          <td />
          <td colspan="3" class="failed-row">
            <span class="ann-sym" title="where clauses this event failed (names only, no values)">failed</span>
            <span v-for="w in r.failed" :key="w" class="failed" data-testid="diagnose-failed" :data-where="w">
              <span class="ann-sym">{{ w }}</span>
              <span v-if="noteOf(w)" class="ann-biz note" data-testid="diagnose-note">{{ noteOf(w) }}</span>
            </span>
          </td>
        </tr>
      </tbody>
      <tbody v-if="hidden > 0">
        <tr>
          <td />
          <td colspan="3">
            <button type="button" class="ann-btn" data-testid="diagnose-more" title="list them one by one"
                    @click="expanded = true">+ {{ hidden }} detected</button>
          </td>
        </tr>
      </tbody>
    </table>
  </div>
</template>

<script setup lang="ts">
/**
 * selection 页样本下面的 diagnose 块(只在 compare、当前 pattern 有 app 时出):
 * - match:app 的买点离样本日在容差内算 matched(stores/compare.ts → annotate/compareRead.ts 的 matchOf),
 *   后面的 ✓ / ✗ 是「app 和这个样本的判断一致与否」,和图上 ▲ 字母后的记号同一个;
 * - diagnose:样本日那天这个 node 在场的 event 各一行,配对的在前;每行写起点、同格消歧(memberLabels)、档位,
 *   有没过的 where 时下面再起一行写 where 名,名下是 mapping notes 里的用户原话(node 的 notes 写在 diagnose 头上)。
 *   和样本日同一年的日子省掉年份。只给类别,不给实测值与门槛(spec 1.4);
 * - 配对那行和档位不低于 qualified 的照列,其余 detected 折成「+ n detected」,点开逐行;
 * - ▶ 跟着当前选中的 event(图上或这里点的、←/→ 走到的)走;点一行 = 选中它,当前日仍在样本日;
 * - 聚焦样本不动档位按钮:那一行的档位低于当前档位、图上画不出来时,档位后写 hidden(悬停说明);
 * - 读的是聚焦的样本:选中的,没选中时是进 compare 时默认聚焦的那个(FocusedSamplePanel 里显示)。
 */
import { computed, ref, watch } from 'vue'
import { useCompareStore } from '../stores/compare'
import { useViewStore } from '../stores/view'
import { useAnnotationStore } from '../stores/annotation'

const cmp = useCompareStore()
const view = useViewStore()
const ann = useAnnotationStore()
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

/** 当前选中的那一行:选中的 event,或选中 hit 绑定在这个 node 上的实例。 */
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

/** 和样本日同一年的日子省掉年份(侧栏窄);悬停仍给全日期。 */
const year = computed(() => (d.value ? (dates.value[d.value.read.day] ?? '').slice(0, 5) : ''))
function short(date: string | undefined): string {
  if (!date) return ''
  return year.value && date.startsWith(year.value) ? date.slice(5) : date
}
function shortLabel(label: string): string {
  return label.replace(/\d{4}-\d{2}-\d{2}/g, m => short(m))
}

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
.mark.off { background: #D55E00; }   /* 朱红:只表示「app 的判断和你相反」(spec 5.8);字照规范用黑 */
.diag-table { width: 100%; border-collapse: collapse; margin-top: 4px; }
.diag-table th { font-family: var(--mono); font-size: 11px; font-weight: 400; text-align: left; color: var(--ink); cursor: help; padding: 1px 4px; }
.diag-table td { padding: 2px 4px; vertical-align: top; white-space: nowrap; }
.diag-table td.failed-row { white-space: normal; padding-bottom: 4px; }
.diag-table tbody[data-testid="diagnose-row"] { cursor: pointer; }
.diag-table tbody.cur td { font-weight: 700; }
.failed { display: inline-flex; flex-direction: column; margin: 0 0 2px 8px; vertical-align: top; }
.note { font-size: 12px; }
.hidden-tag { font-weight: 400; cursor: help; }
</style>
