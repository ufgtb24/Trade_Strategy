<template>
  <div v-if="shown" class="ann-notices" data-testid="annotation-notices">
    <div v-if="ann.status === 'unavailable' || ann.status === 'load_failed'" class="notice"
         data-testid="notice-annotations" :title="ann.loadError ?? ''">
      <span class="key">annotations</span><span class="val">{{ ann.status }}</span>
    </div>
    <div v-if="mismatch" class="notice" data-testid="notice-fingerprint" :title="fingerprintTip">
      <span class="key">data_fingerprint</span><span class="val">mismatched</span>
    </div>
    <div v-if="ann.newConflicts.length" class="notice block" data-testid="notice-conflict"
         title="both machines changed the same object before syncing; the later change is in effect">
      <div class="line">
        <span class="key">conflict</span><span class="val">×{{ ann.newConflicts.length }}</span>
        <button type="button" class="ok" data-testid="notice-conflict-ok" title="seen; do not show these again" @click="ann.ackConflicts()">ok</button>
      </div>
      <div v-for="c in ann.newConflicts" :key="c.later.ref" class="line">
        <span class="key">{{ c.kind }}</span>
        <span v-if="label(c)" class="biz">{{ label(c) }}</span>
        <span v-else-if="feedbackLabel(c)" class="val">{{ feedbackLabel(c) }}</span>
        <span class="key" title="the change in effect">later</span><span class="val">{{ c.later.machine }} {{ when(c.later.ts) }}</span>
        <span class="key" title="the change it did not see">earlier</span><span class="val">{{ c.earlier ? `${c.earlier.machine} ${when(c.earlier.ts)}` : '—' }}</span>
      </div>
    </div>
    <div v-if="links.problem" class="notice" data-testid="notice-url" :title="urlTip">
      <span class="key">url</span>
      <template v-if="links.problem.code === 'not_found'">
        <span class="key">{{ links.problem.kind }}</span>
        <span v-if="links.problem.kind === 'pattern'" class="biz">{{ links.problem.id }}</span>
        <span v-else class="key">{{ links.problem.id }}</span>
      </template>
      <template v-else-if="links.problem.code === 'compare_unavailable'">
        <span class="key">pattern</span><span class="biz">{{ links.problem.pattern }}</span>
      </template>
      <span class="val">{{ links.problem.code }}</span>
      <button type="button" class="ok" data-testid="notice-url-ok" @click="links.problem = null">ok</button>
    </div>
    <div v-if="deleted" class="notice" data-testid="notice-undo" :data-kind="deleted.kind" :title="UNDO_TIP">
      <span class="key">deleted</span><span class="val">{{ deleted.kind }}</span>
      <span v-if="deleted.feature" class="biz">{{ deleted.feature }}</span>
      <span class="key">{{ deleted.text }}</span>
      <span v-if="deleted.boxes" class="key" title="boxes deleted with it">+{{ deleted.boxes }} {{ deleted.boxes === 1 ? 'box' : 'boxes' }}</span>
      <button type="button" class="ok" data-testid="notice-undo-btn" title="put back what this delete removed"
              @click="ann.undoDeletion()">undo</button>
      <button type="button" class="ok" data-testid="notice-undo-ok" title="hide; this delete can no longer be undone"
              @click="ann.lastDeletion = null">ok</button>
    </div>
    <div v-if="ann.saveError" class="notice block" data-testid="notice-save">
      <div class="line">
        <span class="key">save</span><span class="val">rejected</span>
        <button type="button" class="ok" @click="ann.saveError = null">ok</button>
      </div>
      <div v-for="(r, i) in ann.saveError" :key="i" class="line" data-testid="notice-save-reason" :title="r.message">
        <span class="val">{{ r.code }}</span>
        <template v-if="boxOf(r)">
          <span class="key">box</span>
          <span v-if="boxOf(r)!.feature" class="biz">{{ ann.nameOf(boxOf(r)!.feature) }}</span>
          <span class="key">{{ boxOf(r)!.start }} – {{ boxOf(r)!.end }}</span>
        </template>
        <template v-if="sampleOf(r)">
          <span class="key">sample</span><span class="key">{{ sampleOf(r) }}</span>
        </template>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
/**
 * annotate 下图上方的提示条:
 * - 标注读不到(标注目录不在 / 读失败);
 * - data_fingerprint mismatched:标注是对着另一份训练段副本做的(或本机副本没有指纹)。只报出来,图照常显示;
 * - conflict:两台机器同步前改了同一个对象,后改的那次生效。每条冲突只提示一次,点 ok 后不再出现;
 * - url:直达链接没跟成(股票代码、样本编号或 pattern 不存在,认不出的写法,或要落在 compare 却用不了),
 *   一直显示到点 ok;
 * - save rejected:这次保存没通过后端的校验(比如另一台机器同步来的修改让这个框成了某个样本的成员框,
 *   改起止就越过了那个样本日)。每条原因写出 code 和它说的是哪个框、哪个样本(按重读后的状态),悬停看后端的原话;
 *   这次改动没有保存,一直显示到点 ok。
 * - deleted … undo:最近一次删框、删样本(连同一并删的框数)、删反馈,点 undo 放回(规则见 stores/annotation.ts
 *   的模块说明);再删一次换成新的,撤过、点 ok(放弃撤销)或刷新后消失。
 */
import { computed } from 'vue'
import { useAnnotationStore } from '../stores/annotation'
import { useDirectLinkStore } from '../stores/directLinks'
import { findBox, findFeedback, findSample, type AnnConflict } from '../annotate/model'
import { sampleLetters, sampleTag, triOf } from '../annotate/samples'
import type { SaveProblem } from '../stores/annotation'

const ann = useAnnotationStore()
const links = useDirectLinkStore()
const fp = computed(() => ann.fingerprint)
const mismatch = computed(() => !!fp.value && !fp.value.consistent)
const shown = computed(() => mismatch.value || ann.newConflicts.length > 0 || !!ann.saveError || !!links.problem
  || !!deleted.value || ann.status === 'unavailable' || ann.status === 'load_failed')

const UNDO_TIP = 'undo the last delete: puts the deleted objects back under their old ids; '
  + 'changes made since then are kept'
/** 最近一次删除写成一行:删的是什么(框带特征名)、股票与日期、一并删了几个框。 */
const deleted = computed(() => {
  const rec = ann.lastDeletion
  const head = rec?.removed[0]
  if (!rec || !head) return null
  const v = head.value
  const boxes = head.kind === 'sample' ? rec.removed.filter(x => x.kind === 'box').length : 0
  if (head.kind === 'sample') return { kind: 'sample', feature: null, text: `${v.symbol} ${triOf(v.judgment)} ${v.date}`, boxes }
  const feature = head.kind === 'box' && v.feature ? ann.nameOf(v.feature) : null
  return { kind: head.kind, feature, text: `${v.symbol} ${v.start} – ${v.end}`, boxes }
})

const URL_FORMS = 'url forms: #symbol=<code>&date=<YYYY-MM-DD>, '
  + '#symbol=<code>&date=<YYYY-MM-DD>&pattern=<pattern>&mode=compare, or #sample=<sample id>'
const urlTip = computed(() => {
  const p = links.problem
  if (!p) return ''
  if (p.code === 'bad_url') return `unrecognized url: #${p.raw}\n${URL_FORMS}`
  if (p.code === 'compare_unavailable') return `${p.reason}; opened in annotate instead`
  if (p.kind === 'pattern') return `no pattern with this name in the annotations; opened in annotate instead`
  return p.kind === 'sample' ? `no sample with this id in the annotations\n${URL_FORMS}`
    : `not in the training snapshot's symbols; the chart is unchanged\n${URL_FORMS}`
})

const short = (s: string | null) => (s ? `${s.slice(0, 12)}…` : 'none')
const fingerprintTip = computed(() => {
  const f = fp.value
  if (!f) return ''
  const rec = f.recorded.map(r => `${short(r.fingerprint)} (${r.batches} batches)`).join(', ')
  return `annotations were made on another training snapshot; the chart is shown as usual\n`
    + `local: ${short(f.local)}${f.local_error ? ` (${f.local_error})` : ''}\nrecorded: ${rec || 'none'}`
})

/** 时间戳 20261103T091000.000Z → 2026-11-03 09:10 */
function when(ts: string): string {
  const m = /^(\d{4})(\d{2})(\d{2})T(\d{2})(\d{2})/.exec(ts)
  return m ? `${m[1]}-${m[2]}-${m[3]} ${m[4]}:${m[5]}` : ts
}

/** 被拒原因里提到的框(后端在 box 键里给框编号)。 */
function boxOf(r: SaveProblem) {
  const id = r.box
  return typeof id === 'string' && ann.state ? findBox(ann.state, id)?.box ?? null : null
}

/** 被拒原因里提到的样本(sample 键),写成「a ▲ 2025-02-28」。 */
function sampleOf(r: SaveProblem): string | null {
  const id = r.sample
  const hit = typeof id === 'string' && ann.state ? findSample(ann.state, id) : null
  return hit ? sampleTag(hit.sample, sampleLetters(hit.chart, ann.currentPattern).get(hit.sample.id)) : null
}

function label(c: AnnConflict): string | null {
  if (c.kind === 'feature') return ann.nameOf(c.id)
  if (c.kind === 'pattern') return c.id
  return null
}

/** 冲突的是一条反馈:写成「股票 起 – 止」(按眼下的状态;已被删为 null)。 */
function feedbackLabel(c: AnnConflict): string | null {
  if (c.kind !== 'feedback' || !ann.state) return null
  const hit = findFeedback(ann.state, c.id)
  return hit ? `${hit.chart.symbol} ${hit.feedback.start} – ${hit.feedback.end}` : null
}
</script>

<style scoped>
/* 字体与色值见 App.vue 的 :root 变量;提示靠黑色粗边框醒目,不用颜色;特征名是用户的内容,加浅灰底 */
.ann-notices { display: flex; flex-wrap: wrap; gap: 6px; padding: 4px 8px; border-bottom: 1px solid var(--line); background: #fff; }
.notice {
  display: flex; align-items: center; gap: 6px; padding: 2px 8px;
  border: 1.5px solid var(--ink); border-radius: 4px; background: #fff; cursor: help;
}
.notice.block { flex-direction: column; align-items: flex-start; gap: 2px; }
.line { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; }
.key, .val, .ok { font-family: var(--mono); font-size: 12px; color: var(--ink); }
.val { font-weight: 700; }
.biz { font-size: 13px; color: var(--ink); background: var(--chip-bg); padding: 0 4px; border-radius: 3px; }
.ok { padding: 0 6px; border: 1px solid var(--ink); border-radius: 3px; background: #fff; cursor: pointer; }
</style>
