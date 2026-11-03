<template>
  <div v-if="sel" class="sample-panel" data-testid="sample-panel">
    <div class="ann-hdr">
      <span class="ann-sym" data-testid="sample-head"
            :title="`sample date${letter ? '; letter = order among samples of the current pattern on this chart' : ''}`">{{ letter ? `${letter} · ` : '' }}{{ sel.sample.date }}</span>
      <span class="ann-sym" :title="sel.sample.judgment">{{ triOf(sel.sample.judgment) }}</span>
      <span class="ann-grow" />
      <button type="button" class="ann-btn" data-testid="sample-delete"
              title="delete this sample now; its boxes stay on the chart" @click="ann.deleteSample(sel.sample.id)">delete</button>
    </div>
    <div class="ann-kv">
      <span class="ann-k" :title="pending ? 'pick the pattern it looks like' : 'pattern this sample belongs to'">pattern</span>
      <PatternPicker :value="sel.sample.pattern" :pending="pending" tid="sample-pattern"
                     title="pattern this sample belongs to" @pick="ann.setSamplePattern(sel.sample.id, $event)" />

      <span class="ann-k" title="pos: the pattern's app should buy on this date; neg: looks like the pattern but should not be bought. Judge only by what is visible on or before the sample date">judgment</span>
      <div class="ann-row">
        <button v-for="j in JUDGMENTS" :key="j" type="button" :class="['ann-btn', { on: sel.sample.judgment === j }]"
                :data-testid="`sample-judgment-${j}`" @click="ann.setJudgment(sel.sample.id, j)">{{ j }}</button>
      </div>

      <span class="ann-k" title="note on this sample">note</span>
      <input :key="sel.sample.id" class="ann-input" data-testid="sample-note" :value="sel.sample.note ?? ''"
             @change="ann.setSampleNote(sel.sample.id, ($event.target as HTMLInputElement).value)" />
    </div>

    <div class="ann-hdr sec">
      <span class="ann-k" title="member boxes: the basis of this judgment; click a box to remove it, a dashed slot to add it">members</span>
    </div>
    <MemberChain :sample="sel.sample" :chart="sel.chart" :editable="true" tid="sample-members" />

    <template v-if="others.length">
      <div class="ann-hdr sec">
        <span class="ann-k" title="boxes starting on or before the sample date that are not member boxes; click to add">others</span>
      </div>
      <div class="ann-row" data-testid="sample-others">
        <template v-for="o in others" :key="o.box.id">
          <span v-if="o.crosses" class="ann-chip crosses" data-testid="other-chip" :data-box="o.box.id" data-cross="1"
                :title="`${o.box.start} – ${o.box.end}\ncrosses sample date`"><BoxName :box="o.box" /></span>
          <button v-else type="button" :class="['ann-chip', { unclaimed: o.unclaimed }]" data-testid="other-chip" :data-box="o.box.id"
                  :title="`${o.box.start} – ${o.box.end}\n${o.unclaimed ? 'maybe drawn but not added; ' : ''}click to add`"
                  @click="ann.toggleMember(sel.sample.id, o.box.id)">
            <BoxName :box="o.box" /><span v-if="o.unclaimed" class="ann-take">◂</span>
          </button>
        </template>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
/**
 * selection 页里选中一个样本时的内容:
 * - 页头:字母(当前 pattern 的样本才有)· 样本日、三角、delete(框留在图上);
 * - pattern(负样本挂在 unsorted 时显示灰字 pattern?)、judgment(pos / neg)、note;
 * - members:成员链(MemberChain),点成员框拿掉、点画了没收的空槽收进;
 * - others:起点不晚于样本日、不是成员框的框,点一下收进;画了没收的排最前(短虚线、◂),
 *   跨过样本日的排最后(变淡、收不进,悬停写 crosses sample date)。
 */
import { computed } from 'vue'
import { useAnnotationStore } from '../stores/annotation'
import { emptySlots } from '../annotate/membership'
import { othersOf, sampleLetters, triOf } from '../annotate/samples'
import BoxName from './BoxName.vue'
import MemberChain from './MemberChain.vue'
import PatternPicker from './PatternPicker.vue'

const JUDGMENTS = ['pos', 'neg'] as const

const ann = useAnnotationStore()
const sel = computed(() => ann.selectedSample)
const letter = computed(() => (sel.value ? sampleLetters(sel.value.chart, ann.currentPattern).get(sel.value.sample.id) ?? null : null))
const pending = computed(() => !!sel.value && sel.value.sample.judgment === 'neg' && sel.value.sample.pattern === null)
const others = computed(() => {
  const s = sel.value
  if (!s || !ann.state || !ann.membership) return []
  const slots = emptySlots(ann.state.charts, s.chart.symbol, s.sample.id, ann.daysBySymbol[s.chart.symbol] ?? [],
                           ann.membership.near)
  return othersOf(s.sample, s.chart, slots)
})
</script>

<style src="./annotationPanel.css"></style>
<style scoped>
.sec { margin-top: 10px; }
</style>
