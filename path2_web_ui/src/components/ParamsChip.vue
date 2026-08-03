<!-- 参数模式 chip(两态):灰=浏览(snapshot)/绿=探索(Working Copy 现算)+ 白点(WC≠snapshot)
     + 内嵌圆形抽屉 toggle 按钮(任何态可点,P3;开/关随抽屉状态填充蓝/白,与模式解耦)+ yaml 漂移 ⚠。
     spec: docs/research/params-editor-followup-decisions.md D1/D2/D3/P3
     chip 文本点击=A/B 开关(视图轴唯一入口):有 WC 双向 toggle,无 WC 无反应(先在抽屉 Write Copy 立副本,再点 chip 切换)。
     无 snapshot 的 scan(legacy)已淘汰(D3):chip 整体不渲染。-->
<template>
  <div v-if="scanFile && activePatternId && hasSnapshot" class="params-chip-wrap">
    <div class="chip" data-testid="params-chip" :class="modeClass">
      <span class="chip-label" :class="{ actionable: hasWc }" data-testid="chip-label" :title="modeTitle" @click="onChipClick">
        {{ modeText }}<span v-if="dirtyMark" class="dirty"
              title="Working Copy 与 snapshot 存在字段差异(未存盘,也未通过扫描固化)"
              @click.stop>●</span>
      </span>
      <button class="drawer-btn" :class="{ open: drawerOpen }" data-testid="drawer-btn"
              title="打开/关闭参数编辑抽屉 (Shift+P)"
              @click.stop="$emit('toggle-drawer')">✎</button>
    </div>
    <span v-if="diff && !diff.match && diff.has_snapshot && !diff.anchor_missing" class="warn" data-testid="mismatch-dot"
          :title="`${anchorFile} 已与 scan 时不一致(${diff.diffs.length} 字段);debug/preview 仍锚 snapshot。可新扫或在抽屉 Load ${anchorFile}。`">⚠</span>
    <span v-if="diff && diff.anchor_missing" class="anchor-missing" data-testid="anchor-missing-dot"
          :title="`${anchorFile} 已删除,参数对比不可用`">?</span>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { storeToRefs } from 'pinia'
import { useViewStore } from '../stores/view'
import { getParamsDiff, type ParamsDiffResp } from '../api'

defineEmits<{ 'toggle-drawer': [] }>()
defineProps<{ drawerOpen?: boolean }>()
const view = useViewStore()
const { scanFile, activePatternId, workingCopy, isExploring } = storeToRefs(view)

const hasSnapshot = computed(() =>
  !!(activePatternId.value && view.snapshotOf(activePatternId.value)))
const hasWc = computed(() =>
  !!workingCopy.value[activePatternId.value ?? ''])
const modeClass = computed(() => isExploring.value ? 'mode-explore' : 'mode-browse')
const modeText = computed(() =>
  isExploring.value ? '探索 · Working Copy' : '浏览 · snapshot')
const modeTitle = computed(() => {
  if (isExploring.value) return '全 UI(markers/诊断/debug)按 Working Copy 现算。点击回浏览(副本保留)'
  return workingCopy.value[activePatternId.value ?? '']
    ? '全 UI 锚定 scan 参数快照。点击切回 Working Copy 视图(A/B)'
    : '全 UI 锚定 scan 参数快照(与列表 ret 同口径)。用 ✎ 打开抽屉编辑参数'
})
const dirtyMark = computed(() =>
  !!(activePatternId.value && view.wcDirty(activePatternId.value)))

function onChipClick() {
  const pid = activePatternId.value
  if (!pid) return
  const wc = workingCopy.value[pid]
  if (!wc) return                                    // 无 WC:无反应(先 Write Copy 立副本,chip 才有东西可切)
  view.setWorkingCopyEnabled(pid, !wc.enabled)       // A/B 秒切(原 checkbox 语义完整继承)
}

const diff = ref<ParamsDiffResp | null>(null)
// 锚文件名:后端按 provenance 给出(用非 params.yaml 的文件扫描时就是那个文件);
// 老 scan / 老后端无此字段 → 兜底 params.yaml
const anchorFile = computed(() => diff.value?.anchor_file ?? 'params.yaml')
watch([scanFile, activePatternId], async () => {
  diff.value = null
  const ts = scanFile.value?.scan.scan_ts
  const pid = activePatternId.value
  if (!ts || !pid) return
  try { diff.value = await getParamsDiff(pid, ts) } catch (e) { console.warn('getParamsDiff failed', e); diff.value = null }
}, { immediate: true })
</script>

<style scoped>
.params-chip-wrap { display: inline-flex; align-items: center; gap: 6px; }
.chip { display: inline-flex; align-items: center; gap: 6px; border: 1px solid transparent;
        border-radius: 12px; padding: 2px 4px 2px 10px; font-size: 12px; }
.chip-label { cursor: default; user-select: none; border-radius: 8px; padding: 0 4px; margin: 0 -4px; }
.chip-label.actionable { cursor: pointer; }
.chip-label.actionable:hover { background: rgba(0,0,0,.08); }   /* 模式无关暗化:灰/绿底上均可辨 */
.mode-browse  { background: #f1f5f9; color: #475569; border-color: #cbd5e1; }
.mode-explore { background: #10b981; color: #ffffff; border-color: #047857; font-weight: 600; }
.drawer-btn { width: 20px; height: 20px; border-radius: 50%; border: 1px solid rgba(0,0,0,.18);
              background: #ffffff; color: #475569; cursor: pointer; font-size: 12px; line-height: 1;
              display: inline-flex; align-items: center; justify-content: center; padding: 0; }
.drawer-btn:hover { background: #e2e8f0; }
.drawer-btn.open { background: #2563eb; color: #ffffff; border-color: #1d4ed8; }   /* 蓝=面板开,与模式色(灰/绿)正交 */
.drawer-btn.open:hover { background: #1d4ed8; }
.dirty { margin-left: 4px; color: #dc2626; }
.mode-explore .dirty { color: #ffffff; }  /* 红点在饱和绿上=红绿配,色弱不可见,改白点靠亮度差 */
.warn { color: #fcd34d; font-size: 16px; font-weight: 700; cursor: help; line-height: 1;
        text-shadow: 0 0 2px rgba(0,0,0,0.6); }  /* yaml 漂移:亮琥珀 ⚠,与 dirty 白点语义/视觉分离 */
.anchor-missing { color: #94a3b8; font-size: 13px; font-weight: 700; cursor: help; line-height: 1; }  /* 锚文件已删除:灰"?",与 mismatch 琥珀⚠分离 */
</style>
