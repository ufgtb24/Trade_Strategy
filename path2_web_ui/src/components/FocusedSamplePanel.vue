<template>
  <div v-if="smp" class="focused-sample" data-testid="focused-sample">
    <div class="ann-hdr">
      <span class="ann-k" :title="FOCUS_TIP">focus</span>
      <span class="ann-sym" data-testid="focused-sample-head">{{ letter ? `${letter} · ` : '' }}{{ smp.date }}</span>
      <span class="ann-sym" :title="smp.judgment">{{ triOf(smp.judgment) }}</span>
      <span class="ann-grow" />
      <button type="button" class="ann-btn" data-testid="focused-sample-select"
              title="select this sample (boxes you draw then join it by default)"
              @click="ann.selectSample(smp.id)">select</button>
    </div>
    <SampleDiagnose />
  </div>
</template>

<script setup lang="ts">
/**
 * compare 的 selection 页什么都没选中、但有聚焦样本时(进 compare 时默认聚焦的那个)显示它的 diagnose:
 * 默认聚焦只设当前日与 app 的选中,不选中样本——选中样本会让它成为当前样本,之后画的框默认并进它——
 * 所以这里只读,点 select 才真选中。
 */
import { computed } from 'vue'
import { useAnnotationStore } from '../stores/annotation'
import { useCompareStore } from '../stores/compare'
import { chartOf } from '../annotate/model'
import { sampleLetters, triOf } from '../annotate/samples'
import { useViewStore } from '../stores/view'
import SampleDiagnose from './SampleDiagnose.vue'

const FOCUS_TIP = 'sample focused on entering compare (the vertical line is on its date); not selected'

const ann = useAnnotationStore()
const cmp = useCompareStore()
const view = useViewStore()
const smp = computed(() => cmp.focusedSample)
const letter = computed(() => {
  const s = smp.value
  const chart = s && ann.state ? chartOf(ann.state, view.symbol) : null
  return s && chart ? sampleLetters(chart, ann.currentPattern).get(s.id) ?? null : null
})
</script>

<style src="./annotationPanel.css"></style>
