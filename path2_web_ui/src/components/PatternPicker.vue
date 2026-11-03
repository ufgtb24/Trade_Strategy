<template>
  <div ref="root" class="pattern-picker" :data-testid="tid">
    <button type="button" class="cur" :data-testid="`${tid}-button`" :aria-expanded="open"
            :title="pending ? 'pick the pattern it looks like' : title" @click="toggle">
      <span v-if="pending" class="nil">pattern?</span>
      <span v-else-if="value === null" class="sym">unsorted</span>
      <span v-else class="biz">{{ value }}</span>
      <span class="sym caret">▾</span>
    </button>
    <div v-if="open" class="menu" :data-testid="`${tid}-menu`">
      <button v-for="p in names" :key="p" type="button" :class="['opt', { on: p === value }]"
              :data-testid="`${tid}-option`" :data-name="p" @click="pick(p)"><span class="biz">{{ p }}</span></button>
      <button type="button" :class="['opt', { on: value === null && !pending }]" :data-testid="`${tid}-unsorted`"
              title="unsorted: pattern not chosen yet; n = unsorted samples on all charts" @click="pick(null)">
        <span class="sym">unsorted · {{ unsorted }}</span>
      </button>
      <div v-if="adding" class="opt">
        <input ref="input" v-model="draft" class="ann-input" :data-testid="`${tid}-new-input`"
               spellcheck="false" autocomplete="off"
               @keydown.enter.prevent="addNew" @keydown.esc.stop.prevent="adding = false" />
      </div>
      <button v-else type="button" class="opt" :data-testid="`${tid}-new`" title="new pattern" @click="startAdd">
        <span class="sym">+ new</span>
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
/**
 * 选 pattern 的下拉:顶栏的当前 pattern 和样本页的 pattern 一格共用。
 * - 列出已有的 pattern(名字是用户写的内容:正常字体、浅灰底)、unsorted · n(全部图上 unsorted 的样本数)、+ new;
 * - + new 变成一个输入框,回车用这个名字(已有同名的就是选它);
 * - pending:负样本挂在 unsorted 时显示灰字 pattern?(它的「像」还没有对象,算没填完)。
 * 选中后发出 pick(名字,unsorted 为 null)。
 */
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import { useAnnotationStore } from '../stores/annotation'
import { unsortedCount } from '../annotate/samples'

const props = defineProps<{ value: string | null; tid: string; title: string; pending?: boolean }>()
const emit = defineEmits<{ pick: [name: string | null] }>()

const ann = useAnnotationStore()
const names = computed(() => (ann.state?.patterns ?? []).map(p => p.name))
const unsorted = computed(() => (ann.state ? unsortedCount(ann.state.charts) : 0))

const root = ref<HTMLElement | null>(null)
const input = ref<HTMLInputElement | null>(null)
const open = ref(false)
const adding = ref(false)
const draft = ref('')

function toggle() {
  open.value = !open.value
  adding.value = false
}

function pick(name: string | null) {
  open.value = false
  adding.value = false
  if (name !== props.value || props.pending) emit('pick', name)
}

async function startAdd() {
  adding.value = true
  draft.value = ''
  await nextTick()
  input.value?.focus()
}

function addNew() {
  const t = draft.value.trim()
  if (t) pick(t)
}

function onDocDown(e: MouseEvent) {
  if (open.value && root.value && !root.value.contains(e.target as Node)) { open.value = false; adding.value = false }
}
onMounted(() => document.addEventListener('mousedown', onDocDown, true))
onBeforeUnmount(() => document.removeEventListener('mousedown', onDocDown, true))
</script>

<style src="./annotationPanel.css"></style>
<style scoped>
/* 字体与色值见 App.vue 的 :root 变量;程序固定文字等宽,pattern 名是用户的内容(正常字体、浅灰底) */
.pattern-picker { position: relative; display: inline-block; }
.cur {
  display: inline-flex; align-items: center; gap: 4px; padding: 1px 6px;
  border: 1px solid var(--line-strong); border-radius: 3px; background: #fff; cursor: pointer;
}
.sym, .nil { font-family: var(--mono); font-size: 12px; color: var(--ink); }
.nil { color: var(--ink-empty); }
.caret { font-size: 10px; }
.biz { font-size: 13px; color: var(--ink); background: var(--chip-bg); padding: 0 4px; border-radius: 3px; }
.menu {
  position: absolute; top: 100%; left: 0; z-index: 60; margin-top: 2px; min-width: 140px;
  display: flex; flex-direction: column; gap: 2px; padding: 4px;
  background: #fff; border: 1px solid var(--ink); border-radius: 4px;
}
.opt {
  display: flex; align-items: center; padding: 1px 4px; border: 1px solid transparent; border-radius: 3px;
  background: #fff; cursor: pointer; text-align: left;
}
.opt.on { border-color: var(--ink); }
.opt:hover { border-color: var(--line-strong); }
.opt .ann-input { width: 130px; }
</style>
