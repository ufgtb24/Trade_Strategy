<!-- 参数编辑抽屉(dev 式):关联文件下拉(Load)+ 常驻可编辑 monaco + 对比 checkbox + 锚 radio(snapshot|关联文件)
     + Write Copy/Reset/Save/Save As(enable 承载 dirty)+ 清除副本。
     spec: docs/superpowers/specs/2026-07-22-params-editor-dev-parity-design.md
         + docs/research/params-editor-followup-decisions.md(D1-D6/P1-P3,冲突以此为准)
     三层状态:File(app 目录多 yaml,assocFile 关联)→ Editor(共享 textModel)→ Memory(WC.currentDict,Write Copy 产物)。
     共享 model 让 diff 的 modified 侧=编辑缓冲本身:diff 可编辑/切视图零丢字/diff=编辑区实时 vs 当前锚。
     锚模型(D6):比较/还原点只有 snapshot 与关联文件;WC 是纯运行时层,不作锚、无回溯入口。-->
<template>
  <div v-if="open" class="drawer" data-testid="wc-drawer">
    <div class="hdr">
      <strong>{{ activePatternId }} 参数</strong>
      <label class="assoc">关联:
        <select :value="assocFile" data-testid="assoc-select" @change="onLoadSelect">
          <option v-for="f in fileList" :key="f" :value="f">{{ f }}</option>
        </select>
      </label>
      <button v-if="assocFile !== 'params.yaml'" class="del-btn" data-testid="delete-param"
              :title="`删除关联文件 ${assocFile}`" @click="onDeleteParam">🗑</button>
      <button :disabled="!btnStates.canLoadAssoc"
              :title="btnStates.canLoadAssoc ? `把 ${assocFile} 载入编辑区` : '编辑区已与关联文件一致'"
              data-testid="load-assoc" @click="onLoadAssoc">Load</button>
      <button :disabled="!btnStates.canSave"
              :title="btnStates.canSave ? `写入 ${assocFile}` : '与关联文件一致,无需保存'"
              @click="onSave">Save</button>
      <button :disabled="!btnStates.canSaveAs"
              title="另存为 app 目录下新文件,关联切过去"
              @click="onSaveAs">Save As</button>
      <button class="close" @click="$emit('close')">×</button>
    </div>
    <div class="coord-note">口径:label_horizon / 扫描窗恒锚 scan 设置,不随参数探索变。</div>
    <div class="view-ctl">
      <label class="diff-toggle" title="并排显示当前锚(左,只读)与编辑区(右,可编辑)">
        <input type="checkbox" data-testid="diff-toggle" :checked="diffCompare" @change="onDiffToggle" />
        对比
      </label>
      <template v-if="diffCompare">
        <span class="anchor-sel">锚:
          <label><input type="radio" value="snapshot" v-model="anchorKind"
                        data-testid="anchor-snapshot" /> snapshot</label>
          <label><input type="radio" value="assoc" v-model="anchorKind"
                        data-testid="anchor-assoc" /> 关联文件</label>
        </span>
        <button :disabled="!btnStates.canReset"
                :title="btnStates.canReset ? `编辑区重置为 ${anchorLabel}` : `编辑区与 ${anchorLabel} 一致`"
                @click="onReset">Reset</button>
      </template>
    </div>

    <div ref="editorEl" class="editor"></div>
    <div v-if="parseError" class="err">{{ parseError }}</div>
    <div v-if="previewError" class="err">现算失败: {{ previewError }}</div>

    <div class="btns">
      <button :disabled="!btnStates.canWriteCopy"
              :title="btnStates.canWriteCopy ? '编辑区 → Working Copy(只写副本,不切换浏览/探索视图;探索态下立即重算)' : '编辑区与 Working Copy 一致,无需写入'"
              @click="onWriteCopy">Write Copy</button>
      <template v-if="workingCopy[activePatternId ?? '']">
        <button class="low-freq load-wc" :disabled="!btnStates.canLoadWc"
                :title="btnStates.canLoadWc ? '编辑区还原为 Working Copy,使其可见/可续编/可与锚对比' : '编辑区已与 Working Copy 一致'"
                @click="onLoadWc">Load Copy</button>
        <button class="low-freq clear-wc"
                title="删除工作副本(内存参数+localStorage 草稿),回浏览态;不碰编辑区"
                @click="onClearWc">Clear Copy</button>
      </template>
    </div>
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
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, ref, shallowRef, watch } from 'vue'
import { storeToRefs } from 'pinia'
import { useViewStore } from '../stores/view'
import { listParamFiles, readParamFile, saveParamFile, deleteParamFile } from '../api'
import { dictToYamlText, yamlTextToDict } from './workingCopyYaml'
import { computeButtonStates, dictsEqual, normalizeSaveAsName, resolveAssocFile } from './paramsEditorState'
import { materializeKeysByNode, whereLineNumbers } from './workingCopyLayers'

const props = defineProps<{ open: boolean }>()
defineEmits<{ close: [] }>()
const view = useViewStore()
const { activePatternId, previewError, workingCopy } = storeToRefs(view)

// ── File 层状态 ──
const fileList = ref<string[]>([])
const assocFile = ref('params.yaml')                       // 当前关联文件(dev current_file_path)
const assocDict = ref<Record<string, any> | null>(null)    // 关联文件内容(Save enable 比较基准 + 锚=assoc 的源)
// ── Editor 层状态 ──
const editorDict = ref<Record<string, any> | null>(null)   // debounce parse 结果
const parseError = ref<string | null>(null)
const DIFF_LS_KEY = 'p2wc:drawer:diffMode'
const diffCompare = ref(localStorage.getItem(DIFF_LS_KEY) === '1')
// 关联文件选择持久化(per pid;文件列表是 pattern app 目录内容,与 scan 无关 → key 不带 scan_ts)
const ASSOC_LS_PREFIX = 'p2wc:assoc:'
function _loadAssocFile(pid: string): string | null { return localStorage.getItem(ASSOC_LS_PREFIX + pid) }
function _saveAssocFile(pid: string, name: string): void { localStorage.setItem(ASSOC_LS_PREFIX + pid, name) }
const anchorKind = ref<'snapshot' | 'assoc'>('snapshot')   // 锚选择:不持久化,每次打开默认 snapshot

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
// 锚(D6/P2):diff original 侧与 Reset 目标;只管比较/还原,不管运算
const anchorDict = computed<Record<string, any> | null>(() =>
  anchorKind.value === 'snapshot' ? snapDict.value : assocDict.value)
const anchorLabel = computed(() =>
  anchorKind.value === 'snapshot' ? 'snapshot' : `关联文件(${assocFile.value})`)
// 当前生效运算参数:探索态=WC.currentDict;浏览态恒=snapshot(与锚选择无关)
const effectiveDict = computed<Record<string, any> | null>(() => {
  const pid = activePatternId.value
  if (!pid) return null
  const wc = workingCopy.value[pid]
  return wc?.enabled ? wc.currentDict : snapDict.value
})
// WC.currentDict(无 WC 为 null):「载入副本」的源与 enable 判据(D7:查看/续编入口,不作锚)
const wcDict = computed<Record<string, any> | null>(() =>
  workingCopy.value[activePatternId.value ?? '']?.currentDict ?? null)
// 各 node 的物化层 yaml 键(来自 pattern topology,结构属性、对所有参数文件一致)
const mkByNode = computed<Record<string, string[]>>(() => {
  const p = view.effectivePattern
  return p ? materializeKeysByNode(p.topology) : {}
})
const btnStates = computed(() => computeButtonStates({
  parseOk: !parseError.value && editorDict.value !== null,
  editorDict: editorDict.value, assocDict: assocDict.value,
  anchorDict: anchorDict.value, wcDict: wcDict.value,
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
  anchorKind.value = 'snapshot'                                       // 每次装载重置锚选择(不持久化)
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
  if (diffCompare.value) {
    const mod = ed.getModifiedEditor()
    const orig = ed.getOriginalEditor()
    whereDecoMod = mod.deltaDecorations(whereDecoMod, _layerDecos(sharedModel.value.getValue()))
    if (originalModel) whereDecoOrig = orig.deltaDecorations(whereDecoOrig, _layerDecos(originalModel.getValue()))
  } else {
    whereDecoMod = ed.deltaDecorations(whereDecoMod, _layerDecos(sharedModel.value.getValue()))
    whereDecoOrig = []
  }
}

// ── 视图挂载:按 diffCompare 把共享 model 挂进单编辑器或 diff 的 modified 侧 ──
function mountView() {
  if (!editorEl.value || !sharedModel.value || !monacoMod) return
  disposeView()
  if (diffCompare.value && anchorDict.value) {
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
watch(diffCompare, v => {
  localStorage.setItem(DIFF_LS_KEY, v ? '1' : '0')
  if (props.open) mountView()
})
watch(anchorKind, () => {   // 换锚:diff 开着时重建 original 侧(共享 model 不动,编辑不丢)
  if (props.open && diffCompare.value) mountView()
})
watch(assocDict, () => {   // 锚=关联文件时,Load/Save/Save As 换了关联文件内容→重挂 diff 刷新 original 侧
  if (props.open && diffCompare.value && anchorKind.value === 'assoc') mountView()
})
onBeforeUnmount(disposeAll)

function onDiffToggle(e: Event) {
  diffCompare.value = (e.target as HTMLInputElement).checked
}
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
// 载入关联文件到编辑区(原 onLoadSelect 的载入部分,解耦后为独立 Load 按钮)。
// dirty 时 confirm(覆盖性 + setValue 清 undo 栈,同 onReset/onLoadWc);载入后 flushParse 消除 debounce 窗。
function onLoadAssoc() {
  if (!assocDict.value) return
  flushParse()   // F-A:dirty 判定现读现 parse
  const dirty = editorDict.value && !dictsEqual(editorDict.value, assocDict.value)
  if ((dirty || parseError.value)
      && !confirm(`编辑区有未存盘改动,丢弃并载入 ${assocFile.value}?`)) return
  sharedModel.value?.setValue(dictToYamlText(assocDict.value))
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
function onReset() {
  // D5:覆盖性操作且 monaco setValue 清 undo 栈(不可 Ctrl+Z),必 confirm;文案动态带锚名
  if (!anchorDict.value) return
  if (!confirm(`编辑区将被 ${anchorLabel.value} 覆盖(不可撤销),继续?`)) return
  sharedModel.value?.setValue(dictToYamlText(anchorDict.value))
  flushParse()   // F-A:setValue 后立即同步 reparse,消除"重置后立刻点 Save 写入重置前内容"的窗口
}
function onLoadWc() {
  // D7:编辑区还原为 WC → WC 以编辑区形态可见,可续编、可与两锚对比;载入后 Write Copy 自动灰(编辑区==副本)
  if (!wcDict.value) return
  if (!confirm('编辑区将被 Working Copy 覆盖(不可撤销),继续?')) return
  sharedModel.value?.setValue(dictToYamlText(wcDict.value))
  flushParse()   // F-A:setValue 后立即同步 reparse,与 onReset 同一手法
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
.drawer { position: fixed; top: 0; right: 0; width: 480px; height: 100vh; background: #fff;
          border-left: 1px solid #e2e8f0; box-shadow: -4px 0 16px rgba(0,0,0,.08);
          display: flex; flex-direction: column; z-index: 60; padding: 10px; }
.hdr { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; }   /* wrap 兜底:按钮多/文件名长时不截断 × */
.hdr .close { margin-left: auto; }
.assoc { font-size: 12px; color: #475569; display: inline-flex; align-items: center; gap: 4px; }
.coord-note { font-size: 11px; color: #94a3b8; margin: 4px 0; }
:deep(.layer-where-gutter) { background: #d97706; width: 3px !important; margin-left: 4px; }
.view-ctl { display: flex; align-items: center; gap: 12px; margin-bottom: 4px; }
.diff-toggle { font-size: 12px; color: #475569; display: inline-flex; align-items: center;
               gap: 4px; cursor: pointer; }
.anchor-sel { font-size: 12px; color: #475569; display: inline-flex; align-items: center; gap: 6px; }
.anchor-sel label { display: inline-flex; align-items: center; gap: 2px; cursor: pointer; }
.editor { flex: 1; min-height: 0; border: 1px solid #e2e8f0; }
.btns { display: flex; gap: 6px; margin-top: 8px; flex-wrap: wrap; align-items: center; }
.drawer button:not(.close) { font-size: 12px; padding: 3px 8px; }   /* 抽屉内所有操作按钮(除关闭×)统一紧凑字号,不随位置变 */
.low-freq { opacity: .75; }
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
</style>
