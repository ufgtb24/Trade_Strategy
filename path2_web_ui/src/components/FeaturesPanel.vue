<template>
  <div class="features-panel" data-testid="features-panel">
    <span v-if="!features.length" class="ann-nil">empty</span>
    <div v-for="f in features" :key="f.id" class="ann-blk" :data-testid="`feature-${f.name}`">
      <div class="ann-row">
        <template v-if="editing === f.id">
          <input ref="renameInput" v-model="renameDraft" class="ann-input" data-testid="rename-input"
                 spellcheck="false" autocomplete="off"
                 @keydown.enter.prevent="saveRename(f.id)" @keydown.esc.prevent="editing = null" />
          <button type="button" class="ann-btn" @click="saveRename(f.id)">ok</button>
          <span v-if="renameStatus" class="ann-sym status" data-testid="rename-status"
                title="another feature already has this name; use merge to combine them">{{ renameStatus }}</span>
        </template>
        <template v-else>
          <b class="ann-biz">{{ f.name }}</b>
          <button type="button" class="ann-btn" data-testid="rename" title="rename this feature in all charts" @click="startRename(f)">✎</button>
        </template>
        <select class="ann-btn merge-pick" data-testid="merge-select" title="merge this feature into another: preview first, then merge"
                :value="pending?.from === f.id ? pending.into : ''" @change="pickMerge(f.id, $event)">
          <option value="">merge</option>
          <option v-for="o in features.filter(x => x.id !== f.id)" :key="o.id" :value="o.id">{{ o.name }}</option>
        </select>
        <span class="ann-grow" />
        <span class="ann-sym" data-testid="usage" title="boxes using it as feature / as attr (judged true or false); across all charts and patterns">box×{{ usage.get(f.id)?.box ?? 0 }} · attr×{{ usage.get(f.id)?.attr ?? 0 }}</span>
      </div>
      <div class="ann-kv def"><DefinitionField :feature="f" /></div>
      <div v-if="pending?.from === f.id && plan" class="ann-row line" data-testid="merge-preview">
        <span class="ann-biz">{{ f.name }}</span><span class="ann-sym">→</span><span class="ann-biz">{{ ann.nameOf(pending.into) }}</span>
        <span class="ann-sym" title="boxes that will change: as feature / as attr">box×{{ plan.box }} · attr×{{ plan.attr }}</span>
        <span class="ann-grow" />
        <button type="button" class="ann-btn" data-testid="merge-apply" title="apply everywhere; unmerge to undo" @click="ann.applyMerge(f.id, pending.into)">merge</button>
        <button type="button" class="ann-btn" @click="ann.pendingMerge = null">cancel</button>
      </div>
      <template v-for="(m, i) in ann.merges" :key="`m-${i}`">
        <div v-if="m.into === f.id" class="ann-row line" :data-testid="`merged-${m.from.name}`">
          <span class="ann-biz">{{ m.from.name }}</span><span class="ann-sym">→</span><span class="ann-biz">{{ f.name }}</span>
          <span class="ann-sym" title="boxes changed by the merge: as feature / as attr">box×{{ m.box }} · attr×{{ m.attr }}</span>
          <span class="ann-grow" />
          <button type="button" class="ann-btn" data-testid="unmerge" title="split back: the word returns and the changed boxes revert" @click="ann.unmerge(i)">unmerge</button>
        </div>
      </template>
    </div>
  </div>
</template>

<script setup lang="ts">
/**
 * features 页:整张词表。每个词一块:
 * - ✎ 改名(改一处,所有用到它的框跟着变;和别的词重名不改,报 name_taken);
 * - merge 选一个目标词,先预览会改多少个框,点 merge 才改;合并后目标词下面一行可以 unmerge(合并记在标注文件里,
 *   刷新、换机器后照样能拆回,直到拆回为止);
 * - box×n · attr×m:跨全部图、全部 pattern 的用量;
 * - 定义:还空着时留一格写,写下就不再改。
 */
import { computed, nextTick, ref } from 'vue'
import { useAnnotationStore } from '../stores/annotation'
import { featureUsage, type AnnFeature } from '../annotate/model'
import DefinitionField from './DefinitionField.vue'

const ann = useAnnotationStore()
const features = computed(() => ann.state?.features ?? [])
const usage = computed(() => (ann.state ? featureUsage(ann.state) : new Map()))
const pending = computed(() => ann.pendingMerge)
const plan = computed(() => (pending.value ? ann.previewMerge(pending.value.from, pending.value.into) : null))

const editing = ref<string | null>(null)
const renameDraft = ref('')
const renameStatus = ref<'name_taken' | null>(null)
const renameInput = ref<HTMLInputElement[] | null>(null)

async function startRename(f: AnnFeature) {
  editing.value = f.id
  renameDraft.value = f.name
  renameStatus.value = null
  await nextTick()
  renameInput.value?.[0]?.focus()
}

function saveRename(fid: string) {
  const r = ann.renameFeature(fid, renameDraft.value)
  if (r === 'name_taken') { renameStatus.value = 'name_taken'; return }
  editing.value = null
}

function pickMerge(from: string, e: Event) {
  const into = (e.target as HTMLSelectElement).value
  ann.pendingMerge = into ? { from, into } : null
}
</script>

<style src="./annotationPanel.css"></style>
<style scoped>
.features-panel { display: flex; flex-direction: column; }
.merge-pick { padding: 0 2px; }
.def { margin-top: 4px; }
.line { margin-top: 4px; }
.status { padding: 0 4px; border: 1px solid var(--ink); border-radius: 3px; }
</style>
