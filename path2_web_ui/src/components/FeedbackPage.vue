<template>
  <div class="feedback-page" data-testid="feedback-page">
    <div v-if="sessionProblem" class="fb-head" data-testid="feedback-session-problem" :title="sessionProblem">
      <span class="ann-k">session ledger:</span> <span class="ann-k">{{ sessionProblem }}</span>
    </div>
    <div v-if="fb.loading" class="fb-head" data-testid="feedback-loading">
      <span class="ann-k" title="reading each feedback's status under the current app">loading</span>
    </div>
    <div v-else-if="fb.error" class="fb-head" data-testid="feedback-status-error" :title="fb.error">
      <span class="ann-k">status</span> <span class="ann-k">load_failed</span>
    </div>
    <div v-else-if="fb.reason" class="fb-head" data-testid="feedback-no-app" :title="fb.reason">
      <span class="ann-k">app</span> <span class="ann-k">null</span>
    </div>
    <span v-if="!rows.length" class="ann-nil" data-testid="feedback-empty">empty</span>
    <ul v-else class="fb-list">
      <li v-for="r in rows" :key="r.feedback.id"
          :class="['fb-row', toneOf(r), { on: fb.selectedId === r.feedback.id }]"
          data-testid="feedback-row" :data-id="r.feedback.id" :data-tone="toneOf(r)"
          title="open this range in compare" @click="jump(r)">
        <div class="ann-row">
          <span class="ann-sym" data-testid="feedback-row-symbol">{{ r.symbol }}</span>
          <span class="ann-sym" data-testid="feedback-row-range">{{ rangeText(r.feedback) }}</span>
          <span class="ann-grow" />
          <span :class="statusOf(r) ? 'ann-k' : 'ann-nil'" data-testid="feedback-row-status"
                :title="statusTip(r)">{{ statusOf(r) ?? 'null' }}</span>
          <span v-if="tagOf(r)" class="ann-k fb-tag" data-testid="feedback-row-tag"
                title="reason the session gave for this feedback">{{ tagOf(r) }}</span>
          <button type="button" class="ann-btn"
                  data-testid="feedback-row-delete" title="delete this feedback"
                  @click.stop="fb.remove(r.feedback.id)">delete</button>
        </div>
        <div class="ann-row">
          <span class="ann-k" data-testid="feedback-row-answer">{{ r.feedback.answer }}</span>
          <span v-for="seg in r.feedback.segments ?? []" :key="seg" class="ann-sym fb-seg"
                data-testid="feedback-row-segment">{{ seg }}</span>
          <span v-if="r.feedback.note" class="ann-biz" data-testid="feedback-row-note">{{ r.feedback.note }}</span>
        </div>
      </li>
    </ul>
  </div>
</template>

<script setup lang="ts">
/**
 * 侧栏 feedback 页(spec 6.13,只在 compare 下有):当前 pattern 里用户自己挑的反馈(source = picked),跨股票,
 * 取自标注(含还没存完的)。盲看标记状态接口不算,不列(以后盲看进这一页时按来源分组另列)。
 *
 * - 排序:朱红在前、lost 其次、其余在后,同档按股票、日期(annotate/feedback.ts 的 sortFeedbackRows);
 * - 每行:股票、日期范围、状态(后端状态接口给的 matched / unmatched / lost;还没取到或读不到行情为 null,
 *   悬停写原因)、答案、分段、理由;颜色照接口给的 red 与 status:朱红底黑字 / lost 白底橙描边 / 其余常色;
 *   状态是 matched 或 lost 的行挂接口给的会话原因标签 tag(白底蓝描边,同 unmapped)——含 redefined:
 *   定义改过的那条 matched 了也不红,标签说明为什么不红;
 * - 页头:mapping 会话段有形状问题时一行 session ledger: <原因>(悬停写全);状态正在取时 loading;
 * - 点一行:在 compare 里打开那只股票,图窗包住那段日期,当前日竖线停在范围起点,选中那条(图上记号加粗;
 *   落点见 stores/landing.ts);行上 delete 删掉它。
 */
import { computed } from 'vue'
import { useAnnotationStore } from '../stores/annotation'
import { useAppLinkStore } from '../stores/appLink'
import { useFeedbackStore } from '../stores/feedback'
import { useLandingStore } from '../stores/landing'
import { sortFeedbackRows, type FeedbackRow } from '../annotate/feedback'
import { rangeLinkWindow } from '../annotate/directLinks'
import type { AnnFeedback } from '../annotate/model'
import { MISSING_EDGE, UNMAPPED_EDGE, VERMILION } from '../render/annotateLanes'

const ann = useAnnotationStore()
const appLink = useAppLinkStore()
const fb = useFeedbackStore()
const landing = useLandingStore()

// 样式里用的颜色(scoped style 的 v-bind)
const RED_BG = VERMILION
const LOST_EDGE = MISSING_EDGE
const TAG_EDGE = UNMAPPED_EDGE

const rows = computed(() => sortFeedbackRows(ann.feedbackOfPattern().filter(r => r.feedback.source === 'picked'),
                                             fb.statusById))
const sessionProblem = computed(() => appLink.mapping?.session_problem ?? null)

const st = (r: FeedbackRow) => fb.statusById[r.feedback.id]
/** 行的颜色档:red 朱红、lost 白底橙描边、plain 常色(状态还没取到的按常色)。 */
function toneOf(r: FeedbackRow): 'red' | 'lost' | 'plain' {
  const s = st(r)
  return s?.red ? 'red' : s?.status === 'lost' ? 'lost' : 'plain'
}
const statusOf = (r: FeedbackRow) => st(r)?.status ?? null
function statusTip(r: FeedbackRow): string {
  const s = st(r)
  if (!s) return 'status not read yet'
  return s.reason ?? 'status under the current app'
}
/** 会话原因标签:只挂在状态是 matched 或 lost 的行上(不看 red:挂了 redefined 的 matched 不红,照样挂)。 */
function tagOf(r: FeedbackRow): string | null {
  const s = st(r)
  return s?.status === 'matched' || s?.status === 'lost' ? s.tag ?? null : null
}
const rangeText = (f: AnnFeedback) => (f.start === f.end ? f.start : `${f.start} – ${f.end}`)

function jump(r: FeedbackRow): void {
  const f = r.feedback
  fb.select(f.id)
  landing.land(r.symbol, rangeLinkWindow(f.start, f.end), f.start, () => fb.select(f.id))
}
</script>

<style src="./annotationPanel.css"></style>
<style scoped>
/* 字体与色值见 App.vue 的 :root 变量;文字一律黑,颜色只在行底、描边与标签描边上 */
.fb-head { margin: 0 0 6px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; cursor: help; }
.fb-list { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 4px; }
.fb-row {
  display: flex; flex-direction: column; gap: 2px; padding: 3px 6px; cursor: pointer;
  border: 1px solid var(--line); border-radius: 4px; background: #fff; color: var(--ink);
}
.fb-row.red { background: v-bind(RED_BG); border-color: v-bind(RED_BG); }
.fb-row.lost { border: 3px solid v-bind(LOST_EDGE); }
.fb-row.on { outline: 2px solid var(--ink); outline-offset: -1px; }
.fb-tag { padding: 0 4px; border: 1.5px solid v-bind(TAG_EDGE); border-radius: 3px; background: #fff; cursor: help; }
.fb-seg { padding: 0 3px; border: 1px solid var(--line-strong); border-radius: 3px; background: #fff; }
</style>
