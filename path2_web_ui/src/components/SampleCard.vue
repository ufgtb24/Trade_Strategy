<template>
  <button type="button" :class="['sample-card', { cur: ann.selectedSampleId === x.sample.id }]" data-testid="sample-card"
          :data-sample="x.sample.id" :title="`${x.sample.judgment}; click to open in main chart`" @click="open">
    <span class="ann-sym">{{ triOf(x.sample.judgment) }}</span>
    <span class="ann-biz">{{ x.chart.symbol }}</span>
    <span class="ann-sym">{{ x.sample.date }}</span>
  </button>
</template>

<script setup lang="ts">
/**
 * pattern 页、unsorted 页上代表一个样本的卡:三角(正样本 ▲、负样本 △)、股票代码、样本日。
 * 点一下在主图打开那张图(图窗停在样本的跨度上)并选中这个样本,侧栏留在当前页,方便挨个看;
 * 主图上选中的那个样本,卡的边加粗。
 */
import { nextTick } from 'vue'
import { useAnnotationStore } from '../stores/annotation'
import { useViewStore } from '../stores/view'
import { sampleWindow, type ChartSample } from '../annotate/grouping'
import { triOf } from '../annotate/samples'

const props = defineProps<{ x: ChartSample }>()
const ann = useAnnotationStore()
const view = useViewStore()

async function open() {
  view.openSymbol(props.x.chart.symbol, sampleWindow(props.x))
  await nextTick()               // 换图会清掉选中(KlineChart 的 symbol 监听),等它跑完再选中
  ann.selectSample(props.x.sample.id, { keepTab: true })
}
</script>

<style src="./annotationPanel.css"></style>
<style scoped>
.sample-card {
  display: inline-flex; align-items: center; gap: 3px; padding: 1px 4px;
  border: 1px solid var(--line-strong); border-radius: 3px; background: #fff; cursor: pointer; font: inherit;
}
.sample-card:hover { border-color: var(--ink); }
.sample-card.cur { border: 1.5px solid var(--ink); box-shadow: inset 0 -2px 0 var(--ink); }
</style>
