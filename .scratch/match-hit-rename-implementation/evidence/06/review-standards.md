# 票 06 独立审查：Standards 一轴（原文）

固定点 86459c6，审到 6e13fd4。

**Standards 审查：票 06（86459c6...HEAD）**。仓库无 CODING_STANDARDS.md 和 CONTRIBUTING.md；日志只看了性质。

**(a) 硬违规**
1. `.scratch/annotation-path2/manual.md:73`「全仓只有这一个意思」不实：`path2_web/api.py:583` 的 `"match"` 字段仍指参数快照一致。违反 CLAUDE.md「文档只反映当前代码状态」；票面口径是「讨论层面」。
2. 影响低：证据脚本的新函数缺 docstring，违反「编码规范·Docstrings」。涉及 `check_glossary.py` 的 `check_refs`、`check_entries` 等，`residual_check.py` 的 `cmd_report`、`masked`、`region_of`，`compare_with_01.py` 的 `load`，`wall_redirect.py` 全部函数。
3. 影响低，可争议：`path2_web/GLOSSARY.md:28` 改名后仍无英文句，`path2/GLOSSARY.md:189` 的 `matching` 英文缺主体和条件。违反命名规则第 5 条。

**待收尾（Completion artifacts，完成记录须补）**：`test_compare.txt` 终检侧无提交号和工作树状态，基线只有短哈希，而 `run_e2e.sh` 要求临时改配置。vitest、vue-tsc 的命令不在任何脚本里。

**(b) 判断题**
- 可能的 Mysterious Name：`residual_check.py:154` 的形参 `allow_path` 接 `--allow`，`--allow-path` 却传给 `allow_paths_file`。
- 可能的 Duplicated Code：
  - `cmd_report` 与 `cmd_area` 循环同形，`load_allow_path` 与 `load_allow` 同形。
  - `e2e/e2e_backend.py` 与 evidence/02 的字节相同，docstring 还写「票 02」。
- 基线外：`run_py.sh:5`、`run_e2e.sh:6` 写死 worktree 路径，worktree 删除后失效。

**越轴提醒**：e2e 的 `annotate-rally-random` 由通过变失败，验收要求失败清单相同，交 Spec 轴。

## 处理

- 硬违规 1：已修，`manual.md:73` 改成「讨论里只有这一个意思」。
- 硬违规 2：已修，新函数都补了 docstring。
- 硬违规 3：`matching` 的英文已补主体。`path2_web/GLOSSARY.md:28` 不改：票面要这一条「就地改，不移行」，只改三档的名字和定义；这份词表里早于命名规则的词条都没有英文句，补这一条要加一行，会移 `path2_web/GLOSSARY.md:45`、`:48` 的引用。
- 待收尾：`test_compare.txt` 改由 `make_compare.sh` 生成，写明两边的完整提交号和工作树状态，以及 vitest、vue-tsc 的命令。
- Mysterious Name：已修，形参改成 `line_allow_file`、`path_allow_file`。
- Duplicated Code：`e2e_backend.py`、`e2e_results.py` 的副本已删，脚本直接用 evidence/02 那两份。`cmd_report` 与 `cmd_area`、`load_allow_path` 与 `load_allow` 不改：只跑这一次的检查脚本，`cmd_area` 要和票 05 那份保持同样的输出，抽公共函数比重复更重。
- 写死路径：已修，两个脚本都按自身位置找 evidence 目录。
- 越轴提醒：见 `review-spec.md` 的处理。
