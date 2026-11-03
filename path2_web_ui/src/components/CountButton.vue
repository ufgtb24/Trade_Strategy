<template>
  <button type="button" :class="['count-door', { on }]" data-testid="count-door" :data-key="id" :aria-pressed="on"
          :title="`${tip}; click to list these`" @click="ann.openCount = on ? null : id">{{ text }}</button>
</template>

<script setup lang="ts">
/**
 * 一个能点开的计数(决策票 15):samples 写 `pos n`,in 和属性写 `in pos k/N · neg m/M`、`true pos k/N · neg m/M`,
 * 0 也照写。点一下在它下面就地分排(CountParts),再点收起;同一页同时只点开一个(标注 store 的 openCount)。
 * 悬停只说这个数怎么数,不重复数字;neg 的数只说「挑的负样本里有几个」,不写成比率。
 */
import { computed } from 'vue'
import { useAnnotationStore } from '../stores/annotation'
import { countId, countText, type ChartSample, type CountKey } from '../annotate/grouping'

const props = defineProps<{ samples: readonly ChartSample[]; countKey: CountKey; tip: string }>()
const ann = useAnnotationStore()
const id = computed(() => countId(props.countKey))
const on = computed(() => ann.openCount === id.value)
const text = computed(() => countText(props.samples, props.countKey))
</script>

<style scoped>
/* 程序算出的计数:等宽、黑字;按下(点开着)靠黑边与下划线区分,不靠颜色 */
.count-door {
  font-family: var(--mono); font-size: 12px; color: var(--ink); line-height: 1.5; white-space: nowrap;
  padding: 0 4px; border: 1px solid var(--line-strong); border-radius: 3px; background: #fff; cursor: pointer;
}
.count-door.on { border-color: var(--ink); box-shadow: inset 0 -2px 0 var(--ink); }
</style>
