// 参数层判定纯函数(不依赖 monaco):把 topology 的 materialize_keys 投影成
// { node_id: 物化键[] },再扫描 yaml 文本找出 where 层(= section 内非物化键)所在行号。
// 供 WorkingCopyDrawer 的 decoration 接入层消费;本文件可纯单测(jsdom 无需 monaco)。
import type { Topology } from '../types'

/** topology.nodes → { node_id: materialize_keys }(缺失字段防御为空数组)。 */
export function materializeKeysByNode(topology: Topology): Record<string, string[]> {
  const out: Record<string, string[]> = {}
  for (const n of topology.nodes) out[n.node_id] = n.materialize_keys ?? []
  return out
}

const SECTION_RE = /^([A-Za-z_][\w]*):\s*$/
const KV_RE = /^\s+([A-Za-z_][\w]*):/

/** 扫描 yaml 文本,返回 where 层键所在行号(0-based)。
 *  只在 mkByNode 已知、且 materialize_keys 非空的 node section 内判定;
 *  非节点 section(如 edges)/未知 section/空 materialize_keys(旧 scan)跳过,避免误标。
 *  where 层 = section 内键 ∉ materialize_keys。 */
export function whereLineNumbers(yamlText: string, mkByNode: Record<string, string[]>): number[] {
  if (Object.keys(mkByNode).length === 0) return []
  const out: number[] = []
  let section: string | null = null
  yamlText.split('\n').forEach((line, i) => {
    const sec = line.match(SECTION_RE)
    if (sec) { section = sec[1]; return }
    const kv = line.match(KV_RE)
    // 只对有 materialize_keys 数据的 section 判定;空数组(旧 scan 未含该字段/未知 node)
    // 跳过,避免误把整个 section 的键都标 where
    if (kv && section && section in mkByNode && mkByNode[section].length > 0) {
      if (!mkByNode[section].includes(kv[1])) out.push(i)
    }
  })
  return out
}
