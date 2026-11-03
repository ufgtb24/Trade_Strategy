<template>
  <div class="ann-blk feature-block" data-testid="feature-block" :data-feature="name">
    <div class="ann-row">
      <template v-if="parent">
        <span class="ann-biz" :title="ann.definitionOf(parent)">{{ ann.nameOf(parent) }}</span>
        <span class="ann-sym" data-testid="feature-kid-mark" :title="`“${name}” boxes nested in “${ann.nameOf(parent)}” boxes`">⊃</span>
      </template>
      <span class="ann-biz" data-testid="feature-name" :title="ann.definitionOf(block.feature)">{{ name }}</span>
      <span class="ann-grow" />
      <CountButton :samples="samples" :count-key="inKey" :tip="`has a “${name}” box / all samples`" />
    </div>
    <CountParts :samples="samples" :count-key="inKey"
                :tips="{ in: `has a “${name}” box`, not_in: `has no “${name}” box` }" />
    <template v-for="w in attrs" :key="w">
      <div class="ann-row attr" data-testid="feature-attr" :data-attr="ann.nameOf(w)">
        <span class="ann-biz" :title="ann.definitionOf(w)">{{ ann.nameOf(w) }}</span>
        <span class="ann-grow" />
        <CountButton :samples="samples" :count-key="attrKey(w)"
                   :tip="`“${ann.nameOf(w)}” true on a “${name}” box (any one counts) / has a “${name}” box`" />
      </div>
      <CountParts :samples="samples" :count-key="attrKey(w)"
                  :tips="{ true: `“${ann.nameOf(w)}” true on a “${name}” box`,
                           false: `“${ann.nameOf(w)}” false, none true`, null: `“${ann.nameOf(w)}” not judged` }" />
    </template>
    <FeatureBlockView v-for="k in block.kids" :key="k.feature" :block="k" :samples="samples" :parent="block.feature" />
  </div>
</template>

<script setup lang="ts">
/**
 * pattern 页 features 区的一块(决策票 15、spec 5.6):
 * - 特征名(用户的词:正常字体、浅灰底),悬停只放定义;右边是 in 计数;
 * - 这个特征的框判过的属性,一个一行:属性名(悬停只放定义)和 true 计数;
 * - 在这个特征的框里当过子框的特征,挂在这一块里面,写成「横盘 ⊃ 缩量」(开口朝着父块,和成员链、
 *   轨标题「缩量 ⊂ 横盘」同一个读向);
 * 每个计数点开后的几排紧跟在它那一行下面。
 */
import { computed } from 'vue'
import { useAnnotationStore } from '../stores/annotation'
import { attrsUsed, type CountKey, type FeatureBlock, type ChartSample } from '../annotate/grouping'
import CountButton from './CountButton.vue'
import CountParts from './CountParts.vue'

const props = defineProps<{ block: FeatureBlock; samples: readonly ChartSample[]; parent?: string | null }>()
const ann = useAnnotationStore()
const name = computed(() => ann.nameOf(props.block.feature) ?? props.block.feature)
const inKey = computed<CountKey>(() => ({ kind: 'in', feature: props.block.feature }))
const attrs = computed(() => attrsUsed(props.samples, props.block.feature))
const attrKey = (w: string): CountKey => ({ kind: 'attr', feature: props.block.feature, attr: w })
</script>

<style src="./annotationPanel.css"></style>
<style scoped>
.feature-block { display: flex; flex-direction: column; gap: 3px; margin: 0; }
.feature-block .feature-block { margin-top: 2px; }
.attr { padding-left: 12px; }
</style>
