# 票 01 独立审查：规范（Standards）

审查对象：`impl/01-framework-python-api`，`git diff 1359914...690f1d7`。由 code-review skill 派出的子代理完成，看不到执行过程。原文如下。

**Standards 评审（票 01，1359914..HEAD）**

**违反文档规范（1 条，中等）**

1. `scripts/gate_burst_2x2.py` 的 `main()` 和 `_check`。这个函数里 `matched` 改成了 `hit_tickers`，但同一个函数里还留着两个名字：
   - `hits: dict[str, set]`：按 cell 存股票代码集合，和 `hit_tickers` 装的是同一类东西；
   - `ticker, hit, n_burst, err = f.result()`：这里的 `hit` 是 bool。

   这违反票 01 的 Inherited Direction：「`hits` 留给『一组 hit』这个名词」，返回 bool 的叫 `has_hit`。也违反 `GLOSSARY-MAP.md` 命名规则第 2 条「一个名字只占一格」。建议改成 `hit_tickers_by_cell` 和 `has_hit`。这两个名字改名前就在，但本票明确管「gate_burst_2x2.py 里的 Python 名字」。

**判断项（基线异味，都不算硬违规）**

2. **局部名新旧混用**：
   - `path2/dag/engine.py` 用了 `h` / `hid`，`scripts/path2_eval_bottom_burst.py` 也改成了 `h`；
   - `tests/path2*` 全部还用 `m`，如 `tests/path2/dag/test_engine_hit_id_disambiguate.py:41` 的 `mids = [m.hit_id for m in res.hits]`；测试数据 `hit_id="m1"` 也一样；
   - `m` 是 match 的缩写，残留检查扫不到它。属于 Mysterious Name，影响小。
3. **换行续行没对齐**：名字变短以后，下面这几处续行都多缩进了 2～3 格：
   - `path2_web/eval_runner.py:130`
   - `tests/path2/test_eval.py:227/284/292/355`
   - `tests/path2/dag/test_a2_isolated_consumed.py:77`
   - `.claude/skills/feature-study/extract.py:209`

   `path2_eval_bottom_burst.py` 重新对齐了，其余没有，处理不统一。纯外观问题，black 在依赖里但没强制。
4. **`tests/path2/dag/_oracle.py` 的 `hit_key`**，docstring 写「可迭代的 hit（求解层的解）」：这里处理的是还没物化的解（Solution / assign 字典）。按命名规则表，hit 指物化后的那次识别结果，这样叫有点把两格混了。可以考虑叫 `solution_key`。
5. **`residual_check.py` 有两处问题**：
   - `CATEGORIES` / `CN_CATEGORIES` 里写死了几条只对应个别行的字面量：「src_10#0 不匹配」「与它匹配的伙伴」「既有测试只 match 字段名」「no pkl matched」「形态不匹配」「误匹配」。脚本自己的 docstring 规定，逐行人工判定要进 `--allow` 清单，所以现在登记例外的地方有两处（Duplicated Code）。更要紧的是，02～06 都会复用这个脚本（共用执行边界第 11 条），「形态不匹配」「误匹配」这类宽泛短语会变成全仓豁免，可能把文档或 skill 里的旧义残留漏掉。建议挪进 `allow_01.tsv`。
   - `_strip_categories` 里的局部名 `hit_cats` 用的是「命中某一类」这个通用意思。允许列表的「通用的 hit」一行放行这种用法，但出现在改名工具自己的代码里，读起来容易混。

**查过、没有问题的**

- 注释和 docstring 都是中文，指 app 产出的「匹配」统一改成了「命中」，没有新写开发历史。
- JSON 键 `"matches"` / `"match_id"` 原样保留，符合票的范围（归 02）。
- `compare_outputs.py` 的 `_pick` 同时认新旧名，但它只在证据脚本里，用意 docstring 写清了，不违反「不留旧名」（那条管的是产品代码）。两个证据脚本用 argparse 也没问题：它们由 cc 自己调起，不受入口脚本规则限制。
- 有两处问题是本票之前就有的，不算本票违规：
  - `tests/path2/fixtures/positive_case.py` 被改到的那几行本来就是英文注释，没顺手翻成中文；
  - `engine.has_hit` 没有 docstring。
