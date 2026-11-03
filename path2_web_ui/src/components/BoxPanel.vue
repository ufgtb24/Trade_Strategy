<template>
  <div v-if="sel" class="box-panel" data-testid="box-panel">
    <div class="ann-hdr">
      <span class="ann-sym" data-testid="box-span" title="start – end; drag the box edges on its lane to change">{{ sel.box.start }} – {{ sel.box.end }}</span>
      <span class="ann-grow" />
      <button type="button" class="ann-btn" data-testid="box-delete" title="delete this box now" @click="ann.deleteBox(sel.box.id)">delete</button>
    </div>
    <div class="ann-kv">
      <span class="ann-k" title="the feature this box marks">feature</span>
      <div v-if="picking" class="picker">
        <div class="ann-row" data-testid="feature-suggestions">
          <button v-for="s in suggestions" :key="s.feature.id" type="button"
                  :class="['ann-btn', 'word', { near: s.near }]"
                  :data-testid="`suggest-${s.feature.name}`"
                  :title="s.feature.definition ? `definition: ${s.feature.definition}` : 'no definition yet'"
                  @click="ann.setBoxFeature(sel.box.id, { id: s.feature.id })">{{ s.feature.name }}</button>
        </div>
        <div class="ann-row">
          <input ref="nameInput" v-model="query" class="ann-input" data-testid="feature-input"
                 spellcheck="false" autocomplete="off" @keydown.enter.prevent="pickTyped" />
          <button type="button" class="ann-btn" title="use this name (an existing feature with the same name is reused)" @click="pickTyped">+</button>
          <button v-if="sel.box.feature" type="button" class="ann-btn" @click="ann.renaming = false">cancel</button>
        </div>
      </div>
      <div v-else class="ann-row">
        <b class="ann-biz" data-testid="box-feature">{{ feature?.name }}</b>
        <button type="button" class="ann-btn" data-testid="box-change-feature" title="change the feature of this box" @click="ann.renaming = true">⇄</button>
      </div>

      <DefinitionField v-if="feature && !picking" :feature="feature" />

      <template v-if="pRows.length">
        <span class="ann-k" title="the box it belongs to (⊂ on), or boxes it could belong to (⊂ off)">parent</span>
        <div class="parents" data-testid="box-parent">
          <div v-for="r in pRows" :key="r.other.id" class="ann-row">
            <button type="button" :class="['ann-btn', { on: r.on }]" data-testid="parent-toggle"
                    :title="PARENT_TIP[r.via]" @click="ann.toggleBoxParent(sel.box.id, r)">⊂</button>
            <span :class="{ 'ann-off': !r.on }">
              <span v-if="r.other.feature" class="ann-biz">{{ ann.nameOf(r.other.feature) }}</span>
              <span v-else class="ann-sym">unnamed</span>
              <span class="ann-sym"> {{ r.other.start }} – {{ r.other.end }}</span>
            </span>
          </div>
        </div>
      </template>

      <template v-if="feature && !picking">
        <span class="ann-k" title="true: has · false: lacks · null: not judged yet. Judge only by what is visible on or before the sample date">attrs</span>
        <div class="attrs" data-testid="box-attrs">
          <div v-for="w in kidWords" :key="`kid-${w}`" class="ann-row" :data-testid="`kid-${ann.nameOf(w)}`">
            <span class="ann-sym" :title="`“${ann.nameOf(w)}” is drawn as a child box under this feature: if present, draw it inside`">⊂</span>
            <span class="ann-biz">{{ ann.nameOf(w) }}</span>
            <span v-if="hasChild(w)" class="ann-sym" title="a child box with this feature is drawn inside">true</span>
            <template v-else>
              <button type="button" :class="['ann-btn', { on: state(w) === 'false' }]"
                      title="lacks; click again = back to null" @click="ann.setAttr(sel.box.id, w, false)">false</button>
              <span v-if="state(w) === 'null'" class="ann-nil" title="not judged yet">null</span>
            </template>
          </div>
          <div v-for="w in attrWords" :key="w" class="ann-row" :data-testid="`attr-${ann.nameOf(w)}`">
            <span class="ann-biz">{{ ann.nameOf(w) }}</span>
            <button type="button" :class="['ann-btn', { on: state(w) === 'true' }]" :data-testid="`attr-true-${ann.nameOf(w)}`"
                    title="has; click again = back to null" @click="ann.setAttr(sel.box.id, w, true)">true</button>
            <button type="button" :class="['ann-btn', { on: state(w) === 'false' }]" :data-testid="`attr-false-${ann.nameOf(w)}`"
                    title="lacks; click again = back to null" @click="ann.setAttr(sel.box.id, w, false)">false</button>
            <span v-if="state(w) === 'null'" class="ann-nil" :data-testid="`attr-null-${ann.nameOf(w)}`" title="not judged yet">null</span>
          </div>
          <div class="ann-row">
            <input v-model="attrDraft" class="ann-input attr-input" list="ann-attr-words" data-testid="attr-input"
                   spellcheck="false" autocomplete="off" @keydown.enter.prevent="addAttr" />
            <button type="button" class="ann-btn" title="add an attribute (a word from the vocabulary, or a new one); starts as true" @click="addAttr">+ attr</button>
            <datalist id="ann-attr-words">
              <option v-for="f in ann.state?.features ?? []" :key="f.id" :value="f.name" />
            </datalist>
          </div>
        </div>
      </template>

      <span class="ann-k" title="note on this box">note</span>
      <input :key="sel.box.id" class="ann-input" data-testid="box-note" :value="sel.box.note ?? ''"
             @change="ann.setBoxNote(sel.box.id, ($event.target as HTMLInputElement).value)" />
    </div>
  </div>
</template>

<script setup lang="ts">
/**
 * selection 页里选中一个框时的内容:起止、特征(起名或换特征)、定义、parent(框套框的 ⊂)、属性三态、note。
 * - 起名:词表里和输入有共同字的已有词排最前、加粗;回车用输入的名字(有同名的词就用它,没有就新起);
 * - 定义:这个词还没有定义时留一格写,写下就不再改(意思变了另起一个词);
 * - parent:它现在属于的框(⊂ 亮,点掉 = detach 或拿掉 attach),以及能手动挂上的交叠、更长的框(⊂ 灭,点上 = attach);
 * - 属性:列出同一特征的框用过的属性(全部图),默认 null;再点一下已按下的那个回到 null(这一行留着);
 *   在这个特征下画成过子框的词写成「⊂ 词」,不给 true 按钮(有就在框里画,画了这一行写 true)。
 */
import { computed, nextTick, ref, watch } from 'vue'
import { useAnnotationStore } from '../stores/annotation'
import {
  attrState, attrWordsOf, chartParents, featureUsage, kidWordsOf, parentRows, rankSuggestions, type ParentRow,
} from '../annotate/model'
import DefinitionField from './DefinitionField.vue'

const PARENT_TIP: Record<ParentRow['via'], string> = {
  default: 'enclosed by this box, so it belongs to it by default; click off = it just happens to lie inside',
  attach: 'attached by hand to this longer overlapping box; click off = back to the default',
  detached: 'enclosed by this box but marked as not belonging; click on = belongs again',
  candidate: 'longer box overlapping it; click on = it belongs to this box',
}

const ann = useAnnotationStore()
const sel = computed(() => ann.selectedBox)
const feature = computed(() => (sel.value?.box.feature ? ann.featureById.get(sel.value.box.feature) ?? null : null))
const picking = computed(() => !!sel.value && (!sel.value.box.feature || ann.renaming))
const days = computed(() => (sel.value ? ann.daysBySymbol[sel.value.chart.symbol] ?? [] : []))

const query = ref('')
const nameInput = ref<HTMLInputElement | null>(null)
const attrDraft = ref('')

const suggestions = computed(() => (ann.state
  ? rankSuggestions(query.value, ann.state.features, featureUsage(ann.state)) : []))

const pRows = computed(() => (sel.value ? parentRows(sel.value.box, sel.value.chart.boxes, days.value) : []))
const parentsHere = computed(() => (sel.value ? chartParents(sel.value.chart.boxes, days.value) : {}))
const kidWords = computed(() => (feature.value && ann.state
  ? kidWordsOf(feature.value.id, ann.state.charts, s => ann.daysBySymbol[s] ?? null) : []))

// 选中这个框期间列出过的属性一直留着:点回 null 后,即使没有别的框用它,这一行也不消失
const seenAttrs = ref<{ key: string; words: string[] }>({ key: '', words: [] })
const seenKey = computed(() => `${sel.value?.box.id}|${feature.value?.id}`)
const attrWords = computed(() => {
  if (!feature.value || !ann.state || !sel.value) return []
  const ws = seenAttrs.value.key === seenKey.value ? [...seenAttrs.value.words] : []
  for (const k of [...attrWordsOf(feature.value.id, ann.state.charts), ...Object.keys(sel.value.box.attrs ?? {})]) {
    if (!ws.includes(k)) ws.push(k)
  }
  return ws.filter(w => !kidWords.value.includes(w) && ann.featureById.has(w))
})
watch(attrWords, (ws) => {
  const cur = seenAttrs.value
  if (cur.key !== seenKey.value || ws.some(w => !cur.words.includes(w))) seenAttrs.value = { key: seenKey.value, words: ws }
})

const state = (w: string) => attrState(sel.value!.box, w)
const hasChild = (w: string) =>
  !!sel.value && sel.value.chart.boxes.some(c => c.feature === w && parentsHere.value[c.id] === sel.value!.box.id)

function pickTyped() {
  if (!sel.value || !query.value.trim()) return
  ann.setBoxFeature(sel.value.box.id, { name: query.value })
  query.value = ''
}

function addAttr() {
  if (!sel.value || !attrDraft.value.trim()) return
  ann.addAttr(sel.value.box.id, attrDraft.value)
  attrDraft.value = ''
}

// 换了选中的框就清空起名框;刚画的框(还没起名)把光标放进起名框
watch(() => sel.value?.box.id, () => { query.value = ''; attrDraft.value = '' })
watch(() => [ann.nameFocus, picking.value], async () => {
  if (!picking.value) return
  await nextTick()
  nameInput.value?.focus()
}, { immediate: true })
</script>

<style src="./annotationPanel.css"></style>
<style scoped>
.picker, .attrs, .parents { display: flex; flex-direction: column; gap: 4px; min-width: 0; }
.attr-input { width: 140px; }
</style>
