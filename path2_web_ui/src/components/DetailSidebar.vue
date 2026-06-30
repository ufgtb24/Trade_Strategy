<template>
  <div ref="sidebarEl" class="sidebar">
    <div class="panel-name">DetailSidebar</div>

    <!-- 漏斗总览:analysis 就绪时常驻 -->
    <template v-if="effectivePattern && effectiveAnalysis">
      <h3 class="section-title">角色漏斗</h3>
      <div
        v-for="node in effectivePattern.topology.nodes"
        :key="node.node_id"
        class="funnel-row"
        :class="{ 'funnel-row--selected': expandedNode === node.node_id && !isolated.has(node.node_id) }"
        @click="!isolated.has(node.node_id) && toggleExpand(node.node_id)"
      >
        <!-- stream-source(孤立 node):密度徽标行 -->
        <template v-if="isolated.has(node.node_id)">
          <span class="node-label stream-source">{{ node.node_id }}</span>
          <span class="badge">原始检测 {{ detectedCount(node) }}</span>
        </template>
        <!-- pattern role(有边):完整漏斗行 -->
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
          <span class="expand-icon">{{ expandedNode === node.node_id ? '▲' : '▼' }}</span>
        </template>
      </div>

      <!-- 候选表:展开 pattern role 行时显示 -->
      <template v-if="expandedNode && diag">
        <div class="candidate-table-wrap">
          <div class="candidate-table-title">{{ expandedNode }} 候选</div>
          <table class="candidate-table" v-if="expandedRoleAttr.length">
            <thead>
              <tr>
                <th>事件</th>
                <th v-for="cid in expandedClauseIds" :key="cid">{{ cid }}</th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="row in expandedRoleAttr"
                :key="row.event_id"
                class="attr-row"
                :class="{ 'attr-row--selected': selectedEventId === row.event_id, 'attr-row--matched': rowTier(row) === 'matched', 'attr-row--qualified': rowTier(row) === 'qualified' }"
                @click="selectCandidateRow(row.event_id)"
              >
                <td class="cell-id">seg@{{ row.start_idx }}-{{ row.end_idx }}</td>
                <td v-for="cid in expandedClauseIds" :key="cid" class="cell-clause">
                  <template v-if="row.clauses[cid]">
                    {{ fmt(row.clauses[cid].measured) }}
                    <em v-if="row.clauses[cid].op"> ({{ row.clauses[cid].op }}{{ row.clauses[cid].threshold }})</em>
                    {{ row.clauses[cid].satisfied ? '✓' : '✗' }}
                  </template>
                  <template v-else>—</template>
                </td>
              </tr>
            </tbody>
          </table>
          <div v-else class="hint">无候选数据</div>
        </div>
      </template>
    </template>

    <!-- 命中匹配列表:analysis 就绪时常驻;点行 → 选中 match 展开 trace + 图上高亮 -->
    <template v-if="effectivePattern && effectiveAnalysis && effectiveAnalysis.matches.length">
      <h3 class="section-title">命中匹配</h3>
      <div
        v-for="(m, mi) in effectiveAnalysis.matches" :key="m.event_id"
        class="match-row"
        :class="{ 'match-row--selected': selected?.kind === 'match' && (selected as any).matchId === m.event_id }"
        @click="selectMatchAndHighlight(m.event_id, m.children)"
      >
        <span class="match-span">{{ '①②③④⑤⑥⑦⑧⑨'[mi] ?? (mi + 1) }} {{ m.start_idx }}–{{ m.end_idx }}</span>
        <span v-if="m.forward_return !== undefined" class="match-ret"
              :class="m.forward_return !== null && m.forward_return >= 0 ? 'ret-pos' : 'ret-neg'">
          ret_{{ (effectiveScan ?? scanFile?.scan)?.label_horizon }}: {{ formatForwardReturn(m.forward_return) }}
        </span>
      </div>
    </template>

    <!-- per-match trace:选中 match 时叠加显示 -->
    <div v-if="selected?.kind === 'match' && selectedMatch" ref="traceEl" class="match-trace">
      <h3 class="section-title">匹配 trace</h3>
      <div v-if="selectedMatch.forward_return !== undefined" class="ret-row">
        ret_{{ (effectiveScan ?? scanFile?.scan)?.label_horizon }}: <strong>{{ formatForwardReturn(selectedMatch.forward_return) }}</strong>
      </div>
      <!-- role 行:可点击,高亮当前 selectedEventId -->
      <div
        v-for="(nid, roleKey) in selectedMatch.role_index" :key="roleKey"
        class="role-row trace-role-row"
        :class="{ 'trace-role-row--selected': isRoleSelected(nid) }"
        @click="selectRoleEvent(nid)"
      >
        <strong>{{ roleKey }}</strong>
        <span class="event-ref">{{ Array.isArray(nid) ? nid.join(', ') : nid }}</span>
        <template v-if="selectedMatch.predicate_trace?.where_results[roleKey]">
          <span v-for="(w, cid) in selectedMatch.predicate_trace.where_results[roleKey]" :key="cid" class="clause">
            {{ cid }}={{ fmt(w.measured) }}
            <em v-if="w.op">({{ w.op }}{{ w.threshold }})</em>
            {{ w.satisfied ? '✓' : '✗' }}
          </span>
        </template>
      </div>
      <h4>边</h4>
      <div v-for="(w, key) in selectedMatch.predicate_trace?.edge_results" :key="key" class="edge-row">
        {{ key }} gap={{ w.measured }} {{ w.satisfied ? '✓' : '✗' }}
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
import type { TopoNode, AttrRow } from '../types'

const view = useViewStore()
const {
  selected, selectedMatch, effectivePattern, effectiveAnalysis,
  diag, isolated, matchedIds, qualifiedIds, roleColors, selectedEventId, scanFile, effectiveScan,
} = storeToRefs(view)

// DOM refs for scroll-to-trace
const sidebarEl = ref<HTMLElement | null>(null)
const traceEl = ref<HTMLElement | null>(null)

// 本地展开状态
const expandedNode = ref<string | null>(null)

function toggleExpand(nodeId: string) {
  expandedNode.value = expandedNode.value === nodeId ? null : nodeId
}

// 选中状态变化时联动本地展开:role→展开候选表;match→收起候选表后滚到 trace
watch(selected, (sel) => {
  if (sel?.kind === 'role') {
    expandedNode.value = sel.nodeId
  } else if (sel?.kind === 'match') {
    expandedNode.value = null   // 收起候选表,trace 部分即在视口内
    // DOM 更新后将 trace 区域滚入侧栏可见区(jsdom 无 scrollIntoView,防御)
    nextTick(() => {
      if (traceEl.value && sidebarEl.value && typeof traceEl.value.scrollIntoView === 'function') {
        traceEl.value.scrollIntoView({ block: 'nearest', behavior: 'smooth' })
      }
    })
  }
})

function fmt(v: unknown): string {
  return typeof v === 'number' ? (Number.isInteger(v) ? String(v) : v.toFixed(2)) : String(v)
}

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
  return colorOf(tier, nodeId, roleColors.value)
}

// ─── 候选表 ───────────────────────────────────────────────────────────────────

const expandedRoleAttr = computed<AttrRow[]>(() => {
  if (!expandedNode.value || !diag.value) return []
  return diag.value.roles[expandedNode.value]?.attr ?? []
})

const expandedClauseIds = computed<string[]>(() => {
  const ids = new Set<string>()
  for (const row of expandedRoleAttr.value)
    for (const cid of Object.keys(row.clauses)) ids.add(cid)
  return [...ids]
})

/** 候选表行的 tier:先看 matchedIds,再看 qualifiedIds,否则 detected */
function rowTier(row: AttrRow): 'matched' | 'qualified' | 'detected' {
  if (matchedIds.value.has(row.event_id)) return 'matched'
  if (qualifiedIds.value.has(row.event_id)) return 'qualified'
  return 'detected'
}

// ─── 匹配 trace 双向高亮 ─────────────────────────────────────────────────────

/** match role_index 值可能是 string 或 string[](kleene);取第一个 event_id */
function roleEventId(val: string | string[]): string | null {
  if (Array.isArray(val)) return val[0] ?? null
  return val
}

function isRoleSelected(val: string | string[]): boolean {
  const id = roleEventId(val)
  return id !== null && id === selectedEventId.value
}

/** 点击 trace role 行 → 设置 selectedEventId,实现 sidebar→chart 高亮 */
function selectRoleEvent(val: string | string[]) {
  const id = roleEventId(val)
  if (id) view.selectEvent(id)
}

/** 点击候选表行:先退出 M' 候选状态(互斥),再选 event(final review fix) */
function selectCandidateRow(eventId: string) {
  view.clearCandidates()  // exit any M' candidate state — 互斥 §2.2
  view.selectEvent(eventId)
}

/** 点击命中匹配列表行:选中 match(展开 trace)+ 组高亮(等价图上 bracket click) */
function selectMatchAndHighlight(matchId: string, children: string[]) {
  view.setHighlightedEvents(children)
  view.selectMatch(matchId)
  view.clearCandidates()           // 顺手清候选,防残留
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
.candidate-table-title { font-weight: 600; color: #334155; margin-bottom: 4px; font-size: 11px; }
.candidate-table { width: 100%; border-collapse: collapse; font-size: 11px; }
.candidate-table th { text-align: left; padding: 2px 6px; color: #64748b; border-bottom: 1px solid #e2e8f0; }
.attr-row { cursor: pointer; }
.attr-row:hover { background: #f1f5f9; }
.attr-row--selected { background: #fef9c3 !important; }
.attr-row--matched td { border-left: 3px solid #22c55e; }
.attr-row--qualified td { border-left: 3px solid #9ca3af; }
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
.role-row, .edge-row { margin: 4px 0; display: flex; gap: 8px; flex-wrap: wrap; }
.trace-role-row { cursor: pointer; padding: 3px 6px; border-radius: 4px; border: 1px solid transparent; }
.trace-role-row:hover { background: #f1f5f9; }
.trace-role-row--selected { background: #fef9c3 !important; border-color: #fbbf24; }
.event-ref { color: #64748b; font-size: 11px; margin-left: 4px; }
.clause em { color: #64748b; font-style: normal; }
.hint { color: #94a3b8; margin-top: 8px; }
</style>
