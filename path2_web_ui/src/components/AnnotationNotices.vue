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
        <span class="key" title="the change in effect">later</span><span class="val">{{ c.later.machine }} {{ when(c.later.ts) }}</span>
        <span class="key" title="the change it did not see">earlier</span><span class="val">{{ c.earlier ? `${c.earlier.machine} ${when(c.earlier.ts)}` : '—' }}</span>
      </div>
    </div>
    <div v-if="links.problem" class="notice" data-testid="notice-url" :title="urlTip">
      <span class="key">url</span>
      <template v-if="links.problem.code === 'not_found'">
        <span class="key">sample</span><span class="key">{{ links.problem.sample }}</span>
      </template>
      <span class="val">{{ links.problem.code }}</span>
      <button type="button" class="ok" data-testid="notice-url-ok" @click="links.problem = null">ok</button>
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
 * - url:直达链接没跟成(样本编号不存在,或认不出的写法),一直显示到点 ok;
 * - save rejected:这次保存没通过后端的校验(比如另一台机器同步来的修改让这个框成了某个样本的成员框,
 *   改起止就越过了那个样本日)。每条原因写出 code 和它说的是哪个框、哪个样本(按重读后的状态),悬停看后端的原话;
 *   这次改动没有保存,一直显示到点 ok。
 */
import { computed } from 'vue'
import { useAnnotationStore } from '../stores/annotation'
import { useDirectLinkStore } from '../stores/directLinks'
import { findBox, findSample, type AnnConflict } from '../annotate/model'
import { sampleLetters, sampleTag } from '../annotate/samples'
import type { SaveProblem } from '../stores/annotation'

const ann = useAnnotationStore()
const links = useDirectLinkStore()
const fp = computed(() => ann.fingerprint)
const mismatch = computed(() => !!fp.value && !fp.value.consistent)
const shown = computed(() => mismatch.value || ann.newConflicts.length > 0 || !!ann.saveError || !!links.problem
  || ann.status === 'unavailable' || ann.status === 'load_failed')

const URL_FORMS = 'url forms: #symbol=<code>&date=<YYYY-MM-DD> or #sample=<sample id>'
const urlTip = computed(() => {
  const p = links.problem
  if (!p) return ''
  return p.code === 'not_found' ? `no sample with this id in the annotations\n${URL_FORMS}`
    : `unrecognized url: #${p.raw}\n${URL_FORMS}`
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
