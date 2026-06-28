# path2 显示名字段移除 — 设计

## 背景与动机

path2 web UI 当前显示的 pattern 与 role 中文名(如「底部反转突破爆发」/「突破爆发」/「回踩确认」/「单点突破(bo)」)来自 `PatternSpec.display_name` 与 `NodeSpec.label` / `TopoNode.label` 字段值,在 4 处 `path2_apps/*/dag_spec.py` 写死。用户希望 UI 显示英文。

经 fork 调查坐实:这两个字段**纯渲染用,零非显示消费**(无 ID/key/匹配/日志业务消费)。

经 brainstorming 锁定:**显示=id**(id 已是英文且语义清晰:`bo` / `burst` / `tb` / `bottom_breakout_burst` 等),由此两字段失去存在意义 — 直接删除最干净。

## 范围

**本 spec 处理**:
- 删 path2 内核两个字段(`PatternSpec.display_name` + `NodeSpec.label` / `TopoNode.label`)
- 4 处 `path2_apps/*/dag_spec.py` kwarg 删除
- 后端序列化不再 emit 这两个 JSON key
- 前端 5 处 fallback 化简(直接用 id)
- 前端 SVG 节点框宽度估算实证校准(中文宽字符 → ASCII 宇符)
- 测试/fixture/snapshot 清理
- `.claude/skills/authoring-path2-app/SKILL.md` 新增「id 即显示名」短约束

**不处理**(显式 out-of-scope):
- 前端 hardcode UI 中文串(`StopScanDialog.vue` 按钮 / `ChartArea.vue` Level title / `ScanResultDialog.vue` 状态徽章 / `SidebarResultList.vue` 状态提示) — 与 spec 字段无关,保留中文
- `.vue/.ts` 文件内中文注释 — 按 CLAUDE.md「注释/文档中文」规范保留
- `design-heuristics.md` skill 文件 — 不涉命名指引,无需修改
- 字段重命名(brainstorming 曾考虑统一为 `display_name`,被 fork 「直接删」结论取代)

## 设计

### §1 Python 层

**`path2/dag/nodes.py`**
- `NodeSpec` 删字段 `label: str = ""`
- 删 docstring 中 `label: 人类可读名(面板)` 行

**`path2/dag/spec.py`**
- `PatternSpec` 删字段 `display_name: str`
- `TopoNode` 删字段 `label: str = ""`
- `to_topology()` 投影修改:`TopoNode(n.node_id, n.detector.event_cls.class_id)` — 第三参数 `n.label` 删除

**`path2_apps/bo_only/dag_spec.py:33`**
- 删 kwarg `display_name="单点突破(bo)"`

**`path2_apps/bottom_breakout_burst/dag_spec.py`**
- `:48` 删 kwarg `label="突破爆发"`
- `:52` 删 kwarg `label="回踩确认"`
- `:65` 删 kwarg `display_name="底部反转突破爆发"`

### §2 后端 `path2_web`

**`path2_web/serialize.py:209-234` `serialize_pattern_meta()`**
- JSON 输出体删除两个 key:`"display_name"`(:234)、nodes[].`"label"`(:221)
- 单元测试中 assertion 同步删

**scan result JSON 文件向后兼容性 — 实证**:
- 旧 JSON 含 `display_name` / `label` key,新代码无对应字段
- Pydantic schema 若 `extra="ignore"`(默认) → 静默丢弃,UI 正常
- Pydantic schema 若 `extra="forbid"` → 加载报错,需顺手改成 `extra="ignore"`(一行)
- **验证步骤**:
  1. 用主分支扫一次产 baseline JSON(含老 key)落盘到 `outputs/path2_eval/`
  2. 切到本分支加载该 JSON 触发后端 `/scans/<id>` API,确认前端正常渲染
  3. 失败则定位 schema 修 `extra` 配置

### §3 前端 `path2_web_ui`

**类型定义(`path2_web_ui/src/types.ts` 或同等位置)**
- `PatternSpec` interface 删 `display_name`
- `TopoNode` interface 删 `label`

**5 处 fallback 化简**:
| 文件 | 位置 | 现状 | 改为 |
|---|---|---|---|
| `SidebarResultList.vue` | :64-66 | `displayNameOf(pid)` 函数 | 删函数,模板直接 `{{ pid }}` |
| `ChartArea.vue` | :18 | `pattern_spec.display_name ?? pid` | `pid` |
| `SidebarPatternPanel.vue` | :18 | `p.display_name` | `p.pattern_id` |
| `TopologyControl.vue` | :35 | `box.node.label \|\| box.node.node_id` | `box.node.node_id` |
| `DetailSidebar.vue` | :17,22 | `node.label \|\| node.node_id` | `node.node_id` |

**SVG 节点框宽度估算(`render/topology.ts:22`)**:
- 现:`[...(n.label || n.node_id)].length` 算字符数 × 字符宽度
- 改:`[...n.node_id].length`(简化)
- 风险:原中文字符 ≈ 14px / 个,ASCII ≈ 7px / 个 — 若公式硬编码中文宽度系数,SVG 框会过宽;若是自适应 `length × char_width` 则只需确认 char_width 常量
- **验证步骤**:启动 UI,观察 `TopologyControl` 节点框是否过宽或文字溢出,必要时调系数

**测试/fixture/snapshot 清理**:
- `path2_web_ui/src/**/__tests__/` 凡引用 `display_name` / `label` 的 fixture 与 assertion 全部清理
- `tests/**/test_serialize*` 类似处理
- 完整 grep 范围:`grep -rn "display_name\|\.label\b" path2 path2_web path2_web_ui --include="*.py" --include="*.ts" --include="*.vue"` 实施时穷举

### §4 skill `.claude/skills/authoring-path2-app/SKILL.md`

**插入点**:第 75-78 行附近(「渲染分流声明(收尾纪律,落盘前补)」紧邻,同属收尾纪律类)。

**新增段落原文**:
```markdown
**id 即显示名(收尾纪律)**:path2 已删除 PatternSpec.display_name 与
NodeSpec.label/TopoNode.label — 前端直接显示 pattern_id / node_id。
- pattern_id / node_id 起名时即按"用户面板上要看到的英文标签"来定:
  英文、短、可读(`burst` / `tb` / `bo` / `bottom_breakout_burst`),
  不要写中文、不要写形如 `n1`/`role_a` 的占位 id。
- 防御性禁用:勿写 `display_name=...` / `label=...` kwarg —
  dataclass 会直接报 unknown keyword(编译期拦)。
```

**`design-heuristics.md`** 不动。

## 测试与验证

**单元/集成测试**:
- `pytest`(后端 `path2`/`path2_web`)
- `npm test`(前端 vitest)
- `vue-tsc --noEmit`(类型校验)
- `npm run build`(构建)

**端到端实证**:
- 启 `run_path2_web.py`(后端+前端)
- 加载主分支产 baseline JSON,验证 UI 渲染正常(无报错、显示 id 文字、SVG 节点框尺寸合理)
- 截图 `TopologyControl` + `SidebarPatternPanel` + `SidebarResultList` + `ChartArea` 四处确认显示全为英文 id

**对拍**:
- 修改前后 `analyze()` 输出 `AnalysisResult` 应完全一致(本改动不动求解层)
- 修改前后 `serialize_pattern_meta` 仅少两个 JSON key,其他字段字节等价

## 风险与失败模式

| 风险 | 检测 | 缓解 |
|---|---|---|
| 旧 scan JSON 含老 key 致加载报错 | §2 验证步骤 1-2 | Pydantic schema 改 `extra="ignore"` |
| SVG 节点框宽度公式硬编码中文系数 | §3 验证步骤(启 UI 看 TopologyControl) | 调 char_width 常量 |
| 漏改 fallback 处导致 `undefined` 显示 | grep + 单元测试 + e2e | grep 穷举 `display_name\|\.label\b` |
| 测试 fixture 残留老字段 | pytest/vitest 报 unknown field | 顺手清理 |

## 验收

- 4 个 gate 全绿:pytest / vitest / vue-tsc / build
- 端到端实证:UI 全英文显示、SVG 节点框尺寸合理、加载旧 baseline JSON 不报错
- `grep -rn "display_name\|\.label\b" path2 path2_web path2_web_ui --include="*.py" --include="*.ts" --include="*.vue"` 应仅返回与本字段无关的命中(如其他业务字段也叫 label 的情形,需手核确认无残留)
- `.claude/skills/authoring-path2-app/SKILL.md` 新增段落已插入
