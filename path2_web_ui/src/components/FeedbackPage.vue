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
      <li v-for="g in groups" :key="g.key" class="fb-group" data-testid="feedback-group"
          :data-key="g.key" :data-places="g.rows.length">
        <div class="fb-ghead">
          <div class="ann-row">
            <span v-for="n in g.nodes" :key="n" class="ann-sym fb-node"
                  data-testid="feedback-row-node">{{ n }}</span>
            <span v-if="!g.nodes.length" class="ann-nil" data-testid="feedback-row-nodes-none"
                  title="not on any one node, or not said">none</span>
            <span class="ann-grow" />
            <span class="fb-counts">
              <span class="ann-k" data-testid="feedback-group-places"
                    title="places sharing this issue (same note and nodes)">places {{ g.rows.length }}</span>
              <span class="ann-k" data-testid="feedback-group-matched"
                    title="of them, places the app still buys (status matched)">matched {{ matchedOf(g) }}</span>
            </span>
          </div>
          <div v-if="g.note" class="ann-row">
            <span class="ann-biz" data-testid="feedback-row-note">{{ g.note }}</span>
          </div>
        </div>
        <div v-for="r in g.rows" :key="r.feedback.id"
             :class="['fb-row', 'ann-row', toneOf(r), { on: fb.selectedId === r.feedback.id }]"
             data-testid="feedback-row" :data-id="r.feedback.id" :data-tone="toneOf(r)"
             title="open this range in compare" @click="jump(r)">
          <span class="ann-sym" data-testid="feedback-row-symbol">{{ r.symbol }}</span>
          <span class="ann-sym" data-testid="feedback-row-range">{{ rangeText(r.feedback) }}</span>
          <span class="ann-grow" />
          <span :class="statusOf(r) ? 'ann-k' : 'ann-nil'" data-testid="feedback-row-status"
                :title="statusTip(r)">{{ statusOf(r) ?? 'null' }}</span>
          <span v-if="tagOf(r)" class="ann-k fb-tag" data-testid="feedback-row-tag"
                :title="tagHint(tagOf(r)!)">{{ tagOf(r) }}</span>
          <button type="button" class="ann-btn"
                  data-testid="feedback-row-edit" title="open this feedback's panel on the chart"
                  @click.stop="edit(r)">edit</button>
          <button type="button" class="ann-btn"
                  data-testid="feedback-row-delete" title="delete this place; the other places of the issue stay"
                  @click.stop="fb.remove(r.feedback.id)">delete</button>
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
 * - 按 issue 分组(几处反馈共享的同一份内容:note 与点出的 node;不和谁共享的一处也是一组,结构相同):
 *   组头第一行写点出的 node(一个都没点写灰字 none)、处数 places n、其中 app 还在买的处数 matched k
 *   (状态为 matched 的),第二行写理由(没写的没有这一行);组里每处一行。
 *   以前存下的记录上的 answer、dag 不显示;
 * - 排序(annotate/feedback.ts 的 sortIssueGroups):有朱红的组在前、其次有不买了却还挂着原因标签的,其余在后;
 *   同档的组、组内各处都按这三档,再按股票、日期;
 * - 每处一行:股票、日期范围、状态(后端状态接口给的 matched / unmatched;还没取到或读不到行情为 null,
 *   悬停写原因);颜色照接口给的 red:朱红底黑字 / 其余常色;
 *   接口给了会话原因标签 tag 的行照着挂(白底蓝描边,同 unmapped;挂不挂由后端判,悬停逐个取值写意思)——
 *   含 redefined:定义改过的那条 matched 了也不红,标签说明为什么不红;unmatched 而挂着标签的,是那一处
 *   不买了、但会话说原来的毛病还在;
 * - 页头:mapping 会话段有形状问题时一行 session ledger: <原因>(悬停写全);状态正在取时 loading;
 * - 点一行:在 compare 里打开那只股票,图窗包住那段日期,当前日竖线停在范围起点,选中那条(图上记号描黑粗边、
 *   另有一条贯穿主副图的竖带;落点见 stores/landing.ts);行上 edit 同样落过去,落下后在那条记号旁打开作答面板
 *   并预填(等同在图上点了那条记号:面板的锚点要图表算,所以落下后向 stores/feedback.ts 提 requestEdit,
 *   由 KlineChart.vue 接下);行上 delete 只删这一处,同一个 issue 的别的处不动。
 */
import { computed } from 'vue'
import { useAnnotationStore } from '../stores/annotation'
import { useAppLinkStore } from '../stores/appLink'
import { useFeedbackStore } from '../stores/feedback'
import { useLandingStore } from '../stores/landing'
import { sortIssueGroups, tagHint, type FeedbackRow, type IssueGroup } from '../annotate/feedback'
import { rangeLinkWindow } from '../annotate/directLinks'
import type { AnnFeedback } from '../annotate/model'
import { UNMAPPED_EDGE, VERMILION } from '../render/annotateLanes'

const ann = useAnnotationStore()
const appLink = useAppLinkStore()
const fb = useFeedbackStore()
const landing = useLandingStore()

// 样式里用的颜色(scoped style 的 v-bind)
const RED_BG = VERMILION
const TAG_EDGE = UNMAPPED_EDGE

const rows = computed(() => ann.feedbackOfPattern().filter(r => r.feedback.source === 'picked'))
const groups = computed(() => sortIssueGroups(rows.value, fb.statusById))
/** 这个 issue 的各处里 app 还在买的有几处(状态为 matched)。 */
const matchedOf = (g: IssueGroup) => g.rows.filter(r => st(r)?.status === 'matched').length
const sessionProblem = computed(() => appLink.mapping?.session_problem ?? null)

const st = (r: FeedbackRow) => fb.statusById[r.feedback.id]
/** 行的颜色档:red 朱红、plain 常色(状态还没取到的按常色)。 */
function toneOf(r: FeedbackRow): 'red' | 'plain' {
  return st(r)?.red ? 'red' : 'plain'
}
const statusOf = (r: FeedbackRow) => st(r)?.status ?? null
function statusTip(r: FeedbackRow): string {
  const s = st(r)
  if (!s) return 'status not read yet'
  return s.reason ?? 'status under the current app'
}
/** 会话原因标签:接口给了就挂(挂不挂后端已判过)。 */
const tagOf = (r: FeedbackRow): string | null => st(r)?.tag ?? null
const rangeText = (f: AnnFeedback) => (f.start === f.end ? f.start : `${f.start} – ${f.end}`)

function jump(r: FeedbackRow): void {
  const f = r.feedback
  fb.select(f.id)
  landing.land(r.symbol, rangeLinkWindow(f.start, f.end), f.start, () => fb.select(f.id))
}

/** edit:同 jump 落过去,落下后请图表在那条记号旁打开面板。 */
function edit(r: FeedbackRow): void {
  const f = r.feedback
  fb.select(f.id)
  landing.land(r.symbol, rangeLinkWindow(f.start, f.end), f.start, () => { fb.select(f.id); fb.requestEdit(f.id) })
}
</script>

<style src="./annotationPanel.css"></style>
<style scoped>
/* 字体与色值见 App.vue 的 :root 变量;文字一律黑,颜色只在行底、描边与标签描边上 */
.fb-head { margin: 0 0 6px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; cursor: help; }
.fb-list { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 4px; }
/* 一组 = 一个 issue:深色细框圈住,组头在上(白底)、各处一行在下 */
.fb-group {
  display: flex; flex-direction: column; gap: 3px; padding: 4px;
  border: 1px solid var(--line-strong); border-radius: 5px; background: #fff;
}
.fb-ghead { display: flex; flex-direction: column; gap: 2px; padding: 0 2px 2px; }
.fb-counts { display: inline-flex; gap: 8px; white-space: nowrap; }
.fb-row {
  padding: 2px 6px; cursor: pointer;
  border: 1px solid var(--line); border-radius: 4px; background: #fff; color: var(--ink);
}
.fb-row.red { background: v-bind(RED_BG); border-color: v-bind(RED_BG); }
.fb-row.on { outline: 2px solid var(--ink); outline-offset: -1px; }
.fb-tag { padding: 0 4px; border: 1.5px solid v-bind(TAG_EDGE); border-radius: 3px; background: #fff; cursor: help; }
.fb-node { padding: 0 3px; border: 1px solid var(--line-strong); border-radius: 3px; background: #fff; }
</style>
