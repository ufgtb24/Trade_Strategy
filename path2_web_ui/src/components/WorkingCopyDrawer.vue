<!-- 参数编辑抽屉:三源对称表 + 常驻可编辑 monaco。
     三个内容源(snapshot / 关联文件 / Working Copy)地位平等,每源一行,列固定为
     「源 | 载入(源→编辑区) | 写出(编辑区→源) | 基准(diff 对照方)」:
       · 载入判据三源同构(paramsEditorState.computeButtonStates.canLoad),与基准选择无关——
         装谁、对照谁彻底解耦:可「编辑区装文件、拿 snapshot 对照」,反向亦然。
       · 写出:snapshot 是 scan 的只读记录,无写出;关联文件=Save/Save As;WC=Write Copy。
       · 基准四选一 radio(off|三源),取代原「对比 checkbox + 锚 radio」两级控件;
         选 WC 作基准时,刚 Write Copy 后两侧一致、diff 为空是正常的(不是 bug)。
     spec: docs/superpowers/specs/2026-07-22-params-editor-dev-parity-design.md
         + docs/research/params-editor-followup-decisions.md(D1-D6/P1-P3;其中 D6「WC 不作锚」
           已被本次三源对称改造推翻——WC 现可作基准)
     三层状态:File(app 目录多 yaml,assocFile 关联)→ Editor(共享 textModel)→ Memory(WC.currentDict)。
     共享 model 让 diff 的 modified 侧=编辑缓冲本身:diff 可编辑/切视图零丢字/diff=编辑区实时 vs 当前基准。-->
<template>
  <div v-if="open" class="drawer" data-testid="wc-drawer"
       :class="{ moving: dragging || resizing }"
       :style="{ left: rect.x + 'px', top: rect.y + 'px', width: rect.w + 'px', height: rect.h + 'px' }">
    <div class="hdr" data-testid="wc-drag-handle" @pointerdown="onDragPointerDown">
      <strong>{{ activePatternId }} 参数</strong>
      <button class="close" @click="$emit('close')">×</button>
    </div>
    <div class="coord-note">口径:label_horizon / 扫描窗恒锚 scan 设置,不随参数探索变。</div>

    <!-- 三源对称表:整表一个 grid(行 display:contents)才能让四列跨行对齐 -->
    <div class="src-table">
      <div class="src-row src-head">
        <span>源</span><span>载入</span><span>写出</span>
        <label class="c-anchor" title="不对比:回单编辑器">
          <input type="radio" value="off" v-model="anchorKind" data-testid="anchor-off" />关
        </label>
      </div>

      <div class="src-row">
        <span class="c-src">snapshot</span>
        <span>
          <button :disabled="!btnStates.canLoad.snapshot"
                  :title="btnStates.canLoad.snapshot ? '把 snapshot 载入编辑区' : '编辑区已与 snapshot 一致'"
                  data-testid="load-snapshot" @click="loadFrom('snapshot')">Load</button>
        </span>
        <span class="c-none" title="snapshot 是 scan 的只读记录,不可写入">—</span>
        <label class="c-anchor" :title="snapDict ? '以 snapshot 为对比基准' : 'snapshot 不可用'">
          <input type="radio" value="snapshot" v-model="anchorKind" :disabled="!snapDict"
                 data-testid="anchor-snapshot" />
        </label>
      </div>

      <div class="src-row">
        <span class="c-src">文件
          <select :value="assocFile" data-testid="assoc-select" @change="onLoadSelect">
            <option v-for="f in fileList" :key="f" :value="f">{{ f }}</option>
          </select>
          <button v-if="assocFile !== 'params.yaml'" class="del-btn" data-testid="delete-param"
                  :title="`删除关联文件 ${assocFile}`" @click="onDeleteParam">🗑</button>
        </span>
        <span>
          <button :disabled="!btnStates.canLoad.assoc"
                  :title="btnStates.canLoad.assoc ? `把 ${assocFile} 载入编辑区` : '编辑区已与关联文件一致'"
                  data-testid="load-assoc" @click="loadFrom('assoc')">Load</button>
        </span>
        <span>
          <button :disabled="!btnStates.canSave"
                  :title="btnStates.canSave ? `写入 ${assocFile}` : '与关联文件一致,无需保存'"
                  @click="onSave">Save</button>
          <button :disabled="!btnStates.canSaveAs"
                  title="另存为 app 目录下新文件,关联切过去"
                  @click="onSaveAs">Save As</button>
        </span>
        <label class="c-anchor" :title="assocDict ? '以关联文件为对比基准' : '关联文件未拉到'">
          <input type="radio" value="assoc" v-model="anchorKind" :disabled="!assocDict"
                 data-testid="anchor-assoc" />
        </label>
      </div>

      <div class="src-row">
        <span class="c-src">Working Copy
          <button v-if="wcDict" class="del-btn" data-testid="clear-wc"
                  title="删除工作副本(内存参数+localStorage 草稿),回浏览态;不碰编辑区"
                  @click="onClearWc">🗑</button>
        </span>
        <span>
          <button :disabled="!btnStates.canLoad.wc"
                  :title="btnStates.canLoad.wc ? '把 Working Copy 载入编辑区(使其可见/可续编)'
                          : (wcDict ? '编辑区已与 Working Copy 一致' : '尚无 Working Copy')"
                  data-testid="load-wc" @click="loadFrom('wc')">Load</button>
        </span>
        <span>
          <button :disabled="!btnStates.canWriteCopy"
                  :title="btnStates.canWriteCopy ? '编辑区 → Working Copy(只写副本,不切换浏览/探索视图;探索态下立即重算)'
                          : '编辑区与 Working Copy 一致,无需写入'"
                  data-testid="write-copy" @click="onWriteCopy">Write Copy</button>
        </span>
        <label class="c-anchor"
               :title="wcDict ? '以 Working Copy 为对比基准(刚 Write Copy 后两侧一致、diff 为空是正常的)'
                       : '尚无 Working Copy'">
          <input type="radio" value="wc" v-model="anchorKind" :disabled="!wcDict" data-testid="anchor-wc" />
        </label>
      </div>
    </div>

    <div ref="editorEl" class="editor"></div>
    <div v-if="parseError" class="err">{{ parseError }}</div>
    <div v-if="previewError" class="err">现算失败: {{ previewError }}</div>
    <div v-if="confirmingDelete" class="confirm-backdrop" data-testid="delete-confirm">
      <div class="confirm-card">
        <p>删除参数文件 <strong>{{ assocFile }}</strong>?</p>
        <p class="warn">删除后不可恢复,历史扫描的参数对比将不可用。</p>
        <div class="confirm-actions">
          <button @click="confirmingDelete = false">取消</button>
          <button class="btn-stop" data-testid="confirm-delete" @click="performDeleteParam">删除</button>
        </div>
      </div>
    </div>
    <div class="resize-handle" data-testid="wc-resize-handle" title="拖拽调整面板大小"
         @pointerdown="onResizePointerDown"></div>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, ref, shallowRef, watch } from 'vue'
import { storeToRefs } from 'pinia'
import { useViewStore } from '../stores/view'
import { listParamFiles, readParamFile, saveParamFile, deleteParamFile } from '../api'
import { dictToYamlText, yamlTextToDict } from './workingCopyYaml'
import type { AnchorKind, SourceKind } from './paramsEditorState'
import { computeButtonStates, dictsEqual, normalizeSaveAsName, resolveAnchorKind, resolveAssocFile } from './paramsEditorState'
import { materializeKeysByNode, whereLineNumbers } from './workingCopyLayers'
import { useFloatingPanel } from './useFloatingPanel'

const props = defineProps<{ open: boolean }>()
defineEmits<{ close: [] }>()
const view = useViewStore()
const { activePatternId, previewError, workingCopy } = storeToRefs(view)

// 悬浮几何:面板不再是右侧贴边全高抽屉,而是可拖可缩的浮窗,位置/尺寸持久化(见 useFloatingPanel)
const { rect, dragging, resizing, onDragPointerDown, onResizePointerDown } = useFloatingPanel()

// ── File 层状态 ──
const fileList = ref<string[]>([])
const assocFile = ref('params.yaml')                       // 当前关联文件(dev current_file_path)
const assocDict = ref<Record<string, any> | null>(null)    // 关联文件内容(Save enable 比较基准 + 锚=assoc 的源)
// ── Editor 层状态 ──
const editorDict = ref<Record<string, any> | null>(null)   // debounce parse 结果
const parseError = ref<string | null>(null)
const ANCHOR_LS_KEY = 'p2wc:drawer:anchorKind'   // 取代旧 'p2wc:drawer:diffMode';旧值 '1'/'0' 非法 → resolveAnchorKind 回退 off
// 关联文件选择持久化(per pid;文件列表是 pattern app 目录内容,与 scan 无关 → key 不带 scan_ts)
const ASSOC_LS_PREFIX = 'p2wc:assoc:'
function _loadAssocFile(pid: string): string | null { return localStorage.getItem(ASSOC_LS_PREFIX + pid) }
function _saveAssocFile(pid: string, name: string): void { localStorage.setItem(ASSOC_LS_PREFIX + pid, name) }
const anchorKind = ref<AnchorKind>('off')   // 对比基准四选一(off|三源);持久化,装载时经 resolveAnchorKind 恢复

const editorEl = ref<HTMLElement | null>(null)
const viewEditor = shallowRef<any>(null)     // IStandaloneCodeEditor | IStandaloneDiffEditor
const sharedModel = shallowRef<any>(null)    // 编辑缓冲(单编辑器与 diff modified 侧共用)
let originalModel: any = null                // diff original 侧(随视图建/毁)
let whereDecoMod: string[] = []              // modified 侧 where 行 decoration id(增量更新用)
let whereDecoOrig: string[] = []             // diff original 侧
let monacoMod: any = null
let parseTimer: ReturnType<typeof setTimeout> | null = null
let loadGen = 0   // loadContext 代次守卫:每次调用自增,await 后比对防旧请求后发先至覆盖新状态(F4)

// snapshot 恒存在(D3:legacy scan 已淘汰,chip 无 snapshot 不渲染、抽屉进不来)
const snapDict = computed<Record<string, any> | null>(() =>
  activePatternId.value ? view.snapshotOf(activePatternId.value) : null)
// 当前生效运算参数:探索态=WC.currentDict;浏览态恒=snapshot(与锚选择无关)
const effectiveDict = computed<Record<string, any> | null>(() => {
  const pid = activePatternId.value
  if (!pid) return null
  const wc = workingCopy.value[pid]
  return wc?.enabled ? wc.currentDict : snapDict.value
})
// WC.currentDict(无 WC 为 null):三源之一——可载入、可作基准、可被 Write Copy 写入
const wcDict = computed<Record<string, any> | null>(() =>
  workingCopy.value[activePatternId.value ?? '']?.currentDict ?? null)

// ── 三源对称层:取 dict 的唯一入口,载入(loadFrom)与对比(anchorDict)共用同一份内容 ──
function dictOf(kind: SourceKind): Record<string, any> | null {
  return kind === 'snapshot' ? snapDict.value : kind === 'assoc' ? assocDict.value : wcDict.value
}
function sourceLabel(kind: SourceKind): string {
  return kind === 'snapshot' ? 'snapshot'
       : kind === 'assoc' ? `关联文件(${assocFile.value})` : 'Working Copy'
}
// 基准=diff 的 original 侧:只管比较,不参与任何按钮判据、不管运算(载入与对比彻底解耦)
const anchorDict = computed<Record<string, any> | null>(() =>
  anchorKind.value === 'off' ? null : dictOf(anchorKind.value))
// 是否真的呈现 diff:选了基准 且 该源有内容。mountView 与 applyLayerDecorations 共用此判据,
// 防「选了基准但源为空」时后者误走 diff 分支去调 getModifiedEditor()。
const diffOn = computed(() => anchorKind.value !== 'off' && anchorDict.value !== null)
// 各 node 的物化层 yaml 键(来自 pattern topology,结构属性、对所有参数文件一致)
const mkByNode = computed<Record<string, string[]>>(() => {
  const p = view.effectivePattern
  return p ? materializeKeysByNode(p.topology) : {}
})
const btnStates = computed(() => computeButtonStates({
  parseOk: !parseError.value && editorDict.value !== null,
  editorDict: editorDict.value,
  snapDict: snapDict.value, assocDict: assocDict.value, wcDict: wcDict.value,
}))

function _reparse(text: string) {
  try { editorDict.value = yamlTextToDict(text); parseError.value = null }
  catch (e: any) { editorDict.value = null; parseError.value = String(e?.message ?? e) }
}
// F-A:三个提交动作(Write Copy/Save/Save As)点击那一刻强制吸收 pending 的 250ms debounce,
// 现读 sharedModel 现 parse——消除"提交的是上一版文本"的滞后窗(旧实现是现 getValue() 现 parse)。
function flushParse() {
  if (parseTimer) { clearTimeout(parseTimer); parseTimer = null }
  if (sharedModel.value) _reparse(sharedModel.value.getValue())
}

// ── 装载上下文:pattern/scan/打开时机 → 拉文件列表+关联内容,seed 编辑缓冲 ──
async function loadContext() {
  const pid = activePatternId.value
  if (!pid) return
  const gen = ++loadGen                                              // F4:代次守卫,防后发先至的旧请求覆盖新状态
  // 基准恢复:localStorage 记忆值;记忆为 wc 但该 pattern 当前无 WC → 回退 snapshot
  anchorKind.value = resolveAnchorKind(localStorage.getItem(ANCHOR_LS_KEY), wcDict.value !== null)
  let newFileList: string[]
  let newAssocDict: Record<string, any> | null
  let newAssocFile = 'params.yaml'
  try {
    newFileList = await listParamFiles(pid)
    // 持久化恢复:localStorage 记住的上次选择,文件仍在列表里才用(被删/改名回退 params.yaml)
    newAssocFile = resolveAssocFile(newFileList, _loadAssocFile(pid))
    newAssocDict = await readParamFile(pid, newAssocFile)
  } catch { newFileList = ['params.yaml']; newAssocFile = 'params.yaml'; newAssocDict = null }
  if (gen !== loadGen) return                        // 已被更新的一次 loadContext 取代,丢弃本次网络结果
  fileList.value = newFileList
  assocFile.value = newAssocFile                     // 代次守卫后才写,与 fileList/assocDict 同步
  assocDict.value = newAssocDict
  // 编辑区种子=当前生效参数(dev 表单常驻显示内存参数的对应物);不是 WC 回溯入口(Reset 不能回 WC)
  const seed = effectiveDict.value
  if (!monacoMod) monacoMod = (await import('../monaco')).default
  if (gen !== loadGen) return                        // import 也是 await,同样要防后发先至
  // F3:清 debounce 必须紧贴 dispose——await 期间旧编辑器仍在屏上可打字,那时新起的 timer
  // 会在 model 被 dispose 后触发 getValue() 而抛 "Model is disposed!"。
  if (parseTimer) { clearTimeout(parseTimer); parseTimer = null }
  disposeView()
  if (sharedModel.value) { sharedModel.value.dispose(); sharedModel.value = null }
  const text = seed ? dictToYamlText(seed) : ''
  const m = monacoMod.editor.createModel(text, 'yaml')
  m.onDidChangeContent(() => {
    if (parseTimer) clearTimeout(parseTimer)
    parseTimer = setTimeout(() => { _reparse(m.getValue()); applyLayerDecorations() }, 250)
  })
  sharedModel.value = m
  _reparse(text)
  mountView()
}

// 把 yaml 文本里的 where 行转成 monaco 整行背景 decoration 描述
function _layerDecos(yamlText: string): any[] {
  if (!monacoMod) return []
  return whereLineNumbers(yamlText, mkByNode.value).map(l => ({
    range: new monacoMod.Range(l + 1, 1, l + 1, 1),
    options: { isWholeLine: true, linesDecorationsClassName: 'layer-where-gutter' },
  }))
}
// 给当前视图(modified [+ original])刷 where 行高亮;开关关或无数据则清空
function applyLayerDecorations() {
  const ed = viewEditor.value
  if (!ed || !sharedModel.value || Object.keys(mkByNode.value).length === 0) {
    whereDecoMod = []; whereDecoOrig = []; return
  }
  if (diffOn.value) {
    const mod = ed.getModifiedEditor()
    const orig = ed.getOriginalEditor()
    whereDecoMod = mod.deltaDecorations(whereDecoMod, _layerDecos(sharedModel.value.getValue()))
    if (originalModel) whereDecoOrig = orig.deltaDecorations(whereDecoOrig, _layerDecos(originalModel.getValue()))
  } else {
    whereDecoMod = ed.deltaDecorations(whereDecoMod, _layerDecos(sharedModel.value.getValue()))
    whereDecoOrig = []
  }
}

// ── 视图挂载:按 diffOn 把共享 model 挂进单编辑器或 diff 的 modified 侧 ──
function mountView() {
  if (!editorEl.value || !sharedModel.value || !monacoMod) return
  disposeView()
  if (diffOn.value && anchorDict.value) {
    const de = monacoMod.editor.createDiffEditor(editorEl.value, {
      automaticLayout: true, minimap: { enabled: false }, fontSize: 12,
      originalEditable: false, renderSideBySide: true,
    })
    originalModel = monacoMod.editor.createModel(dictToYamlText(anchorDict.value), 'yaml')
    de.setModel({ original: originalModel, modified: sharedModel.value })
    viewEditor.value = de
  } else {
    viewEditor.value = monacoMod.editor.create(editorEl.value, {
      model: sharedModel.value, automaticLayout: true,
      minimap: { enabled: false }, fontSize: 12,
    })
  }
  applyLayerDecorations()
}
function disposeView() {
  whereDecoMod = []; whereDecoOrig = []
  if (viewEditor.value) { viewEditor.value.dispose(); viewEditor.value = null }
  if (originalModel) { originalModel.dispose(); originalModel = null }  // 显式释放,防 model 注册表泄漏
}
function disposeAll() {
  if (parseTimer) { clearTimeout(parseTimer); parseTimer = null }   // F3:组件卸载时清理未触发的 debounce
  disposeView()
  if (sharedModel.value) { sharedModel.value.dispose(); sharedModel.value = null }
}

let loadedPid: string | null = null      // sharedModel 当前承载的 pattern(toast 文案「原 pattern」用)
let loadedScanTs: string | null = null   // sharedModel 当前承载的 scan 身份;与 loadedPid 复合判别是否要重装(F1)
watch([() => props.open, activePatternId, () => view.scanFile?.scan.scan_ts ?? null],
    async ([open, pid, scanTs]) => {
  if (!open) { disposeView(); return }   // 关抽屉只卸视图,保 sharedModel——重开不丢未存盘编辑
  await nextTick()   // v-if 刚翻 true 时 DOM 未 patch
  const samePid = pid === loadedPid
  const sameScan = scanTs === loadedScanTs
  if (sharedModel.value && samePid && sameScan) { mountView(); return }  // 重开且 pattern/scan 均未变:直接挂,文本保持
  if (sharedModel.value && loadedPid !== null && assocDict.value
      && editorDict.value && !dictsEqual(editorDict.value, assocDict.value)) {
    view.showToast(samePid
      ? '编辑区未存盘内容已随 scan 切换丢弃'
      : `编辑区未存盘内容已随 pattern 切换丢弃(原 ${loadedPid})`)   // 修正 1:事后提示,适配 pattern/scan 两种切换
  }
  loadedPid = pid ?? null
  loadedScanTs = scanTs ?? null
  void loadContext()
}, { flush: 'post' })
watch(anchorKind, k => {   // 换基准(含开/关对比):持久化 + 重挂视图(共享 model 不动,编辑不丢)
  localStorage.setItem(ANCHOR_LS_KEY, k)
  if (props.open) mountView()
})
watch(assocDict, () => {   // 基准=关联文件时,Load/Save/Save As 换了关联文件内容→重挂 diff 刷新 original 侧
  if (props.open && anchorKind.value === 'assoc') mountView()
})
watch(wcDict, d => {       // WC 被删(Clear)时基准不能停在空源:回退 snapshot(该 watch 触发重挂)
  if (d === null && anchorKind.value === 'wc') anchorKind.value = 'snapshot'
})
onBeforeUnmount(disposeAll)

// 切下拉:只换关联文件标识 + 内容(供 Save 目标 + 锚=关联文件时 diff original 侧刷新),不载入编辑区。
// 载入编辑区走独立 Load 按钮(onLoadAssoc)。切下拉不碰 sharedModel → 无需 dirty confirm、不丢未存盘改动。
function onLoadSelect(e: Event) {
  const name = (e.target as HTMLSelectElement).value
  if (name === assocFile.value) return
  const gen = loadGen   // F-B:代次守卫(读取,非 ++)——察觉 await 期间是否发生过 loadContext 重载
  void (async () => {
    try {
      const d = await readParamFile(activePatternId.value!, name)
      if (gen !== loadGen) return   // F-B:await 期间已被后发先至的 loadContext 取代,丢弃(不写组件状态)
      assocFile.value = name
      _saveAssocFile(activePatternId.value!, name)   // 持久化关联文件选择(per pid,跨刷新恢复)
      assocDict.value = d                            // watch(assocDict) 在锚=关联文件时自动刷新 diff original 侧
    } catch (err: any) {
      alert(`加载失败: ${err?.message ?? err}`)
      ;(e.target as HTMLSelectElement).value = assocFile.value   // F5:还原下拉
    }
  })()
}
// 三源载入的唯一实现(源→编辑区),取代原 onReset/onLoadAssoc/onLoadWc 三个同形函数。
// 覆盖性且 monaco setValue 清 undo 栈(不可 Ctrl+Z),故必 confirm;按钮灰化已保证
// 「编辑区==源」时点不到,所以这里恒确认一次并不冗余(与原三者的实际行为等价)。
function loadFrom(kind: SourceKind) {
  const src = dictOf(kind)
  if (!src) return
  flushParse()   // F-A:先吸收 pending debounce,确保覆盖判断基于最新文本
  if (!confirm(`编辑区将被 ${sourceLabel(kind)} 覆盖(不可撤销),继续?`)) return
  sharedModel.value?.setValue(dictToYamlText(src))
  flushParse()   // F-A:setValue 后立即同步 reparse,消除 250ms 内 editorDict 仍是旧 dict 的窗口
}
function onWriteCopy() {
  flushParse()   // F-A:提交前吸收 pending debounce
  const pid = activePatternId.value
  if (!pid) return
  if (parseError.value || !editorDict.value) { view.showToast('yaml 解析失败,请先修正'); return }
  if (!snapDict.value) return
  // 解耦(严格版,spec §2):只写内容轴。ensureWorkingCopy 保证副本存在(创建为 disabled),
  // updateWorkingCopy 写入编辑区内容;enabled 由 chip 独占,探索态下 updateWorkingCopy 自动重算。
  view.ensureWorkingCopy(pid, snapDict.value)
  view.updateWorkingCopy(pid, JSON.parse(JSON.stringify(editorDict.value)))
}
async function onSave() {
  flushParse()   // F-A:提交前吸收 pending debounce
  const pid = activePatternId.value
  if (!pid) return
  if (parseError.value || !editorDict.value) { view.showToast('yaml 解析失败,请先修正'); return }
  const gen = loadGen   // F-B:代次守卫(读取,非 ++)
  const fname = assocFile.value
  const dict = editorDict.value
  const warn = fname === 'params.yaml'
    ? `将编辑区写入 ${pid} 的 params.yaml(基线)?\n影响 CLI 与后续新扫的缺省参数(注释保留)。`
    : `将编辑区写入 ${fname}?`
  if (!confirm(warn)) return
  try {
    await saveParamFile(pid, fname, dict)
    // F-B:磁盘写入(写到 pid 目录下的 fname)已经发生,与代次无关;代次不符时只跳过组件状态更新,
    // 成功 toast 仍要给(用户需要知道保存确实成功了)。
    if (gen === loadGen) assocDict.value = JSON.parse(JSON.stringify(dict))
    view.showToast(`已保存 ${fname}`)
  } catch (e: any) { alert(`保存失败: ${e?.message ?? e}`) }
}
async function onSaveAs() {
  flushParse()   // F-A:提交前吸收 pending debounce
  const pid = activePatternId.value
  if (!pid) return
  if (parseError.value || !editorDict.value) { view.showToast('yaml 解析失败,请先修正'); return }
  const gen = loadGen   // F-B:代次守卫(读取,非 ++)
  const raw = prompt('新文件名(app 目录下,.yaml 可省略):')
  if (raw === null) return
  const name = normalizeSaveAsName(raw)
  if (!name) { alert('文件名只允许字母/数字/下划线/连字符'); return }
  if (fileList.value.includes(name) && !confirm(`${name} 已存在,覆盖?`)) return
  const dict = editorDict.value
  try {
    await saveParamFile(pid, name, dict)
    // F-B:磁盘写入已经发生,与代次无关;代次不符时只跳过组件状态更新,成功 toast 仍要给。
    if (gen === loadGen) {
      if (!fileList.value.includes(name)) fileList.value = [...fileList.value, name]
      assocFile.value = name                                   // dev 式:关联切到新文件
      assocDict.value = JSON.parse(JSON.stringify(dict))
    }
    view.showToast(`已另存为 ${name}`)
  } catch (e: any) { alert(`另存失败: ${e?.message ?? e}`) }
}
function onClearWc() {
  const pid = activePatternId.value
  if (pid && confirm('删除工作副本?(内存参数与 localStorage 草稿一并删除,回浏览态)'))
    view.discardWorkingCopy(pid)
}
const confirmingDelete = ref(false)
function onDeleteParam() {
  if (assocFile.value === 'params.yaml') return       // 防御:基线不删(模板已 v-if 隐藏)
  confirmingDelete.value = true
}
async function performDeleteParam() {
  const pid = activePatternId.value
  const name = assocFile.value
  confirmingDelete.value = false
  if (!pid || name === 'params.yaml') return
  try {
    await deleteParamFile(pid, name)
    // 本地 splice 刷新 fileList(省一次 GET,单用户无害)
    fileList.value = fileList.value.filter(f => f !== name)
    // 关联切回 params.yaml + 重载内容
    assocFile.value = 'params.yaml'
    _saveAssocFile(pid, 'params.yaml')
    assocDict.value = await readParamFile(pid, 'params.yaml')
    // ScanConfigDialog 的参数源 LS 若指向被删名则清(localStorage 全局可清;不清也无害,resolve 会回退)
    if (localStorage.getItem('p2wc:scan:paramSource:' + pid) === name)
      localStorage.removeItem('p2wc:scan:paramSource:' + pid)
    view.showToast(`已删除 ${name},关联已回退 params.yaml`)
  } catch (e: any) {
    alert(`删除失败: ${e?.message ?? e}`)
  }
}
</script>

<style scoped>
/* 悬浮窗:left/top/width/height 由 useFloatingPanel 的 rect 驱动(内联 style)。
   刻意不用 transform 平移——面板内嵌 monaco,祖先带 transform 会成为新包含块,
   补全框/hover 浮层的定位会跑偏。 */
.drawer { position: fixed; background: #fff; border: 1px solid #e2e8f0; border-radius: 6px;
          box-shadow: 0 6px 24px rgba(0,0,0,.16);
          display: flex; flex-direction: column; z-index: 60; padding: 10px; }
.drawer.moving { user-select: none; }   /* 拖动/缩放中禁选,避免在面板内划出选区 */
/* wrap 兜底:按钮多/文件名长时不截断 ×;整条标题栏即拖拽把手(其中的 button 由 handler 放行) */
.hdr { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; cursor: move; }
.hdr .close { margin-left: auto; cursor: pointer; }
.coord-note { font-size: 11px; color: #94a3b8; margin: 4px 0; }
:deep(.layer-where-gutter) { background: #d97706; width: 3px !important; margin-left: 4px; }
/* 三源对称表:整表单 grid + 行 display:contents,使四列跨行对齐 */
.src-table { display: grid; grid-template-columns: minmax(0, 1fr) auto auto 28px;
             align-items: center; gap: 4px 6px; margin: 6px 0; font-size: 12px; color: #475569; }
.src-row { display: contents; }
.src-row > span, .src-row > label { display: inline-flex; align-items: center; gap: 4px; min-width: 0; }
.src-head > * { font-size: 11px; color: #94a3b8; padding-bottom: 3px; border-bottom: 1px solid #e2e8f0; }
.c-src select { max-width: 118px; }
.c-none { color: #cbd5e1; justify-content: center; }
.c-anchor { justify-content: center; cursor: pointer; }
.c-anchor input { cursor: pointer; }
.editor { flex: 1; min-height: 0; border: 1px solid #e2e8f0; }
.drawer button:not(.close) { font-size: 12px; padding: 3px 8px; }   /* 抽屉内所有操作按钮(除关闭×)统一紧凑字号,不随位置变 */
.err { color: #dc2626; font-size: 12px; margin-top: 4px; }
.del-btn { font-size: 13px; padding: 2px 6px; cursor: pointer; border: 1px solid #dc2626;
           color: #dc2626; background: #fff; border-radius: 4px; line-height: 1; }
.del-btn:hover { background: #fef2f2; }
.confirm-backdrop { position: absolute; inset: 0; background: rgba(0,0,0,.4); z-index: 70;
                    display: flex; align-items: center; justify-content: center; }
.confirm-card { background: #fff; border-radius: 8px; padding: 16px; max-width: 320px;
                box-shadow: 0 4px 16px rgba(0,0,0,.2); }
.confirm-card p { margin: 0 0 8px; font-size: 13px; }
.confirm-card .warn { color: #dc2626; }
.confirm-actions { display: flex; gap: 8px; justify-content: flex-end; }
.confirm-actions button { font-size: 12px; padding: 4px 12px; cursor: pointer; }
.confirm-actions .btn-stop { background: #dc2626; color: #fff; border: none; border-radius: 4px; }
/* 右下角缩放把手:两道斜纹(色盲友好——靠形状不靠色相),压在 monaco 之上 */
.resize-handle { position: absolute; right: 0; bottom: 0; width: 16px; height: 16px;
                 cursor: nwse-resize; z-index: 80;
                 background: linear-gradient(135deg, transparent 0 45%, #94a3b8 45% 55%, transparent 55% 70%,
                                                     #94a3b8 70% 80%, transparent 80%); }
.resize-handle:hover { background: linear-gradient(135deg, transparent 0 45%, #475569 45% 55%, transparent 55% 70%,
                                                           #475569 70% 80%, transparent 80%); }
</style>
