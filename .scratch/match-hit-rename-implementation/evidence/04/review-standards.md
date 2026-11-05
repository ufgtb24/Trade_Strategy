# 票 04 独立审查：Standards 轴

固定点 3e2637a，审查时的分支尖 d50f62f。子代理看不到执行过程。下面是它的报告原文，「处理」节是执行者写的。

**(a) 硬违反（依据 CLAUDE.md「文档只反映当前代码状态」）**

1. `diagnose-event/reference.md:100,121`、`detectors/throwback.md:80`：这几处让人去看 scan 的 `dropped_hits`（`drop_reason='isolated_consumed'`）。`path2/`、`path2_web/` 里没有这两个名字，票 04 自己的 `smoke_diagnose.txt` 也显示 scan 里没有这个键。旧文档本来就指向不存在的字段，这次只是改了名。
2. `feature-study/apps/bb_v1/adapter.py:23`：改动行仍写「当前配套的 scan（20260908T113225.json）」。实查该文件是旧格式（`"matches"` 634 处），`extract.py:159` 读 `["hits"]` 会报 KeyError。按 `scan-file-no-backcompat.md`，旧 scan 已作废。

其余规范没有发现违反：description 触发词、运行时只暴露业务层、命名规则、scan 兼容。

**(b) 基线坏味道（都是判断题）**

- possible Mysterious Name：`observe(m, …)` 的 hunk 写着「m: 一条 hit」（两个 adapter），`m` 是 match 留下的字母。同一个东西现在有三个名字：`hit`（`daily.py`）、`h`（`compare_longtable.py`）、`m`。
- possible Duplicated Code：`throwback.md` 和 `reference.md` 的「cand 为空」代码段相同，同一处改动要做两遍。`_engine_keys` 和 `_ref_keys` 的四态回填形状也相同。

改名分散在各文件是命名规则要求的，不算 Shotgun Surgery。其他坏味道没有发现。

## 处理

- (a)1 已修：三处删掉「看 dropped_hits」的指引。这个键后端不产，指引本身是错的，换名字改不对它。
- (a)2 已修：注释不再点名那份旧文件，改成「配套的 scan 要用现行格式（有 analysis.hits）」；新扫 scan 的 `tb.max_day_drop_pct` 核过存在（0.2）。
- (b) Mysterious Name 不改：`m` 是 01、02 留下的循环变量通名（`path2/eval.py`、`serialize.py` 的 `m_counts` 同样留着），`observe` 的 hunk 文档已写明「一条 hit」；只在这里改会多出一种约定。`compare_longtable.py` 的 `mm` 改成 `h`，是因为 `mm` 紧挨 `matches` 一起改。
- (b) Duplicated Code 不改：两处都是改名前就有的重复，本票只改名字。
