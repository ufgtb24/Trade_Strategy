# -*- coding: utf-8 -*-
"""run_battery 单元测试(feature-study skill 自带;需显式路径跑,不进默认 pytest 收集):
uv run pytest .claude/skills/feature-study/test_run_battery.py -q -p no:cacheprovider
覆盖:BH 与同批假设并族 / suppression 反转 / 无控制降级 / 按股去簇 / 时间窗固定效应 / 分年稳定性只在功效足够时判 /
离散标签下的方向 / 首次穿越口径的分箱。
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))

import run_battery as RB  # noqa: E402
from run_battery import _decluster, _shape_note, rate_table, run_battery, tail_enrichment  # noqa: E402

D0 = pd.Timestamp("2025-01-02")


def _dates(offsets):
    """日历天偏移 → ISO 日期串。"""
    return [str((D0 + pd.Timedelta(days=int(o))).date()) for o in offsets]


def _df(seed: int = 7, n: int = 600) -> pd.DataFrame:
    """构造 suppression 场景:x 与 label 原始正相关,控制 ctrl 后反号。"""
    rng = np.random.default_rng(seed)
    ctrl = rng.normal(0, 1, n)
    x = ctrl + 0.15 * rng.normal(0, 1, n)          # 与 ctrl 高共线
    label = ctrl - 0.5 * x + 0.15 * rng.normal(0, 1, n)   # raw cov>0, 控制 beta<0
    return pd.DataFrame({"symbol": [f"S{i}" for i in range(n)],
                         "label": label, "x_supp": x, "ctrl": ctrl})


def test_bh_textbook_example():
    """电池用的 BH(tune-gates inference.bh)教学例(m=10, q=0.05):前 3 过关、第 4 名 p=0.028 出局。"""
    qs = RB.inference.bh([0.001, 0.008, 0.012, 0.028, 0.040, 0.110,
                          0.190, 0.310, 0.420, 0.670])
    expect = [0.01, 0.04, 0.04, 0.07, 0.08, 0.183, 0.271, 0.388, 0.467, 0.67]
    assert all(abs(a - b) < 1e-3 for a, b in zip(qs, expect))
    assert all(q < 0.05 for q in qs[:3]) and qs[3] >= 0.05


def test_extra_pvals_join_bh_family(capsys):
    """同批其余假设(如闸级 p)并进 BH 族:q 值 = 对「本批特征 p + 附加 p」整体做 BH,族大小随之变。"""
    d = _df()
    alone = run_battery(d, features=["x_supp"], controls=["ctrl"])["x_supp"]
    extra = {"gate:a": 0.001, "gate:b": 0.5, "gate:c": 0.9}
    joined = run_battery(d, features=["x_supp"], controls=["ctrl"], extra_pvals=extra)["x_supp"]
    assert alone["family_size"] == 1 and joined["family_size"] == 4
    assert joined["q_fdr"] == RB.inference.bh([alone["p_raw"], *extra.values()])[0]


def test_suppression_reversed_verdict(capsys, tmp_path):
    """suppression:原始正相关、控制后反号显著 → 判「反转」,不得当有信号报(走 CSV 读入路径)。"""
    csv = tmp_path / "supp.csv"
    _df().to_csv(csv, index=False)
    v = run_battery(str(csv), features=["x_supp"], binaries=[], controls=["ctrl"])
    assert "反转" in v["x_supp"]["verdict"]
    assert v["x_supp"]["gate2"] is not None and not v["x_supp"]["gate2"]


def test_no_controls_downgrade(capsys):
    """无 controls、也没有时间窗:关2 跳过,判定自动降级并在文案声明。"""
    v = run_battery(_df(), features=["x_supp"], binaries=[], controls=[])
    assert "降级" in v["x_supp"]["verdict"]
    assert v["x_supp"]["gate2"] is None


def test_pure_noise_no_signal(capsys):
    """纯噪声 + FDR:q 不达标 → 无信号。"""
    rng = np.random.default_rng(3)
    n = 500
    d = pd.DataFrame({"symbol": [f"S{i}" for i in range(n)],
                      "label": rng.normal(0, 1, n),
                      "x_noise": rng.normal(0, 1, n),
                      "y_noise": rng.normal(0, 1, n)})
    v = run_battery(d, features=["x_noise", "y_noise"], binaries=[], controls=[])
    assert all(r["verdict"] == "无信号" for r in v.values())


def test_decluster_keeps_best_row_per_symbol():
    """_decluster 只剩排行榜语义:每 symbol 留 label 最高一条(子抽样去簇已删除)。"""
    d = pd.DataFrame({"symbol": ["A", "A", "B"],
                      "label": [1.0, 5.0, 2.0]})
    assert set(_decluster(d, "label")["label"]) == {5.0, 2.0}


def test_tail_enrichment_keeps_best_semantics():
    """tail_enrichment 保留 per-symbol 最佳(镜像 UI 排行榜的语义)。"""
    d = pd.DataFrame({"symbol": ["A", "A", "B"],
                      "label": [1.0, 5.0, 2.0],
                      "flag": [1, 0, 1]})
    # per-symbol 最佳行:A(label=5, flag=0)、B(label=2, flag=1) → 基率 1/2
    lines = tail_enrichment(d, "flag", "label", ks=(2,))
    assert "50.0%" in lines[0]


def test_stock_cluster_is_not_independent_evidence(capsys):
    """同一只股票的反复观测不当独立证据:30 只股、每股 20 行,x 与 label 各自只有股票层面的取值、两者本无关系。

    把每行当独立观测(每行一只股)时,30 只股之间碰巧的相关被 600 行放大成「有信号」;按股去簇后 → 无信号。
    (旧电池靠「每股留首条」子抽样做这件事,丢掉 95% 的样本。)
    """
    rng = np.random.default_rng(0)
    G, per = 30, 20
    us, vs = rng.normal(0, 1, G), rng.normal(0, 1, G)
    d = pd.DataFrame({"symbol": np.repeat([f"S{i}" for i in range(G)], per),
                      "x": np.repeat(us, per) + 0.3 * rng.normal(0, 1, G * per),
                      "label": np.repeat(vs, per) + 0.3 * rng.normal(0, 1, G * per)})
    clustered = run_battery(d, features=["x"], controls=[])["x"]
    as_iid = run_battery(d.assign(symbol=[f"R{i}" for i in range(len(d))]), features=["x"], controls=[])["x"]
    assert as_iid["gate1"] and clustered["verdict"] == "无信号"
    assert abs(clustered["z_raw"]) < abs(as_iid["z_raw"]) / 3


def test_time_cluster_absorbed_by_window_fixed_effects(capsys):
    """同期跨股共同行情:40 股分散在各时间窗、无关联;20 股挤同一天、x 与 label 双高。

    原始关联显著,但加时间窗固定效应后只剩窗内比较(那 20 股窗内 x 与 label 无关)→ 关2 不过、判「代理」。
    """
    rng = np.random.default_rng(13)
    n0, n1 = 40, 20
    d = pd.DataFrame({"symbol": [f"S{i}" for i in range(n0 + n1)],
                      "entry_date": _dates(np.concatenate([np.arange(n0) * 10, np.full(n1, 5000)])),
                      "x_ev": np.concatenate([rng.normal(0, 1, n0), rng.normal(3, 0.3, n1)]),
                      "label": np.concatenate([rng.normal(0, 1, n0), rng.normal(3, 0.5, n1)])})
    v = run_battery(d, features=["x_ev"], binaries=[], controls=[], label_horizon=5)["x_ev"]
    assert v["gate1"] and v["gate2"] is False
    assert v["verdict"].startswith("代理")


def test_clean_signal_passes(capsys):
    """普通强相关、日期分散在多个时间窗、带一列无关控制:关1、关2 都过 → 有信号,方向 +。"""
    rng = np.random.default_rng(3)
    n = 60
    x = rng.normal(0, 1, n)
    d = pd.DataFrame({"symbol": [f"S{i}" for i in range(n)],
                      "entry_date": _dates(np.arange(n) * 10),
                      "x_ok": x, "ctrl": rng.normal(0, 1, n), "label": x + 0.5 * rng.normal(0, 1, n)})
    v = run_battery(d, features=["x_ok"], binaries=[], controls=["ctrl"], label_horizon=40)["x_ok"]
    assert v["gate1"] and v["gate2"] is True
    assert v["verdict"].startswith("有信号,方向+") and v["direction"] == "+"


def _year_reversal(n: int, seed: int) -> pd.DataFrame:
    """2024 年 x 与 label 正相关、2025 年反向;合并后仍为正。"""
    rng = np.random.default_rng(seed)
    yr = rng.integers(0, 2, n)
    start = pd.to_datetime(np.where(yr == 0, pd.Timestamp("2024-01-01"), pd.Timestamp("2025-01-01")))
    x = rng.normal(0, 1, n)
    return pd.DataFrame({"symbol": [f"S{i % (n // 4)}" for i in range(n)],
                         "entry_date": start + pd.to_timedelta(rng.integers(0, 360, n), "D"),
                         "x": x, "ctrl": rng.normal(0, 1, n),
                         "label": np.where(yr == 0, 1.0, -0.35) * x + rng.normal(0, 1.5, n)})


def test_year_reversal_unstable_only_when_powered(capsys):
    """分年估计显著反向:每年都有足够把握看到合并效应时判「不稳」;样本小、分年功效不够时不判不稳。"""
    big = run_battery(_year_reversal(4000, 0), features=["x"], controls=["ctrl"], label_horizon=40)["x"]
    assert big["verdict"].startswith("不稳") and big["stable"] is False
    small = run_battery(_year_reversal(300, 1), features=["x"], controls=["ctrl"], label_horizon=40)["x"]
    assert small["gate1"] and small["stable"] is None
    assert not small["verdict"].startswith("不稳") and "分年功效不足" in small["verdict"]



def test_time_dim_missing_degrades(capsys):
    """缺 entry_date 列或未传 label_horizon → 时间窗固定效应没加,verdict 标注降级。"""
    rng = np.random.default_rng(3)
    n = 60
    x = rng.normal(0, 1, n)
    d = pd.DataFrame({"symbol": [f"S{i}" for i in range(n)],
                      "x_ok": x, "label": x + 0.5 * rng.normal(0, 1, n)})
    v1 = run_battery(d, features=["x_ok"], binaries=[], controls=[], label_horizon=40)["x_ok"]   # 有参数、缺列
    v2 = run_battery(d, features=["x_ok"], binaries=[], controls=[])["x_ok"]                     # 无参数
    for v in (v1, v2):
        assert v["gate2"] is None and v["z_ctrl"] is None
        assert "时间维未控" in v["verdict"]
    assert "entry_date" in capsys.readouterr().out  # 警告打印提到缺列原因


def test_time_undetermined_only_when_structurally_uncheckable(capsys):
    """「时间维未定」只在时间维结构上检查不了时标出:有数据的时间窗 < 2,或只覆盖 1 个年份;窗数少本身不是理由。"""
    rng = np.random.default_rng(7)
    n = 60
    x = rng.normal(0, 1, n)
    base = pd.DataFrame({"symbol": [f"S{i}" for i in range(n)], "x_ok": x, "label": x + 0.5 * rng.normal(0, 1, n)})
    run = lambda offsets: run_battery(base.assign(entry_date=_dates(offsets)), features=["x_ok"],  # noqa: E731
                                      controls=[], label_horizon=40)["x_ok"]
    one_window = run(np.arange(n) % 5)                 # 5 天内:1 个时间窗、1 个年份
    assert one_window["time_flags"] == ["时间维未定"] and (one_window["n_windows"], one_window["n_years"]) == (1, 1)
    assert "有数据的时间窗 1 个、年份 1 个" in one_window["verdict"]
    assert "时间维未定" in capsys.readouterr().out
    one_year = run((np.arange(n) % 5) * 60)            # 同一年里 5 个时间窗
    assert one_year["time_flags"] == ["时间维未定"] and one_year["n_years"] == 1 and one_year["n_windows"] == 5
    spread = run(np.arange(n) * 12)                    # 跨两年、十几个时间窗
    assert spread["time_flags"] == [] and spread["n_years"] == 2 and spread["n_windows"] > 2
    assert "时间维未定" not in spread["verdict"]


def test_binary_direction_from_coefficient_on_discrete_label(capsys):
    """离散标签(0/1)下两组中位数差恒为 0:旧电池拿它定方向,和控制后 t 的符号对不上就误判「反转」。
    方向改取回归系数符号 → 有信号,方向 +。"""
    rng = np.random.default_rng(11)
    n = 800
    flag = rng.integers(0, 2, n)
    d = pd.DataFrame({"symbol": [f"S{i % 200}" for i in range(n)], "flag": flag, "ctrl": rng.normal(0, 1, n),
                      "label": (rng.random(n) < np.where(flag == 1, 0.40, 0.25)).astype(float)})
    assert d.loc[d.flag == 1, "label"].median() - d.loc[d.flag == 0, "label"].median() == 0
    v = run_battery(d, features=[], binaries=["flag"], controls=["ctrl"])["flag"]
    assert "反转" not in v["verdict"]
    assert v["verdict"].startswith("有信号,方向+") and v["direction"] == "+"


def test_binary_direction_first_passage_counts(capsys):
    """首次穿越四态计数下的二元特征:方向取回归系数符号,flag=1 的首次穿越率更高 → 方向 +;不跑前瞻收益的排行榜富集。"""
    rng = np.random.default_rng(12)
    n = 1500
    flag = rng.integers(0, 2, n)
    L = 1 + rng.poisson(3, n)
    dirn = rng.binomial(L, 0.9)
    up = rng.binomial(dirn, np.where(flag == 1, 0.58, 0.48))
    both = rng.binomial(dirn - up, 0.1)
    d = pd.DataFrame({"symbol": [f"S{i % 300}" for i in range(n)], "flag": flag, "ctrl": rng.normal(0, 1, n),
                      "up": up, "down": dirn - up - both, "both": both, "none": L - dirn})
    v = run_battery(d, features=[], label_type="first_passage", binaries=["flag"], controls=["ctrl"])["flag"]
    assert v["verdict"].startswith("有信号,方向+")
    out = capsys.readouterr().out
    assert "Fisher" not in out and "基率" not in out


def test_first_passage_bins_use_pooled_rate():
    """首次穿越分箱按合并率 ΣU/ΣD,不是逐行份额的平均:一行 1/1、一行 0/9 → 合并率 0.1,行均值 0.5。"""
    d = pd.DataFrame({"symbol": ["A", "B", "C", "D"], "x": [1.0, 2.0, 3.0, 4.0],
                      "up": [1, 0, 3, 3], "down": [0, 9, 3, 3], "both": [0, 0, 0, 0], "none": [5, 0, 0, 0]})
    qt = rate_table(d, "x", k=2)
    assert qt["rate"].tolist() == [0.1, 0.5]
    assert qt["n_dir"].tolist() == [10, 12]
    assert (qt["ci_lo"] <= qt["rate"]).all() and (qt["rate"] <= qt["ci_hi"]).all()


def test_shape_note_judges_median_not_mean():
    """形状注记主判 med_lab;与 mean_lab 打架时必须说出来。

    数值取自 2026-09-08 那轮实测(v_median20):mean 单调升,med 却有两处下行、
    尾箱回落、甜点在第4箱。当时注记按均值判,研究报告把这个标签抄到自己引用的
    中位数序列上、写成「med_lab 单调升」,被复审用它自己贴的数字推翻。
    形状是交给执行端定硬闸时最要紧的信息——尾箱回落与单调升导出完全不同的闸形。
    """
    qt = pd.DataFrame({
        "mean_lab": [0.217, 0.284, 0.484, 0.581, 0.796],   # 单调升
        "med_lab":  [0.164, 0.159, 0.275, 0.352, 0.336],   # 非单调,峰在第4箱后回落
    })
    note = _shape_note(qt)
    assert note.startswith("非单调"), note
    assert "峰在第4箱后回落" in note, note
    assert "mean_lab 读作单调升" in note, note


def test_shape_note_silent_when_mean_and_median_agree():
    """两者形状一致时不追加提示(默认输出保持简洁)。"""
    qt = pd.DataFrame({"mean_lab": [1.0, 2.0, 3.0, 4.0, 5.0],
                       "med_lab": [1.0, 2.0, 3.0, 4.0, 5.0]})
    assert _shape_note(qt) == "单调升"
