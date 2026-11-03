# 参照层 `peaks`（M8）

Status: ready-for-agent
Progress: done
Claimed: 2026-11-03 parallel-tickets ticket-10 @ worktree impl/10-peaks-reference-layer
Blocked by: 04

## Purpose

「突破了好几个峰」这类概念，不看峰在哪里标不准。本票给一个峰的参照层：默认关，换股票自动关，用户需要时才打开，不会被它带偏。

## Source

- [spec](../annotation-path2/spec.md) 的这几处：5.2 的 `ref`；5.7；1.3「框和词表」的最后一条；1.8 第 5 行。
- 说明书报告 M8。
- 峰不是 event，见 `path2/GLOSSARY.md:15`。
- 前置交付：[04](04-open-by-symbol-shell.md)。

## Inherited Direction

- 共用执行边界。
- **参照层是唯一的例外**：标注图上不画任何别的系统算出来的东西。参照层默认关，换股票自动关（说明书报告第 7 节第 4 条）。防的是：用户被现成的 detector 结果带偏。
- 峰取自现有 bo 检测产出的峰，只用截到 2025-12-31 的数据算。
- 峰画成深灰细实线，不碰配色规范里有意义的颜色（spec 5.7）。

## What to build

- 顶栏的 `ref` 组加 `peaks` 复选框，只在 `annotate` 和 `compare` 下可用。
- 后端加一个路由，给出这只股票在训练段里的峰。
- 前端把峰画成水平线；换股票时自动关掉。

## Blocked by

04

## Acceptance criteria

- 默认是关的；打开后画出峰；换股票后自动关掉。用 e2e 验。
- 峰只用截断后的数据算：用一个 2025-12-31 之后价格更高的合成例子，图上不出现截止之后的峰。
- `app` 模式下不能用。
- 拍截图自查：峰线和 K 线、用户的框都分得开。
- `未安排人审：界面是否顺手、颜色是否分得开；原因：第一次真实使用就是 V-S1，它本身是用户的审查，那批标注只当试用（spec 第 7 节 V-S1）`

## 完成记录

2026-11-03，parallel-tickets ticket-10。合并提交 c967c60（`--no-ff` 合回 `annotation-path2`），测试与审查所在提交 b190679，合并后的树与之相同。

**做了什么**
- 后端（`path2_web/`）：
  - 新模块 `peaks.py` 的 `peak_lines`：对一只股票截到训练段末日的行情跑一遍 bo 检测（`BODetector` 的构造默认参数），把它产出的峰投影成线 `{date, price, end}`。
    - `date` 是峰那根 K 线；
    - `price` 是峰登记时的价，探测器之后因小幅突破抬高的价不算；
    - `end` 是第一次被突破的那根，也就是第一个在 broken 引用里收了它的 bo；没被突破的画到最后一根。
  - 新路由 `/peaks?symbol=`：读数走 `read_bars`，截到 2025-12-31。代码名不合格回 400；没有这只股票、或截完一根不剩回 404。
  - 「截完一根不剩 → 404」原来写在 `/ohlc` 里，现在收进 `_all_bars`，`/ohlc` 不给区间时和 `/peaks` 共用。`/ohlc` 的行为不变。
- 前端（`path2_web_ui/`）：
  - 顶栏加 `ref` 组，里面一个 `peaks` 复选框（`TopBar.vue`）。
  - 新 store `stores/refLayers.ts` 管开关：
    - 只在 `REF_MODES = ['annotate', 'compare']` 下、且已打开一只股票时可用，按模式名判断；
    - 默认关；换股票的那一刻自动关，切到 `app` 也关，回来仍是关的。开关不记在浏览器里；
    - 打开时向 `/peaks` 要峰；正在要的时候换了股票或关掉，回来的结果不用；
    - 状态提示 `loading` / `load_failed` / `empty`，`empty` 表示这只股票在训练段里没有峰。
  - 新系列 `render/refLayers.ts` 的 `peaksSeries`：峰线是深灰 `#52525b`、1 像素的实线，压在 K 线上面，不挡鼠标，不改 y 轴范围。只在 annotate 下画，图窗外的部分裁掉。
  - `KlineChart.vue`：annotate 下主图加这个系列；开关或峰变了，只重画这一个系列。

**验收**
- 默认关、打开后画出峰、换股票后自动关，用 e2e 验：`e2e/annotate-ref-peaks.spec.ts` 第 1 条。
  - 股票从 `/symbols` 里现找有峰的，不写死。
  - 勾上后，主图峰线的条数、起止日期、高度和 `/peaks` 给的逐条相同，最晚都到 2025-12-31。
  - 换一只股票后，复选框取消勾选，峰线不画。
  - 单测在 `tests/annotate.ref-peaks.spec.ts`、`tests/components/TopBar.spec.ts`、`tests/components/KlineChart.annotate.spec.ts`。
- 峰只用截断后的数据算：`tests/path2_web/test_peaks.py`。
  - 合成股票 2026 年涨到 20，远高于截止前的峰。合成数据里有三样截止之后才有的东西，路由一样都没给出来：
    - 2025-12-23 的峰：要 2026 年的 K 线才确认；
    - 2026 年的高点；
    - 截止前的峰 2 在 2026 年才被突破：路由里它的线画到 2025-12-31，拿完整行情算则画到 2026-01-08。
  - 作为对照，用完整行情算，这三样都在。
  - 「图上」那一半由 e2e 接上：图上画的就是 `/peaks` 给的那些线。
- `app` 下不能用：
  - e2e 第 2 条：走 view store 的 `selectSymbol`，即从扫描列表选股的那条路。复选框取消勾选、变灰、不能勾。
  - 单测另外验了：没打开股票时也不能勾；`app` 下调用打开也打不开。
- 拍截图自查：`evidence/10/01-ref-peaks-page.png`（整页）、`02-ref-peaks-main.png`（主图），2560×1440，scale=device。
  - 图窗停在 KMT 的两条峰线附近，在线上画了一个框并选中。
  - 峰线是深灰实线；用户的框是黑色虚线边加浅灰底；K 线是红绿实体。三者分得开。
  - 框的浅灰底里，峰线照样看得清。
  - 顶栏复选框勾上是黑的：浏览器默认的蓝会被读成会话蓝，所以改成黑色。
  - 截图里还有一条蓝色虚线，横在约 20.1 的位置。它是主视图原有的「鼠标停过的那根 K 线的收盘价线」（`KlineChart.vue` 的 `updateAxisPointer`），鼠标离开后还留着，不是本票加的。它在 annotate 下用了蓝色和虚线，和配色规范 4.4「虚线只表示用户画的」相冲，留给后续处理。
- 测试结果：
  - `pytest tests/path2_web tests/scripts`：503 个通过、2 个跳过、1 个失败。失败的是 `test_serialize_tbseg.py::test_serialize_tbseg_walked_from_container`，它读 `datasets/pkls/ACUT.pkl`，在基线上就失败（同票 01、04 的记录）。
  - `npx vitest run`：1056 个通过、4 个失败，都在 `components.sidebar-result-list.spec.ts`，基线上同样失败。
  - `npx vue-tsc -b` 通过。
  - 标注 e2e 回归 17 条全过：`annotate-*.spec.ts` 加上 `symbol-search.spec.ts`，日志在 `evidence/10/e2e-annotate.log`，跑的是提交 886586f，即审查修改之后的代码。
- 独立审查：`evidence/10/review-standards.md`、`review-spec.md`。
  - 规范违反，已修：
    - 注释里「先只有 peaks」「compare 还没有的时候」改成只写现状；
    - 「截完不剩 → 404」的重复收进 `_all_bars`。
  - 规范违反，没改的一条：峰线色 `#52525b` 不在安全色板的色块里。
    - 色板里的灰都已经有含义：`#9ca3af` 是 qualified，`#d1d5db` 是 detected，`#888888` 是兜底色。选它们会违反 spec 5.7「不碰有意义的颜色」。
    - 票 04 已经把 `palette.html` 页面自身用的中性色当作安全色取用：`--line-soft #e4e4e7`、`--chip-bg #f4f4f5`、`--bar-bg #fafafa` 都出自那里。`#52525b` 是同一页面的说明文字色，照同一口径取用。
    - 颜色分不分得开，由票面的「未安排人审」交给 V-S1。
  - 坏味道，没改，理由如下：
    - `.chk.off` 的灰字：spec 5.2 对不可用的模式本来就写「变灰」，这里照同一口径。
    - `PeaksStatus` 与 `RandomStatus` 取值相同：两者含义不同，`empty` 一个指没有峰、一个指股票池空，各自管自己的提示。
    - e2e 里自带一份 `PeakLine` 类型：e2e 文件一律不 import `src`（如 rally 的 e2e 也自带类型）。
    - `REF_MODES` 用 `string[]`：调度要求按模式名先列上 `compare`，`ViewMode` 里还没有它。票 11 把 `compare` 加进 `ViewMode` 后可以收紧。
    - `peak_lines` 读探测器的引用：这是把 path2 的只读结构投影成 JSON，和前端 `peakState.ts` 合成峰三态同类，不是二次判定。
    - 名字 peaks 与词表规范词 pk：`peaks` 是 spec 5.2、5.7 定的界面名。

**实现上的选择**（都由测试守着；只有用户判断得了的，写在末尾的「未安排人审」里）
- 线画多长：从峰那根画到第一次被突破的那根，没被突破的画到最后一根。不画成横贯全图的线，因为 4 年里一只股票的峰常有几十个。
- 「被突破」用 bo 检测的默认口径：看最高价、超出峰价 0.3%。
  - 主线 app 的口径不同：bottom_burst 看收盘价，bb_v1 看收盘价、超出 0.75%，所以线断在哪根可能和这些 app 认的突破不一致。
  - 参照层不跟某个 app 走，因为 annotate 下可能还没有 app。
  - 认峰的几个参数（窗口 20 根、两侧各 6 根、相对高度 20%、看最高价）各 app 与默认值相同，所以峰本身是同一批。
- 被更高的新峰吃掉的峰不另算终点：更高的那根 K 线越过它时，它已经被突破过了。在 25 只随机股票上核过，被吃掉却没被突破的峰为 0 个。
- 切到 `app` 也自动关，回来仍是关的。
- 状态提示复用已有的界面名 `loading`、`load_failed`、`empty`，没有起新名字。

**运行环境**
- worktree 的 `uv sync` 13 分钟没装上东西（卡在下载），已按进程号停掉。pytest 和 e2e 后端改用主目录 `.venv` 的解释器，在 worktree 根目录用 `python -m` 跑。已核对导入的是 worktree 的代码。
- worktree 的端口临时改成 8090 / 5190（skip-worktree，没提交），合回前已改回。
- 有一次 `vitest run` 与 `vue-tsc -b` 误在主目录的 `path2_web_ui/` 里跑了：后台命令把 `cd` 带进了子 shell。
  - 那次只读了主目录的代码；
  - 写到的只有被忽略的构建缓存：`tsconfig.tsbuildinfo`、`node_modules/.vite-temp`、`node_modules/.vue-global-types`；
  - 结果作废，之后已在 worktree 里重跑。

**界面名**：`ref`、`peaks` 是 spec 5.2 已定的；状态复用 `loading`、`load_failed`、`empty`。没有新起的界面名。「参照层」不在 `path2_web/GLOSSARY.md` 里，要不要进词表由用户定。

**共享机制与复核**
- 改了：
  - `path2_web/api.py` 加 `_all_bars`，`/ohlc` 不给区间时走它，行为不变；
  - 新路由 `/peaks`；
  - 前端：`types.ts` 的 `PeakLine`，`api.ts` 的 `getPeaks`，新 store `stores/refLayers.ts`（`REF_MODES`、`useRefLayerStore`），`TopBar.vue` 的 `ref` 组，`KlineChart.vue` 的峰线系列。
- 复核了还没开始的 11、12，条文都仍然成立，没有改动。spec 自认领以来没有变化。
- 给 11 的提示：
  - `compare` 已按名字算作可用，但峰线现在只在 annotate 的画法里画：`renderBarsOnly` 加系列，`renderRefLayers` 以 `annotating` 为前提；
  - 11 做 `compare` 的主图时，要把 `peaksSeries` 也加进去，并让 `renderRefLayers` 在 `compare` 下照样重画；
  - `REF_MODES` 届时可收紧成 `ViewMode` 的类型。

**写了共享数据**：无。只读了主目录的训练段副本；e2e 的标注写在系统临时目录，测试扫描写在本票 worktree 的 `outputs/`，随 worktree 删除。已核对主目录的 `annotations/`、`datasets/` 在本票期间没有新改动的文件。

`未安排人审：界面是否顺手、颜色是否分得开；原因：第一次真实使用就是 V-S1，它本身是用户的审查，那批标注只当试用（spec 第 7 节 V-S1）`

`未安排人审：峰线从峰画到第一次被突破的那根（不横贯全图）、「被突破」用 bo 检测的默认口径（最高价超出 0.3%，与 bb 系 app 看收盘价不同）、峰价取登记时的价、峰线颜色 #52525b；原因：都只有用户实际标「突破了几个峰」时判断得了，build-on 是 V-S1，它本身就是这次审查（spec 第 7 节 V-S1、第 10 节「参照层」一行由用户在 V-S1 定）`
