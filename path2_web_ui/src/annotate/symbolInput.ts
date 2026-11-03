/**
 * 顶栏 symbol 输入框:把用户敲的文字解析成要打开的股票代码。
 *
 * 规则:去首尾空白、转大写(股票列表里的代码全是大写);在股票列表里 → 打开它;不在 → not_found。
 * 股票列表没拿到(null)时不拦,交给后端判(不存在 404 / 不合法 400)。
 */
export type SymbolInputResult =
  | { kind: 'empty' }
  | { kind: 'ok'; symbol: string }
  | { kind: 'not_found'; symbol: string }

export function resolveSymbolInput(raw: string, list: ReadonlySet<string> | null): SymbolInputResult {
  const symbol = raw.trim().toUpperCase()
  if (!symbol) return { kind: 'empty' }
  if (list && !list.has(symbol)) return { kind: 'not_found', symbol }
  return { kind: 'ok', symbol }
}
