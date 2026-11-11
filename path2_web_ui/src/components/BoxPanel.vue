<template>
  <div v-if="sel" class="box-panel" data-testid="box-panel">
    <div v-if="cur" class="ann-blk cur" data-testid="current-sample">
      <button type="button" class="ann-btn on" data-testid="current-sample-button"
              title="current sample: boxes drawn now join it by default; click to return to it"
              @click="ann.selectSample(cur.sample.id)">{{ sampleTag(cur.sample, curLetter) }}</button>
      <MemberChain :sample="cur.sample" :chart="cur.chart" :editable="false" tid="current-sample-members" />
    </div>
    <div class="ann-hdr">
      <span class="ann-sym" data-testid="box-span" title="start – end; drag the box edges on its lane to change">{{ sel.box.start }} – {{ sel.box.end }}</span>
      <span class="ann-grow" />
      <button type="button" class="ann-btn" data-testid="box-delete" title="delete this box now (key: Delete)" @click="ann.deleteBox(sel.box.id)">delete</button>
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

      <template v-if="read">
        <span class="ann-k" title="compare: the part of the app that recognizes this feature (from the mapping)">node</span>
        <div class="ann-row" data-testid="box-node">
          <span class="ann-sym">⇣ {{ read.node }}</span>
          <span v-if="cmp.notes[read.node]" class="ann-biz">{{ cmp.notes[read.node] }}</span>
        </div>
      </template>

      <span class="ann-k" title="samples this box is a member box of; click to add / remove. Samples of other patterns are read-only">member_of</span>
      <div class="ann-row" data-testid="box-member-of">
        <button v-for="r in memberOf" :key="r.sample.id" type="button"
                :class="['ann-btn', { on: r.state === 'member', 'ann-off': !r.editable }]"
                :disabled="!r.editable" :data-testid="`member-of-${r.sample.id}`" :data-state="r.state"
                :title="MEMBER_OF_TIP[r.editable ? r.state : r.state === 'member' ? 'other' : r.state]"
                @click="ann.toggleMember(r.sample.id, sel.box.id)">
          {{ sampleTag(r.sample, letters.get(r.sample.id)) }}<span v-if="r.sample.pattern !== ann.currentPattern" :class="r.sample.pattern === null ? 'ann-sym pad' : 'ann-pat'">{{ r.sample.pattern ?? 'unsorted' }}</span>
        </button>
        <span v-if="!memberOf.length" class="ann-nil" title="no sample on or after its start yet">—</span>
      </div>

      <template v-if="pRows.length">
        <span class="ann-k" :title="PARENT_RULE">parent</span>
        <div class="parents" data-testid="box-parent">
          <div v-for="r in pRows" :key="r.other.id" class="ann-row">
            <button type="button" :class="['ann-btn', { on: r.on }]" data-testid="parent-toggle"
                    :title="parentTip(r)" @click="ann.toggleBoxParent(sel.box.id, r)">⊂</button>
            <span class="ann-sym" data-testid="parent-rel" :title="REL_TIP[r.rel]">{{ r.rel }}</span>
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
 * selection 页里选中一个框时的内容:起止、特征(起名或换特征)、定义、member_of、parent(框套框的 ⊂)、属性三态、note。
 * - 顶上:这张图上有当前样本时,一条它的成员链(只显示),点样本回到它;
 * - member_of:收了它的全部样本(别的 pattern 的变淡、只读)和当前 pattern 里能收它的样本,点一下收进或拿掉;
 *   框跨过样本日的那个样本变灰、点不了。删框前在这里看得见会波及哪些样本;
 * - 起名:词表里和输入有共同字的已有词排最前、加粗;回车用输入的名字(有同名的词就用它,没有就新起);
 * - 定义:这个词还没有定义时留一格写,写下就不再改(意思变了另起一个词);
 * - parent:它现在属于的框(⊂ 亮,点掉 = detach 或拿掉 attach),以及能手动挂上的交叠、更长的框(⊂ 灭,点上 = attach);
 *   每行 ⊂ 后面写一个词说明两个框在日期上的关系:contains(那个框把它整个包住,只有这种才默认属于)、
 *   overlaps(只重合一部分,要手动点上才属于);规则全文在 parent 这个键的悬停里。只列它范围里的框:
 *   它被样本收着时,只列和它同被一个样本收着的框(别的样本各自的框不列);没被收着时列整张图上的;
 * - 属性:列出同一特征的框用过的属性(全部图),默认 null;再点一下已按下的那个回到 null(这一行留着);
 *   在这个特征下画成过子框的词写成「⊂ 词」,不给 true 按钮(有就在框里画,画了这一行写 true);
 * - compare 下特征 map 到 app 的某个 node 时多一行 node:app 用哪一部分认这个特征(⇣ node 名 + mapping 里的说明)。
 *   不写 app 把这个框认到哪一档:那是找 app 错在哪一步用的,归会话看
 *   (stores/compare.ts 的 boxReads;框的左端不比)。
 */
import { computed, nextTick, ref, watch } from 'vue'
import { useAnnotationStore } from '../stores/annotation'
import { useCompareStore } from '../stores/compare'
import { useViewStore } from '../stores/view'
import {
  attrState, attrWordsOf, chartParents, featureUsage, kidWordsOf, parentRows, rankSuggestions, type ParentRow,
} from '../annotate/model'
import { memberOfRows, sampleLetters, sampleTag } from '../annotate/samples'
import DefinitionField from './DefinitionField.vue'
import MemberChain from './MemberChain.vue'

// parent 一行的规则(键的悬停)、每行那个词的意思、⊂ 点下去会怎样
const PARENT_RULE = 'which box this one belongs to (⊂ on = belongs, off = does not). '
  + 'scope: a box held by samples (member_of) only looks among boxes held by one of the same samples; a box held by no sample looks among all boxes on the chart. '
  + 'contains: the other box covers it entirely; it belongs to the shortest such box by default, click ⊂ off to say it just happens to lie inside. '
  + 'overlaps: the other box is longer and shares only some days with it; never automatic, click ⊂ on to attach by hand.'
const REL_TIP: Record<ParentRow['rel'], string> = {
  contains: 'this box lies entirely inside that one; belongs by default to the shortest box that contains it',
  overlaps: 'that box is longer and shares only some days with this one; belongs only if you click ⊂ on',
}
const PARENT_TIP: Record<ParentRow['via'], string> = {
  default: 'belongs by default (contained); click off = it just happens to lie inside',
  attach: 'attached by hand; click off = back to the default',
  detached: 'contained, but marked as not belonging; click on = belongs again',
  candidate: 'not attached; click on = it belongs to this box',
}
function parentTip(r: ParentRow): string {
  // 被两个以上的框包住时,默认只属于最短的那个,其余的也列成可挂的
  return r.via === 'candidate' && r.rel === 'contains'
    ? 'also contains it, but the default is the shortest containing box; click on = it belongs to this box instead'
    : PARENT_TIP[r.via]
}

const MEMBER_OF_TIP = {
  member: 'member box of this sample; click to remove',
  open: 'not a member box of this sample; click to add',
  crosses: 'crosses sample date: this box ends after the sample date, so it cannot be a member box',
  other: 'member box of a sample of another pattern; read-only (switch the pattern to edit)',
} as const

const ann = useAnnotationStore()
const sel = computed(() => ann.selectedBox)
const cmp = useCompareStore()
const view = useViewStore()
const read = computed(() => (sel.value ? cmp.boxReads.get(sel.value.box.id) ?? null : null))
// 这张图上的当前样本:画框时顶上一条它的成员链,看得见新画的框收没收进去
const cur = computed(() => (ann.currentSample && sel.value && ann.currentSample.chart.symbol === sel.value.chart.symbol
  ? ann.currentSample : null))
const letters = computed(() => sampleLetters(sel.value?.chart ?? null, ann.currentPattern))
const curLetter = computed(() => (cur.value ? letters.value.get(cur.value.sample.id) ?? null : null))
const memberOf = computed(() => (sel.value ? memberOfRows(sel.value.box, sel.value.chart, ann.currentPattern) : []))
const feature = computed(() => (sel.value?.box.feature ? ann.featureById.get(sel.value.box.feature) ?? null : null))
const picking = computed(() => !!sel.value && (!sel.value.box.feature || ann.renaming))
const days = computed(() => (sel.value ? ann.daysBySymbol[sel.value.chart.symbol] ?? [] : []))

const query = ref('')
const nameInput = ref<HTMLInputElement | null>(null)
const attrDraft = ref('')

const suggestions = computed(() => (ann.state
  ? rankSuggestions(query.value, ann.state.features, featureUsage(ann.state)) : []))

const pRows = computed(() => (sel.value
  ? parentRows(sel.value.box, sel.value.chart.boxes, sel.value.chart.samples, days.value) : []))
const parentsHere = computed(() => (sel.value
  ? chartParents(sel.value.chart.boxes, sel.value.chart.samples, days.value) : {}))
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
.cur { display: flex; flex-wrap: wrap; align-items: flex-start; gap: 6px; }
.pad { margin-left: 4px; }
.ann-pat { font-family: system-ui, sans-serif; font-size: 12px; margin-left: 4px; padding: 0 3px; background: var(--chip-bg); border-radius: 3px; }
.attr-input { width: 140px; }
</style>
