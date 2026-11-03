<template>
  <span v-if="name !== null" class="ann-biz">{{ name }}</span>
  <span v-else class="ann-sym">unnamed</span>
</template>

<script setup lang="ts">
/** 一个框在侧栏里的名字:特征名是用户写的内容(正常字体、浅灰底);还没起名的写等宽的 unnamed。 */
import { computed } from 'vue'
import { useAnnotationStore } from '../stores/annotation'
import type { AnnBox } from '../annotate/model'

const props = defineProps<{ box: AnnBox }>()
const ann = useAnnotationStore()
const name = computed(() => ann.nameOf(props.box.feature))
</script>

<style src="./annotationPanel.css"></style>
