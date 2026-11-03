<template>
  <div class="chain" :data-testid="tid">
    <template v-for="(it, i) in items" :key="it.kind === 'node' ? it.node.box : `slot-${it.slot.box}`">
      <span v-if="i" class="ann-sym arr">→</span>
      <span v-if="it.kind === 'node'" class="nest">
        <span class="ann-row nw">
          <component :is="editable ? 'button' : 'span'" :type="editable ? 'button' : undefined"
                     class="chip on" data-testid="member-chip" :data-box="it.node.box"
                     :title="`${spanOf(it.node.box)}${editable ? '\nmember box; click to remove' : ''}`"
                     @click="editable && ann.toggleMember(sample.id, it.node.box)">
            <BoxName :box="box(it.node.box)" />
          </component>
          <span v-if="it.dup" class="tag" data-testid="member-dup"
                :title="`two “${nameOf(it.node.box)}” segments at the top of this sample; if they are two things, rename one`">dup</span>
        </span>
        <span v-for="k in flat(it.node.kids)" :key="k.box" class="ann-row nw kid" :style="{ paddingLeft: `${k.depth * 10}px` }">
          <span class="ann-sym" title="nested in the box above">⊃</span>
          <component :is="editable ? 'button' : 'span'" :type="editable ? 'button' : undefined"
                     class="chip on" data-testid="member-chip" :data-box="k.box"
                     :title="`${spanOf(k.box)}${editable ? '\nmember box; click to remove' : ''}`"
                     @click="editable && ann.toggleMember(sample.id, k.box)">
            <BoxName :box="box(k.box)" />
          </component>
        </span>
      </span>
      <component :is="editable ? 'button' : 'span'" v-else-if="it.slot.reason === UNCLAIMED" :type="editable ? 'button' : undefined"
                 class="chip slot cand" data-testid="member-slot" :data-box="it.slot.box" :data-reason="it.slot.reason"
                 :title="`${spanOf(it.slot.box)}\nmaybe drawn but not added${editable ? '; click to add' : ''}`"
                 @click="editable && ann.toggleMember(sample.id, it.slot.box)">
        <BoxName :box="box(it.slot.box)" /><span class="ann-sym take">◂</span>
      </component>
      <span v-else class="chip slot cross" data-testid="member-slot" :data-box="it.slot.box" :data-reason="it.slot.reason"
            :title="`${spanOf(it.slot.box)}\ncrosses sample date: this box ends after the sample date, so it cannot be a member box`">
        <BoxName :box="box(it.slot.box)" /><span class="ann-sym take">⇥</span>
      </span>
    </template>
    <span v-if="items.length" class="ann-sym arr">→</span>
    <span class="ann-sym tri" :title="sample.judgment">{{ triOf(sample.judgment) }}</span>
  </div>
</template>

<script setup lang="ts">
/**
 * 样本的成员链:成员框树的顶层框按先后排,被包住的子框竖着挂在下面(前面写 ⊃);空槽按先后插在中间,
 * 末尾是样本的三角。
 * - 成员框:editable 时点一下拿掉(手动点出);
 * - 画了没收的空槽(unclaimed):短虚线、带 ◂,editable 时点一下收进;
 * - 跨过样本日的空槽(crosses_sample_date):灰、带 ⇥,收不进,悬停写明原因;
 * - 顶层同一特征两段:后面挂 dup。
 * editable 为 false 时只显示(框页顶上那条当前样本的成员链)。
 */
import { computed } from 'vue'
import { useAnnotationStore } from '../stores/annotation'
import { UNCLAIMED, type TreeNode } from '../annotate/membership'
import { memberChain, triOf } from '../annotate/samples'
import type { AnnChart, AnnSample } from '../annotate/model'
import BoxName from './BoxName.vue'

const props = defineProps<{ sample: AnnSample; chart: AnnChart; editable: boolean; tid: string }>()
const ann = useAnnotationStore()

const items = computed(() => {
  if (!ann.state || !ann.membership) return []
  const days = ann.daysBySymbol[props.chart.symbol] ?? []
  return memberChain(props.sample, props.chart, ann.state.charts, days, ann.membership.near)
})
const byId = computed(() => new Map(props.chart.boxes.map(b => [b.id, b])))
const box = (id: string) => byId.value.get(id)!
const spanOf = (id: string) => `${box(id).start} – ${box(id).end}`
const nameOf = (id: string) => ann.nameOf(box(id).feature) ?? 'unnamed'

/** 子框一层层摊平成竖排,depth 是缩进的层数(1 起)。 */
function flat(kids: TreeNode[], depth = 1): { box: string; depth: number }[] {
  return kids.flatMap(k => [{ box: k.box, depth }, ...flat(k.kids, depth + 1)])
}
</script>

<style src="./annotationPanel.css"></style>
<style scoped>
/* 文字一律黑;成员框是实线黑边(按下的样子),画了没收是短虚线(虚线只表示「用户画的」框),跨过样本日的变淡 */
.chain { display: flex; flex-wrap: wrap; align-items: flex-start; gap: 3px 4px; }
.nest { display: inline-flex; flex-direction: column; gap: 2px; }
.nw { flex-wrap: nowrap; }
.arr, .tri { padding-top: 2px; }
.chip {
  display: inline-flex; align-items: center; gap: 2px; padding: 0 3px; border-radius: 3px;
  border: 1px solid var(--line-strong); background: #fff; font: inherit;
}
button.chip { cursor: pointer; }
.chip.on { border: 1.5px solid var(--ink); }
.chip.slot.cand { border: 1.5px dashed var(--ink); }
.chip.slot.cross { border: 1px solid var(--line-strong); opacity: 0.45; cursor: help; }
.take { font-weight: 700; }
.tag {
  font-family: var(--mono); font-size: 11px; color: var(--ink); padding: 0 3px;
  border: 1px solid var(--ink); border-radius: 3px; background: #fff; cursor: help;
}
</style>
