<template>
  <span class="ann-k" :title="TIP">definition</span>
  <span v-if="feature.definition" class="ann-biz" data-testid="definition-text">{{ feature.definition }}</span>
  <textarea v-else class="ann-area" data-testid="definition-input" rows="2"
            placeholder="fixed once written" :title="INPUT_TIP"
            @keydown.enter.exact.prevent="($event.target as HTMLTextAreaElement).blur()"
            @blur="ann.setDefinition(feature.id, ($event.target as HTMLTextAreaElement).value)" />
</template>

<script setup lang="ts">
/**
 * 一个词的定义(放在 .ann-kv 两列网格里,占一行):还空着时留一格写,回车或离开就存;写下就只显示、不再改
 * (定义定下就不改,意思变了另起一个词)。selection 页和 features 页共用。
 * 写之前就提示(spec 6.14 G3):空格子里灰字占位 fixed once written,悬停写意思变了怎么办。
 */
import { useAnnotationStore } from '../stores/annotation'
import type { AnnFeature } from '../annotate/model'

defineProps<{ feature: AnnFeature }>()
const TIP = 'what it is; shared across charts. Fixed once written: if the meaning changes, start a new feature'
const INPUT_TIP = 'fixed once written; if the meaning changes, start a new feature'
const ann = useAnnotationStore()
</script>

<style scoped>
/* 占位提示是程序固定文字:等宽;灰字只留给空着的状态 */
.ann-area::placeholder { font-family: var(--mono); font-size: 12px; color: var(--ink-empty); }
</style>
