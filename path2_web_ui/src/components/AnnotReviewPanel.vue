<template>
  <aside class="review" data-testid="review-panel">
    <div class="title">已标注 {{ store.draftCount }} 条（未发送）</div>
    <div v-if="!store.draftCount && !store.lastSent" class="empty">还没有标注。</div>
    <table v-if="store.draftCount" class="rows">
      <thead>
        <tr><th>代码</th><th>起止</th><th>买点</th><th>判定</th><th>备注</th><th /></tr>
      </thead>
      <tbody>
        <tr v-for="a in store.draftList" :key="a.item_id" :data-item-id="a.item_id"
            :class="{ incomplete: missingFields(a).length > 0 }">
          <td>
            <button type="button" class="link" data-testid="goto" @click="store.gotoItem(a.item_id)">
              {{ a.symbol }}</button>
          </td>
          <td class="mono">{{ a.range_start ?? '—' }}<br>{{ a.range_end ?? '—' }}</td>
          <td class="mono" data-testid="row-buys">
            <template v-if="a.buy_points.length">
              <div v-for="b in orderedBuyPoints(a.buy_points)" :key="b.date">{{ b.primary ? '★' : '' }}{{ b.date }}</div>
            </template>
            <template v-else>—</template>
          </td>
          <td>
            <select :value="a.label ?? ''" data-testid="row-label"
                    @change="store.upsertAnnotation(a.item_id, { label: (($event.target as HTMLSelectElement).value || null) as any })">
              <option value="">未标</option>
              <option value="positive">{{ labelText('positive', store.listKind) }}</option>
              <option value="negative">{{ labelText('negative', store.listKind) }}</option>
              <option value="data_error">{{ labelText('data_error', store.listKind) }}</option>
            </select>
            <div v-if="missingFields(a).length" class="miss">缺{{ missingFields(a).join('、') }}</div>
          </td>
          <td>
            <input type="text" :value="a.note" maxlength="500" data-testid="row-note"
                   @input="store.upsertAnnotation(a.item_id, { note: ($event.target as HTMLInputElement).value })">
          </td>
          <td>
            <button type="button" data-testid="row-delete" @click="store.deleteAnnotation(a.item_id)">删除</button>
          </td>
        </tr>
      </tbody>
    </table>
    <div class="actions">
      <button type="button" class="primary" data-testid="send"
              :disabled="!store.draftCount || store.sending" @click="store.send()">
        {{ store.sending ? '发送中…' : '发送' }}</button>
      <template v-if="!confirmClear">
        <button type="button" data-testid="clear-all" :disabled="!store.draftCount"
                @click="confirmClear = true">清空</button>
      </template>
      <template v-else>
        <span>确定清空全部 {{ store.draftCount }} 条？</span>
        <button type="button" data-testid="clear-confirm" @click="store.clearDrafts(); confirmClear = false">确定清空</button>
        <button type="button" @click="confirmClear = false">取消</button>
      </template>
    </div>
    <div v-if="store.sendError" class="err" data-testid="send-error">{{ store.sendError }}</div>
    <div v-if="store.lastSent" class="ok" data-testid="send-ok">
      已发送：批次 {{ store.lastSent.batch_id }}，共 {{ store.lastSent.n }} 条，文件 {{ store.lastSent.path }}
    </div>
  </aside>
</template>

<script setup lang="ts">
/** 已标注抽屉:列出本批全部草稿(买点一列列出全部买点,主买点前加 ★),就地改判定与备注、删除、
 *  跳到所在页;发送 / 清空(二次确认)。判定文字随清单种类变,与图上同一套。 */
import { ref } from 'vue'
import { labelText, missingFields, orderedBuyPoints, useWorkflowStore } from '../stores/workflow'

const store = useWorkflowStore()
const confirmClear = ref(false)
</script>

<style scoped>
.review { width: 420px; flex: 0 0 420px; border-left: 1px solid #cbd5e1; padding: 8px; overflow: auto;
          font-size: 12px; background: #f8fafc; }
.title { font-weight: 700; margin-bottom: 6px; }
.empty { color: #475569; }
.rows { width: 100%; border-collapse: collapse; }
.rows th, .rows td { border-bottom: 1px solid #e2e8f0; padding: 3px 2px; vertical-align: top; text-align: left; }
.rows tr.incomplete td:first-child { border-left: 3px solid #0f172a; }
.mono { font-family: ui-monospace, monospace; white-space: nowrap; }
.miss { font-weight: 700; }
.rows input { width: 100%; font-size: 12px; }
.link { background: none; border: none; padding: 0; font-weight: 700; text-decoration: underline; cursor: pointer; }
.actions { display: flex; gap: 6px; align-items: center; margin-top: 8px; flex-wrap: wrap; }
.primary { font-weight: 700; }
.err { margin-top: 6px; color: #b91c1c; white-space: pre-wrap; }
.ok { margin-top: 6px; font-weight: 700; word-break: break-all; }
</style>
