# 标注工具「反馈」功能实施计划

本 plan 中所有项目内路径均相对 repo root。本文件是计划正本（2026-11-09 用户批准后，按一轮只读审查修订过：拖选与面板的键鼠、族命中区对现有点击的影响、快照写入时机等）。在主目录、当前分支 `annotation-path2` 上做；**不提交、不推送、不开 PR**（用户要时再提交）。

## Context

用户用看图标注做 path2 pattern（spec：`.scratch/annotation-path2/spec.md`）。第二轮里用户确认 new_step 第二版大体对了、只差细节条件，但「在会话里说清哪只股票哪一段哪里不对」很费劲。2026-11-09 用户定：在 `compare` 里直接对 app 已经买了的地方挑刺（反馈 / `feedback`），记录存进用户的标注文件，会话经 `read_annotations` 读；同时定了「改标注是反馈迭代的本职、页面负责引导」。设计经两轮 agent team 审查后写进 spec，用户逐题拍板。

本计划实现：spec 1.11、1.12、**6.13 全部**，以及 **6.14 里标明「随反馈一起做」的部分**：G3 的特征定义写前提示；G4（删样本提示、删除可撤最近一次、两处悬停文字）；会话每轮固定动作第 1～3 条（定格、求差、翻转按原因拆开）；改版报告。
**不做**：G1、G2、G6（随 `next` 以后做）；6.14 第 4 条与 G7（等第二段定级）；盲看本身；框与成员改动对 `diff tag` / 认出档位的按原因报（第二段）。

权威设计：spec 第 1.11、1.12、6.13、6.14、8、10（反馈相关行）、11（U7～U10）节。实施者**先读 spec 6.13、6.14 全文**，本计划只补实现落点、默认取值和坑。设计依据可查（只给实施者查，产出不得引用）：`docs/research/2026-11-09_feedback-design-review/impl_check.md`（现状代码位置）、`docs/research/2026-11-09_feedback-scope-annotation-edits/spec_audit.md`。

## 红线（每个子代理 prompt 原样带上）

- 不读 `datasets/pkls`；行情只经 `path2_web/data.py` 的 `read_bars`（读 `datasets/pkls_until_20251231`，已截到 2025-12-31）。测试一律用合成数据或测试自建目录。
- **绝不写 `annotations/`**（用户标注，只增不删）。会话侧读标注只经 `path2_web/annotation/store.py` 的 `read_annotations`。测试、e2e、真数据核对一律用临时标注目录（`create_app(config_override=...)` 或 `path2_web_ui/e2e/annotationBackend.py`）。
- 不碰端口 8001 / 5171 / 8767 上不是本次实施启动的进程；**不要运行 `scripts/path2/run_path2_web.py`**（它会按配置端口杀掉占用者，即用户正开着的 8001 / 5171）。关进程只按自己记下的进程号。注意：用户的 8001 后端是 `reload=True`，改 `.py` 时它会自动重启，属正常。
- 不碰代理配置、Syncthing；不改 `docs/research/` 下任何东西（工作区里 `docs/research/2026-10-*` 的暂存删除不是本任务做的，别动）；不碰标注票 12。
- `path2_web/GLOSSARY.md`、`path2/GLOSSARY.md` 不改（新界面名先列给用户认，见「交付」）。
- 前端是类型无关渲染器：不为任何具体事件类型 / node 名写分支；后端只做投影与日期比对。
- 界面文字照 `~/.claude/rules/ui-text-style.md`：程序固定文字用英文标识符风格、等宽（现成 class `.ann-k` / `.ann-btn`，见 `path2_web_ui/src/components/annotationPanel.css`），用户写的内容正常字体加灰底（`.ann-biz`）；文字一律黑色；解释放悬停（现有写法是原生 `title=`，英文小写短句）。配色照 `~/.claude/rules/color-vision.md`。
- 中文注释与 docstring；不用 TDD 流程，但测试要写、要跑；产出（代码、测试、注释、文档）不得出现 `docs/research` 字样或研究里的实验编号。
- 调工具纪律：中途消息正文至多一句状态行（无代码 token、不预告"我去调用 X"），随后直接发调用；长篇解释只放不再调工具的收尾消息。若发现自己把调用写成了正文文字，不要停笔，在同一条消息里立即发出真正的调用。

## 执行方式

- 主会话先跑基线并存失败清单（作对照）：`uv run pytest tests/path2_web tests/path2 -q`、`cd path2_web_ui && npx vitest run`、`npx playwright test e2e/annotate-*.spec.ts --workers=1`。
- 每个任务派一个 general-purpose 子代理实施；完成后另派一个 general-purpose 子代理**只读审查**（对照本计划该节 + spec 6.13 / 6.14 + 红线；跑该任务的测试）；审查意见回给实施者改；主会话核对测试结果后进下一个。
- 顺序：T1 与 T2 可并行（文件不相交）→ T3 → T4 → T5 → T6 → T7 → T8 → T10 → T11；T9 依赖 T1～T3（含 T3 的 `pattern_changes`）和下文定死的链接格式，可与 T4～T8 并行。
- 新路由与新模块读配置一律用 `path2_web/config.py` 的 `get_config()`（不用 `load_config()`），读 mapping 一律经 `read_mappings`（不要 `from path2_web.mapping import mapping_path`）：e2e 后端靠替换配置与 `mapping.mapping_path` 这个模块属性做隔离（`path2_web_ui/e2e/annotationBackend.py:31-38`）。
- 子代理中途断掉而产物已在磁盘：先 SendMessage 唤醒它核对、补说明，再下结论。

## 定下的实现默认（cc 默认，待用户用起来再调）

- **`lost` 的判法按 1.11 原意落到事件上**：一族「起点认不出」= 当前 app 结果里，参与求解的 node（会出现在 hit 的 `node_index` 里的那些；判法见 `path2/dag/_solve.py:99-108` 的 bound_ids）的事件（不论档位）没有一个起于 `family_start`。只看参与求解的 node，免得别的 node 恰好同一天起的事件把该判 `lost` 的判成常色。（spec 6.13 原句写成「起于 `family_start` 的 hit」；new_step 每个 hit 都有买点，照字面族反馈只会在 `matched` / `lost` 之间跳、永远到不了常色，与 1.11「改好了恢复常色」矛盾。交付时请用户认这句措辞改动。）
- **会话账本形状**（`path2_apps/<app>/mapping.yaml` 顶层键 `session`，后端原样带出、形状单独查）：
  ```yaml
  session:
    snapshot: {seen: {pc: 171}, samples: [s-pc-3, ...], at: "2026-11-10"}   # 每轮开头定格
    conditions:                                   # 由反馈 / 负样本 note / 盲看理由推出的条件
      - {where: plateau.no_chase, from: [f-pc-1], state: unmeasured}        # state 自由文字
    tags: {f-pc-1: for_tuning}                    # 红着或 lost 的反馈的原因标签
  ```
  原因标签暂名（U10，交付时请用户认）：`unhandled` 还没处理 / `for_tuning` 留给调参 / `not_worth` 量过不值得加 / `invisible` 当天看不出 / `accepted` 你说过接受 / `redefined` 定义改过（挂了它的反馈不再算朱红，6.14）。
- 其余新界面名暂用：第三态 `lost`、`no buy in range`、`redraw`、`pos sample inside`（U10）。
- `app_ver`：sha256 前 16 位十六进制。只记出处，界面上不因它显示任何「过期」或「旧版」提示（spec 6.9 / 6.12 反馈不过期）。
- **落在 compare 的链接格式**（T7 实现、T9 生成）：`#symbol=<代码>&date=<YYYY-MM-DD>&pattern=<标注里的 pattern 名>&mode=compare`。
- 反馈带行高 14px（固定，不随缩放）；常色描边深灰 `#555`、1.5px；朱红 `#D55E00` 底、黑字（同 `✗` 现有做法，`src/render/annotateLanes.ts:447`）；`lost` 白底橙描边 `#E69F00` 黑字（同 `missing`）；会话原因标签白底蓝描边 `#0072B2`（同 `unmapped`）。都待截图过目。

---

## T1 存储：新 kind `feedback`（`path2_web/annotation/store.py`）

现状要点（行号为写计划时）：`KINDS` :115、`_VALUE_KEYS` :119-124、`_ID_LETTER` :125、`_ID_RE` 写死 `[wbs]` :126、`_state` 除 feature/pattern 外一律归 `samples` :344-346、`_batch_reasons` :427-440、`_causality` :443-470、`_value_problems` 兜底 `else: # sample` :563、`_check_date` 卡训练段末日 :602-604、序号 `append_batch` :395、重放排序 :244。

1. 加 kind `feedback`、编号字母 `f`（`_ID_LETTER`、`_ID_RE` 一起改）。**`SCHEMA`（:114）不变**（spec 6.13：不改 schema 号）。`_VALUE_KEYS["feedback"] = (("id","symbol","pattern","app_id","app_ver","start","end","target","source","answer"), ("note","nodes","family_start"))`。
2. `_value_problems` 加 `feedback` 分支（**别落进 sample 的兜底 else**）：
   - `symbol` 走 `_check_symbol`；`pattern`、`app_id`、`app_ver` 非空字符串；`start`、`end`、`family_start` 走 `_check_date`（含 ≤ 训练段末日）且 `start ≤ end`；
   - `target ∈ {point, family, range}`；`source ∈ {picked, random, added, removed, tuned_added, tuned_removed}`；
   - `source = picked`：`answer ∈ {neg, off_pattern}`；`point` 时 `start == end`；`family` 时必有 `family_start` 且 `family_start ≤ start`，非 `family` 不得有 `family_start`；`neg` 的 `note` 非空（带不带 `nodes` 不管，前端切到 `neg` 时清掉已选的 node）；`off_pattern` 的 `nodes`、`note` 至少一样非空；`nodes` 为不重复的非空字符串数组；
   - 非 `picked`（盲看标记，现在只为「不可改」能测）：`target = point`、`start == end`、`answer ∈ {pos, neg, off_pattern}`，后两者 `note` 非空。
3. `_batch_reasons`：已存在且 `source ≠ picked` 的反馈，本批把它删掉、或改了**任何**已有字段（含 `source`，防「先改成 picked 再改」绕过）→ 拒收（新原因码 `blind_immutable`）；只许新增现在还没定义的盲看专有字段——眼下没有，所以实际是一律不可改。
4. 读时违规：`_replay` 记下每个非 `picked` 反馈第一次出现时的值；`read_annotations` 的 `violations` 追加「后来被删或任何已有字段被改」的条目（与第 3 条同口径）（同成员框越界的做法，同步来的修改不经保存校验）。
5. `_state` 按 kind 分桶：反馈进 `chart["feedback"]`，按 `(start, end, id)` 排；**这只股票没有反馈时不出 `feedback` 键**；只有反馈的股票照样在 `charts` 里出一项（`boxes`、`samples` 为空列表）。
6. `read_annotations(cfg, *, as_of: dict[str, int] | None = None)`：给了 `as_of` 时，**在 `_replay` 之前**只留「机器 m 的序号 ≤ `as_of.get(m, 0)`」的批次（按机器 + 序号过滤，**不按文件名、不按时刻**），其余照旧（指向被截批次的 base 会记成 unsynced，状态不受影响）。
7. 读结果加一键 `machines: {机器名: {"through": n}}`：`through` = 这台机器从 1 起连续到齐的最大序号（Syncthing 默认乱序拉文件，所以不能记最大序号；同机同号两个文件不破坏连续判定）；**用全部文件算，不受 `as_of` 影响**。会话定格就记 `{m: through}`。（各台最后时间只服务以后的 G6，这次不做。）
8. 模块说明（:1-98）同步写进 `feedback` 的形状、校验码、`as_of`、`machines`。

测试（`tests/path2_web/test_annotation_store.py`、`test_annotation_api.py`，用现成小工具 `_cfg` / `_op` / `_at`）：
- 黄金重放 `fixtures/annotation_store_v1` 的测试与期望**一字不改**且照样通过；
- 合法反馈三种 target 写进去、重放出来原样；第 2 条每条规则各一例被拒（`end` 晚于 2025-12-31 一例）；没有反馈的股票不出 `feedback` 键；只有反馈的股票出现在 `charts`；
- 非 `picked` 的反馈改 `answer`、删掉都被拒，补一个无关的合法操作照常放行；手写一个绕过保存的批次文件改它，读出来 `violations` 有一条；
- `as_of`：两台机器交错写、一台缺中间序号时，`machines.through` 停在缺口前；无缺口时 `as_of` 截出的状态等于当时的状态；有缺口时截出的状态等于「只重放 ≤ 截止序号的批次」（缺口之后已到的批次被截掉，下一轮会被当成新的再报一次——只多报不漏报），按这个写断言；`SCHEMA` 没变；
- 正常操作照常放过：box / sample 的现有测试全过。

## T2 判法、`app_ver` 与跑 app（纯 Python）

1. 新文件 `path2_web/app_version.py`：`app_ver(mod) -> str`：取 app 包目录（`Path(mod.__file__).parent`，`mod` 是 `path2_apps.<app>.dag_spec`）下全部 `.py`（递归、排除 `__pycache__`）加默认参数文件 `mod.DEFAULT_YAML_PATH`（`path2_web/api.py:506-512` 的 `_params_dir` 有取法），按相对路径排序、把相对路径和内容一起喂 sha256，取前 16 位；不含 `mapping.yaml` 和另存的参数文件。
2. 新文件 `path2_web/app_run.py`（不依赖 FastAPI）：
   - 把 `path2_web/api.py:453-503` `get_preview` 里「取参数 → `require_eval_meta` → 算缓冲窗 → `slice_window` → `mod.analyze`」那段抽成 `run_app(mod, cfg, symbol, start, end, params, label_horizon) -> (res, win, meta)`（缓冲窗终点要用 `label_horizon`，`api.py:478-480`）；它不依赖 FastAPI，读不到股票、代码不合格时抛 `FileNotFoundError` / `ValueError`，由 `get_preview` 在兜底 500（:500-501）之前映射成原来的 404 / 400（`_bars` :84-91 的语义）。`get_preview` 改为调用它，行为不变：`tests/path2_web/test_preview.py`（含 :100 的 404）、`test_data_wall.py` 必须照过；
   - `app_buys(res, win, end_node, spec) -> AppBuys`：买点日 = 每个 hit 经 `path2/eval.py:95` `_resolve_end_events(hit, end_node)` 取到的事件跨度里的每一根（与前端 `path2_web_ui/src/render/fold.ts:138` `buyDaysOf` 同口径，**不是** serialize 里的 `buy_date`）；族 = 按 `hit.start_idx` 分组，`families: {起点日期: [买点日...]}`；`event_starts`: 参与求解的 node 的全部事件（不论档位）的起点日期集合（见「定下的实现默认」的 `lost`）；另带 `dates`（这只股票窗口内全部交易日，`sample_match` 按根数算距离要用）；全部转成日期字符串，`AppBuys` 能 JSON 往返（T9 要存盘）。
3. `path2_web/annotation/match.py`（保留现有三个常数）加纯函数：
   - `feedback_status(fb, buys: AppBuys) -> "matched" | "unmatched" | "lost"`：`point` / `range` 看 `[start, end]` 内有无买点日；`family` 另加「`families[family_start]` 非空 → matched」，两样都没有且 `family_start ∉ event_starts` → `lost`；
   - `is_red(status, tag)`：`matched` 且标签不是 `redefined`；
   - `sample_match(date, judgment, buy_days, dates, tol) -> "matched" | "unmatched"`：前端 `path2_web_ui/src/annotate/compareRead.ts:81-95` `matchOf` 的 Python 版（按 K 线根数算距离，`tol` = 这里的 `POS_TOL` / `NEG_TOL`；样本日不是交易日 → unmatched）。
   - 模块说明改写：反馈状态的唯一实现在这里（后端状态接口、会话报告都用它）；样本 match 有两份实现（前端画图、这里给会话报告），过同一份例子文件。`compareRead.ts` 文件头 :14-17「唯一实现」那句同步改。
4. 新例子文件 `tests/path2_web/fixtures/match_examples.json`（按 K 线下标写：样本日、judgment、各 hit 的买点日、期望），`tests/path2_web/test_annotation_match.py` 与新 vitest `path2_web_ui/tests/annotate.match-examples.spec.ts`（照 `tests/annotate.membership.spec.ts:10` 读同目录 fixture 的写法）逐例通过。
5. 测试 `test_annotation_match.py` 还要覆盖 spec 6.13「检查·判法」：合成买点上 `point` 当天有（matched）/ 只有前后一天有（unmatched）；`range` 边界内、外各一例；`family` 范围外同起点 hit 还在买（matched）、起点认不出（lost）、起点事件还在但不买（unmatched）各一例；`app_ver` 改 `.py`、改默认参数文件会变，改 `mapping.yaml`、增删 `__pycache__` 不变。

## T3 后端接口与 mapping 会话段

1. `path2_web/mapping.py` `_read_one`（:80-116）：**在任何提前 return 之前**解析顶层 `session`，输出**恒有**两个新键 `session`（形状对时原样带出，否则或没有会话段时 `None`）和 `session_problem`（没有问题时 `None`）（英文一句，形状问题只进这里，**绝不写进 `problem`**——`problem` 非空会让 compare 整个变灰）。形状：`session` 是字典，键只许 `snapshot` / `conditions` / `tags`；`snapshot.seen` 为 `{str: int≥0}`、`snapshot.samples` 为字符串数组；`conditions` 为字典数组，每项 `where` 非空字符串、`from` 字符串数组、`state` 字符串；`tags` 为 `{反馈编号: 标签}`，标签取上文六个暂名之一（常量放 `mapping.py`）。文件说明（:13-20）补这段格式。反馈编号是否存在由前端核（后端不读标注，照现有分工）。
2. 单股预览 `GET /preview` 的 `scan` 元信息（`path2_web/api.py:493-497`）加 `app_ver`。
3. 新只读路由 `GET /feedback/status?pattern=<标注里的 pattern 名>`：
   - 由 `read_mappings(registry)` 找 `pattern` 恰好一个、`problem` 为空的 mapping 得到 app；找不到返回 `{app: null, items: []}` 加原因；
   - 读标注，取这个 pattern 的全部反馈；每只股票 `run_app(mod, cfg, symbol, "1900-01-01", TRAIN_END, mod.load_params(), 20)` → `app_buys`（区间与图上一致：前端 `stores/appLink.ts:68` 就是这么调预览的，`label_horizon` 也是 20）；
   - 进程内缓存，键 `(app, app_ver, symbol)`，值是 `AppBuys`；
   - 返回 `{app, app_ver, items: [{id, status, tag, red}]}`：`tag` 取 mapping 会话段 `tags` 里这条的标签（没有为 `null`），`red = match.is_red(status, tag)`——**朱红与否只在 Python 判一次**，前端照着画、照着排；行情读不到的股票该条 `status: null` 加原因，不整体失败。
4. 新只读路由 `GET /annotations/changes?pattern=<名>`：从这个 pattern 的 mapping 会话段取 `snapshot`；没有就 `{since: null, changes: []}`；有就 `read_annotations(cfg, as_of=seen)` 与当前状态交给新纯函数 `path2_web/annotation/changes.py` `pattern_changes(old_state, new_state, pattern) -> list`：这个 pattern 的样本新增 / 删除 / 改 judgment / 挪进挪出、这些样本（新旧任一）成员框的增删与起止 / 特征 / 属性改动、pattern 定义改动，每条 `{kind, id, change}`。会话求差与以后的 `edited n` 都用这一个函数。
5. 测试：`test_mapping.py`（会话段合法原样带出；各种坏形状只进 `session_problem`、`problem` 仍为 `None`、compare 不受影响；`:67`、`:107` 两处整字典相等断言同步补上两个新键）；`test_annotation_api.py`（状态接口三态各一例：用 `monkeypatch` 把 `run_app` / `app_buys` 换成合成结果，或用 `test_api.py:19-30` 的合成 pkl 跑 `bo_only`；缓存命中时不再跑 app；`changes` 接口）；`test_data_wall.py` 加两条：状态接口在任何参数下读到的行情不晚于 2025-12-31；`/annotations/changes` 不读行情（照 `test_annotation_api.py:160-166` 把读行情的函数换成会报错的替身）。

## T4 前端数据层

1. `path2_web_ui/src/annotate/model.ts`：`AnnKind` 加 `'feedback'`；类型 `AnnFeedback`；`AnnChart.feedback?: AnnFeedback[]`；`newId` 收 `'f'`、`ID_SEQ` 改 `[wbsf]`；`applyOps` 按 kind 分桶（:188 现在把非 box 一律当样本）；**:164 浅拷贝时 `feedback` 数组有就一起拷**（否则 splice 会改到后端读结果），空的 `feedback` 不出键，过滤 :199 改为「有框、样本或反馈」；`feedbackValue(...)` 生成带 symbol 的存储值；`AnnRead` 加 `machines?`。修好写死 `revs: {feature, pattern, box, sample}` 的测试夹具（`tests/annotate.model.spec.ts`、`annotate.grouping.spec.ts`、`stores.direct-links.spec.ts`、`stores.annotation.spec.ts`）。
2. `src/types.ts`：`AppMapping` 加 `session?`、`session_problem?`；预览 `scan` 类型加 `app_ver?`。`src/api.ts` 加 `getFeedbackStatus(pattern)`。
3. `src/stores/annotation.ts`：`saveFeedback(draft)`（新建或改，改时 `app_ver` 刷新为当前 `view` 里预览带回的值）、`deleteFeedback(id)`，都走现有 `commit` 队列；`feedbackOf(symbol)`、`feedbackOfPattern(pattern)` 取 `view` 里的记录。`AnnotationNotices.vue:113-117` 冲突标签补 `feedback`。
4. 新 store `src/stores/feedback.ts`：`statusById`、`loading`、`refresh()`（读当前 pattern 全部反馈的状态）；触发时机：进入 compare、换 pattern、保存 / 删除反馈落盘后（`ann.flushed()` 之后）、`view.setLinkedRun` 之后（app 重跑）、窗口重新拿到焦点（同 `appLink` 重读 mapping 的时机）。`statusById` 存接口给的 `{status, tag, red}`。面板状态也放这里：`panel: {x, y, symbol, start, end, target, family_start?, editingId?, answer?, note?, nodes?, carry?} | null` 与 `open / close / switchTo`；另有 `selectedId`（选中的那条反馈，图上加粗、侧栏点行时设）。
5. 纯函数文件 `src/annotate/feedback.ts`（T5、T6、T7 共用，在这里建）：同范围查重、范围里的当前 pattern 正样本（`pos sample inside`）、保存条件、`off_pattern` 的 node 按钮取法、侧栏排序。
6. 单测：`feedback.ts` 各函数（node 按钮取法用含孙 node 的合成拓扑）；`applyOps` 反馈分桶、过滤、不改入参；`stores.annotation.spec.ts` 加保存 / 改 / 删反馈的批次断言（照 :196-210 的写法）；`feedback` store 在保存后重取。

## T5 图上：点 ▼ / 格 / 族，反馈带

现状要点：hits 行数据在 `src/render/chart.ts:329-363`（▼ 数据项带 `buy_day`、`buy_date`、`family_key`、`family_start`；格带 `family_start`），族底线系列 `bracket-lines` 系列级与组级都 `silent`（:860-863、:1253），band 族的透明命中区写法 `makeRenderFamilyLine` :1192-1226（`fill: 'rgba(0,0,0,0.001)'`，不用 transparent）；hits 区高度 `src/render/subGeometry.ts:110-146` `computeSubGeometry`；系列点击 `KlineChart.vue:996-1008` → `handleChartClick`（`KlineChart.ts:69-97`，其 payload 类型没有原生事件，坐标从 `p.event.event.clientX/Y` 取，先例 `handleMaybeShiftClick` :320）；空白点击清焦点 `KlineChart.vue:1053-1058`。

1. **只在 `compare`**（`view.comparing`），`app` 模式行为与外观一律不变：`buildSubOption` 两种模式共用（`chart.ts:776`），可点的族命中区与反馈带要经渲染输入里的开关只在 compare 生成（`e2e/subchart-blankclick-yaxis.spec.ts` 这类依赖「点副图空白清焦点」的 app 模式测试必须照过）。
2. 族命中区：`bracket-lines` 改成「一整行高的透明 rect（可点）+ silent 底线与竖头」，压在格与 ▼ 下面（z 低于 `brackets`）；数据项带族的全部买点日。点它：族里有买点日时打开 `family` 面板（`start`/`end` = 这一族全部 ▼ 的最早 / 最晚，`family_start` = 族起点**日期**——图数据里 `family_start` 是 K 线下标（`chart.ts:351`），要经 dates 换成日期再存，否则存储会拒），没有买点日不弹。`handleChartClick`（`KlineChart.ts:79-96`）加一个 `bracket-lines` 分支并**返回 true**，这样 `onAppClick` 会照旧 `ann.selectBox(null)`（否则先选框再点族、按 Delete 会删掉那个框，`e2e/annotate-compare.spec.ts:16`、`:111` 守的就是这条）；分支里只设 `activeFamily`（或不动焦点），**不要用 `focusHits`**（几个 hit 买点日不同时它会进待选）。代价照 spec 6.13 写进代码注释：原来点格间空白是清选中。
（面板组件在 T6 写；本任务只调 T4 的 `feedback.open(...)`，单测断言 store 里的 `panel` 状态。）
3. 点 ▼：照旧 `focusBuyDay`，同时打开 `point` 面板（`start = end =` 那天）；点格：照旧 `focusHits`，这一格那天有买点就同样打开 `point` 面板，没有不弹。同范围已有反馈时打开那条（面板逻辑在 T6）。
4. 反馈带：`computeSubGeometry` 输入加 `feedbackRowCount`，在 hit 行下面加 `feedbackRowCount × 14px`（固定，不乘缩放）计入 hits 区高度（`bracketH`），band 整体顺移；compare 分界线位置不受影响（只加在 hit 行下面）。几条反馈范围交叠时用 `src/render/geometry.ts:8` `packLanes` 错行。每条一个横跨 `[start, end]` 的记号：宽度放得下才写 `neg` / `off_pattern`，否则只画记号；悬停写全（答案、理由或点出的 node、`status`、原因标签、`pos sample inside`（悬停时现算）、`nodes` 里当前拓扑已没有的 node 原样显示）；颜色按接口给的 `red` / `status`（朱红 = `red`；`lost` 白底橙描边；其余常色），状态未取到时按常色。点记号打开同一面板（预填、带 `delete`）。选中的那条加粗描边。
5. 单测：`computeSubGeometry` 加反馈行后的高度与 band 起点；hits 行数据里族命中区、▼、格各带的范围字段。`app` 模式的现有单测与快照不变。

## T6 `feedback` 工具与作答面板

1. 工具：`src/stores/annotation.ts:53` `Tool` 加 `'feedback'`。`src/components/TopBar.vue:54-61` 工具组里 `box`、`point` 旁加 `feedback` 按钮，**只在 compare 出现**；title 照 box 写法（`Shift+F toggles, Esc turns off`）。快捷键 Shift+F 照 `KlineChart.vue:855-860` Shift+B 写，条件改为 compare。熄灭规则沿用：用一次熄（`toolDone`）、Esc（:878-883）、换股换模式（:971）。
2. 手势（`src/components/annotateGestures.ts`）：`tool()` 可返回 `'feedback'`；亮着时 `claims(y)`（`KlineChart.vue:963-967`）对整张副图（含 app 区）与主图都返回真；新增手势 `range`：按下记起点，移动超过 4 像素（`src/annotate/boxGeometry.ts:10`）才算拖，拖动中 `setDraft` 一个新草稿类型 `{range: [start, end]}`，由标注层画一条贯穿主图与副图的竖带（主图可照 `src/render/annotateLanes.ts:479-500` `mainMarksSeries` 的整高 rect，副图另画一层；浅灰半透明填充 + 深灰虚线边）；松手：工具熄灭，按首尾两根 K 线日期取范围，范围里有买点日（用当前 hits 的买点日）就在松开处打开 `range` 面板，没有就在松开处浮一个 2 秒的提示 `no buy in range`（不是底部 toast）；点一下不拖：当普通点击、工具不熄。（拖动超过 4 像素时 zrender 不派 click，`node_modules/zrender/lib/Handler.js:241-245`，所以拖完落在 ▼ 上不会再开 `point` 面板；但**浏览器在 mouseup 后照样派原生 click 冒泡到 document**，会把刚在 `onUp` 里开的 range 面板当「点面板外」关掉——见下条的处理。）光标 `cursorAt`（:289-304）在工具亮时副图 app 区也返回 `crosshair`。
3. 面板组件 `src/components/FeedbackPanel.vue`（挂在 `KlineChart.vue`，定位照右键菜单 `openContextMenuAt` :363-382 的「越界就翻边」）：
   - 页头：股票、日期范围、`target`；初始只有 `neg` / `off_pattern` 两个按钮；点 `neg` 展开一行 `note` 输入并把光标放进去；点 `off_pattern` 展开 node 按钮和可选的 `note`；
   - **不抢焦点**：打开时不 focus 任何东西；按钮 `@mousedown.prevent` 防止点按钮抢焦点；
   - 关闭不存：点面板外（参照 `handleDocumentClick` :443-448；**「点外面就关」的 document 监听要在面板打开后 `setTimeout(0)` 再挂上**，这样打开它的那次图表点击、拖选松手后的原生 click 都不会把它关掉）、平移缩放（dataZoom）、副图滚动、换股、换模式、app 重跑；点到另一个 ▼ / 族 / 记号时关旧开新；
   - 按键：面板开着时在 window 捕获阶段截下 Enter（保存，焦点在按钮上也一样）与 Esc（第一下只关面板，不清选中、不熄工具），截下后 `preventDefault` + `stopPropagation`；**输入法守卫**：`e.isComposing` 或 `e.keyCode === 229` 时一律不截（中文理由组字时 Enter 是上屏、Esc 是取消组字），这个判定写成纯函数并单测；←/→ 不截，照旧在族里走；
   - 保存条件同 T1 校验（`neg` 要 `note`；`off_pattern` 点出的 node 或 `note` 至少一样），不满足时 Enter 不存、在面板里标出缺什么；切到 `neg` 时清掉已选的 node；
   - 防重复：打开时若这只股票、这个 pattern 已有 `start`、`end` 完全相同的反馈，直接打开那条；
   - 已有记录：预填，多 `delete` 与 `redraw`；`redraw` = 关面板、点亮 `feedback` 工具并把答案、理由、点出的 node 带进下一次拖动，拖完开面板（预填），保存时覆盖原记录（同编号，`target` 改 `range`，去掉 `family_start`）；
   - 范围里有当前 pattern 的正样本（这只股票）：页头下一行 `pos sample inside`，不拦；
   - 保存的值：`symbol`、`pattern` = 当前 pattern、`app_id` = 当前 mapping 的 app、`app_ver` = 预览带回的、`source = picked`，其余照面板。
4. node 按钮：取范围里买的那些 hit 的 `node_index` 键，加它们在拓扑里的子 node（递归：子 node 由 `TopoNode.parent_refs` 认父，`src/types.ts:16-17`），按拓扑顺序，根 node 保留，可多选；按钮文字与 band 表头相同（node 名 + `bandExtras` 给的特征名，`KlineChart.vue:217-232`，特征名用浅灰底）；悬停 title = mapping `notes[node]` 原话；悬停时对应 band 加亮（新 reactive 状态，副图装饰层在那条 band 表头后画一条浅底，离开即消失）。
5. 单测：按键截获判定（含输入法组字）；手势的 range 起止换算。纯函数在 T4 的 `feedback.ts` 里已测。

## T7 侧栏 `feedback` 页与落在 compare 的链接

1. `src/stores/annotation.ts:52` `SidebarTab` 加 `'feedback'`；`src/components/AnnotationSidebar.vue:36` 的 `TABS` 在 compare 下多一个 `feedback`（annotate 下不出，切回 annotate 时若停在这页就退回 `selection`）；v-if 链 :11-16 加新组件 `src/components/FeedbackPage.vue`；`tests/components/ChartArea.annotate.spec.ts:31` 断言同步改。
2. 页内容：当前 pattern 的全部反馈（跨股票，来自标注 `view`）；`loading` 态；每行：股票（`.ann-sym`）、日期范围、答案、理由（`.ann-biz`）或点出的 node、`status`；按接口给的 `red` 排前，`lost` 其次，再按股票、日期（排序函数在 `feedback.ts`）；红或 `lost` 的行挂接口给的会话原因标签 `tag`（白底蓝描边）；`session_problem` 非空时页头一行 `session ledger: <原因>`（悬停写全）；行上 `delete`。
3. 点一行：在 compare 里打开那只股票（`view.openSymbol` 在 compare 下保留模式），视窗移到包住那段日期（可借 `src/annotate/directLinks.ts:61-64` `chartLinkWindow` 的窗口算法），当前日竖线停在 `start`，设 `feedback.selectedId`（记号加粗）。
4. 链接：`src/annotate/directLinks.ts` `parseLink`（:44-58 现在只认 `date,symbol` 与 `sample`）加「定下的实现默认」里那种带 `pattern` 与 `mode=compare` 的写法；`src/stores/directLinks.ts` 的 `follow`（末尾现在无条件 `enterAnnotate`，:69）对这种链接：先把当前 pattern 设为链接里的 pattern，**等 mappings（页面刚打开时是 null，`appLink.ts:33`）和标注都读完**，这只股票的 compare 可用就落在 compare，否则照旧落在 annotate 并说明原因（文件头说明同步改）。会话改版报告的链接用它。
5. 单测：`parseLink` 三种写法与坏写法；`follow` 在 mappings 晚到时仍落在 compare；组件挂载断言页签。

## T8 页面引导里随反馈做的部分（6.14 G3、G4）

1. G3：`src/components/DefinitionField.vue` 的输入框（:4-6）在写之前就提示：灰字占位 `fixed once written` + title `fixed once written; if the meaning changes, start a new feature`。
2. G4 悬停：`src/components/PatternPanel.vue:12-15` 定义框 title 加 `grading follows this sentence`；`SamplePanel.vue` 的 judgment 标签（:16-20）与 `delete`（:8-9）title 加分流口诀 `visible that day it should not buy → neg; not this pattern at all → move to unsorted or another pattern; bad data → delete`。
3. 删样本提示：`delete` 点下时，用成员关系现算「只服务这个样本的框」（它的成员框里，不是别的任何样本的当前成员的那些；现成 `src/annotate/samples.ts:115-125` `memberOfRows` / `membership.ts` `currentMemberBoxes`）；没有就直接删；有 n 个就在面板里展开一行 `also delete n boxes only it uses?`，按钮 `yes` / `no` / `cancel`；`yes` = 一批里删样本加这些框（框的删法照 `deleteBox` :297-314 同批清 `attach` 引用，但**同一批要删的框之间不做 attach 清理**——否则对同一个框既发删除又发改值，后端按 `duplicate_op` 整批拒收，`store.py:420-423`；加单测：两个只服务它的框一个 attach 在另一个上）。
4. 删除可撤最近一次：删框、删样本、删反馈后记下「最近一次删除」（删前的值与这一批动到的对象）；`AnnotationNotices.vue` 加一行 `deleted <what>` + `undo` 按钮（底部 toast 是 `pointer-events:none`，放不了按钮）；`undo` = 新一批：被删的对象用原编号写回原值（base 取当前 rev，存储层允许，先例是拆回合并），被顺带改了的对象（样本的 `members`、框的 `attach`）只把拿掉的那一项加回**当前值**，不整值覆盖（防冲掉删除之后的修改）；再删一次就换成新的，撤过或刷新后消失。
5. 测试：`stores.annotation.spec.ts` 加删样本带框 / 不带框、撤销（含删框后改了样本 judgment 再撤，judgment 不被冲掉）；改动导致的现有 e2e 失败（`e2e/annotate-samples.spec.ts:211` 删样本）在 T10 一并修。

## T9 会话侧：定格与改版报告（`path2_web/annotation/revision.py`，可与 T4～T8 并行）

给会话用 `uv run python -c` 调；模块说明写清用法与一轮的顺序。cfg 默认 `load_config()`，可传入（测试用）。

模块文件头写明一轮的顺序与禁忌：① `start_round`，**立刻**把它打印的新快照写进 `mapping.yaml` 的 `session.snapshot`（spec 6.14「开头定格」）；② 改 app；③ `revision_report`。**不要用 `git stash` 回到旧版 app**（主目录有用户未提交的改动会被一起收走）；旧版买点只来自 round 文件。

1. `start_round(pattern, out_path) -> dict`：先把 mapping 会话段里**现有的** `snapshot` 抄进 round 文件记作 `prev`（没有为 `null`）；读当前标注，记新快照 `seen = {m: machines[m].through}`、这个 pattern 的样本编号集合、日期；股票集合 = `prev` 时的状态（`read_annotations(as_of=prev.seen)`）∪ 当前状态里这个 pattern 有样本或反馈的股票；用当前 app 逐只 `run_app` + `app_buys`（含交易日 `dates`），连同 `app_id`、`app_ver` 存成 JSON 到 `out_path`（会话放 scratchpad）；打印新快照的 YAML 供会话立刻写进 mapping。会话中途断掉时，mapping 里已有新快照、scratchpad 里有 round 文件，不丢基线。
2. `revision_report(pattern, round_path, link_base=None) -> str`（Markdown）：旧标注 = `as_of` round 文件里的 `prev.seen`（`prev` 为空就等于新标注），新标注 = `as_of` round 文件里的新 `seen`；旧买点 = round 文件，新买点 = 现在重跑；报：
   - ① 各条反馈的状态变化（`feedback_status` 新旧对照），每条 `lost` 留一行「改好了 / 认法变了」待会话填；
   - ② 反馈范围里砍掉的买点日只给个数；
   - ③ 范围外砍掉的、④ 新长出来的：按族（hit 起点日期）折叠，如「CRNC 2024-10-31 起的一族：11 天剩 6 天」，每族一个落在 compare 那天的链接（`link_base` 默认 `http://localhost:<frontend_port>/`，格式见「定下的实现默认」）；一版细看以 12 族为限，按变化天数从大到小挑，其余给个数；
   - ⑤ 样本结论的翻转：旧 = 旧标注 × 旧买点、新 = 新标注 × 新买点，用 `sample_match`（距离按 round 文件 / 重跑带的 `dates` 算）与 ✓/✗ 口径（正样本 matched、负样本 unmatched 为一致）；样本级变化（新增、删除、改 judgment、挪 pattern）**用 T3 的 `pattern_changes(old_state, new_state, pattern)` 取**（与以后的 `edited n` 同一个函数），有变化的翻转归「你改标注造成的」，其余归「app 改动造成的」；一行「翻了 n 张：app 改的 a、你改标注的 b」，下面分列；后者点名新放在新 app 买点日上的正样本；
   - ⑥ 删掉、挪走的正样本另起一节全部列出（它们在新标注里没有结论，进不了「翻转」），点名其中旧 app 认不出（旧结论 unmatched）的那些（spec 6.14「收窄」行）。
3. 调参后的报告（6.6）直接复用 ①～④。
   读配置用 `get_config()`、读 mapping 经 `read_mappings`（见「执行方式」）。
4. 测试 `tests/path2_web/test_annotation_revision.py`：合成标注目录 + 合成 `AppBuys`（monkeypatch `run_app` / `app_buys`），覆盖折叠、上限、翻转拆因（app 改的、标注改的各一例）、删掉的正样本单列、链接格式、`as_of` 缺口、`prev` 为空的第一轮。

## T10 端到端（`path2_web_ui/e2e/feedback.spec.ts`）与修现有 e2e

照 `e2e/annotate-compare.spec.ts` 的隔离写法：`startBackend(fill, mappings)` 起 `e2e/annotationBackend.py`（临时标注目录 + 手写 mapping 目录），`routeTo(page, backend)` 把请求转过去；`--workers=1`。playwright 的 webServer 会复用正在 5171 上的前端（只连不动）。覆盖 spec 6.13「检查·界面」：点 ▼、点琥珀格弹面板，保存后记号出现；点族的命中区得到 `family` 范围与起点；工具拖选、用一次熄灭、Esc 熄灭、范围里没有 ▼ 不弹并出 `no buy in range`；面板不抢焦点、点别处关、Esc 先关面板、焦点在按钮上 Enter 也是保存、**拖选松手后面板还在**；先选中一个框再点族，框的选中被取消；`redraw`；同范围不重复；改、删；侧栏排序与点行跳到 compare；`app` 模式不出现反馈。另加：删样本提示与撤销。顺手把 T8 改动弄坏的现有 e2e 修好。截两张图（反馈带三种状态、面板展开 node 按钮）存 scratchpad，`scale: 'device'`、不改视口以外的尺寸，交付时给用户过目。

## T11 文档

1. `.scratch/annotation-path2/manual.md` 补反馈用法，并写清 spec 6.13「说明书」条列的五件事（负样本与反馈 `neg` 的分工；`neg` / `off_pattern` 拿不准随便选、理由写清；系统性毛病给一两个例子加一句；一族的后见之明不用分天说；会话改完 app 后刷新页面）；再加两条：两台机器都更新到含反馈的代码之后再存第一条反馈（旧代码读到新 kind 会整个读取失败，升级即好）；删除可撤最近一次、刷新后撤不了。
2. `.scratch/annotation-path2-implementation/v-s1-notes.md` 末尾进度加一句：2026-11-xx 反馈功能（spec 6.13 及 6.14 随反馈部分）已实现，待用户用。
3. 根 `CLAUDE.md` 代码地图 path2_web 那条边界红线，在「标注读写只做存储与因果校验」后补「反馈状态只做 app 买点日与日期范围的比对」（后端新增了这项计算）。
4. 自查：`grep -rn "docs/research" path2_web path2_web_ui/src path2_web_ui/tests path2_web_ui/e2e tests/path2_web .scratch/annotation-path2/manual.md` 结果为空。

## 验证（主会话）

1. `uv run pytest tests/path2_web tests/path2 -q`：新测试全过；其余失败与基线清单相同；黄金重放测试与 `test_discovery_eval_meta_required.py` 必过。
2. `cd path2_web_ui && npx vitest run`；类型检查（`npx vue-tsc --noEmit`，或 `npm run build` 若它含类型检查）。
3. `npx playwright test e2e/feedback.spec.ts e2e/annotate-*.spec.ts --workers=1`：全过，失败与基线对照。
4. 真数据接通（scratchpad 一次性脚本，不入库）：`TestClient(create_app(config_override={**load_config(), "annotation_dir": <scratchpad 临时目录>, "machine": "chk"}, ...))`，往临时目录存一条 CRNC 2025-01-07～2025-01-30 的 `off_pattern`（`pattern` = `new_step`），`GET /feedback/status?pattern=new_step` 应为 `matched`；再用 `revision.start_round` / `revision_report` 对这个临时目录跑一遍（app 不改，报告应为「无变化」）。
5. 截图过目：T10 存的两张图交给用户看配色与反馈带。
6. 若本回合用过 playwright MCP，清空 `.playwright-mcp/`。

## 交付时讲给用户的

- 能用了：在 compare 里点 ▼ / 点一族 / 用 `feedback` 工具拖一段就能反馈；侧栏 `feedback` 页看全部。
- 两台机器：都更新代码后再存第一条反馈（`annotations/` 现在还没接 Syncthing，眼下只有 pc 有标注）。
- 请认的新名字（U10）：`lost`、`no buy in range`、`redraw`、`pos sample inside`、六个原因标签暂名；以及 6.13 一句措辞改动（`lost` 判「起点的事件认不出」而不是「起点的 hit 没有」）。认了再进词表、改 spec。
- 改动后的行为代价：compare 下 hits 行格与格之间的空白点了会弹一族的面板（原来是清选中）；点 ▼ 会顺带弹面板。

## 进度（每完成一个任务更新一次）

计划 2026-11-09 用户批准；设计文档已提交 `41ada92`。

| 任务 | 状态 |
|---|---|
| T1 存储 | 完成（审查通过，2026-11-09） |
| T2 判法、`app_ver`、跑 app | 完成（审查通过，2026-11-09） |
| T3 后端接口与 mapping 会话段 | 完成（审查通过，2026-11-09） |
| T4 前端数据层 | 完成（审查通过，2026-11-09） |
| T5 图上 | 完成（审查通过，2026-11-09） |
| T6 工具与面板 | 完成（审查通过，2026-11-09） |
| T7 侧栏与链接 | 完成（审查通过，2026-11-09） |
| T8 页面引导 G3、G4 | 完成（审查通过，2026-11-09） |
| T9 会话侧改版报告 | 完成（审查通过，2026-11-09） |
| T10 端到端 | 完成（feedback 5/5；4 条环境类旧失败，见交付说明，2026-11-09） |
| T11 文档 | 完成（主会话核过，2026-11-09） |
| 改名：反馈里点出认错的那一块从「分段」/ `segments` 改叫 node / `nodes` | 完成（2026-11-09 用户定：node 是 path2 规范词，原叫法是自造词；用户标注里还没有反馈记录，直接改名、不兼容旧字段。存储字段 `segments` → `nodes`，保存条件的问题码 `segments_or_note` / `segments` → `nodes_or_note` / `nodes`，前端 `segmentChoices` / `toggleSegment` / `panelSegments` → `nodeChoices` / `toggleNode` / `panelNodes`，面板标签与 testid 同改） |
| 打磨（2026-11-09 用户定）：`off_pattern` 加固定按钮 `dag`（毛病不在某个 node 上，必须写 note；nodes 与 dag 至少点一样，只写 note 不再能存；记录多可选键 `dag: true`）；顶层 node 不排除；note 改多行自动长高；feedback 页卡片加 `edit`；选中的反馈加粗边与贯穿主副图的竖带 | 完成（2026-11-09，主会话核过：pytest、vitest、vue-tsc、e2e feedback 6/6） |
| issue 复用（2026-11-10 用户定）：一份作答（answer、nodes、dag、note）叫一个 issue，几处反馈可共享；面板点了答案后列出同答案的已有 issue 供挑；所属 issue 还有别处且内容改了才问 `all` / `only this`；换答案是这一处离开原 issue；侧栏按 issue 分组、组头写处数与还在买的处数。存法：作答仍写在每条反馈里，共享的几处带同一个可选键 `issue`，保存时校验各处作答相同（原因码 `issue_diverged`）；撤销删除时写回的作答照 issue 现有各处 | 完成（2026-11-10，主会话核过：pytest、vitest、vue-tsc、e2e feedback 7/7） |
| 反馈不分答案、会话一轮写成 skill（2026-11-10 用户定）：面板拿掉 `neg` / `off_pattern` 与 `dag` 按钮，作答 = 必写的 note + 可选的 node（意思统一为「问题落在这一块上」）；issue = pattern + note + nodes，挑选列表不再按答案过滤。记录：反馈不带 `answer`、`dag`；带 `answer` 的记录（已有文件里的、没更新的页面存的）规则不变、一直收，读出来原样，界面与报告不显示，改一条时去掉；issue 一致性只比 pattern、note、nodes。会话侧：改版报告一条反馈写「（落在 node）「理由」」、「各 issue 现在」逐个 issue 一行；新增 `round_digest`（这一轮的输入摘要）；`start_round` 在还没有 app 时也能定格；round 文件放 `outputs/annotation_rounds/<pattern 名>/`；会话每轮按 issue 给处理清单（直接改 / 要你定 / 这一轮不改），流程写成 skill `annotation-round`；账本 `conditions.state` 约定五个开头词 | 后端与文档完成（2026-11-10：`uv run pytest tests/path2_web -q` 652 过，1 条与本任务无关的旧失败 `test_serialize_tbseg`）；前端、skill 见各自的完成记录 |

基线里已有的失败（2026-11-09 实施前跑，与反馈无关，作对照）：

- pytest（`tests/path2_web tests/path2`，6 个）：`tests/path2_web/test_serialize_tbseg.py::test_serialize_tbseg_walked_from_container`；`tests/path2/atoms/test_throwback_v4.py` 的 `TestStable::test_new_high_arm_exit`、`TestStable::test_weak_exit_reentry`、`TestGlobalBreak::test_ratchet_chain_then_break`、`TestGates::test_no_gate_on_normal_exits`；`tests/path2/test_self_contained.py::test_no_breakoutstrategy_imports_in_path2`。
- vitest（4 个，都在 `path2_web_ui/tests/components.sidebar-result-list.spec.ts`）：hover tooltip 的首次穿越块 1 个，global char forwarding 3 个。
- e2e 基线未跑。
