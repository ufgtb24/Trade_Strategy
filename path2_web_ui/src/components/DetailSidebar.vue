<template>
  <div ref="sidebarEl" class="sidebar">
    <div class="panel-name">DetailSidebar</div>

    <!-- 入口 A(brush 时段查询)/ 入口 D(shift+click pair 查询):query 结果卡片,叠在其余
         内容之上、互斥展示(activeDetailCard 单值)。caveats 顶部条挂在各自 response 上。 -->
    <div v-if="activeDetailCard === 'time' && timeScopeResponse" class="detail-query-card">
      <button type="button" class="close-query-btn" title="关闭" @click="closeDetailCard">×</button>
      <div v-if="timeScopeResponse.caveats.length" class="caveats-top">
        <div v-for="c in timeScopeResponse.caveats" :key="c.code" class="caveat">⚠ {{ c.message }}</div>
      </div>
      <FailedAttemptsCard
        :payload="timeScopeResponse.payload"
        :event-class="view.currentTimeEventClass"
        @update:event-class="onTimeEventClassChange"
      />
    </div>
    <div v-else-if="activeDetailCard === 'pair' && pairScopeResponse" class="detail-query-card">
      <button type="button" class="close-query-btn" title="关闭" @click="closeDetailCard">×</button>
      <div v-if="pairScopeResponse.caveats.length" class="caveats-top">
        <div v-for="c in pairScopeResponse.caveats" :key="c.code" class="caveat">⚠ {{ c.message }}</div>
      </div>
      <PairDetailCard
        v-if="pairPayloadValid"
        :payload="(pairScopeResponse.payload as PairPayload)"
        @undo-swap="undoSwap"
      />
      <div v-else class="hint">scope=pair 端点未接线(见上方 caveat)</div>
    </div>

    <!-- v2 event-debug(2026-07-15) · marker 右键触发的 debug pending 卡片
         detail-debug-card 只作 hook class(不带样式) · 视觉全靠 detail-query-card 继承 -->
    <div v-else-if="activeDetailCard === 'debug' && debugTarget" class="detail-query-card detail-debug-card">
      <button type="button" class="close-query-btn" title="关闭" @click="closeDetailCard">×</button>
      <div class="debug-header">
        Debugging <b>{{ debugTarget.className }}</b>
        <b>{{ debugTarget.anchor }}</b>
        at bar <b>{{ debugTarget.bar }}</b>
      </div>
      <div v-if="debugPending" class="debug-spinner">
        <span class="spinner-dot"></span>
        等待 IDE 断点命中,请在 PyCharm 按 F9 继续,或点取消放弃本次 debug
      </div>
      <div v-else-if="debugError" class="debug-error">断点释放失败({{ debugError }})· 请检查后端 / 网络</div>
      <div v-else class="debug-done">断点已释放,可再次触发或关闭卡片</div>
      <button type="button" class="debug-cancel-btn"
              title="取消 = 放弃本次 fetch; IDE 断点需自行 F9/F8 unblock; 新 debug 请求会 abort 本次"
              @click="onCancelDebug">
        取消
      </button>
    </div>

    <!-- 硬伤级修补:被 A2 post-filter 淘汰的残缺 match(数据未到时恒不渲染,见 droppedMatches 注释) -->
    <div v-if="droppedMatches.length" class="dropped-matches-notice">
      ⚠ 这些 marker 属于被消费的 node · 当前 pattern 未触发({{ droppedMatches.length }} 个残缺 match)
    </div>

    <!-- 漏斗总览:analysis 就绪时常驻 -->
    <template v-if="effectivePattern && effectiveAnalysis">
      <h3 class="section-title">node 漏斗</h3>
      <div v-for="node in effectivePattern.topology.nodes" :key="node.node_id">
        <div class="funnel-row"
             :class="{ 'funnel-row--selected': expandedNodeIds.has(node.node_id) && !isolated.has(node.node_id) }"
             @click="!isolated.has(node.node_id) && toggleExpand(node.node_id)">
          <!-- stream-source(孤立 node):密度徽标行 -->
          <template v-if="isolated.has(node.node_id)">
            <span class="node-label stream-source">{{ node.node_id }}</span>
            <span class="badge">原始检测 {{ detectedCount(node) }}</span>
          </template>
          <!-- pattern node(有边):完整漏斗行 -->
          <template v-else>
            <span class="node-label">{{ node.node_id }}</span>
            <span class="funnel-segment" :style="{ color: tierColor('detected', node.node_id) }">
              {{ detectedCount(node) }}
            </span>
            <span class="funnel-arrow">▸</span>
            <span class="funnel-segment" :style="{ color: tierColor('qualified', node.node_id) }">
              {{ tracedCount(node) }}
            </span>
            <span class="funnel-arrow">▸</span>
            <span class="funnel-segment" :style="{ color: tierColor('matched', node.node_id) }">
              {{ matchedCountForNode(node) }}
            </span>
            <span class="expand-icon">{{ expandedNodeIds.has(node.node_id) ? '▲' : '▼' }}</span>
          </template>
        </div>
        <!-- 就地展开:候选表跟在当前展开的 funnel-row 下方(spec §3.4a) -->
        <div v-if="expandedNodeIds.has(node.node_id) && !isolated.has(node.node_id) && diag"
             class="candidate-table-wrap">
          <table class="candidate-table" v-if="nodeAttr(node.node_id).length">
            <thead>
              <tr>
                <th>事件</th>
                <th v-for="cid in nodeClauseIds(node.node_id)" :key="cid">{{ cid }}</th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="row in nodeAttr(node.node_id)"
                :key="row.event_id"
                class="attr-row"
                :class="{ 'attr-row--selected': markedEventIds.has(row.event_id) }"
                @click="selectCandidateRow(row.event_id)"
              >
                <td class="cell-id" :style="{ borderLeft: `${leftWidth(row)}px solid ${leftColor(row, node.node_id)}`, paddingLeft: `${15 - leftWidth(row)}px` }">seg@{{ row.start_idx }}-{{ row.end_idx }}</td>
                <td v-for="cid in nodeClauseIds(node.node_id)" :key="cid" class="cell-clause">
                  <template v-if="row.clauses[cid]">
                    <!-- 硬伤 C 前端 · 跨节点 clause 未复核/延后 → 用 ⚠ 替代判定值(数据来时才亮,Sprint 2 落) -->
                    <PendingIcon v-if="clausePendingReason(row.clauses[cid])" :reason="clausePendingReason(row.clauses[cid])!" />
                    <template v-else>
                      {{ fmtValue(row.clauses[cid].measured) }}
                      <em v-if="row.clauses[cid].op"> ({{ row.clauses[cid].op }}{{ row.clauses[cid].threshold }})</em>
                      {{ row.clauses[cid].satisfied ? '✓' : '✗' }}
                    </template>
                  </template>
                  <template v-else>—</template>
                </td>
              </tr>
            </tbody>
          </table>
          <div v-else class="hint">无候选数据</div>
        </div>
      </div>
    </template>

    <!-- 命中匹配列表:analysis 就绪时常驻;点行 → 选中 match 展开 trace + 图上高亮 -->
    <template v-if="effectivePattern && effectiveAnalysis && effectiveAnalysis.matches.length">
      <h3 class="section-title">命中匹配</h3>
      <div
        v-for="(m, mi) in effectiveAnalysis.matches" :key="m.event_id"
        class="match-row"
        :class="{ 'match-row--selected': markedMatchIds.has(m.event_id) }"
        @click="selectMatchRow(m.event_id)"
      >
        <span class="match-span">{{ '①②③④⑤⑥⑦⑧⑨'[mi] ?? (mi + 1) }} {{ m.start_idx }}–{{ m.end_idx }}</span>
        <span v-if="m.forward_return !== undefined" class="match-ret"
              :class="m.forward_return !== null && m.forward_return >= 0 ? 'ret-pos' : 'ret-neg'">
          ret_{{ (effectiveScan ?? scanFile?.scan)?.label_horizon }}: {{ formatForwardReturn(m.forward_return) }}
        </span>
      </div>
    </template>

    <!-- per-match trace:选中 match 时叠加显示 -->
    <div v-if="showTrace && selectedMatch" ref="traceEl" class="match-trace">
      <h3 class="section-title">匹配 trace</h3>
      <div v-if="selectedMatch.forward_return !== undefined" class="ret-row">
        ret_{{ (effectiveScan ?? scanFile?.scan)?.label_horizon }}: <strong>{{ formatForwardReturn(selectedMatch.forward_return) }}</strong>
      </div>
      <!-- node 行:可点击,高亮当前 selectedEventId -->
      <div
        v-for="(nid, nodeKey) in selectedMatch.node_index" :key="nodeKey"
        class="node-row trace-node-row"
        :class="{ 'trace-node-row--selected': isNodeSelected(nid) }"
        @click="selectNodeEvent(nid)"
      >
        <strong>{{ nodeKey }}</strong>
        <!-- 硬伤 A · node.rel "K/N ✓" 徽标(数据存在才亮,来自 diag.nodes[node].rel) -->
        <RelBadge v-if="nodeRel(nodeKey)" :ok="nodeRel(nodeKey)!.ok" :total="nodeRel(nodeKey)!.total" size="sm" />
        <span class="event-ref">{{ Array.isArray(nid) ? nid.join(', ') : nid }}</span>
        <template v-if="selectedMatch.predicate_trace?.where_results[nodeKey]">
          <span v-for="(w, cid) in selectedMatch.predicate_trace.where_results[nodeKey]" :key="cid" class="clause">
            {{ cid }}={{ fmtValue(w.measured) }}
            <em v-if="w.op">({{ w.op }}{{ w.threshold }})</em>
            {{ w.satisfied ? '✓' : '✗' }}
          </span>
        </template>
      </div>
      <h4>边</h4>
      <div v-for="(w, key) in selectedMatch.predicate_trace?.edge_results" :key="key" class="edge-row">
        {{ key }} {{ fmt(w.measured?.value, w.measured?.kind) }} {{ w.satisfied ? '✓' : '✗' }}
      </div>
    </div>

    <div v-if="!effectivePattern || !effectiveAnalysis" class="hint">hover K 线 event 看属性 · 点匹配带看 trace · 点拓扑节点展开候选表</div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, nextTick } from 'vue'
import { storeToRefs } from 'pinia'
import { useViewStore } from '../stores/view'
import { colorOf } from '../render/colors'
import { formatForwardReturn } from '../render/visible'
import RelBadge from '../shared/RelBadge.vue'
import PendingIcon from '../shared/PendingIcon.vue'
// fmt(val, kind) 按 EdgeWitness.measured.kind 加前缀(硬伤 E · Task 13 落地接线);fmtValue 硬伤 D 数组/scalar 递归格式化
import { fmt, fmtValue } from '../shared/formatters'
import FailedAttemptsCard from './FailedAttemptsCard.vue'
import PairDetailCard from './PairDetailCard.vue'
import type { TopoNode, AttrRow, ClauseWitness, PairPayload } from '../types'

const view = useViewStore()
const {
  selectedMatch, effectivePattern, effectiveAnalysis,
  diag, isolated, matchedIds, qualifiedIds, nodeColors, selectedEventId, scanFile, effectiveScan,
  activeDetailCard, timeScopeResponse, pairScopeResponse,
  debugPending, debugTarget, debugError,
  showTrace, expandedNodeIds, markedMatchIds, markedEventIds,   // Task 4 新增(集合版)
  focusedMatchId,   // watch 滚动 trace 用
} = storeToRefs(view)

// DOM refs for scroll-to-trace
const sidebarEl = ref<HTMLElement | null>(null)
const traceEl = ref<HTMLElement | null>(null)

// 手动 toggle:点已展开 node → 折叠该行;点未展开 → 加入展开集(不折叠其他)。
function toggleExpand(nodeId: string) {
  view.toggleExpandedNode(nodeId)
}

// trace 展开时滚入视口(旧 watch(selected) 里 kind==='match' 分支迁到这里)
watch([showTrace, focusedMatchId], ([show]) => {
  if (show) {
    nextTick(() => {
      if (traceEl.value && sidebarEl.value && typeof traceEl.value.scrollIntoView === 'function') {
        traceEl.value.scrollIntoView({ block: 'nearest', behavior: 'smooth' })
      }
    })
  }
})

// ─── 计数派生(单一真相源,从 store computed 读) ────────────────────────────────

/** 某 node 所对应 band 的所有 events */
function bandEvents(node: TopoNode) {
  const events = effectiveAnalysis.value?.events ?? []
  return events.filter(e => view.bandKey(e) === node.source_tag)
}

function detectedCount(node: TopoNode): number {
  return bandEvents(node).length
}

function tracedCount(node: TopoNode): number {
  return bandEvents(node).filter(e =>
    qualifiedIds.value.has(e.event_id) || matchedIds.value.has(e.event_id)
  ).length
}

function matchedCountForNode(node: TopoNode): number {
  return bandEvents(node).filter(e => matchedIds.value.has(e.event_id)).length
}

// ─── 着色 ─────────────────────────────────────────────────────────────────────

function tierColor(tier: 'detected' | 'qualified' | 'matched', nodeId: string): string {
  return colorOf(tier, nodeId, nodeColors.value)
}

// ─── 候选表 ───────────────────────────────────────────────────────────────────

// 循环体内每 node 独立取候选表数据(避免 expandedNode 单值假设)。
function nodeAttr(nodeId: string): AttrRow[] {
  return diag.value?.nodes[nodeId]?.attr ?? []
}

function nodeClauseIds(nodeId: string): string[] {
  const ids = new Set<string>()
  for (const row of nodeAttr(nodeId))
    for (const cid of Object.keys(row.clauses)) ids.add(cid)
  return [...ids]
}

/** 候选表行的 tier:先看 matchedIds,再看 qualifiedIds,否则 detected */
function rowTier(row: AttrRow): 'matched' | 'qualified' | 'detected' {
  if (matchedIds.value.has(row.event_id)) return 'matched'
  if (qualifiedIds.value.has(row.event_id)) return 'qualified'
  return 'detected'
}
/** 候选表首列左侧色块色 · 走 colorOf 与副图 marker + 漏斗数字三处共用同一 API
 * leftColor 接受 nodeId 参数(template 从 v-for 传入,取代 expandedNode 单值假设) */
function leftColor(row: AttrRow, nodeId: string): string {
  return colorOf(rowTier(row), nodeId, nodeColors.value)
}
/** 色条宽度按 tier 分档:matched 最宽,便于色盲/低对比场景通过宽度识别层级(色恒非唯一信道)。
 * total = borderWidth + paddingLeft 保持 15px 恒定 → 文字左端在三档间对齐,只有色条本身变宽/变窄。 */
function leftWidth(row: AttrRow): number {
  const t = rowTier(row)
  return t === 'matched' ? 12 : t === 'qualified' ? 6 : 3
}

/**
 * 硬伤 C 前端 · clause 是否跨节点未复核/延后判定 → PendingIcon 呈现的 reason。
 * ClauseWitness 当前类型无 refs_other_node/pending 字段(Sprint 2 Task 14 才落),
 * 用 any 做防御式探测,数据未到时恒 null(不渲染,不破坏现有展示)。
 */
function clausePendingReason(clause: ClauseWitness): 'refs_other_node' | 'cross_node_pending' | null {
  const c = clause as any
  if (c.refs_other_node) return 'refs_other_node'
  if (c.pending) return 'cross_node_pending'
  return null
}

// ─── 匹配 trace 双向高亮 ─────────────────────────────────────────────────────

/**
 * 硬伤 A · node 的入边关系判定汇总(K/N)。diag.nodes[node].rel 是 RelRow[](按 src class 分行);
 * 汇总 ok_count/total_src 得 RelBadge 的 {ok,total}。空数组(无关系边节点,或诊断未跑)→ null 不渲染。
 */
function nodeRel(nodeKey: string | number): { ok: number; total: number } | null {
  const rel = diag.value?.nodes[String(nodeKey)]?.rel
  if (!rel || rel.length === 0) return null
  return {
    ok: rel.reduce((sum, r) => sum + r.ok_count, 0),
    total: rel.reduce((sum, r) => sum + r.total_src, 0),
  }
}

/** match node_index 值可能是 string 或 string[](kleene);取第一个 event_id */
function nodeEventId(val: string | string[]): string | null {
  if (Array.isArray(val)) return val[0] ?? null
  return val
}

function isNodeSelected(val: string | string[]): boolean {
  const id = nodeEventId(val)
  return id !== null && id === selectedEventId.value
}

/** 点击 trace node 行 → focusEvent(spec §3.3 统一 action) */
function selectNodeEvent(val: string | string[]) {
  const id = nodeEventId(val)
  if (id) view.focusEvent(id)
}

/** 点击候选表行 → focusEvent(等价图上 marker click,spec §3.3) */
function selectCandidateRow(eventId: string) {
  view.focusEvent(eventId)
}

/** 点击命中匹配列表行 → focusMatch(等价图上 bracket click,spec §3.3) */
function selectMatchRow(matchId: string): void {
  view.focusMatch(matchId)
}

// ─── Task 18 · 入口 A(brush 时段查询)+ 入口 D(shift+click pair 查询)query 卡片 ─────────
// KlineChart 触发(brush/shift+click)→ view.triggerTimeQuery/triggerPairQuery → 落地
// timeScopeResponse/pairScopeResponse + activeDetailCard,这里只负责渲染 + 关闭。

/** scope=pair 端点未接线(api.py 尚未 recompute+attach AnalysisResult,Task 17 遗留 systemic gap)
 * 时降级为 {stub:true},非真 PairPayload——'valid' in payload 探测,防裸渲染时读 undefined 字段炸模板。*/
const pairPayloadValid = computed(() =>
  !!pairScopeResponse.value && 'valid' in pairScopeResponse.value.payload)

/** 硬伤级修补:dropped_matches(A2 post-filter 淘汰的残缺 match)已加到 path2/dag/result.py::
 * AnalysisResult,但 serialize.py 尚未序列化进前端 Analysis 契约——any-cast 防御式探测,同
 * clausePendingReason 既有模式,数据未到时恒空数组、不渲染。*/
const droppedMatches = computed<unknown[]>(() => (effectiveAnalysis.value as any)?.dropped_matches ?? [])

function closeDetailCard() {
  view.clearDetailCard()   // clearDetailCard 内部已重置 currentTimeEventClass
}

// v2 event-debug(2026-07-15) · cancel debug fetch(不 unblock IDE 断点)
function onCancelDebug() {
  view.cancelDebug()
}

/** 入口 A · event_class 下拉 filter。'' = 全部 · 其余按 class_id 二次过滤重新查询。
 * frame 从当前 timeScopeResponse.payload.frame 取,不重叠框选;triggerTimeQuery 覆写 timeScopeResponse。
 * 过滤态提升到 view store(currentTimeEventClass),KlineChart brush handler 也能读并透传。*/
function onTimeEventClassChange(v: string) {
  view.currentTimeEventClass = v
  const frame = timeScopeResponse.value?.payload.frame
  if (!frame) return
  view.triggerTimeQuery(frame[0], frame[1], v || undefined)
}
/** 卡片切离 'time'(关闭/切走 pair/candidate)→ 复位下拉,防陈旧值。
 * brush 从 'time' → 'time' 无变化、不触发此 watch,是**正确**行为:此时应沿用当前过滤,由 KlineChart 透传。*/
watch(activeDetailCard, (v) => { if (v !== 'time') view.currentTimeEventClass = '' })
/** PairDetailCard 撤回:无 force-no-swap 查询参数(backend 按 edge 存在性确定性判定方向,
 * 非记忆用户点击史)· "撤回" 语义上只能是撤销本次查询展示,而非重新以原始顺序强制查询。*/
function undoSwap() {
  view.clearDetailCard()
}
</script>

<style scoped>
.sidebar { padding: 10px 12px; font-size: 12px; overflow-y: auto; }
.panel-name { font-weight: 700; font-size: 13px; color: #334155; padding-bottom: 6px; margin-bottom: 8px; border-bottom: 1px solid #e2e8f0; }
.section-title { font-size: 12px; font-weight: 600; color: #475569; margin: 8px 0 4px; }

.funnel-row {
  display: flex; align-items: center; gap: 6px; padding: 4px 6px;
  border-radius: 4px; cursor: default; flex-wrap: wrap;
  border: 1px solid transparent; margin-bottom: 2px;
}
.funnel-row:not(.funnel-row--stream-source) { cursor: pointer; }
.funnel-row:hover:not(.funnel-row--stream-source) { background: #f1f5f9; }
.funnel-row--selected { background: #e0f2fe; border-color: #7dd3fc; }

.node-label { font-weight: 600; min-width: 48px; color: #1e293b; }
.node-label.stream-source { color: #64748b; }
.badge { background: #e2e8f0; border-radius: 4px; padding: 1px 6px; font-size: 11px; color: #475569; }
.funnel-segment { font-weight: 700; font-size: 13px; min-width: 20px; text-align: right; }
.funnel-arrow { color: #94a3b8; font-size: 10px; }
.expand-icon { margin-left: auto; color: #94a3b8; font-size: 10px; }

.candidate-table-wrap { margin: 4px 0 8px; background: #f8fafc; border-radius: 4px; padding: 6px; }
.candidate-table { width: 100%; border-collapse: collapse; font-size: 11px; }
.candidate-table th { text-align: left; padding: 2px 6px; color: #64748b; border-bottom: 1px solid #e2e8f0; }
.attr-row { cursor: pointer; }
.attr-row:hover { background: #f1f5f9; }
.attr-row--selected { background: #fef9c3 !important; }
.attr-row--selected td { border-top: 1px solid #fbbf24; border-bottom: 1px solid #fbbf24; }
.attr-row--selected td:first-child { border-left: 1px solid #fbbf24; }
.attr-row--selected td:last-child { border-right: 1px solid #fbbf24; }
.cell-id { padding: 2px 6px; color: #475569; white-space: nowrap; }
.cell-clause { padding: 2px 6px; }
.cell-clause em { color: #94a3b8; font-style: normal; }

.match-row {
  display: flex; align-items: center; gap: 8px; padding: 4px 6px;
  border-radius: 4px; cursor: pointer; border: 1px solid transparent; margin-bottom: 2px;
}
.match-row:hover { background: #f1f5f9; }
.match-row--selected { background: #fef9c3; border-color: #fbbf24; }
.match-span { font-size: 11px; color: #475569; flex: 1; }
.match-ret { font-weight: 700; font-size: 12px; }
.ret-pos { color: #16a34a; }
.ret-neg { color: #dc2626; }

.ret-row { margin: 4px 0; color: #334155; }
.match-trace { margin-top: 10px; border-top: 1px solid #e2e8f0; padding-top: 8px; }
.node-row, .edge-row { margin: 4px 0; display: flex; gap: 8px; flex-wrap: wrap; }
.trace-node-row { cursor: pointer; padding: 3px 6px; border-radius: 4px; border: 1px solid transparent; }
.trace-node-row:hover { background: #f1f5f9; }
.trace-node-row--selected { background: #fef9c3 !important; border-color: #fbbf24; }
.event-ref { color: #64748b; font-size: 11px; margin-left: 4px; }
.clause em { color: #64748b; font-style: normal; }
.hint { color: #94a3b8; margin-top: 8px; }

.detail-query-card {
  position: relative; margin-bottom: 10px; padding: 8px 10px 4px;
  border: 1px solid #7dd3fc; border-radius: 6px; background: #f0f9ff;
}
.close-query-btn {
  position: absolute; top: 2px; right: 4px; border: none; background: transparent;
  cursor: pointer; font-size: 14px; line-height: 1; color: #64748b; padding: 2px 4px;
}
.caveats-top { margin: 2px 20px 6px 0; }
.caveat { font-size: 11px; color: #92400e; background: #fefcbf; border-radius: 4px; padding: 3px 6px; margin-bottom: 2px; }
.dropped-matches-notice {
  font-size: 11px; color: #92400e; background: #fefcbf; border-radius: 4px;
  padding: 4px 6px; margin-bottom: 8px;
}

/* v2 event-debug(2026-07-15) */
.debug-header {
  font-size: 13px;
  padding: 8px 12px 4px;
  color: #333;
}
.debug-spinner {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 12px;
  font-size: 12px;
  color: #666;
  line-height: 1.5;
}
.spinner-dot {
  display: inline-block;
  width: 8px;
  height: 8px;
  background: #4a90e2;
  border-radius: 50%;
  animation: pulse 1.2s ease-in-out infinite;
  flex-shrink: 0;
}
@keyframes pulse {
  0%, 100% { opacity: 0.3; transform: scale(0.8); }
  50% { opacity: 1; transform: scale(1.2); }
}
.debug-done {
  padding: 10px 12px;
  font-size: 12px;
  color: #4a7;
}
.debug-error {
  padding: 10px 12px;
  font-size: 12px;
  color: #c0392b;
}
.debug-cancel-btn {
  margin: 4px 12px 12px;
  padding: 6px 12px;
  background: #e74c3c;
  color: white;
  border: none;
  border-radius: 4px;
  cursor: pointer;
  font-size: 12px;
}
.debug-cancel-btn:hover {
  background: #c0392b;
}
</style>
