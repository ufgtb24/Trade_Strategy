/// <reference types="vite/client" />
// monaco 精简单例:仅 editor core + yaml 语法。经动态 import 消费(懒加载,不进主 bundle)。
// vite/client 类型声明补 `*?worker` 环境类型(本仓库此前无 worker 型 import,故未见先例)。
// 注:monaco-editor 0.56 起子路径导出改用 package.json "exports" 字段(./* → ./esm/vs/*.js),
// 深路径不再带 esm/vs 前缀,故实际 import 路径与旧版教程/文档不同。
import * as monaco from 'monaco-editor/editor/editor.api'
import 'monaco-editor/languages/definitions/yaml/register'
import EditorWorker from 'monaco-editor/editor/editor.worker?worker'

;(self as any).MonacoEnvironment = { getWorker: () => new EditorWorker() }
export default monaco
