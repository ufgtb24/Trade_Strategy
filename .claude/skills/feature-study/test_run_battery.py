# -*- coding: utf-8 -*-
"""run_battery 单元测试(feature-study skill 自带;需显式路径跑,不进默认 pytest 收集):
uv run pytest .claude/skills/feature-study/test_run_battery.py -q
覆盖 reviewer 指出的无回归网核心逻辑:BH 已知答案 / suppression 反转 / 无控制降级。
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))

from run_battery import _bh_fdr, _decluster, run_battery  # noqa: E402


def _df(seed: int = 7, n: int = 600) -> pd.DataFrame:
    """构造 suppression 场景:x 与 label 原始正相关,控制 ctrl 后反号。"""
    rng = np.random.default_rng(seed)
    ctrl = rng.normal(0, 1, n)
    x = ctrl + 0.15 * rng.normal(0, 1, n)          # 与 ctrl 高共线
    label = ctrl - 0.5 * x + 0.15 * rng.normal(0, 1, n)   # raw cov>0, 控制 beta<0
    return pd.DataFrame({"symbol": [f"S{i}" for i in range(n)],
                         "label": label, "x_supp": x, "ctrl": ctrl})


def test_bh_textbook_example():
    """BH 教学例(m=10, q=0.05):前 3 过关、第 4 名 p=0.028 出局。"""
    qs = _bh_fdr([0.001, 0.008, 0.012, 0.028, 0.040, 0.110,
                  0.190, 0.310, 0.420, 0.670])
    expect = [0.01, 0.04, 0.04, 0.07, 0.08, 0.183, 0.271, 0.388, 0.467, 0.67]
    assert all(abs(a - b) < 1e-3 for a, b in zip(qs, expect))
    assert all(q < 0.05 for q in qs[:3]) and qs[3] >= 0.05


def test_bh_batch_size_dependency():
    """同一 p=0.028 排第 4 名:m=10 出局(q=0.07)、m=4 过关(q=0.028×4/4)——门槛随批量。"""
    q10 = _bh_fdr([0.001, 0.008, 0.012, 0.028] + [0.5] * 6)[3]
    q4 = _bh_fdr([0.001, 0.008, 0.012, 0.028])[3]
    assert q10 >= 0.05 and q4 < 0.05


def test_suppression_reversed_verdict(capsys):
    """suppression:原始正相关、控制后反号 → 判「反转」,不得当有信号报。"""
    d = _df()
    csv = Path("/tmp/fs_supp_test.csv")
    d.to_csv(csv, index=False)
    v = run_battery(str(csv), features=["x_supp"], binaries=[],
                    controls=["ctrl"])
    assert "反转" in v["x_supp"]["verdict"]
    assert v["x_supp"]["gate2"] is not None and not v["x_supp"]["gate2"]


def test_no_controls_downgrade(capsys):
    """无 controls:判定自动降级并在文案声明。"""
    d = _df()
    csv = Path("/tmp/fs_noctrl_test.csv")
    d.to_csv(csv, index=False)
    v = run_battery(str(csv), features=["x_supp"], binaries=[], controls=[])
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
    csv = Path("/tmp/fs_noise_test.csv")
    d.to_csv(csv, index=False)
    v = run_battery(str(csv), features=["x_noise", "y_noise"],
                    binaries=[], controls=[])
    assert all(r["verdict"] == "无信号" for r in v.values())


def test_decluster_pick_modes():
    """pick 分家:first=数据原序首条(与 label 无关);best=每簇 label 最高(旧行为)。"""
    d = pd.DataFrame({"symbol": ["A", "A", "B"],
                      "label": [1.0, 5.0, 2.0]})
    first = _decluster(d, "label", pick="first")
    best = _decluster(d, "label", pick="best")
    # A 股两行:原序首条 label=1.0;label 最高 label=5.0。B 股一条两边都在。
    assert set(first["label"]) == {1.0, 2.0}
    assert set(best["label"]) == {5.0, 2.0}


def test_tail_enrichment_keeps_best_semantics():
    """tail_enrichment 保留 per-symbol 最佳(镜像 UI 排行榜的语义,不随关 3 改)。"""
    from run_battery import tail_enrichment
    d = pd.DataFrame({"symbol": ["A", "A", "B"],
                      "label": [1.0, 5.0, 2.0],
                      "flag": [1, 0, 1]})
    # per-symbol 最佳行:A(label=5, flag=0)、B(label=2, flag=1) → 基率 1/2
    # (A 原序首条 flag=1:若误用 pick="first" 基率变 2/2=100%,first/best 可区分)
    lines = tail_enrichment(d, "flag", "label", ks=(2,))
    assert "50.0%" in lines[0]


def _csv(d: pd.DataFrame, name: str) -> str:
    p = Path(f"/tmp/fs_{name}.csv")
    d.to_csv(p, index=False)
    return str(p)


def test_gate3a_symbol_cluster_kills(capsys):
    """股簇杀:相关由 3 只妖股各 15 条重复观测刷出 → 股内去簇(留首条)后死。

    妖股 tb 时间分散(i*17 错开,时去簇不伤妖点)、散股 40 只挤 6 个桶
    (时去簇压散股抬妖点浓度)→ 3a 死 / 3b 活,死因归「个股驱动」。
    """
    rng = np.random.default_rng(5)
    rows = []
    for i in range(3):  # 3 只妖股 × 15 条,股内 x/label 双高
        x = rng.normal(2, 0.4, 15); lab = rng.normal(2, 0.5, 15)
        rows += [(f"M{i}", i * 17 + j * 3, xx, ll) for j, (xx, ll) in enumerate(zip(x, lab))]
    for i in range(40):  # 40 只正常股各 1 条,无关联,同期挤桶
        rows.append((f"S{i}", 100 + (i % 6) * 5, rng.normal(0, 1), rng.normal(0, 1)))
    d = pd.DataFrame(rows, columns=["symbol", "tb_start", "x_m", "label"])
    v = run_battery(_csv(d, "symclus"), features=["x_m"], binaries=[],
                    controls=[], time_bucket_days=5)["x_m"]
    assert v["gate1"] and v["gate3_sym"] is False
    assert "个股驱动" in v["verdict"] and v["gate3"] is False


def test_gate3b_time_cluster_kills(capsys):
    """时簇杀:每股一条(3a 无压缩)、但 20 股挤同一时间桶 → 时间去簇后死。"""
    rng = np.random.default_rng(13)
    n0 = 40  # 分散桶,每股一条,无关联
    x0 = rng.normal(0, 1, n0); lab0 = rng.normal(0, 1, n0)
    tb0 = np.arange(n0) * 5           # 桶 0..39,每桶一条
    n1 = 20   # 事件簇:同一桶,x/label 双高
    x1 = rng.normal(3, 0.3, n1); lab1 = rng.normal(3, 0.5, n1)
    tb1 = np.full(n1, 400)            # 全在桶 80
    d = pd.DataFrame({"symbol": [f"S{i}" for i in range(n0 + n1)],
                      "tb_start": np.concatenate([tb0, tb1]),
                      "x_ev": np.concatenate([x0, x1]),
                      "label": np.concatenate([lab0, lab1])})
    v = run_battery(_csv(d, "timeclus"), features=["x_ev"], binaries=[],
                    controls=[], time_bucket_days=5)["x_ev"]
    assert v["gate1"] and v["gate3_sym"] is True   # 每股一条,股内去簇活着
    assert v["gate3_time"] is False                # 时间去簇杀死
    assert "事件驱动" in v["verdict"] and v["gate3"] is False


def test_gate3_both_pass(capsys):
    """两检都过:每股一条、每桶一条的普通强相关 → gate3 True。"""
    rng = np.random.default_rng(3)
    n = 60
    x = rng.normal(0, 1, n)
    d = pd.DataFrame({"symbol": [f"S{i}" for i in range(n)],
                      "tb_start": np.arange(n) * 5,
                      "x_ok": x, "label": x + 0.5 * rng.normal(0, 1, n)})
    v = run_battery(_csv(d, "bothpass"), features=["x_ok"], binaries=[],
                    controls=[], time_bucket_days=5)["x_ok"]
    assert v["gate3_sym"] is True and v["gate3_time"] is True
    assert v["gate3"] is True and "有信号" in v["verdict"]


def test_gate3b_opposite_sign_death(capsys):
    """3b 反号死亡:时间去簇后 stat 显著但与原始反号 → 死因文案落「事件驱动」。

    20 桶各 2 股:首条 x 低/label 更低(段内反号)、次条 x 高/label 高(撑正相关);
    原始 rho=+0.75,3b 只留各桶首条 → 20 条完美反号 rho=-1 → gate3_time 走
    「p<0.05 但 sign 反」路径(np 布尔),文案必须命中「事件驱动」细分分支。
    """
    rows = []
    for k in range(20):
        rows.append((f"A{k}", k * 5, k, -(40 + k)))      # 桶首条:反号
        rows.append((f"B{k}", k * 5, 50 + k, 50 + k))     # 桶次条:同号
    d = pd.DataFrame(rows, columns=["symbol", "tb_start", "x_rev", "label"])
    v = run_battery(_csv(d, "revsign"), features=["x_rev"], binaries=[],
                    controls=[], time_bucket_days=5)["x_rev"]
    assert v["gate1"] and v["gate3_sym"] is True
    assert v["gate3_time"] is False and v["gate3"] is False
    assert "事件驱动" in v["verdict"]


def test_time_dim_missing_degrades(capsys):
    """缺 tb_start 列或未传 time_bucket_days → 3b 跳过,verdict 标注降级。"""
    rng = np.random.default_rng(3)
    n = 60
    x = rng.normal(0, 1, n)
    d = pd.DataFrame({"symbol": [f"S{i}" for i in range(n)],
                      "x_ok": x, "label": x + 0.5 * rng.normal(0, 1, n)})
    out = capsys.readouterr().out
    v1 = run_battery(_csv(d, "nocol"), features=["x_ok"], binaries=[],
                     controls=[], time_bucket_days=5)["x_ok"]      # 有参数、缺列
    v2 = run_battery(_csv(d, "nocol"), features=["x_ok"], binaries=[],
                     controls=[])["x_ok"]                          # 无参数(默认)
    for v in (v1, v2):
        assert v["gate3_time"] is None and v["declust_time_p"] is None
        assert v["gate3"] == v["gate3_sym"] is True
        assert "时间维未检" in v["verdict"]
    assert "tb_start" in capsys.readouterr().out  # 警告打印提到缺列原因
