// 参数编辑 / 扫描配置的纯函数层(monaco 无关,可测)。
// spec: docs/superpowers/specs/2026-07-22-params-editor-dev-parity-design.md §6
//      + docs/superpowers/specs/2026-07-23-write-copy-chip-decouple-design.md §3.1(Write Copy 解耦)

export function dictsEqual(a: unknown, b: unknown): boolean {
  if (a === b) return true
  if (typeof a !== 'object' || typeof b !== 'object' || a === null || b === null) return false
  if (Array.isArray(a) !== Array.isArray(b)) return false
  if (Array.isArray(a)) {
    const bb = b as unknown[]
    return a.length === bb.length && a.every((v, i) => dictsEqual(v, bb[i]))
  }
  const ka = Object.keys(a as object), kb = Object.keys(b as object)
  if (ka.length !== kb.length) return false
  return ka.every(k => dictsEqual((a as any)[k], (b as any)[k]))
}

export interface ButtonStateInput {
  parseOk: boolean
  editorDict: Record<string, any> | null    // parse 失败为 null
  assocDict: Record<string, any> | null     // 当前关联文件内容(未拉到为 null)
  anchorDict: Record<string, any> | null    // Reset/diff 锚:锚 radio 二选一(snapshot|关联文件)的当前值
  wcDict: Record<string, any> | null        // WC.currentDict(无 WC 为 null;Write Copy 与「载入副本」判据)
}
export interface ButtonStates {
  canWriteCopy: boolean; canReset: boolean; canSave: boolean; canSaveAs: boolean; canLoadWc: boolean; canLoadAssoc: boolean
}

export function computeButtonStates(s: ButtonStateInput): ButtonStates {
  const ed = s.parseOk ? s.editorDict : null
  return {
    // Write Copy=内容轴唯一入口(解耦 spec §3.1):无 WC → parseOk 即可点(空转创建,决策3);
    // 有 WC → 编辑区≠副本才有写入意义。永不碰 enabled(视图轴归 chip)。
    canWriteCopy: !!ed && (s.wcDict === null || !dictsEqual(ed, s.wcDict)),
    // Reset:偏离锚 或 parse 失败(改坏 yaml 的逃生门必须可点)
    canReset: !s.parseOk || (!!ed && !!s.anchorDict && !dictsEqual(ed, s.anchorDict)),
    // Save:异于关联文件才有存盘意义(取代「● 未存盘」标)
    canSave: !!ed && s.assocDict !== null && !dictsEqual(ed, s.assocDict),
    canSaveAs: s.parseOk,
    // 载入副本(D7):WC 存在且编辑区≠WC(或 parse 失败逃生);把 WC 装进编辑区使之可见/可续编
    canLoadWc: s.wcDict !== null && (!s.parseOk || !ed || !dictsEqual(ed, s.wcDict)),
    // 载入关联文件:关联文件已拉到且编辑区≠其内容(或 parse 失败逃生)才亮。
    // 切下拉只换 assocFile/assocDict(标识+内容,供 diff 锚=关联文件刷新),不载入编辑区;载入走独立 Load 按钮
    canLoadAssoc: s.assocDict !== null && (!s.parseOk || !ed || !dictsEqual(ed, s.assocDict)),
  }
}

const _NAME_RE = /^[A-Za-z0-9_\-]+\.yaml$/

export function normalizeSaveAsName(input: string): string | null {
  const t = input.trim()
  if (!t) return null
  const withExt = t.endsWith('.yaml') ? t : `${t}.yaml`
  return _NAME_RE.test(withExt) ? withExt : null
}

// 持久化关联文件恢复:persisted 仍在当前文件列表里才用,否则回退 fallback(默认 params.yaml)。
// 防文件被删/改名后恢复到不存在的文件。localStorage 值是文件名字符串(per pid,与 scan 无关)。
export function resolveAssocFile(fileList: string[], persisted: string | null, fallback = 'params.yaml'): string {
  return persisted && fileList.includes(persisted) ? persisted : fallback
}

// ScanConfigDialog pattern 子集持久化恢复:JSON.parse → 仅留当前仍存在的 pid。
// 返回 null = 无有效记录(含 filtered 后空)→ 调用方 selectAll(避免 Start 按钮灰着打开)。
export function restoreSelectedPatterns(stored: string | null, allPids: string[]): string[] | null {
  if (!stored) return null
  let arr: unknown
  try { arr = JSON.parse(stored) } catch { return null }
  if (!Array.isArray(arr)) return null
  const valid = new Set(allPids)
  const filtered = arr.filter((x): x is string => typeof x === 'string' && valid.has(x))
  return filtered.length > 0 ? filtered : null
}

// ScanConfigDialog 参数源恢复:'wc' 单独判 hasWc;具名 .yaml 委托 resolveAssocFile;
// 首次(null)→ fallback=params.yaml(用户确认统一,放弃「有 WC 选 WC」动线)。
// 'wc' 必须前置 hasWc 分支,否则 resolveAssocFile 会把 'wc' 当不在列表的文件、漏掉 WC 仍在的合法情形。
export function resolveParamSource(
  persisted: string | null, fileList: string[], hasWc: boolean, fallback = 'params.yaml',
): string {
  if (persisted === 'wc') return hasWc ? 'wc' : fallback
  return resolveAssocFile(fileList, persisted, fallback)
}
