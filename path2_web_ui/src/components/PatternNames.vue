<template>
  <span class="pattern-names"><template v-for="p in patterns" :key="p ?? ''"><span v-if="p !== null" class="chip">{{ p }}</span><span v-else class="key">unsorted</span></template></span>
</template>

<script setup lang="ts">
/**
 * 一串 pattern 名(找图清单的 patterns 一格、悬停浮层的一行):用户起的名字是业务内容,正常字体加浅灰底;
 * null 是没归 pattern 的样本,写程序的词 unsorted(等宽、不加底)。字体与色值见 App.vue 的 :root 变量。
 */
defineProps<{ patterns: readonly (string | null)[] }>()
</script>

<style scoped>
.pattern-names > * + * { margin-left: 4px; }
.chip { padding: 0 4px; border-radius: 2px; background: var(--chip-bg); }
.key { font-family: var(--mono); font-size: 12px; }
</style>
