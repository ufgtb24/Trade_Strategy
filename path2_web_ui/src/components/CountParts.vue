<template>
  <div v-if="ann.openCount === id" class="count-parts" data-testid="count-parts" :data-key="id">
    <div v-for="p in parts" :key="p.label" class="part" data-testid="count-part" :data-label="p.label">
      <span class="ann-sym head" data-testid="part-head" :title="tips[p.label] ?? ''">
        <span :class="p.label === 'null' ? 'ann-nil' : ''">{{ p.label }}</span>{{ partCount(countKey, p) }}
      </span>
      <div v-if="p.samples.length" class="ann-row cards">
        <SampleCard v-for="x in p.samples" :key="x.sample.id" :x="x" />
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
/**
 * 一个计数点开后的几排(决策票 15):每排写排头(这一排的名字 + 个数,如 `in pos 2 · neg 0`;samples 那排写 `pos 3`),
 * 下面是这一排的样本卡;各排之和等于分母,空的排也写排头、不带卡。只在这个计数点开着时显示。
 * 名字是 null 的那排(属性没判过)用灰字:它是空着的状态。
 */
import { computed } from 'vue'
import { useAnnotationStore } from '../stores/annotation'
import { countId, countParts, partCount, type ChartSample, type CountKey, type Part } from '../annotate/grouping'
import SampleCard from './SampleCard.vue'

const props = defineProps<{ samples: readonly ChartSample[]; countKey: CountKey; tips: Partial<Record<Part['label'], string>> }>()
const ann = useAnnotationStore()
const id = computed(() => countId(props.countKey))
const parts = computed(() => countParts(props.samples, props.countKey))
</script>

<style src="./annotationPanel.css"></style>
<style scoped>
/* 点开的几排挂在点它的那一行下面:缩进 + 左边一道竖线 */
.count-parts {
  grid-column: 1 / -1; display: flex; flex-direction: column; gap: 4px;
  margin: 2px 0 4px 6px; padding-left: 8px; border-left: 2px solid var(--line-strong);
}
.part { display: flex; flex-direction: column; gap: 2px; }
.cards { gap: 3px; }
</style>
