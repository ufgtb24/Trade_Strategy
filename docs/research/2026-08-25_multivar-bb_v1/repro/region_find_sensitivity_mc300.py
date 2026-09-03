# -*- coding: utf-8 -*-
"""多维稳健区 v2 · 识别端:候选长表 → 联合空间(真扫维 × where 维)打分 → 按股 bootstrap + 三口径校正
→ cells.csv / folds_6M.csv / 切片图 / 热力图 / region_report.md。
用法:复制到研究目录改 main() 常量后 `uv run python <路径>/region_find.py`
"""
from __future__ import annotations

import re, subprocess, sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
plt.rcParams["font.sans-serif"] = ["Noto Sans CJK JP", "WenQuanYi Zen Hei", "DejaVu Sans"]  # 中文标题/图例回退(matplotlib 只认 .ttc 里的第一个 name record,Noto CJK 在这台机器上只注册成 "...JP",但字形覆盖全部 CJK 统一表意文字,SC/TC 汉字同样能渲染)
plt.rcParams["axes.unicode_minus"] = False
import numpy as np
import pandas as pd

REPO = Path(subprocess.check_output(["git", "rev-parse", "--show-toplevel"], text=True).strip())
# 显式 REPO 相对路径,不用 Path(__file__).parent——本文件按文档用法要被复制到研究目录运行,
# 复制后 Path(__file__).parent 会指向复制目标目录而非 tune-gates/,导致 region_core 导入失败
# (与冒烟副本 region_find_smoke.py 同款写法)。
sys.path.insert(0, str(REPO)); sys.path.insert(0, str(REPO / ".claude/skills/tune-gates"))
from region_core import (VERDICT_CANDIDATE, VERDICT_CORRECTED_NEGATIVE, analyze_tensor,  # noqa: E402
                         bootstrap, cell_coords, fp_count, order_rows_by_rank, prepare,
                         split_half, tensor, tolerance, verdict)


def _load(lt_dir: Path) -> pd.DataFrame:
    return pd.concat([pd.read_parquet(p) for p in sorted(lt_dir.glob("part-*.parquet"))], ignore_index=True)


def _check_head_buffer(ledger: Path, head_buffer: int) -> None:
    m = re.search(r"HEAD_BUFFER=(\d+)", ledger.read_text())
    if not m or int(m.group(1)) != head_buffer:
        raise SystemExit(f"ledger 的 HEAD_BUFFER={m and m.group(1)} 与本脚本 {head_buffer} 不一致,拒绝比较")


def main() -> None:
    LONGTABLE_DIR = "docs/research/2026-08-25_multivar-bb_v1/longtable/"
    HEAD_BUFFER = 250
    # 轴序 = COMBO_LEVELS(真扫维,含 F 维——F 维在下面按 FILTER_PREDS 变谓词,不出现在这里)+ 后面的 preds
    COMBO_LEVELS = {"bo.min_relative_height": [0.1, 0.15, 0.2, 0.3], "bo.exceed_threshold": [0.001, 0.003, 0.01, 0.03],
                    "burst.gap_max": [4, 8, 12, 20], "tb.stop_confirm_bars": [0, 1, 2, 3], "tb.big_rise_k": [3.0, 5.0, 8.0, 12.0]}
    FILTER_PREDS = [("burst.count", ">=", [1, 2, 3, 4])]              # F 维:长表列 burst.count,档位 = burst.min_bos 档位
    WHERE_PREDS = [("burst.first_drought", ">=", [0, 20, 40]), ("burst.distinct_pk", ">=", [1, 3, 4]),
                   ("burst.max_bar_vol_ratio", ">=", [0, 10, 15]), ("burst.peak_age_max", ">=", [0, 125]),
                   ("tb.day_drop", "<", [None, 0.2])]
    FOLD_COL, FOLDS = "fold_Y", ["2024", "2025"]
    MIN_COUNT_PER_FOLD = 300   # 敏感性重跑(控制方要求):实测买点日/match 比率约 2.5~4×,300 大致对齐 match 口径的 100
    REF_POINT = {"bo.min_relative_height": 0.2, "bo.exceed_threshold": 0.003, "burst.gap_max": 8,
                 "tb.stop_confirm_bars": 2, "tb.big_rise_k": 5.0}     # 参照 = 此检测组合 × 全部谓词最松档
    NEIGHBOR_AXES = "all"
    B_BOOT, SEED, TOP_N = 300, 0, 20
    FLAG_RULES = [lambda c: "first_drought 闸恒真" if c["burst.gap_max"] >= c["burst.first_drought"] > 0 else None]
    OUT_DIR = "docs/research/2026-08-25_multivar-bb_v1/sensitivity_mc300/"   # 独立子目录,不覆盖主结果;内含 ledger.md 副本供 HEAD_BUFFER 核验

    out = REPO / OUT_DIR
    # sensitivity_mc300/ledger.md 被 .gitignore 排除(内容与根目录 ledger.md 完全相同,不
    # 重复提交,见 docs/research/2026-08-25_multivar-bb_v1/.gitignore)——干净 clone 直接跑
    # 本脚本会在这里 FileNotFoundError(复审 M-9)。先手动同步一份:
    #   cp docs/research/2026-08-25_multivar-bb_v1/ledger.md \
    #      docs/research/2026-08-25_multivar-bb_v1/sensitivity_mc300/ledger.md
    _check_head_buffer(out / "ledger.md", HEAD_BUFFER)
    df = _load(REPO / LONGTABLE_DIR)
    preds = FILTER_PREDS + WHERE_PREDS
    prep = prepare(df, COMBO_LEVELS, preds, FOLD_COL, FOLDS)
    axes = list(range(prep.n_combo_axes + prep.n_pred_axes)) if NEIGHBOR_AXES == "all" else NEIGHBOR_AXES
    ref_index = tuple(COMBO_LEVELS[c].index(REF_POINT[c]) for c in COMBO_LEVELS) + (0,) * prep.n_pred_axes
    R = analyze_tensor(prep, ref_index, MIN_COUNT_PER_FOLD, axes)
    shape = R["s_nb"].shape
    n_cells = int(np.prod(shape)); n_eval = int(R["evaluable"].sum()); n_neg = int((R["s_nb"] < 0).sum())
    c_hat = int(R["order"][0]); c_idx = np.unravel_index(c_hat, shape)
    tol = tolerance(R["s_nb"], c_idx)
    bs = bootstrap(prep, ref_index, MIN_COUNT_PER_FOLD, axes, B_BOOT, SEED, TOP_N)
    sh = split_half(prep, ref_index, MIN_COUNT_PER_FOLD, axes, SEED)
    naive = float(R["s_nb"].ravel()[c_hat])
    opt, opt_se = bs["optimism"], bs["optimism_se"]
    if not np.isfinite(opt):
        corrected = float("nan")
        opt_line = "optimism 不可估(bootstrap 副本里选中格全部不可评估,B 太小或功效线太高)"
    else:
        corrected = naive - opt
        if opt >= 0:
            opt_line = (f"optimism = {opt:.4f} ± {opt_se:.4f}(SE, n_opt={bs['n_opt']}/{B_BOOT}) >= 0:"
                        f"corrected = naive − optimism = {corrected:.4f},按 Efron 标准口径可视为上界")
        else:
            opt_line = (f"optimism = {opt:.4f} ± {opt_se:.4f}(SE, n_opt={bs['n_opt']}/{B_BOOT}) < 0:"
                        f"本次未观测到选择偏差(或被蒙特卡洛噪声掩盖),corrected = {corrected:.4f} "
                        f"**不构成保守上界**,只是同一公式算出的另一个数字,不要按'上界'解读")

    # cells.csv(每格一行)
    rows = []
    fp, cnt, delta = R["fp"], R["count"], R["delta"]
    for flat in range(n_cells):
        idx = np.unravel_index(flat, shape); c = cell_coords(prep, flat)
        row = dict(flat=flat, **c, evaluable=bool(R["evaluable"][idx]), s=R["s"][idx], s_nb=R["s_nb"][idx],
                   n_eval_nb=int(R["n_eval_nb"][idx]), boot_top=bs["top_freq"].get(flat, 0))
        for f, fold in enumerate(FOLDS):
            row[f"count_{fold}"] = int(cnt[idx + (f,)]); row[f"fp_{fold}"] = fp[idx + (f,)]; row[f"delta_{fold}"] = delta[idx + (f,)]
        row["flags"] = ";".join(x for x in (r(c) for r in FLAG_RULES) if x)
        rows.append(row)
    # 必须按 rank_cells 的 order 排(而非自行按 s_nb 数值 sort_values)——order 有硬前置键
    # (0 可评估邻居的孤立尖峰排到有邻居支撑的格之后),数值排序推不出这条键,详见
    # order_rows_by_rank 文档。表格首行 == ĉ 由此保证,folds_6M 的 TOP_N 也共享同一口径。
    cells = pd.DataFrame(order_rows_by_rank(rows, R["order"]))
    cells.to_csv(out / "cells.csv", index=False)

    # 半年诊断视图
    prep6 = prepare(df, COMBO_LEVELS, preds, "fold_6M", sorted(df["fold_6M"].unique()))
    fp6, cnt6 = fp_count(tensor(prep6))
    r6 = []
    for flat in cells["flat"].head(TOP_N):
        idx = np.unravel_index(int(flat), shape)
        r6.append(dict(flat=int(flat), **{f"count_{f}": int(cnt6[idx + (i,)]) for i, f in enumerate(prep6.folds)},
                       **{f"fp_{f}": fp6[idx + (i,)] for i, f in enumerate(prep6.folds)}))
    pd.DataFrame(r6).to_csv(out / "folds_6M.csv", index=False)

    # 图:一维切片 / 二维热力 / bootstrap 频率
    axis_names = list(COMBO_LEVELS) + [c for c, _, _ in preds]
    axis_levels = list(COMBO_LEVELS.values()) + [lv for _, _, lv in preds]
    for ax, name in enumerate(axis_names):
        sl = [slice(None) if i == ax else c_idx[i] for i in range(len(shape))]
        xs = [str(v) for v in axis_levels[ax]]
        plt.figure(figsize=(5, 3.2))
        plt.plot(xs, R["s_nb"][tuple(sl)], "o-", label="s_nb")
        plt.plot(xs, R["s"][tuple(sl)], "s--", label="s")
        for f, fold in enumerate(FOLDS):
            plt.plot(xs, delta[tuple(sl) + (f,)], ":", label=f"Δ{fold}")
        plt.axhline(0, color="k", lw=0.5); plt.title(f"过 c_hat 的切片:{name}"); plt.legend(fontsize=7); plt.tight_layout()  # 图内标题用 ASCII c_hat(ĉ 这个重音字符不在任何已装 CJK 字体里,会渲染成缺字方块;报告 markdown 文本里的 ĉ 不受影响)
        plt.savefig(out / f"slice_{name}.png", dpi=110); plt.close()
    for a in range(prep.n_combo_axes):
        for b in range(a + 1, prep.n_combo_axes):
            sl = [c_idx[i] for i in range(len(shape))]; sl[a] = slice(None); sl[b] = slice(None)
            Z = R["s_nb"][tuple(sl)]
            plt.figure(figsize=(4.2, 3.6)); plt.imshow(np.where(np.isfinite(Z), Z, np.nan).T, origin="lower", cmap="RdBu", vmin=-0.05, vmax=0.05)
            plt.colorbar(label="s_nb"); plt.xticks(range(len(axis_levels[a])), axis_levels[a], fontsize=7); plt.yticks(range(len(axis_levels[b])), axis_levels[b], fontsize=7)
            plt.xlabel(axis_names[a]); plt.ylabel(axis_names[b]); plt.scatter([c_idx[a]], [c_idx[b]], marker="*", c="k")
            plt.tight_layout(); plt.savefig(out / f"heat_{axis_names[a]}_{axis_names[b]}.png", dpi=110); plt.close()
    top = sorted(bs["top_freq"].items(), key=lambda kv: -kv[1])[:TOP_N]
    if top:
        plt.figure(figsize=(6, 3)); plt.bar([str(k) for k, _ in top], [v for _, v in top]); plt.xticks(rotation=90, fontsize=6)
        plt.title(f"bootstrap 入选前 {TOP_N} 频次"); plt.tight_layout(); plt.savefig(out / "boot_top.png", dpi=110); plt.close()

    # 报告
    ref_c = cell_coords(prep, int(np.ravel_multi_index(ref_index, shape)))
    ev_axes = []
    for ax, name in enumerate(axis_names):
        ok = R["evaluable"].any(axis=tuple(i for i in range(len(shape)) if i != ax))
        ev_axes.append(f"{name}: 可评估档 {[str(v) for v, o in zip(axis_levels[ax], ok) if o]}")
    keep_n, keep_ratio = int(prep.row_keep.sum()), float(prep.row_keep.mean())
    short_axes = [name for name, n in zip(axis_names, shape) if n <= 2]
    # 判据抽成 region_core.verdict(复审 I-3):原 has_region 只看 naive,与 SKILL.md 红线
    # "naive 只作参考;optimism 校正当上界,split-half 当下界"冲突——2026-08-25 bb_v1 真实
    # 运行撞上过(naive 为正、但 optimism 校正与 split-half 均翻负,报告仍打出"推荐格"的
    # 假象)。三档判词见 verdict() 文档;下面只按三档结果选标题/导语文案,不重复判据逻辑。
    #
    # ĉ 本身是"有邻居的格里 s_nb 最高者"(修复轮4订正,rank_cells 的 no_neighbor 硬前置键
    # 把 0 邻居的孤立正分格压到有邻居组之后)——naive = s_nb(ĉ) 不会漏报"是否存在稳健区":
    # 只要存在任何有邻居的格,ĉ 必落在该组且是最大者,故"有邻居的格里存在正分" ⟺
    # "s_nb(ĉ) > 0";s_nb(ĉ) <= 0 则意味着正分(若有)全在 0 邻居的孤立格上,方法论上
    # "邻域分不存在",本不该算稳健区。
    tier = verdict(naive, opt, sh)
    has_region = tier == VERDICT_CANDIDATE
    if tier == VERDICT_CANDIDATE:
        verdict_title = "## 推荐格(邻域最小分最高)"
        verdict_lead = f"- ĉ = {cell_coords(prep, c_hat)}"
    elif tier == VERDICT_CORRECTED_NEGATIVE:
        verdict_title = "## 本次未发现稳健区(naive 为正,但按 optimism 校正后翻负)"
        verdict_lead = (f"- naive s_nb(ĉ) = {naive:.4f} > 0,但按 Efron 口径 corrected = naive − optimism"
                        f" = {corrected:.4f} <= 0,不构成「发现稳健区」的结论;以下仍列出分数最高"
                        f"(最不坏)的格供诊断,**不构成推荐**:{cell_coords(prep, c_hat)}")
    else:
        verdict_title = "## 本次未发现稳健区(可评估面上无正邻域分)"
        verdict_lead = (f"- 全部有可评估邻居的格的邻域分 s_nb 均 <= 0(若有正分,只可能落在 0 邻居的孤立"
                        f"格上;邻域分为负 {n_neg}/{n_eval} 个可评估格);以下仍列出分数最高(最不坏)的格"
                        f"供诊断,**不构成推荐、不构成「存在稳健区」的结论**:{cell_coords(prep, c_hat)}")
    lines = [f"# region_find 报告", "", f"- 长表 {LONGTABLE_DIR};HEAD_BUFFER={HEAD_BUFFER};fold={FOLDS};功效线 {MIN_COUNT_PER_FOLD}/fold;邻域轴 {NEIGHBOR_AXES}",
             f"- 保留行 {keep_n}/{len(df)} = {keep_ratio:.4f}(丢弃行 = combo/pred 列不在档位表 / 谓词列 NaN / fold 不在 FOLDS 里,详见 prepare() 文档)",
             f"- 联合空间 {shape} = {n_cells} 格;可评估 {n_eval};不可评估 {n_cells - n_eval};邻域分为负 {n_neg}",
             f"- 参照格 {ref_c}:" + ";".join(f"{fold} count {int(cnt[ref_index + (f,)])} FP {fp[ref_index + (f,)]:.4f}" for f, fold in enumerate(FOLDS)),
             "", verdict_title, verdict_lead, f"- naive s_nb = {naive:.4f};split-half = {sh:.4f}(下界)",
             f"- {opt_line}",
             f"- bootstrap:选中格稳定性 P(ĉ_b ∈ N(ĉ)) = {bs['stability']:.2f}(基于 {bs['n_valid']}/{B_BOOT} 个有效副本);s_nb(ĉ) 95% CI = [{bs['ci'][0]:.4f}, {bs['ci'][1]:.4f}](B={B_BOOT})",
             f"- 容错宽度(向下档数, 向上档数):" + "; ".join(f"{axis_names[a]} {tol[a]}" for a in tol),
             "", "## 可评估面", *[f"- {x}" for x in ev_axes], "", f"## 前 {TOP_N} 格", "",
             cells.head(TOP_N).to_markdown(index=False, floatfmt=".4f"), "",
             "## 读数纪律", "- 三口径并报,不折中;唯一无偏数字是同 HEAD_BUFFER 的 2026 外推窗(本工具不做)。",
             "- 不可评估 ≠ 坏:计数不足的格只报计数;不降功效线硬凑。", "- 半年诊断视图见 folds_6M.csv;标记列 flags 见 cells.csv。",
             ("- 只要网格里存在**任意一条**长度 ≤2 的轴,排序第 4 平局键(离边界距离)就在**整个网格**"
              f"恒为 0(跨轴取 min,一条短轴即可把全网格压平),不能当排序依据;本次这样的轴:"
              f"{short_axes if short_axes else '无'}。"),
             "", "## 下一步",
             ("- 同 HEAD_BUFFER 的 2026 窗独立验证推荐格与其邻域(tune-gates 现流程)。" if has_region else
              "- 本次无推荐格可外推;若后续换网格/窗口找到正邻域分区域,再按同 HEAD_BUFFER 的 2026 窗独立验证。")]
    (out / "region_report.md").write_text("\n".join(lines))
    print("\n".join(lines[:12]))


if __name__ == "__main__":
    main()
