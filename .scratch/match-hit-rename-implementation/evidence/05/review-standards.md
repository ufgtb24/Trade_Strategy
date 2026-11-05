# 票 05 独立审查：Standards

固定点 239974f，审查时分支尖 66b6752。审查子代理没有看到执行过程。

## 报告（原文）

**Standards 审查：票 05（239974f..HEAD）**

已确认仓库没有 CODING_STANDARDS.md 和 CONTRIBUTING.md。

**(a) 成文规范违反**

1. **硬，新造了代码里没有的名字。** `docs/explain/path2_漏检分析_v1_v2_脉络.md:61,90,119`：`AnalysisResult.dropped_matches` 换成了 `AnalysisResult.dropped_hits`（来自 `rename_docs.py:186`）。
   - `path2/dag/*.py` 里根本没有 dropped 字段。拆分总览只把这个改名派给 02 的 JSON 键和 03 的前端。
   - 违反 CLAUDE.md「文档只反映当前代码状态」。票 04 的 Standards 审查已把同类情况判为硬违反。
   - 同一批里 `SKIP_TILL_NEXT_MATCH` 按过时旧名留着没改，两处处理不一致。
   - 建议：改回旧名并列入过时清单。

2. **硬，过时清单漏项。** `docs/path2/guide/hits-and-results.md:536`：`print(hit.event_id)`。
   - `path2/` 里已没有 `event_id`，CLAUDE.md「编码规范」也把它列为退役名，但 `stale_names.txt` 没收。票面要求过时处列清单。
   - 原因在 `stale_names.py:43`：按整词比对全部代码，`path2_web` 里还有这个词，就判成「还在」。别的名字也可能这样漏掉。
   - `stale_names.py` 只扫 `docs/path2`，`docs/explain` 的旧名靠手工收。

3. **硬，影响低。** 证据脚本的函数缺 docstring，如 `check_memory.py` 的 `norm` / `front`，`token_diff.py` 的 `mask` / `compare`，`check_links.py` 的 `slug` / `anchors`。CLAUDE.md「编码规范」要求函数写明用途；这条是否管一次性脚本，可以另议。

4. **待收尾，现在还不算违反。** `evidence/05/logs/` 里没有提交号或哈希。票还在进行中，完成记录要补上代码身份和记忆目录前后的身份（`implementation-tickets.md`「Completion artifacts」）。

**(b) 判断题**

- **possible Mysterious Name（`求解` 的搭配）：** `getting-started.md` 的「跑通你的第一个走势求解」、`example-bottom-burst.md` 的「把它求解出来」。词表里求解的对象是事件组合，「走势求解」「形态求解」接近自造词。这里最好说「第一次命中」。
- **possible Mysterious Name：** `check_memory.py:27` 的 `HIT = re.compile(r"match|匹配")`，在 hit 已有定义的改名票里读着混。`gen_allow.py:41,47` 的 `_` 后面还被读取了。
- **possible Speculative Generality：** `token_diff.py:57` 的 `ok` 过了行数检查后不会再变，`if x == y: continue` 也没验证什么。所以摘要里「未改行逐字校验：通过」这半句恒真，实际只校验了行数。
- **possible Duplicated Code：** `rename_docs.py:207-233` 和 `rename_memory.py:87-110` 的主循环同形。都是一次性脚本，价值低。
- **`命中` 作动词：** 如「具体命中了哪段下跌」。命名规则里 hit 是名词，动作词是 recognize；但用户定了译法，原文也有这种用法，可接受。

**不报**

- 词表里 match 还是旧义。
- CLAUDE.md 的 `detected、qualified、in_hit` 要等 06 才有对应词条。
- `feature_candidates.md` 和 `next_mode_ptr_advance_通俗解释.md` 里的 `docs/research` 引用，改动前就有。
- 证据脚本用 argparse：由 cc 调起，不受限。
- 手改行里留着的「角色」：票面排除了无关过时内容。
- `residual_check.py` 按票复制一份：规范认可，且和 01 的版本只差一行修复。

## 处理

- (a)1 已修：三处改回 `dropped_matches`，进 `allow_05.tsv` 的「docs/explain 过时旧名」，也写进过时清单。
- (a)2 已修：`stale_names.py` 加一节，CLAUDE.md 点名退役的身份词不靠比对、一律列。`docs/explain` 的过时旧名在残留检查里单列。
- (a)3 已修：四个证据脚本的函数都写了 docstring。
- (a)4 已修：`logs/memory-identity.txt` 记备份与改后的内容哈希，完成记录写提交号。
- 「走势求解」「把它求解出来」已改：`getting-started.md` 标题改「你的第一次命中」，`example-bottom-burst.md` 改「把它找出来」；「形态求解」四处改成「求解」。
- `HIT` 改名 `OLD_WORD`；`gen_allow.py` 的 `_` 改名 `lineno`；`token_diff.py` 去掉恒真的 `ok`，摘要只说「行数校验」。
- 不改的坏味道：`rename_docs.py` 和 `rename_memory.py` 主循环同形。都是只跑一次的脚本，为它们抽公共模块比重复更重。
- 接受：「命中」作动词。用户定了「匹配」改「命中」，原文语序就是动词用法。
