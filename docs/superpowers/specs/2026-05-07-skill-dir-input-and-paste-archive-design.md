# 设计：analyze-stock-charts 支持目录输入 + paste 自动归档

> **创建日期**：2026-05-07
> **状态**：design 已确认，待生成 implementation plan
> **范围**：扩展 `.claude/skills/analyze-stock-charts/` 的输入处理；新增 ephemeral 自动归档；不改 7 teammate prompts

---

## 1. 问题陈述

当前 skill 的 3 种输入模式（拖入 / paste / 路径列表）共享同一缺陷：**当输入是 paste/drag 来的图片，路径是 `~/.claude/image-cache/<sessionId>/N.png`，session 结束后该目录被清理，对应路径失效**。

具体痛点：

1. **跨 session 不可重跑**：user 在 session A 跑了一次 batch，几小时后想用调整后的 model_tier 重跑，但 image-cache 路径已失效。
2. **无法归档**：跑出有趣的 batch 后想把原图存档供日后参考，需要 user 手动找 image-cache 路径并 `cp`。
3. **补图困难**：user 看完结果想"加一张图重跑做对比"，需要补图 + 凑出原 batch 的 N 张图，但原 N 张已找不到。

同时，user 提到一个 UX 改进：希望直接给 skill 一个**目录路径**作为输入，而不是逐张拖入或列路径。

---

## 2. 设计目标

| # | 目标 |
|---|---|
| G1 | 支持目录路径作为输入（与拖入 / 路径列表并列） |
| G2 | paste/drag 来的 ephemeral 图片自动归档到永久路径（`docs/charts_analysis/images_cache/<run_id>/`） |
| G3 | 已经是永久路径的 user 输入（目录或文件路径）保持原样，不复制 |
| G4 | 对 7 teammate 透明 — 它们只看到永久 chart_paths，不区分图来自哪里 |
| G5 | LLM-only 合规（不引入 Python 脚本作为 runtime 依赖；只用 Bash mkdir/ls/cp 原子工具调用） |
| G6 | 不破坏现有 chartset_hash 机制（同 batch 仍稳定 hash） |

---

## 3. 核心决策（与用户讨论后定稿）

| 决策 | 选择 | 理由 |
|---|---|---|
| 输入模式数量 | **3 → 4**（新增 dir 模式，与拖入 / paste / 路径列表并列） | YAGNI；不破坏现有触发方式 |
| 目录扫描范围 | **顶层 only**（不递归子目录） | batch = "3-7 张同形态" 是扁平概念；user 想分层就组织成多个 dir |
| 接受的扩展名 | **`.png .jpg .jpeg`**（含大写变体），其他格式警告但跳过 | VLM 对这三种最稳；webp 偶有兼容问题；未匹配文件警告但不阻塞 |
| 多源混合输入 | **合并**（dir + 拖入 + paste + 路径列表 → 一个 batch） | user 实际场景：dir 主样本 + 临时补几张做对比 |
| 自动归档范围 | **仅 ephemeral** image-cache 路径 | 永久输入复制是浪费存储；user 自管理永久目录不该被 skill 二次干涉 |
| 归档目录命名 | `docs/charts_analysis/images_cache/<run_id>/`（**与 runs/<run_id>/ 共享 run_id**） | 一目了然映射"输入图集 ↔ 输出 run 目录" |
| 归档触发时机 | skill 入口的 pre-check 阶段（spawn team 之前） | 此时 image-cache 还在（同 session），cp 必成功；归档后 spawn 用永久路径 |
| ephemeral 检测 | 路径字面匹配 `/.claude/image-cache/` | 简单可靠；image-cache 路径有固定 pattern |

---

## 4. 输入处理流程（设计核心）

skill 入口在现有 `§3 输入预检`之前**新增 §3.0 路径展开 + 归档**步骤：

```
def expand_and_archive_inputs(user_message) -> list[Path]:
    # Step 1: 提取 path-like tokens
    raw_paths = []  # list of {path, source: 'ephemeral' | 'persistent_file' | 'persistent_dir'}
    
    for token in extract_path_tokens(user_message):
        # 1a. ephemeral 检测（字面匹配）
        if "/.claude/image-cache/" in token:
            if not Path(token).exists():
                raise UserError(
                    f"image-cache 路径 {token} 已失效（可能是旧 session 残留）。"
                    f"请重新粘贴或提供永久路径。"
                )
            raw_paths.append({path: token, source: 'ephemeral'})
            continue
        
        # 1b. 目录展开
        if Path(token).is_dir():
            allowed_exts = {'.png', '.jpg', '.jpeg'}  # 大小写变体均接受
            for f in Path(token).iterdir():  # 顶层 only，不递归
                if f.suffix.lower() in allowed_exts:
                    raw_paths.append({path: str(f), source: 'persistent_dir'})
                else:
                    warn(f"跳过 {f.name}：扩展名 {f.suffix} 不在 PNG/JPG/JPEG 内")
                    # warning 输出到 skill 入口给 user 的进度消息中（与 bootstrap / spawn 进度同渠道）
            continue
        
        # 1c. 单文件路径
        if Path(token).is_file():
            if Path(token).suffix.lower() in {'.png', '.jpg', '.jpeg'}:
                raw_paths.append({path: token, source: 'persistent_file'})
            else:
                raise UserError(f"文件 {token} 扩展名不支持（仅 PNG/JPG/JPEG）")
            continue
        
        # 1d. 都不是 → 当文本忽略
    
    # Step 2: 按 abspath 去重（避免同文件因 dir + paste 双重出现）
    raw_paths = dedup_by_abspath(raw_paths)
    
    # Step 3: 计算 run_id（基于全部 paths 的文件名）
    chartset_hash = sha1(sorted([Path(r.path).name for r in raw_paths]))[:5]
    run_id = f"{now('YYYY-MM-DD_HHMMSS')}_{chartset_hash}"
    
    # Step 4: 归档 ephemeral 项
    ephemeral = [r for r in raw_paths if r.source == 'ephemeral']
    if ephemeral:
        archive_dir = f"docs/charts_analysis/images_cache/{run_id}/"
        bash_run(f"mkdir -p {archive_dir}")
        for r in ephemeral:
            new_path = f"{archive_dir}{Path(r.path).name}"
            bash_run(f"cp {r.path} {new_path}")
            r.path = new_path  # 替换为永久路径
    
    # Step 5: 返回最终 chart_paths（全永久）+ run_id
    return [r.path for r in raw_paths], run_id
```

> **注**：以上是伪码描述决策树，**不会**作为 Python 脚本提交进 skill。skill 入口（调用方 Claude）按此决策逻辑用 Bash 工具调用（mkdir / ls / cp）+ LLM 跟规则（路径模式判定 / 去重 / hash）完成。这是 SKILL.md §0.2 L2 行为（LLM 跟结构化规则 + 原子工具调用），不是 L3 真函数。

---

## 5. 归档目录布局

```
docs/charts_analysis/                        ← v2.1 已 .gitignore
├── images_cache/                            ← 新增（自动归档目录）
│   └── 2026-05-07_113000_xy3kf/             ← 与 runs/<run_id>/ 同 run_id
│       ├── 1.png                             paste 来的图（cp 自 ~/.claude/image-cache/.../1.png）
│       ├── 2.png
│       └── 3.png
├── stock_pattern_runs/
│   └── 2026-05-07_113000_xy3kf/             ← 与 images_cache/<run_id>/ 同名
│       ├── findings.md
│       └── written.md
└── stock_pattern_library/
    └── ...                                   不变
```

user 想知道"某次 run 用了哪些图"，去 `images_cache/<run_id>/` 看即可。

---

## 6. 触发场景（更新）

| 场景 | skill 入口处理 | 归档？ |
|---|---|---|
| user paste 1-9 张图 → 立刻"分析" | 检测 image-cache 路径，归档到 `images_cache/<run_id>/`，spawn team | ✅ |
| user 拖入 1-9 张图 → 立刻"分析" | 同上（拖入也走 image-cache） | ✅ |
| user 给目录路径 `/home/yu/charts/long_base/` | 顶层扫描扩展 → spawn team（目录原地引用） | ❌ |
| user 列文件路径 `@/home/yu/foo.png @/home/yu/bar.png` | 加入 chart_paths（原地引用） | ❌ |
| user 混合：dir + paste 几张补图 | dir 顶层扫 + paste 归档；合并去重；spawn team | ✅（仅 paste 部分归档） |
| user 引用旧 session 的 image-cache 路径 | 检测路径不存在 → 报错"路径已失效，请重新粘贴或提供永久路径" | n/a |

---

## 7. 文档改动范围

| 文件 / 段 | 改动 | 估时 |
|---|---|---|
| `SKILL.md` `description` 字段 | 加"支持目录路径；paste 自动归档" | 2 min |
| `SKILL.md §1 触发条件` | 新增 "user 提供本地目录路径" 触发条目；澄清 paste 触发 | 5 min |
| `SKILL.md §2.1 必需输入` | "图片来源"改 4 种：拖入 / paste / 路径列表 / 目录路径 / chat 历史；加持久化说明 | 5 min |
| `SKILL.md §3.0`（**新增段**） | 输入路径展开 + 归档伪码 + 决策树 | 30 min |
| `SKILL.md §3 现有 4 步 pre-check` | 编号顺移；逻辑不变（chart_paths 已永久） | 3 min |
| `SKILL.md §3.1 Bootstrap` | 创建目录列表加 `docs/charts_analysis/images_cache/` | 2 min |
| `SKILL.md §4 runId 计算` | 显式说明 `images_cache/<run_id>/` 与 `runs/<run_id>/` 共享 run_id | 3 min |
| `references/00_README.md` | 文件树更新含 `images_cache/` | 5 min |
| `references/02_memory_system.md` §A.1 | 库 root 物理切分图加 `images_cache/`（标注 user-managed） | 5 min |
| `docs/explain/analyze_stock_charts_logic_analysis.md` §5 | 输出位置树加 `images_cache/`；§6.1 触发示例加目录模式 | 10 min |

总改动：**约 1 hour**，全是 markdown 编辑。

---

## 8. 不做（YAGNI）

- ❌ 不递归扫描子目录
- ❌ 不支持 glob pattern（`*.png` 等）
- ❌ 不归档 user 永久输入（不浪费存储）
- ❌ 不做归档目录 retention / 自动 cleanup（user 自删；磁盘不够手动清）
- ❌ 不做 image content fingerprint dedup（依赖 abspath 去重 + user 自觉）
- ❌ 不存"哪个 run 用了哪个 images_cache 目录"的反向索引（用同 run_id 关联即可）
- ❌ 不为 dir 模式新增 batch_label / batch_id 字段（chartset_hash 已稳定）
- ❌ 不修改 7 teammate prompts（归档对 teammate 透明）

---

## 9. 风险与边界

| 风险 | 影响 | mitigation |
|---|---|---|
| user 在 paste 后**未立即**调用 skill（中间穿插聊天），image-cache 仍在 session 内但路径长度变化（cache 是按消息 index 分的） | path 引用变化导致归档失效 | 实践中 paste 立即调用是主流；中间穿插的场景 user 自己 paste 时能看到新路径，重提即可 |
| user 提供 image-cache 路径但实际是旧 session 残留 | 路径不存在 → 报错 | §3.0 检测 path.exists()，报错 + 提示重新粘贴 |
| dir 含 100+ 张图（user 误把整个图库给了 skill） | N ≥ 10 触发 § 拒绝，但扫描可能慢 | dir 扫描有上限警告："扫到 N 张，仅前 9 张参与；建议分批" |
| user 重跑同一 batch（同一 dir，同 image-cache paste） | 同 chartset_hash → 同 run_id；timestamp 不同 → 实际生成新 run_id（同 hash 不同 timestamp） | 这是 expected — 每次跑都是独立 run，不应混淆 |
| images_cache/ 占空间膨胀 | user 跑多了硬盘满 | 不自动清理；user 看到目录大可手动删；`docs/charts_analysis/` 已 .gitignore 不影响 git |

---

## 10. 验收标准

实施后用以下场景验证：

1. **单 paste 触发**：粘贴 5 张图 + 输入"分析" → 检查 `images_cache/<run_id>/` 内有 5 张 cp 来的图；team 跑完 written.md 引用永久路径
2. **目录模式**：`/some/dir/ + 用 sonnet 跑分析`，dir 内含 4 张 png + 1 张 webp + 1 个子目录 → spawn team 用 4 张 png；webp 警告输出；子目录被忽略；`images_cache/<run_id>/` **不存在**（因无 ephemeral 项）
3. **混合模式**：dir 路径 + paste 1 张图 → 合并 batch；只 paste 那 1 张被归档；dir 内的图原地引用
4. **旧 session 路径**：user 引用旧 session 的 image-cache 路径 → 报错"路径已失效"
5. **重跑稳定性**：同一 dir 跑两次 → 同 chartset_hash，不同 timestamp → 不同 run_id；两次的 images_cache/<run_id>/ 不存在（dir 是永久的，不归档）
6. **chartset_hash 稳定**：同一 batch（无论来自哪种源）→ 相同 chartset_hash

---

## 11. 与现有架构的兼容性

- ✅ chartset_hash 机制不变（仍 sha1 of sorted basenames）
- ✅ 7 teammate prompts 不动（chart_paths 对它们仍是文件路径列表）
- ✅ run_dir 结构不变（仍 `runs/<run_id>/`）
- ✅ library_root 结构不变（patterns / conflicts / _meta）
- ✅ v2.1 的 LLM-only 设计约束不破坏（归档用原子 Bash 工具调用，不引入 Python 脚本）
- ✅ .gitignore 现有规则覆盖 `images_cache/`（已含 `docs/charts_analysis`）

---

## 12. 后续步骤

设计 approved 后：
1. → writing-plans skill 生成 implementation plan
2. → subagent-driven-development 执行
3. → 单 commit 提交所有 markdown 改动
