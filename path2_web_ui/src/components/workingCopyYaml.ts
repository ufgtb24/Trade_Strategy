// WC dict ⇄ yaml 文本(编辑器 wire 格式)。js-yaml 仅前端展示/编辑用,后端落盘走 ruamel。
import { dump, load } from 'js-yaml'

export function dictToYamlText(d: Record<string, any>): string {
  return dump(d, { sortKeys: false, lineWidth: 120 })
}
export function yamlTextToDict(text: string): Record<string, any> {
  const v = load(text)
  if (v === null || typeof v !== 'object' || Array.isArray(v)) throw new Error('yaml 根必须是映射')
  return v as Record<string, any>
}
