<template>
  <header class="top-bar" data-testid="top-bar">
    <label class="grp">
      <span class="key">symbol</span>
      <input
        v-model="draft"
        class="symbol-input"
        data-testid="symbol-input"
        list="symbol-list"
        placeholder="code"
        spellcheck="false" autocomplete="off"
        title="输入代码回车打开(训练段副本里的股票,图画到 2025-12-31)"
        @input="status = null"
        @keydown.enter.prevent="onEnter"
        @keydown.up.stop
        @keydown.down.stop
      />
      <datalist id="symbol-list">
        <option v-for="s in symbols" :key="s" :value="s" />
      </datalist>
    </label>
    <span v-if="status" class="status" data-testid="symbol-status"
          title="训练段副本里没有这只股票(2026 年才上市的不在列表里)">{{ status }}</span>
  </header>
</template>

<script setup lang="ts">
/**
 * 主视图顶栏。现在只有 symbol:输入代码回车,不经扫描直接打开那只股票的图,落在 annotate。
 * 代码先对股票列表(训练段副本里有的股票)核一遍,不在列表里就报 not_found、不动当前的图。
 * 输入框平时显示当前打开的股票。
 */
import { computed, onMounted, ref, watch } from 'vue'
import { storeToRefs } from 'pinia'
import { getSymbols } from '../api'
import { useViewStore } from '../stores/view'
import { resolveSymbolInput } from '../annotate/symbolInput'

const view = useViewStore()
const { symbol } = storeToRefs(view)

const symbols = ref<string[] | null>(null)        // null:还没拿到或拿失败(此时交给后端判)
const symbolSet = computed(() => symbols.value ? new Set(symbols.value) : null)
const draft = ref(symbol.value ?? '')
const status = ref<'not_found' | null>(null)

watch(symbol, (s) => { draft.value = s ?? ''; status.value = null })

onMounted(async () => {
  try { symbols.value = await getSymbols() } catch { symbols.value = null }
})

function onEnter() {
  const r = resolveSymbolInput(draft.value, symbolSet.value)
  if (r.kind === 'empty') return
  if (r.kind === 'not_found') { status.value = 'not_found'; return }
  status.value = null
  draft.value = r.symbol
  view.openSymbol(r.symbol)
}
</script>

<style scoped>
.top-bar {
  display: flex; align-items: center; gap: 6px 16px; flex-wrap: wrap;
  padding: 4px 10px; background: #fafafa; border-bottom: 1px solid #d4d4d8; color: #111;
}
.grp { display: flex; align-items: center; gap: 6px; }
.key, .status { font-family: ui-monospace, "JetBrains Mono", "DejaVu Sans Mono", Consolas, monospace; font-size: 12px; color: #111; }
.status { padding: 0 6px; border: 1px solid #111; border-radius: 3px; }
.symbol-input {
  width: 110px; padding: 2px 6px; font-size: 13px; color: #111;
  border: 1px solid #a1a1aa; border-radius: 3px; background: #fff;
}
.symbol-input::placeholder { font-family: ui-monospace, "JetBrains Mono", "DejaVu Sans Mono", Consolas, monospace; font-size: 11px; color: #a1a1aa; }
</style>
