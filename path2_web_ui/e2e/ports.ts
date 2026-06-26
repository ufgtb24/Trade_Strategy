import { readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import yaml from 'js-yaml'

// 单点读取仓库根 configs/path2_web.yaml,导出 Node 侧用到的派生量。
// 改端口请改 configs/path2_web.yaml 的 backend_port / frontend_port。
const here = dirname(fileURLToPath(import.meta.url))
const yamlPath = resolve(here, '../../configs/path2_web.yaml')
const cfg = yaml.load(readFileSync(yamlPath, 'utf8')) as {
  backend_port?: number
  frontend_port?: number
}

export const backendPort = cfg.backend_port ?? 8000
export const frontendPort = cfg.frontend_port ?? 5173
export const apiBase = `http://localhost:${backendPort}`
export const baseURL = `http://localhost:${frontendPort}`
