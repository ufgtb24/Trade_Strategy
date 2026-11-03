<template>
  <div v-if="ann.state" class="pattern-panel" :data-testid="unsorted ? 'unsorted-page' : 'pattern-page'">
    <div class="ann-hdr">
      <span class="ann-k" title="current pattern; switch it in the top bar">pattern</span>
      <span v-if="unsorted" class="ann-sym" data-testid="pattern-name"
            title="not a pattern: samples not yet assigned to one">unsorted</span>
      <span v-else class="ann-biz" data-testid="pattern-name">{{ ann.currentPattern }}</span>
    </div>

    <div class="ann-kv">
      <template v-if="!unsorted">
        <span class="ann-k" title="one sentence: what this pattern should catch">definition</span>
        <textarea :key="ann.currentPattern ?? ''" class="ann-area" data-testid="pattern-definition" rows="2"
                  :value="definition" @keydown.enter.exact.prevent="($event.target as HTMLTextAreaElement).blur()"
                  @blur="ann.setPatternDefinition(ann.currentPattern!, ($event.target as HTMLTextAreaElement).value)" />
      </template>
      <span class="ann-k" :title="unsorted ? 'samples not yet in a pattern' : 'all samples of this pattern'">samples</span>
      <div class="ann-row" data-testid="samples-count">
        <CountDoor :samples="samples" :count-key="POS" tip="samples judged pos" />
        <span class="ann-sym">·</span>
        <CountDoor :samples="samples" :count-key="NEG" tip="samples judged neg" />
      </div>
      <CountParts :samples="samples" :count-key="POS" :tips="{ pos: 'samples judged pos' }" />
      <CountParts :samples="samples" :count-key="NEG" :tips="{ neg: 'samples judged neg' }" />
    </div>

    <!-- unsorted 页:按骨架分行,整行 move -->
    <template v-if="unsorted">
      <div class="ann-hdr sec">
        <span class="ann-k" title="samples not yet in a pattern, one row per judgment and sequence; click a card to open it in the main chart">samples</span>
      </div>
      <div class="grid head">
        <span class="ann-k" :title="JUDGMENT_TIP">judgment</span>
        <span class="ann-k" title="top-level member features, in order; nested boxes and attrs left out">sequence</span>
        <span />
      </div>
      <div v-for="(r, i) in rows" :key="i" class="ann-blk" data-testid="unsorted-row"
           :data-judgment="r.judgment" :data-sequence="sequenceText(r)">
        <div class="grid">
          <span class="ann-row nw">
            <span class="ann-sym" :title="JUDGMENT_TIP">{{ r.judgment }}</span>
            <span v-if="r.judgment === 'neg'" class="ann-nil" data-testid="row-pending"
                  title="pick the pattern it looks like">pattern?</span>
          </span>
          <span class="ann-row seq">
            <template v-for="(f, j) in r.skeleton" :key="j">
              <span v-if="j" class="ann-sym">→</span>
              <span v-if="f !== null" class="ann-biz" :title="definitionOf(f)">{{ ann.nameOf(f) }}</span>
              <span v-else class="ann-sym">unnamed</span>
            </template>
            <span v-if="!r.skeleton.length" class="ann-nil" title="no member boxes">∅</span>
          </span>
          <span class="ann-sym" title="samples in this row">×{{ r.samples.length }}</span>
        </div>
        <!-- move 管整行:单占卡片右边一栏,不落到某张卡正下方 -->
        <div class="cardline">
          <div class="ann-row cards">
            <SampleCard v-for="x in r.samples" :key="x.sample.id" :x="x" />
          </div>
          <PatternPicker :value="null" move tid="row-move" class="move"
                         :title="`move ${r.samples.length === 1 ? 'this sample' : `these ${r.samples.length} samples`} to a pattern`"
                         @pick="$event !== null && ann.moveSamples(r.samples.map(x => x.sample.id), $event)" />
        </div>
      </div>
      <span v-if="!rows.length" class="ann-nil">empty</span>
    </template>

    <!-- pattern 页:features 区平铺、samples 表按 judgment 折行 -->
    <template v-else>
      <div class="ann-hdr sec">
        <span class="ann-k" title="top-level features in member boxes of this pattern's samples (pos and neg), in order; features nested in their boxes hang under them (⊃)">features</span>
      </div>
      <template v-for="(b, i) in blocks" :key="b.feature">
        <div v-if="i" class="conn" data-testid="feature-arrow"><span class="ann-sym" :title="ORDER_TIP">↓</span></div>
        <FeatureBlockView :block="b" :samples="samples" />
      </template>
      <span v-if="!blocks.length" class="ann-nil">empty</span>

      <div class="ann-hdr sec">
        <span class="ann-k" title="all samples of this pattern, one row per judgment; click a card to open it in the main chart">samples</span>
      </div>
      <div class="grid head two">
        <span class="ann-k" :title="JUDGMENT_TIP">judgment</span>
        <span />
      </div>
      <div v-for="j in JUDGMENTS" :key="j" class="ann-blk" data-testid="samples-row" :data-judgment="j">
        <div class="grid two">
          <span class="ann-sym" :title="JUDGMENT_TIP">{{ j }}</span>
          <span class="ann-sym" title="samples in this row">×{{ byJ[j].length }}</span>
        </div>
        <div v-if="byJ[j].length" class="ann-row cards">
          <SampleCard v-for="x in byJ[j]" :key="x.sample.id" :x="x" />
        </div>
      </div>
    </template>
  </div>
  <span v-else class="ann-nil">empty</span>
</template>

<script setup lang="ts">
/**
 * 侧栏 pattern 页(spec 5.6;还没有 app 时):
 * - 当前 pattern 是 unsorted 时是 unsorted 页:samples 计数一行;未归类的样本按(judgment、骨架)分行,
 *   一整行可以 move 进已有 pattern 或 + new;负样本那一行在 judgment 后面写灰字 pattern?(它的「像」还没有对象,
 *   算没填完);
 * - 否则是 pattern 页:definition(写进这个 pattern)、samples 计数一行、features 区平铺(块之间一律画 ↓)、
 *   samples 表按 judgment 折行(pos、neg 两行,0 个也写)。
 * 计数一律数样本、点开就地分排(CountDoor / CountParts,规则见 annotate/grouping.ts)。
 */
import { computed } from 'vue'
import { useAnnotationStore } from '../stores/annotation'
import {
  featureBlocks, featureOrder, patternSamples, unsortedRows, type CountKey, type PSample, type SkeletonRow,
} from '../annotate/grouping'
import CountDoor from './CountDoor.vue'
import CountParts from './CountParts.vue'
import FeatureBlockView from './FeatureBlockView.vue'
import PatternPicker from './PatternPicker.vue'
import SampleCard from './SampleCard.vue'

const JUDGMENTS = ['pos', 'neg'] as const
const POS: CountKey = { kind: 'samples', judgment: 'pos' }
const NEG: CountKey = { kind: 'samples', judgment: 'neg' }
const JUDGMENT_TIP = 'pos: should buy on the sample date; neg: looks like it but should not'
const ORDER_TIP = 'order: the one above comes first'

const ann = useAnnotationStore()
const unsorted = computed(() => ann.currentPattern === null)
const daysOf = (symbol: string) => ann.daysBySymbol[symbol]
const samples = computed<PSample[]>(() => (ann.state ? patternSamples(ann.state, ann.currentPattern) : []))
const definition = computed(() => ann.state?.patterns.find(p => p.name === ann.currentPattern)?.definition ?? '')
const rows = computed<SkeletonRow[]>(() => (ann.state && unsorted.value ? unsortedRows(ann.state, daysOf, ann.nameOf) : []))
const blocks = computed(() => (unsorted.value ? [] : featureBlocks(samples.value, daysOf, featureOrder(samples.value))))
const byJ = computed(() => ({
  pos: samples.value.filter(x => x.sample.judgment === 'pos'),
  neg: samples.value.filter(x => x.sample.judgment === 'neg'),
}))

const definitionOf = (fid: string) => ann.featureById.get(fid)?.definition ?? ''
const sequenceText = (r: SkeletonRow) => r.skeleton.map(f => (f === null ? 'unnamed' : ann.nameOf(f))).join(' → ')
</script>

<style src="./annotationPanel.css"></style>
<style scoped>
.pattern-panel { display: flex; flex-direction: column; }
.sec { margin-top: 12px; }
/* 表的三列:judgment、sequence、×n;pattern 页的表只有 judgment、×n 两列 */
.grid { display: grid; grid-template-columns: 96px 1fr 28px; gap: 4px; align-items: start; }
.grid.two { grid-template-columns: 96px 1fr; }
.grid.two > :last-child { justify-self: end; }
.grid.head { padding: 0 9px 2px; }
.nw { flex-wrap: nowrap; }
.seq { gap: 2px 4px; }
.cards { margin-top: 4px; gap: 3px; }
.cardline { display: flex; align-items: flex-start; gap: 4px; }
.cardline .cards { flex: 1; }
.cardline .move { flex: none; margin-top: 4px; }
.conn { padding: 0 0 2px 10px; }
</style>
