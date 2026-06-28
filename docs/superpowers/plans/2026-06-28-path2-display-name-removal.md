# path2 显示名字段移除 — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (推荐) 或 superpowers:executing-plans 实施。步骤用 `- [ ]` 跟踪。

**Goal:** 删除 `PatternSpec.display_name` 与 `NodeSpec.label` / `TopoNode.label` 字段,UI 显示直接使用 id;skill 新增「id 即显示名」收尾约束。

**Architecture:** 三段联动,前后端 + skill;Python 内核 + 后端序列化为一个原子改动(中间状态会因 `serialize.py` 引用已删字段而崩);前端独立化简 fallback 与类型;skill 文档独立追加段落;最后端到端实证旧 JSON 兼容性与 SVG 宽度估算视觉效果。

**Tech Stack:** Python 3 + pytest(后端) / Vue3 + TypeScript + Vitest + vue-tsc(前端) / uv 管包 / git

## 全局约束(每个 task 隐含)

- **Implementer 模型固定 `sonnet`**, Reviewer 模型固定 `opus`(per CLAUDE.md superpowers section)
- 不写 `--no-verify`、不跳 hook、不动 git config
- 中文注释 / 英文界面 — 本次删除不引入新 UI 中文串;新增的 skill 段落用中文
- 调工具纪律:中途消息正文至多一句状态行,不预告"我去调用 X",勿把调用写成正文文字
- 不动 `.claude/docs/`(模块架构意图)、不动 `BreakoutStrategy/`(legacy)
- 末尾若用过 playwright MCP → 清 `.playwright-mcp/*`
- 实证 > 文档:有任何「应该…」的疑虑,直接跑命令看结果

## Spec 参照
`docs/superpowers/specs/2026-06-28-path2-display-name-removal-design.md`

---

## Task 1: 删 Python 内核 + 4 处 app kwarg + 后端 serialize

**目标**:`PatternSpec.display_name` / `NodeSpec.label` / `TopoNode.label` 三字段同 commit 删除并清理所有引用(原子动作:中间状态会导致 dataclass instantiation 失败或 serialize.py AttributeError)。

**Files:**
- Modify: `path2/dag/nodes.py`(删 `NodeSpec.label` 字段)
- Modify: `path2/dag/spec.py`(删 `PatternSpec.display_name` 字段 + `TopoNode.label` 字段 + `to_topology()` 投影)
- Modify: `path2_apps/bo_only/dag_spec.py:33`(删 `display_name=` kwarg)
- Modify: `path2_apps/bottom_breakout_burst/dag_spec.py:48,52,65`(删 2 处 `label=` + 1 处 `display_name=`)
- Modify: `path2_web/serialize.py:209-234`(删 JSON 输出体 `"display_name"` 与 nodes[].`"label"` 两个 key)
- Test (new): `tests/path2_web/test_display_name_field_removed.py`
- Modify: 所有 `tests/path2/`、`tests/path2_web/`、`tests/path2_apps/` 下含 `display_name` / `.label` 引用的测试 / fixture(grep 穷举)

**Interfaces:**
- Consumes: 无(本 task 是源头)
- Produces 给 Task 3 消费:
  - `serialize_pattern_meta(spec) -> dict` 返回结构:`{"pattern_id": str, "topology": {"nodes": [{"node_id": str, "class_id": str}, ...], "edges": [...]}, "event_styles": dict}` — 即 **顶层无 `display_name`,nodes[i] 无 `label`**

- [ ] **Step 1: 写失败测试** — 新建 `tests/path2_web/test_display_name_field_removed.py`

```python
"""验证 display_name/label 字段已从 path2 数据模型与后端序列化中清除。"""
import dataclasses

from path2.dag.nodes import NodeSpec
from path2.dag.spec import PatternSpec, TopoNode


def test_pattern_spec_no_display_name_field():
    names = {f.name for f in dataclasses.fields(PatternSpec)}
    assert "display_name" not in names


def test_node_spec_no_label_field():
    names = {f.name for f in dataclasses.fields(NodeSpec)}
    assert "label" not in names


def test_topo_node_no_label_field():
    names = {f.name for f in dataclasses.fields(TopoNode)}
    assert "label" not in names


def test_serialize_pattern_meta_omits_fields():
    from path2_apps.bottom_breakout_burst.dag_spec import PATTERN_DAG
    from path2_web.serialize import serialize_pattern_meta

    meta = serialize_pattern_meta(PATTERN_DAG)
    assert "display_name" not in meta, f"meta keys: {list(meta.keys())}"
    assert meta["topology"]["nodes"], "nodes 列表非空"
    for n in meta["topology"]["nodes"]:
        assert "label" not in n, f"node 残留 label: {n}"
```

- [ ] **Step 2: 跑测试看红**

```bash
uv run pytest tests/path2_web/test_display_name_field_removed.py -v
```

Expected: 4 FAIL(字段当前都存在/serialize 当前都 emit)

- [ ] **Step 3: 删 NodeSpec.label** — Edit `path2/dag/nodes.py`

读 nodes.py 当前 `NodeSpec` dataclass 与 docstring,删除:
- 字段定义行 `label: str = ""`
- docstring 中 `label: 人类可读名(面板)。` 这一行

不动其他字段/方法/校验。

- [ ] **Step 4: 删 PatternSpec.display_name + TopoNode.label + 改 to_topology**

Edit `path2/dag/spec.py`:
- `TopoNode` dataclass 删 `label: str = ""` 字段
- `PatternSpec` dataclass 删 `display_name: str` 字段
- `to_topology()` 内 `TopoNode(n.node_id, n.detector.event_cls.class_id, n.label)` → `TopoNode(n.node_id, n.detector.event_cls.class_id)`

- [ ] **Step 5: 删 4 处 app kwarg**

Edit `path2_apps/bo_only/dag_spec.py`:删 `PatternSpec(...)` 内 `display_name="单点突破(bo)",` 那一行

Edit `path2_apps/bottom_breakout_burst/dag_spec.py`:
- `:48` `NodeSpec("burst", ...)` 内删 `label="突破爆发"`(若与 `consumes_stream="bo"` 同行,移除该 kwarg 并保留 `consumes_stream`)
- `:52` `NodeSpec("tb", ...)` 内删 `label="回踩确认"`
- `:65` `PatternSpec(...)` 内删 `display_name="底部反转突破爆发",`

- [ ] **Step 6: 删后端 serialize.py 两 key**

Edit `path2_web/serialize.py`:
- 第 ~221 行 `nodes[].label` 不再写出(只留 `node_id` 与 `class_id`)
- 第 ~234 行 `"display_name": spec.display_name,` 整行删除

- [ ] **Step 7: 跑新测试验证全绿**

```bash
uv run pytest tests/path2_web/test_display_name_field_removed.py -v
```

Expected: 4 PASS

- [ ] **Step 8: 清理残留引用测试 / fixture**

先 grep 穷举:

```bash
grep -rn "display_name\|\.label\b\|'label'\|\"label\"" tests/path2 tests/path2_web tests/path2_apps --include="*.py"
```

逐条核对:与本字段相关的(NodeSpec.label / TopoNode.label / PatternSpec.display_name / 序列化 JSON 中这两 key)→ 删除该行或更新 assertion;**与本字段无关的(其他业务字段恰好也叫 label 的)→ 不动**(逐条人核,勿盲删)。

特别注意 `tests/path2/dag/test_nodes.py`:含 NodeSpec.label 的构造/断言要全部更新。

- [ ] **Step 9: 跑完整 path2 + path2_web 测试**

```bash
uv run pytest tests/path2 tests/path2_web tests/path2_apps -x
```

Expected: 全 PASS,无 AttributeError / TypeError 残留。

- [ ] **Step 10: Commit**

```bash
git add path2/dag/nodes.py path2/dag/spec.py path2_apps/bo_only/dag_spec.py path2_apps/bottom_breakout_burst/dag_spec.py path2_web/serialize.py tests/path2_web/test_display_name_field_removed.py
# 还需 git add Step 8 中清理的测试 / fixture 文件
git status      # 核对未追踪/已修改清单与本 task 范围一致
git -c commit.gpgsign=false commit -m "$(cat <<'EOF'
refactor(path2): 删除 PatternSpec.display_name 与 NodeSpec/TopoNode.label

字段纯渲染用、零非显示消费(per 2026-06-28 spec)。UI 显示改为直接使用
pattern_id / node_id;serialize 不再 emit 两个 JSON key。

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: 旧 scan JSON 向后兼容性实证

**目标**:验证主分支产 baseline JSON(含老 `display_name`/`label` key)在本分支后端加载不报错;若 Pydantic schema 是 `extra="forbid"` 则改为 `extra="ignore"`。

**Files(可能):**
- Modify(若需):`path2_web/api.py` 或 `path2_web/serialize.py` 中相关 Pydantic schema(改 `model_config = ConfigDict(extra="ignore")`)

**Interfaces:**
- Consumes from Task 1:Task 1 已删字段,后端代码不再读取它们
- Produces 给 Task 3 / 5:无新接口,纯验证

- [ ] **Step 1: 用主分支扫一份 baseline JSON**

```bash
git stash      # 暂存本分支改动
git checkout master      # 或 main,取 path2_web 已合入的分支
mkdir -p outputs/path2_eval
uv run python -c "from path2_web.eval_runner import run_eval; run_eval(module_path='path2_apps.bottom_breakout_burst', start='2023-01-01', end='2023-12-31', out_path='outputs/path2_eval/baseline_legacy.json')"
git checkout dag      # 回本分支
git stash pop
```

注:若主分支 path2_web 不存在,改为 grep `outputs/path2_eval/` 找已有 JSON;若也无,跳过 Step 1-3,Step 4 直接做就地扫描验证(自然产 new-format JSON)即可。

- [ ] **Step 2: 启后端**

```bash
uv run python scripts/run_path2_web.py &
# 等 5 秒让后端就绪
sleep 5
```

- [ ] **Step 3: 触发加载老 JSON 的 API**

```bash
curl -sS http://localhost:8000/scans | head -c 500
# 找一个含 baseline_legacy 的 scan_id,触发详情:
curl -sS http://localhost:8000/scans/<scan_id> | head -c 200
```

Expected: HTTP 200 + 合法 JSON body;若返回 422 / 500 → 进入 Step 4。

- [ ] **Step 4: (按需)修 Pydantic schema 接受额外字段**

定位 schema:

```bash
grep -rn "BaseModel\|ConfigDict\|extra=" path2_web/ --include="*.py"
```

凡描述 scan 文件结构的 schema(尤其反序列化 `ScanResult` / `PerPatternResult` / `PatternMeta` / `TopoNode` 的),`model_config = ConfigDict(extra="ignore")`。仅当 schema 当前是 `extra="forbid"` 才改;Pydantic v2 默认 `ignore` 不需动。

再跑 Step 3 直到 200。

- [ ] **Step 5: 关后端 + 记结果**

```bash
kill %1     # 或 pkill -f run_path2_web
```

若 Step 4 改了 schema → commit;若未改任何文件 → 本 task 为 no-op,直接进 Task 3。

```bash
# 若有改动:
git add path2_web/<改的文件>
git -c commit.gpgsign=false commit -m "$(cat <<'EOF'
chore(path2_web): Pydantic schema 接受老 JSON 字段以保持向后兼容

旧 scan 文件含 display_name/label key,新代码不再使用;extra='ignore'
确保静默丢弃而非 forbid 报错。

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: 前端 5 fallback 化简 + types 删字段 + SVG 宽度估算

**目标**:前端类型删两字段;5 处 `?? pid` / `|| node_id` fallback 直接化简为 id;SVG 节点框宽度估算更新(`render/topology.ts:22`)。

**Files:**
- Modify: `path2_web_ui/src/types.ts:5`(`TopoNode` 删 `label`)和 `:13`(`PatternSpec` 删 `display_name`)
- Modify: `path2_web_ui/src/components/SidebarResultList.vue:29,64-66`(删 `displayNameOf` 函数,模板直接 `{{ pid }}`)
- Modify: `path2_web_ui/src/components/ChartArea.vue:18`(`?? pid` 移除,直接 `pid`)
- Modify: `path2_web_ui/src/components/SidebarPatternPanel.vue:18`(`p.display_name` → `p.pattern_id`)
- Modify: `path2_web_ui/src/components/TopologyControl.vue:35`(`box.node.label || box.node.node_id` → `box.node.node_id`)
- Modify: `path2_web_ui/src/components/DetailSidebar.vue:17,22`(`node.label || node.node_id` → `node.node_id`)
- Modify: `path2_web_ui/src/render/topology.ts:22`(`[...(n.label || n.node_id)].length` → `[...n.node_id].length`)
- Modify: 所有 `path2_web_ui/tests/` 含 `display_name` / `.label` 字段引用的 fixture / 断言(grep 穷举)

**Interfaces:**
- Consumes from Task 1:后端 `serialize_pattern_meta` JSON 顶层无 `display_name`、nodes[i] 无 `label`
- Produces 给 Task 5:无新接口

- [ ] **Step 1: 改 types.ts 删两字段**

Edit `path2_web_ui/src/types.ts`:
- 第 5 行 `TopoNode` interface:`{ node_id: string; class_id: string; label: string }` → `{ node_id: string; class_id: string }`
- 第 13 行 `PatternSpec` interface:`{ pattern_id: string; display_name: string }` → `{ pattern_id: string }`

(若实际行号略偏,以 interface 名为准。)

- [ ] **Step 2: 化简 5 个 vue 文件 fallback**

读每个文件确认上下文后:

Edit `path2_web_ui/src/components/SidebarResultList.vue`:
- 第 ~29 行模板 `{{ displayNameOf(pid) }}` → `{{ pid }}`
- 第 ~64-66 行 `function displayNameOf(pid: string): string { return scanFile.value?.per_pattern[pid]?.pattern_spec.display_name ?? pid }` 整函数删除

Edit `path2_web_ui/src/components/ChartArea.vue`:
- 第 ~18 行 `view.scanFile?.per_pattern[pid]?.pattern_spec.display_name ?? pid` → `pid`

Edit `path2_web_ui/src/components/SidebarPatternPanel.vue`:
- 第 ~18 行 `{{ p.display_name }}` → `{{ p.pattern_id }}`

Edit `path2_web_ui/src/components/TopologyControl.vue`:
- 第 ~35 行 `{{ box.node.label || box.node.node_id }}` → `{{ box.node.node_id }}`

Edit `path2_web_ui/src/components/DetailSidebar.vue`:
- 第 ~17 行 `{{ node.label || node.node_id }}` → `{{ node.node_id }}`
- 第 ~22 行 `{{ node.label || node.node_id }}` → `{{ node.node_id }}`

- [ ] **Step 3: 改 SVG 宽度估算**

Edit `path2_web_ui/src/render/topology.ts:22`:
- 现:`const chars = [...(n.label || n.node_id)].length`
- 改:`const chars = [...n.node_id].length`

(注释保留,语义未变 — 按 Unicode 码点。)

- [ ] **Step 4: 清理测试 fixtures**

grep 穷举:

```bash
grep -rn "display_name\|\.label\b\|'label'\|\"label\"" path2_web_ui/tests path2_web_ui/src --include="*.ts" --include="*.vue"
```

逐条核对,与本字段相关的(节点 label / pattern display_name)删除 / 简化;与本字段无关的(其他业务字段叫 label 的 — 如 ECharts 系列内部 label / `e.label` for edge path label / hover label 等)不动。

特别检查 `path2_web_ui/tests/fixtures.ts`(已知含此类 fixture)。

- [ ] **Step 5: 跑 vitest**

```bash
cd path2_web_ui && npx vitest run 2>&1 | tail -30
```

Expected: 全绿;如有失败,定位是 fixture 未更新还是断言未更新,补改后重跑。

- [ ] **Step 6: 跑 vue-tsc**

```bash
cd path2_web_ui && npx vue-tsc --noEmit 2>&1 | tail -20
```

Expected: 0 error;若有 TS error 指向 `display_name` / `label`,补改。

- [ ] **Step 7: 跑 build**

```bash
cd path2_web_ui && npm run build 2>&1 | tail -10
```

Expected: build 成功。

- [ ] **Step 8: Commit**

```bash
git add path2_web_ui/src/types.ts path2_web_ui/src/components/SidebarResultList.vue path2_web_ui/src/components/ChartArea.vue path2_web_ui/src/components/SidebarPatternPanel.vue path2_web_ui/src/components/TopologyControl.vue path2_web_ui/src/components/DetailSidebar.vue path2_web_ui/src/render/topology.ts
# 加 Step 4 改的 fixtures/tests
git status     # 核对范围
git -c commit.gpgsign=false commit -m "$(cat <<'EOF'
refactor(ui): 化简显示名 fallback 与类型,直接使用 pattern_id / node_id

后端不再 emit display_name/label(per Task 1)。前端 5 处模板 ?? 兜底
化简为直接 id;types.ts 同步删两字段;SVG 节点框宽度估算字符源切到 node_id。

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: skill SKILL.md 新增「id 即显示名」段

**目标**:`.claude/skills/authoring-path2-app/SKILL.md` 在「渲染分流声明」段附近插入「id 即显示名」收尾纪律段。

**Files:**
- Modify: `.claude/skills/authoring-path2-app/SKILL.md`(在第 75-78 行「渲染分流声明」段紧邻插入新段落)

**Interfaces:**
- Consumes:无
- Produces:无(纯文档)

- [ ] **Step 1: 读 SKILL.md 第 70-85 行确认插入点**

```bash
sed -n '70,85p' .claude/skills/authoring-path2-app/SKILL.md
```

(允许用 cat 读小段;插入点 = 「渲染分流声明(收尾纪律,落盘前补)」段的紧后方,作为另一条「收尾纪律」。)

- [ ] **Step 2: 用 Edit 插入新段落**

在「渲染分流声明」段(`**渲染分流声明(收尾纪律,落盘前补)**:为每个 node 声明 NodeSpec.render_grid...`)整段之后,插入空行 + 以下段落原文:

```markdown
**id 即显示名(收尾纪律)**:path2 已删除 PatternSpec.display_name 与
NodeSpec.label / TopoNode.label — 前端直接显示 pattern_id / node_id。
- pattern_id / node_id 起名时即按"用户面板上要看到的英文标签"来定:
  英文、短、可读(`burst` / `tb` / `bo` / `bottom_breakout_burst`),
  不要写中文、不要写形如 `n1` / `role_a` 的占位 id。
- 防御性禁用:勿写 `display_name=...` / `label=...` kwarg —
  dataclass 会直接报 unknown keyword(编译期拦)。
```

- [ ] **Step 3: 核对插入结果**

```bash
sed -n '70,95p' .claude/skills/authoring-path2-app/SKILL.md
```

Expected:看到「渲染分流声明」段后紧跟新插入的「id 即显示名」段。

- [ ] **Step 4: Commit**

```bash
git add .claude/skills/authoring-path2-app/SKILL.md
git -c commit.gpgsign=false commit -m "$(cat <<'EOF'
docs(skill): authoring-path2-app 新增「id 即显示名」收尾纪律

字段 display_name/label 已删,id 直接显示给用户;skill 提示 id 命名
要英文短可读,并防御性禁用已删字段 kwarg。

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 5: 端到端 UI 实证

**目标**:启 web UI,加载真实扫描数据,目视确认四处显示全为英文 id、SVG 节点框尺寸合理、无 console error。

**Files:** 无 code 改动(若发现 SVG 框需调宽度系数 → 改 `render/topology.ts` 并 commit)

**Interfaces:**
- Consumes from Task 1/2/3/4:前后端全清,skill 已更
- Produces:实证报告

- [ ] **Step 1: 启全栈**

```bash
uv run python scripts/run_path2_web.py &
# 后端 + 前端 dev server 均在该脚本内拉起,等 5 秒
sleep 5
```

- [ ] **Step 2: 用 playwright MCP 打开浏览器并扫一次**

```
mcp__plugin_playwright_playwright__browser_navigate http://localhost:5173
# 在 SidebarPatternPanel 勾选 bottom_breakout_burst
# 点扫描;等 SidebarResultList 出结果
```

(具体交互按界面实际控件;若 ScanResultDialog 弹窗,继续。)

- [ ] **Step 3: 截图四个面板**

```
mcp__plugin_playwright_playwright__browser_take_screenshot filename="task5-1-sidebar-pattern.png"     # SidebarPatternPanel
# 点结果列表中一行,加载 K 线
mcp__plugin_playwright_playwright__browser_take_screenshot filename="task5-2-topology.png"     # TopologyControl 节点框
mcp__plugin_playwright_playwright__browser_take_screenshot filename="task5-3-sidebar-result.png"     # SidebarResultList
mcp__plugin_playwright_playwright__browser_take_screenshot filename="task5-4-chart-area.png"     # ChartArea dropdown
```

- [ ] **Step 4: 视觉核查清单**

读每张截图,逐项确认:
- [ ] `SidebarPatternPanel`:pattern 名显示为 `bottom_breakout_burst` / `bo_only` 等英文 id,无中文
- [ ] `SidebarResultList`:列表头显示 pattern_id(英文),无 `display_name` 残留
- [ ] `ChartArea`:顶部 dropdown 显示 pattern_id,无中文
- [ ] `TopologyControl`:每个节点框内显示 `bo` / `burst` / `tb` 等英文 id,框宽度合理(文字未溢出、框未过宽过窄到失衡)
- [ ] `DetailSidebar`(若打开):node 名显示为 node_id 英文

- [ ] **Step 5: 加载老 JSON 兼容性实证(若 Task 2 跑了)**

若 Task 2 已产 `baseline_legacy.json` 且未失败,本步骤可省;否则:
```bash
ls outputs/path2_eval/
```
找一个老 JSON 文件,在 UI 中触发加载,确认渲染正常(老 JSON 含 `display_name`/`label` 字段但被忽略,UI 走 id 显示)。

- [ ] **Step 6: console 检查**

```
mcp__plugin_playwright_playwright__browser_console_messages
```

Expected: 0 error;warning 与显示名无关可忽略。

- [ ] **Step 7: SVG 宽度估算若不合理则调整**

若 Step 4 发现 TopologyControl 节点框文字溢出或框明显过宽:
- 读 `path2_web_ui/src/render/topology.ts` 看 width 公式
- 调常量系数(如每字符宽度 px 值)
- 重启前端,重截图核查
- 若有改动 → commit:`refactor(ui): topology 节点框宽度系数适配 ASCII id`

- [ ] **Step 8: 关浏览器 + 关后端 + 清 playwright 缓存**

```
mcp__plugin_playwright_playwright__browser_close
kill %1     # 或 pkill -f run_path2_web
rm -rf .playwright-mcp/*     # 本 task 用了 playwright MCP,清缓存
```

- [ ] **Step 9: 最终 4-gate 全绿确认**

```bash
uv run pytest tests/path2 tests/path2_web tests/path2_apps -q
cd path2_web_ui && npx vitest run 2>&1 | tail -5 && npx vue-tsc --noEmit && npm run build 2>&1 | tail -3
```

Expected: pytest 全 PASS / vitest 全 PASS / vue-tsc 0 error / build 成功。

- [ ] **Step 10: 实证报告(本 task 收尾汇报)**

向上层报告:
- 4 个 gate 状态(pytest/vitest/vue-tsc/build)
- 4 张截图路径
- console error 数
- SVG 宽度系数是否调整(yes/no)
- 老 JSON 兼容性(yes/no,Task 2 是否动了 schema)

无 commit(除非 Step 7 调了宽度系数)。

---

## 自查与回归
- 完整 grep:`grep -rn "display_name\|\.label\b" path2 path2_web path2_web_ui --include="*.py" --include="*.ts" --include="*.vue"` 应仅返回业务上「恰好叫 label 但与本字段无关」的命中(逐条人核确认)
- 已修改文件清单:`git diff --name-only master..HEAD` 应与 spec §1-4 范围一致,无意外文件
