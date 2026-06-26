# Stop Scan: Save / Discard / Continue 设计

## Context

path2_web UI 当前的「停止扫描」按下后无条件杀 worker、丢弃已聚到的部分命中结果（`path2_web/scan.py` 在 `cancel_event.is_set()` 时直接 `raise ScanCancelled()`，绕过 `write_result_file()`）。用户经常等了很久看到「再扫几只就够用」，但只能"扫完才停"或"白扫一场"——没有"我够了，存下来"的路径。

本设计加一种"停止时让用户选保存/丢弃/反悔"的能力，把已聚到的部分命中作为正常 scan 结果文件落盘，沿用本会话刚做的"扫描结束自动加载新结果"路径直接呈现，并在「打开历史…」里和完整扫描区分开。

## 用户体验

```
点击「停止扫描」
   │
   ├─ 当前 hits == 0  ──→ 直接停止 + 丢弃（无 modal、当前行为）
   │
   └─ 当前 hits > 0   ──→ 弹 StopScanDialog
                          │  文案：「当前已经命中 X，是否保存？」
                          │  X 实时跟 SSE progress 跳，扫描在 modal 期间继续在跑
                          │
                          ├─ 「保存」    ──→ 后端落盘 partial 文件 → SSE done 走成功 shape
                          │                  → 主视图自动加载（沿用本会话刚做的 auto-load）
                          ├─ 「丢弃」    ──→ 当前 cancel 行为（杀 worker、不落盘、SSE done cancelled）
                          └─ 「继续扫描」──→ 关 modal、什么也不做、扫描继续
                          
                          Esc / 点外面：无效（不响应）
                          
                          扫描自然跑完（modal 还开着）：modal 自动关、走完整扫描结束流程
```

### 「未完成」标记

保存下来的 partial 文件，在「打开历史…」列表里那一行带「未完成」小标（或类似词），与完整扫描一眼可分。主视图加载时**不**特别 badge——加载体验与完整结果一致，是否完整由历史列表负责呈现。

## 后端契约

### 1. cancel 接口加参数

```
POST /scan/{scan_id}/cancel?save=true|false   # 缺省 false，与现状兼容
```

### 2. cancel 执行路径

- `save=false`（默认）：当前行为完全不变——杀 worker、`raise ScanCancelled()`、SSE done = `{cancelled:true, hits:0, ...}`、文件不落盘。
- `save=true`：杀 worker、**不抛**，用已聚 result 正常构造（`scan` 节加 `partial: true`）、`write_result_file()` 落盘、`run_scan` 返回；SSE done 走当前成功 shape（带 `pattern_id` / `scan_ts` / `hits` / `errors` / `total`），多带一个 `partial: true` 字段。

### 3. 历史列表

`GET /scans/{pattern_id}` 返回的 `ScanHistoryEntry` 加 `partial: bool` 字段（从已读到的文件 metadata 取，无额外开销）。

## 前端契约

### 1. 主按钮（SidebarScanPanel）

`onPrimary()` 在 running 状态下点击：
- 当前 `progress.hits === 0` → 直接 `scan.cancel(false)`（当前行为）
- 当前 `progress.hits > 0` → 打开 StopScanDialog（**不**调任何后端接口）

### 2. StopScanDialog（新组件）

- 文案：`当前已经命中 {{ progress.hits }}，是否保存？` —— hits 直接 bind 到 reactive `progress.hits`，扫描跑、X 跳。
- 三按钮：
  - 「保存」  → `scan.cancel(true)` + 关 modal
  - 「丢弃」  → `scan.cancel(false)` + 关 modal
  - 「继续扫描」→ 关 modal
- Esc / 点外面：无视（dialog 不消失）
- 监听：扫描自然完成（`running` 变 false）时 modal 自动关。

### 3. store 改造

- `scan.cancel(save: boolean)` 调 `cancelScan(scan_id, save)`
- `api.cancelScan(scan_id, save)` HTTP 调用加 `?save=true|false` query

### 4. 已有的 auto-load 链路

`stores/scan.ts` done 成功分支已在本会话改成自动调 `open(pattern_id, scan_ts)`。保存路径走的是成功 shape done（带 `pattern_id` / `scan_ts`）→ 自动加载直接生效，零额外分支。`partial:true` 仅影响"历史列表标签"展示，不影响加载链路。

### 5. 历史列表 badge

`ScanResultDialog.vue` 每一行末尾在 `partial===true` 时显示小标「未完成」。

## 关键边界

- **modal 期间扫描在跑**：用户不点保存/丢弃，扫描会一直跑到自然结束；自然结束时 modal 自动关、走完整扫描结束流程。期间 SSE progress / done 监听不变。
- **modal 期间 hits 仍可涨**：保存时 X 取的是"点保存那一刻"的已聚 result（不是 modal 打开那一刻的快照），扫描没停，丢掉提前几秒扫到的反而是逻辑漏洞。
- **save=true 与 cancelled shape 互斥**：partial 保存路径走的是成功 shape done；cancelled shape done 仅用于 save=false 路径。
- **0 hits 时无 modal**：把"保存空文件"这个无意义动作压根不暴露。
- **modal 是 singleton**：modal 打开期间再次点主按钮无效（被 `dialogOpen.value` 阻塞）。

## 验证

后端：
1. 单元测试 / 集成测试：`run_scan` 在 `cancel_event.set()` + `save=true` 时返回带 `partial:true` 的 result，文件落盘；`save=false` 时仍抛 `ScanCancelled`、不落盘。
2. `listScans` 返回的 entry 含 `partial` 字段。

前端：
3. `vitest` 单测：`scan.cancel(true)` 与 `scan.cancel(false)` 分别调通带 `?save=...` 的 HTTP；`StopScanDialog` 三按钮分支；hits=0 不弹 modal；扫描自然完成时 modal 自动关。
4. `vue-tsc --noEmit` + `npm run build` 三绿。

端到端（手工）：
5. 真的开扫 → 等 hits>0 → 点停止 → modal 出现 → 点保存 → 主视图加载该结果 → 打开历史列表能看到这一行后带「未完成」。
6. 同上但点丢弃 → 主视图不变、历史列表里**没**这条。
7. 同上但点继续扫描 → modal 关、扫描继续 → 直到自然完成 → 主视图加载完整结果（历史列表里这一行**无**「未完成」标）。
8. hits=0 时点停止 → modal 不出现、直接走丢弃。
9. modal 开着时扫描自然跑完 → modal 自动关、走完整结束流程。
