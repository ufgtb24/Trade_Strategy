# 票 18 独立审查：Standards 轴

审的是 `beb78fe...d9d1584`（code-review skill，Standards 子代理，2026-11-16）。原文如下。

---

## 标准审查：票 18（d9df886..d9d1584）

**一、违反项目文档规范的地方**

1. **证据没有记下它是用哪版代码跑的（硬性违反）。** `implementation-tickets.md` 的「Completion artifacts」要求证据写明所跑代码的提交号，未提交的代码要写 blob id。`backfill_reference.py` 产出的 `dry-run/plan.json`、`status_*.json`、`write_result.json` 都没有这项。按 `pytest.txt` 的说法，这个脚本试跑时还没提交。`old_reference.py:59-64` 已经示范了做法（记 commit 和工作区是否改动），但补存脚本没照做。真写只跑一次，`write_result.json` 是唯一凭证，所以建议在真写之前，让三个子命令的输出都记上当前提交号、工作区是否改动、本脚本的 `git hash-object`。
2. **函数缺 docstring（轻度，属字面违反）。** CLAUDE.md「编码规范」要求每个函数说明用途、参数和算法。`backfill_reference.py` 有 12 个函数，其中 8 个没有 docstring：`_sha`、`_cfg`、`_is_real_dir`、`_old_reference`、三个 `cmd_*`、`main`；`old_reference.py` 的 `main` 也没有。模块 docstring 已经讲清了三个子命令，票 17 的证据脚本也同样省略，所以算轻度。其中 `_old_reference` 校验不过会直接退出，最好补一行说明。
3. **证据里写了临时目录的绝对路径（轻度）。** `old_reference.json` 的 `code_root`、`view_dataset_dir` 写的是临时旧版 worktree 的绝对路径，「Completion artifacts」说临时的东西不应引用。提交号和数据指纹都已记下，代码和数据的身份不受影响，可以删掉这两项。
4. **附带一条，归 Spec 审查：** `dry-run/` 下没有 `before_files.json`、`after_files.json`。票 18 第 31 行要求真写时把这两份存进证据。

以下几处核对过，不算违反：
- `_files` 直接读标注目录的文件，但只算哈希、不解析内容，而且这些哈希正是票里要求的。
- 往标注目录写入，有票 18 第 20 行记下的用户本票特许。
- 用 argparse 是允许的：这是 cc 自己调起的脚本，不在 `scripts/` 下。
- 「基准 node」是词表 `path2/GLOSSARY.md:152` 词头里的说法，脚本里没有出现被避免的词；也没有引用 `docs/research`。
- 证据里没有 note 原文：`plan.json` 只存了每条记录的哈希。

**二、代码坏味道（都属判断，不是硬伤）**

- **重复代码：** 「`write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n")` 再 `print` 一遍」出现了 4 次（`old_reference.py:88-89`，`backfill_reference.py:131-132`、`162-163`、`206-207`）。`run_app(mod, cfg, sym, "1900-01-01", TRAIN_END, params, 20)`（`old:70`、`backfill:146`）和 `REFERENCE = "step"` 两个文件各写了一份。`reference_events` 照抄当前版本是必要的（旧版没有这个函数），docstring 也说明了，可以接受。
- **名字看不出意思：** `build_ops(r: dict)`（第 74 行）、`a`、`o`、`hs`、`bd`；`recs_a[i][1]`（第 190、198-199 行）要靠元组下标才知道取的是记录。
- **魔法值：** `"1900-01-02"` 用来代表「没有买点的一天」（第 148 行）；位置参数 `20` 实际是 label_horizon。
- **`--approved` 只是自报：** 它接受任意非空字符串（第 225 行），脚本没法核验用户真的点过头，不能把它当成真正的闸。
- **用法说明写错了路径：** `old_reference.py:4` 写的是 `<本票 worktree>/evidence/18/…`，少了 `.scratch/annotation-path2-implementation/` 这一段。
- **`old_reference.py:27` 引用了私有函数** `_resolve_end_events`。它要在旧版代码里跑，旧版没有公开入口可用，可以接受。
