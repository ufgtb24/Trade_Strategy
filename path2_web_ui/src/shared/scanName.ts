/** 扫描结果名称校验(与后端 path2_web/api.py 的 _SCAN_NAME_RE 同口径)。
 * \w 含中文;天然排除 . / \ 空格(防路径穿越)。空串 = 默认时间戳,合法。
 * 返回 null 表示合法,否则返回错误提示文案。 */
const NAME_RE = /^[\p{L}\p{N}_\-]+$/u   // Unicode 字母(\p{L} 含中文)/数字/下划线/连字符,与后端 \w(re.UNICODE)同口径
export function validateScanName(name: string): string | null {
  const t = name.trim()
  if (!t) return null
  return NAME_RE.test(t) ? null : '名称只能含字母、数字、下划线、连字符、中文'
}
