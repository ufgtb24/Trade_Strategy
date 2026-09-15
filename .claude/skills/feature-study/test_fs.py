# -*- coding: utf-8 -*-
"""fs 调用面单元测试(tmp 账本 + tmp 登记簿 + 假取数口):
uv run pytest .claude/skills/feature-study/test_fs.py -q -p no:cacheprovider
golden(现存 bb_v1 main 长表上的对账第二步):TUNE_GOLDEN=1 uv run pytest .claude/skills/feature-study/test_fs.py -q -p no:cacheprovider
"""
import json
import os
import sys
import types
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

HERE = Path(__file__).parent
REPO = HERE.parents[2]
sys.path.insert(0, str(HERE))

import extract  # noqa: E402
import fs  # noqa: E402

ledger = fs.ledger
STUDY_IO = fs.RB.load_tune_gates("study_io")

CL = {"app": "fake", "app_module": "fake_app", "base_yaml": "params.yaml", "end_node": "tb",
      "kinds": {"bo.th": "D", "burst.min_n": "F", "burst.pk_min": "W", "tb.drop_pct": "W"},
      "scan_grid": {"bo.th": [0.1, 0.2], "burst.min_n": [1, 2]},
      "where_levels": {"burst.pk_min": [1, 3, 5], "tb.drop_pct": [None, 0.2]},
      "filter_fields": {"burst.min_n": ["burst", "count", ">="]},
      "where_fields": {"burst.pk_min": ["burst", "pk", ">="], "tb.drop_pct": ["tb", "drop", "<"]},
      "detector_nodes": {"bo.th": ["bo"]}}
FORMAL = {"bo.th": 0.2, "burst.min_n": 1, "burst.pk_min": 3, "tb.drop_pct": 0.2}
META = {"app": "fake", "start_date": "2024-01-01", "end_date": "2025-12-31", "label_horizon": 40,
        "first_passage_k": 5.0, "head_buffer": 0}
FPS = {"git_head": "abc1234", "base_fingerprint": "b" * 64, "source_fingerprint": "s" * 64, "ruler_fingerprint": "r" * 64}
WINDOW = {"start": "2024-01-01", "end": "2025-12-31"}
REGISTRY_TEXT = """# 登记簿

## 规则

(略)

## 待验证

### FC-001 · 峰数闸
- **口径**：`burst.pk >= 3`

### FC-002 · 某个特征 f1
- **口径**：f1

### FC-003 · 已经关了的
- **口径**：略

---

## 已关闭

- FC-003 · 已经关了的 · 口径 · 无信号 · 样本 · → x
"""


def _adapter(known=(), param_features=None):
    return types.SimpleNamespace(KNOWN_SIGNALS=list(known), PARAM_FEATURES=dict(param_features or {}))


def _rec(kind, **kw):
    base = dict(actor="test", round=None, window=WINDOW, label_horizon=40, head_buffer=0,
                git_head=None, base_fingerprint=None, source_fingerprint=None, ruler_fingerprint=None)
    base.update(kw)
    return ledger.make_record(kind, "fake", **base)


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("TUNE_LEDGER_DIR", str(tmp_path / "ledger"))
    reg = tmp_path / "feature_candidates.md"
    reg.write_text(REGISTRY_TEXT, encoding="utf-8")
    monkeypatch.setattr(fs, "_adapter", lambda app: _adapter())
    monkeypatch.setattr(fs, "_classification", lambda app, window: CL)
    monkeypatch.setattr(fs, "_run_meta", lambda app, window: META)
    monkeypatch.setattr(fs, "_formal", lambda cl: FORMAL)
    monkeypatch.setattr(extract, "formal_params", lambda cl: FORMAL)
    monkeypatch.setattr(fs, "_fingerprints", lambda app, window: dict(FPS))
    monkeypatch.setattr(fs, "_calendar", lambda: pd.bdate_range("2018-01-01", "2028-12-29"))
    return {"registry": reg, "tmp": tmp_path}


# ── status ──

def test_status_known_signal_review_rules(env, monkeypatch):
    """已知信号:最近的判定记录标签口径不是首次穿越 → 待复核;找不到带口径的判定记录 → 待复核;首次穿越口径 → 不列。"""
    monkeypatch.setattr(fs, "_adapter", lambda app: _adapter(known=["sig_fr", "sig_none", "sig_fp", "sig_nolabel"]))
    ledger.append(_rec("verify", fc=["FC-002"], axes=["feature:sig_fr"], data={"label": {"metric": "forward_return"}}))
    ledger.append(_rec("verify", fc=["FC-002"], axes=["feature:sig_fp"], data={"label": {"metric": "forward_return"}}))
    ledger.append(_rec("verify", fc=["FC-002"], axes=["feature:sig_fp"], data={"label": {"metric": "first_passage"}}))
    ledger.append(_rec("verify", fc=["FC-002"], axes=["feature:sig_nolabel"], data={"verdict": "有信号"}))
    before = (ledger.ledger_path("fake").read_bytes(), env["registry"].read_bytes())

    st = fs.status("fake", registry=env["registry"])
    review = {r["signal"]: r["reason"] for r in st["known_signal_review"]}
    assert set(review) == {"sig_fr", "sig_none", "sig_nolabel"}
    assert "不是首次穿越" in review["sig_fr"]
    assert review["sig_none"] == review["sig_nolabel"] == "找不到带标签口径的判定记录"
    assert (ledger.ledger_path("fake").read_bytes(), env["registry"].read_bytes()) == before   # 只读
    assert "已知信号「sig_fr」待复核" in st["text"]


def test_status_axis_states_open_fc_and_recheck(env):
    """轴状态按指纹核对;登记簿未关闭条目;定案背景快照与现在的正式参数不同 → 需复核。"""
    ledger.append(_rec("verify", fc=["FC-001"], axes=["burst.pk_min"], data={"verdict": "有信号+"},
                       **{**FPS, "source_fingerprint": "x" * 64}))
    ledger.append(_rec("verify", fc=["FC-001"], axes=["tb.drop_pct"], data={"verdict": "无信号"},
                       **{**FPS, "base_fingerprint": "y" * 64}))
    ledger.append(_rec("verify", fc=["FC-001"], axes=["burst.min_n"], data={}, **FPS))
    ledger.append(_rec("preregister", fc=["FC-001"], axes=["burst.min_n"],
                       data={"manifest_hash": "h", "manifest": {}, "expected_power": {"backward": 0.5, "forward": 0.5},
                             "survivorship": {}}))
    ledger.append(_rec("decide", axes=["bo.th"], data={"params": {"bo.th": [0.1, 0.2]}, "selects_on": ["bo.th"],
                                                     "provisional": True, "depends_on": {"burst.pk_min": 5}}))
    st = fs.status("fake", registry=env["registry"])
    assert st["axes"]["burst.pk_min"]["state"] == "已失效"
    assert st["axes"]["tb.drop_pct"]["state"] == "有效" and "补算" in st["axes"]["tb.drop_pct"]["reason"]
    assert st["axes"]["burst.min_n"]["state"] == "进行中"
    assert st["axes"]["bo.th"]["state"] == "未开始"
    assert st["open_fc"] == ["FC-001", "FC-002"]
    assert st["needs_recheck"] == [{"param": "bo.th", "decided": st["needs_recheck"][0]["decided"],
                                    "changed": {"burst.pk_min": {"decided": 5, "now": 3}}}]
    assert st["edge"] is None and "还没做优势检查" in st["text"]


# ── reconcile ──

def test_reconcile_step3_unavailable_messages(env, monkeypatch):
    """第三步:参数在 PARAM_FEATURES 里没有对应特征,或声明的特征字段当前 detector 事件上不存在 → 暂不可做(参数名动态填入)。"""
    monkeypatch.setattr(fs, "_event_fields", lambda cl, param: {"drought", "vol_ratio"})
    for adapter in (_adapter(), _adapter(param_features={"bo.th": "exceed_x"})):
        out = fs.step3_availability(CL, adapter, "bo.th")
        assert out["available"] is False
        assert out["message"] == "bo.th 缺少对应的特征字段，第三步暂不可做"
    monkeypatch.setattr(fs, "_event_fields", lambda cl, param: {"drought", "exceed_x"})
    assert fs.step3_availability(CL, _adapter(param_features={"bo.th": "exceed_x"}), "bo.th")["available"] is True


def _ev_rows(events):
    """events: [(symbol, start, 年, 四态, [(count, pk, drop), ...前缀行])] → 长表取数形状的行。"""
    rows = []
    for sym, start, year, st, prefixes in events:
        for count, pk, drop in prefixes:
            rows.append({"symbol": sym, "date": pd.Timestamp(f"{year}-03-01"), "year": str(year),
                         "tb.start": start, "tb.end": start + 2, "burst.count": count, "burst.pk": pk, "tb.drop": drop,
                         "M": 0.02, "c0_atr_pct": 0.03, **dict(zip(("up", "down", "both", "none"), st))})
    return pd.DataFrame(rows)


def test_reconcile_decomposition_counts_and_record(env, monkeypatch):
    """集合拆解:掉出组分「段没了」「过不了闸」,新进组分「新出现的段」「原来过不了闸」;总变化 / 只删 / 只加三个量;写 reconcile。"""
    monkeypatch.setattr(fs, "_adapter", lambda app: _adapter(param_features={"bo.th": "exceed_x"}))
    monkeypatch.setattr(fs, "_event_fields", lambda cl, param: {"drought"})
    ok, low_pk = (1, 4, 0.1), (1, 1, 0.1)
    old = _ev_rows([("A", 10, 2024, (3, 1, 0, 0), [ok]),               # 共同
                    ("A", 20, 2024, (0, 4, 0, 0), [low_pk, ok]),       # 改动后段没了 → 掉出(段没了)
                    ("B", 30, 2024, (1, 3, 0, 1), [ok]),               # 改动后前缀变了过不了闸 → 掉出(过不了闸)
                    ("B", 40, 2024, (2, 2, 0, 0), [low_pk])])          # 原来过不了闸,改动后过了 → 新进(原来过不了闸)
    new = _ev_rows([("A", 10, 2024, (3, 1, 0, 0), [ok]),
                    ("B", 30, 2024, (1, 3, 0, 1), [low_pk]),
                    ("B", 40, 2024, (2, 2, 0, 0), [ok]),
                    ("C", 50, 2024, (4, 0, 0, 0), [ok])])              # 新出现的段
    monkeypatch.setattr(extract, "build_from_longtable",
                        lambda app, window, combo, **kw: old if combo["bo.th"] == 0.1 else new)
    out = fs.reconcile("fake", "FC-001", change={"bo.th": [0.1, 0.2]}, out_dir=env["tmp"] / "rec", B=50)

    work = next(r for r in out["table"] if r["base"] == "工作点")
    assert work["dropped"] == {"events": 2, "up": 1, "dir": 8, "segment_gone": 1, "failed_gates": 1}
    assert work["added"] == {"events": 2, "up": 6, "dir": 8, "new_segment": 1, "passed_gates": 1}
    assert work["common"] == {"events": 1, "up": 3, "dir": 4}
    r_old, r_new, r_common, r_old_added = 4 / 12, 9 / 12, 3 / 4, 10 / 20
    assert work["total"] == pytest.approx(r_new - r_old)
    assert work["drop_only"] == pytest.approx(r_common - r_old)
    assert work["add_only"] == pytest.approx(r_old_added - r_old)
    wide = next(r for r in out["table"] if r["base"] == "宽进")
    assert wide["dropped"]["events"] == 1 and wide["added"]["events"] == 1        # 宽进下 B30、B40 都一直在

    rec = ledger.read("fake")[-1]
    assert rec["kind"] == "reconcile" and rec["fc"] == ["FC-001"] and rec["axes"] == ["bo.th"]
    assert rec["data"]["step3"] == "bo.th 缺少对应的特征字段，第三步暂不可做"
    assert Path(out["path"]).exists()


# ── plan → run → close ──

def _flow_rows(seed=0, n_sym=200, per=10):
    """假长表行:峰数 ≥ 3 的买点事件首次穿越率高 10 点;单日跌幅闸无效;每个事件 1~2 个前缀行。"""
    rng = np.random.default_rng(seed)
    n = n_sym * per
    pk = rng.integers(1, 6, n)
    date = pd.Timestamp("2024-01-01") + pd.to_timedelta(rng.integers(0, 730, n), "D")
    bars = 1 + rng.poisson(4, n)
    dirn = rng.binomial(bars, 0.85)
    up = rng.binomial(dirn, np.where(pk >= 3, 0.55, 0.45))
    both = rng.binomial(dirn - up, 0.1)
    ev = pd.DataFrame({"symbol": np.repeat([f"S{i:03d}" for i in range(n_sym)], per), "date": date,
                       "year": date.year.astype(str), "tb.start": np.tile(np.arange(per) * 10, n_sym),
                       "burst.count": 1, "burst.pk": pk, "tb.drop": rng.uniform(0, 0.4, n),
                       "M": rng.uniform(0.01, 0.05, n), "c0_atr_pct": rng.uniform(0.01, 0.06, n),
                       "up": up, "down": dirn - up - both, "both": both, "none": bars - dirn})
    ev["tb.end"] = ev["tb.start"] + bars - 1
    extra = ev.sample(frac=0.3, random_state=seed).assign(**{"burst.pk": lambda d: np.maximum(d["burst.pk"] - 2, 1)})
    return pd.concat([ev, extra]).sort_values(["symbol", "tb.start"], kind="stable").reset_index(drop=True)


def test_plan_run_close_flow(env, monkeypatch):
    """plan 冻结闸子族(在役闸 × 切点 + 不读标签的功效预检)→ run 按冻结族判定(与同批特征同族)→ close 写 verify 与登记簿关闭行。"""
    rows = _flow_rows()
    tmp = env["tmp"]
    ledger.append(_rec("edge", data={"points": {}, "verdict": {}, "resolution": {"deff": 2.5, "s_dec": 0.85}}))
    ledger.append(_rec("discover", fc=["FC-001"], axes=["burst.pk_min"], data={}))
    monkeypatch.setattr(fs, "_read_label_free",
                        lambda app, window, cl, combo, columns: (rows.drop(columns=["up", "down", "both", "none"]),
                                                                 ["tb.start", "tb.end"], ["tb.start", "tb.end"]))
    monkeypatch.setattr(extract, "build_from_longtable", lambda app, window, combo, **kw: rows)
    ds = rows.drop_duplicates(["symbol", "tb.start"]).assign(entry_date=lambda d: d["date"],
                                                             f1=lambda d: np.random.default_rng(1).normal(0, 1, len(d)))
    csv = tmp / "dataset.csv"
    ds[["symbol", "entry_date", "c0_atr_pct", "up", "down", "both", "none", "f1"]].to_csv(csv, index=False)

    gf = fs.plan("fake", "w", extra=[{"features": ["f1"], "csv": str(csv), "fc": ["FC-002"]}], delta=0.05,
                 out_dir=tmp / "round", registry=env["registry"])
    plan_path = tmp / "round" / "plan.json"
    assert json.loads(plan_path.read_text())["gate_family"] == gf
    assert gf["population"]["working"] == {"burst.min_n": 1, "burst.pk_min": 3, "tb.drop_pct": 0.2}
    assert (gf["delta"], gf["q"]) == (0.05, 0.05)
    gates = {g["param"]: g for g in gf["gates"]}
    assert set(gates) == {"burst.pk_min", "tb.drop_pct"}                 # burst.min_n 在机制下限:不在役
    assert gates["burst.pk_min"]["cuts"] == [3, 5] and gates["burst.pk_min"]["fc"] == ["FC-001"]
    assert gates["tb.drop_pct"]["cuts"] == [0.2] and gates["tb.drop_pct"]["fc"] == []
    assert all("mde" in c for g in gf["gates"] for c in g["power"])
    assert [r["kind"] for r in ledger.read("fake")] == ["edge", "discover"]   # 轮内不写账本

    # 冻结族改成与读标签后现场实测不同的样子(峰数闸只留切点 3、单日跌幅闸进族与否翻过来):run 必须按冻结的判
    frozen = json.loads(plan_path.read_text())
    for g in frozen["gate_family"]["gates"]:
        for c in g["power"]:
            c["in_family"] = c["cut"] == 3 if g["param"] == "burst.pk_min" else not c["in_family"]
    frozen["gate_family_hash"] = STUDY_IO.canonical_hash(frozen["gate_family"])
    plan_path.write_text(json.dumps(frozen, ensure_ascii=False), encoding="utf-8")
    family = {g["column"]: [c["cut"] for c in g["power"] if c["in_family"]] for g in frozen["gate_family"]["gates"]}

    n_before = len(ledger.read("fake"))
    res = fs.run(plan_path, B=50)
    assert len(ledger.read("fake")) == n_before                          # run 不写账本
    pk = res["gates"]["burst.pk_min"]
    assert pk["verdict"] == "有信号+" and pk["time_verified"] is False   # 发现样本与本窗时间重叠
    assert pk["bucket"] == "判不了" and "时间维未验证" in pk["reason"]
    assert pk["soft_conflicts"][0]["fc"] == ["FC-001"]
    assert {r["column"]: r["stats"]["family_cuts"] for r in res["gates"].values()} == family
    assert {r["stats"]["family_source"] for r in res["gates"].values()} == {"预注册冻结"}
    assert {r["column"]: [e["cut"] for e in r["curve"] if e["powered"]] for r in res["gates"].values()} != family
    fam = pk["stats"]["family_size"]
    assert fam == sum(bool(cuts) for cuts in family.values()) + 1                  # 冻结族 + 同批特征
    assert res["features"]["f1"]["family_size"] == fam
    assert Path(res["path"]).name == "verdicts.json"

    out = fs.close(plan_path, res, registry=env["registry"])
    text = env["registry"].read_text(encoding="utf-8")
    assert "### FC-004 · [闸存在性] tb.drop_pct" in text                # 没有登记条目的闸先补登记
    assert text.index("### FC-004") < text.index("## 已关闭")
    closed = fs.registry_state(env["registry"])["closed"]
    assert {"FC-001", "FC-002", "FC-004"} <= closed
    assert "首次穿越率 = up/(up+down+both)" in text and "git_head abc1234" in text
    verifies = [r for r in ledger.read("fake") if r["kind"] == "verify"]
    assert len(verifies) == 3 and out["n_records"] == 3
    v_pk = next(r for r in verifies if r["axes"] == ["burst.pk_min"])
    assert v_pk["data"]["label"]["metric"] == "first_passage" and v_pk["data"]["axis"] == {"node": "burst", "field": "pk", "op": ">="}
    assert v_pk["n_looks"] == 2 and v_pk["source_fingerprint"] == FPS["source_fingerprint"]
    assert "manifest_hash" not in v_pk["data"] and "confirm_window" not in v_pk["data"]     # 训练窗上的判定不带
    assert set(out["columns"]) == {"确实有用", "没用删了不亏", "判不了"}
    assert any("burst.pk" in h for h in out["hints"])


def test_plan_out_of_round_writes_preregister_and_needs_edge(env, monkeypatch):
    """没有优势检查就拒绝;轮外预注册写 preregister(manifest = 闸子族);候选配置 K 改变条件总体与在役闸。"""
    rows = _flow_rows(n_sym=50)
    monkeypatch.setattr(fs, "_read_label_free",
                        lambda app, window, cl, combo, columns: (rows, ["tb.start", "tb.end"], ["tb.start", "tb.end"]))
    with pytest.raises(SystemExit, match="优势检查"):
        fs.plan("fake", "w", out_dir=env["tmp"] / "r0", registry=env["registry"])
    ledger.append(_rec("edge", data={"points": {}, "verdict": {}, "resolution": {"deff": 2.5, "s_dec": 0.85}}))
    gf = fs.plan("fake", "w", in_round=False, out_dir=env["tmp"] / "r1", registry=env["registry"])
    rec = ledger.read("fake")[-1]
    assert rec["kind"] == "preregister" and rec["data"]["manifest"] == {"gate_family": gf}
    assert rec["data"]["manifest_hash"] == STUDY_IO.canonical_hash({"gate_family": gf})
    assert set(rec["axes"]) == {"burst.pk_min", "tb.drop_pct"}

    k = fs.plan("fake", "w", config={"burst.pk_min": 5, "tb.drop_pct": None}, out_dir=env["tmp"] / "r2",
                registry=env["registry"])
    assert [g["param"] for g in k["gates"]] == ["burst.pk_min"] and k["gates"][0]["cuts"] == [3, 5]
    assert k["population"]["working"]["tb.drop_pct"] is None
    with pytest.raises(ValueError, match="不是这个 app 的参数"):
        fs.plan("fake", "w", config={"nope.x": 1}, out_dir=env["tmp"] / "r3", registry=env["registry"])


def test_delta_from_ruling_then_settings(env, monkeypatch):
    """δ 的来源:账本里最近一条 δ 裁定(单位点);没有裁定时等于 tune-gates Settings 的最小关心改进。"""
    settings_delta = fs.RB.load_tune_gates("tune").Settings().min_effect_pt / 100
    rows = _flow_rows(n_sym=50)
    monkeypatch.setattr(fs, "_read_label_free",
                        lambda app, window, cl, combo, columns: (rows, ["tb.start", "tb.end"], ["tb.start", "tb.end"]))
    ledger.append(_rec("edge", data={"points": {}, "verdict": {}, "resolution": {"deff": 2.5, "s_dec": 0.85}}))
    assert fs.resolve_delta("fake") == settings_delta
    assert fs.plan("fake", "w", out_dir=env["tmp"] / "d0", registry=env["registry"])["delta"] == settings_delta
    for pt in (3, 2.5):
        ledger.append(_rec("ruling", window=None, label_horizon=None, data={"topic": "delta", "value": pt}))
    assert fs.resolve_delta("fake") == 0.025
    assert fs.plan("fake", "w", out_dir=env["tmp"] / "d1", registry=env["registry"])["delta"] == 0.025


OPEN_DATA = {"data_start": "2018-01-01", "data_end": "2028-12-29", "n_probed": 1,
             "train": {"start": "2024-01-01", "end": "2025-12-31", "label_end": "2026-02-25"},
             "confirm": {"backward": {"start": "2021-01-04", "end": "2023-10-31", "label_end": "2023-12-26"},
                         "forward": {"start": "2026-03-02", "end": "2026-06-18", "label_end": "2026-08-13"}}}


def test_confirm_window_gate_family(env, monkeypatch):
    """确认窗上的闸子族补检:本地清单与冻结清单一致、这一段已按清单开过才放行;取数入口可注入;
    verify 带清单哈希与确认窗、窗口是确认窗买点区间;同一段只能检一次。"""
    rows = _flow_rows(seed=2)
    tmp = env["tmp"]
    holdout = fs.RB.load_tune_gates("holdout")
    monkeypatch.setattr(holdout, "default_calendar", lambda: pd.bdate_range("2018-01-01", "2028-12-29"))
    monkeypatch.setattr(fs, "_read_label_free",
                        lambda app, window, cl, combo, columns: (rows, ["tb.start", "tb.end"], ["tb.start", "tb.end"]))
    ledger.append(_rec("open", data=OPEN_DATA))
    ledger.append(_rec("edge", data={"points": {}, "verdict": {}, "resolution": {"deff": 2.5, "s_dec": 0.85}}))
    ledger.append(_rec("discover", fc=["FC-001"], axes=["burst.pk_min"], data={}))
    gf = fs.plan("fake", "w", delta=0.05, out_dir=tmp / "round", registry=env["registry"])
    plan_path = tmp / "round" / "plan.json"
    manifest = {"gate_family": gf}
    h = STUDY_IO.canonical_hash(manifest)
    ledger.append(_rec("preregister", data={"manifest_hash": h, "manifest": manifest,
                                            "expected_power": {"backward": 0.6, "forward": 0.6}, "survivorship": {}}))
    fw = OPEN_DATA["confirm"]["forward"]
    confirm_rows = rows.assign(date=pd.Timestamp(fw["start"]) + pd.to_timedelta(rows["tb.start"] % 90, "D"))
    confirm_rows["year"] = confirm_rows["date"].dt.year.astype(str)
    calls = []

    def loader(app, confirm_window, combo, gate_cols):
        calls.append((confirm_window, combo, list(gate_cols)))
        return confirm_rows

    with pytest.raises(holdout.HoldoutLocked) as e:                   # 这一段还没按这份清单开过
        fs.run(plan_path, confirm_window="forward", manifest_hash=h, load_rows=loader, B=20)
    assert e.value.reason == "gate_family_refused" and not calls
    ledger.append(_rec("extrapolate", window={"start": fw["start"], "end": fw["end"]},
                       data={"manifest_hash": h, "confirm_window": "forward", "results": {}}))

    res = fs.run(plan_path, confirm_window="forward", manifest_hash=h, load_rows=loader, B=20)
    assert calls == [("forward", gf["population"]["combo"], ["burst.count", "burst.pk", "tb.drop"])]
    assert Path(res["path"]).name == "verdicts_forward.json"
    assert res["sample"]["window"] == {"start": fw["start"], "end": fw["end"]}
    assert res["gates"]["burst.pk_min"]["time_verified"] is True     # 发现样本在训练窗,与前向确认窗时间不相交

    fs.close(plan_path, res, registry=env["registry"])
    verifies = [r for r in ledger.read("fake") if r["kind"] == "verify"]
    assert len(verifies) == 2
    assert all(r["data"]["manifest_hash"] == h and r["data"]["confirm_window"] == "forward" for r in verifies)
    assert all(r["window"] == {"start": fw["start"], "end": fw["end"]} for r in verifies)
    assert "训练期之后留出的那段验证数据" in env["registry"].read_text(encoding="utf-8")

    with pytest.raises(holdout.HoldoutLocked) as e:                   # 同一段只能检一次
        fs.run(plan_path, confirm_window="forward", manifest_hash=h, load_rows=loader, B=20)
    assert e.value.reason == "gate_family_refused"

    tampered = json.loads(plan_path.read_text())
    tampered["gate_family"]["delta"] = 0.03
    (tmp / "tampered").mkdir()
    (tmp / "tampered" / "plan.json").write_text(json.dumps(tampered))
    with pytest.raises(ValueError, match="不一致"):
        fs.run(tmp / "tampered" / "plan.json", confirm_window="backward", manifest_hash=h, load_rows=loader)
    with pytest.raises(ValueError, match="manifest_hash"):
        fs.run(plan_path, confirm_window="backward", load_rows=loader)


# ── golden:现存 bb_v1 main 长表 ──

LT = REPO / "outputs/tune_gates/bb_v1/main/longtable"
golden = pytest.mark.skipif(os.environ.get("TUNE_GOLDEN") != "1" or not LT.exists(),
                            reason="golden:需 TUNE_GOLDEN=1 且存在 outputs/tune_gates/bb_v1/main/longtable")


@golden
def test_golden_reconcile_exceed_threshold(tmp_path, monkeypatch):
    """bb_v1 main:提高 bo.exceed_threshold 0.003→0.0075 的集合拆解(回踩去重)。定案前工作点(峰龄闸 60):
    2024 年总变化 +3.09 点、掉出 33 个回踩;宽进点 2024 年 −0.16 点、掉出 474 个。第三步暂不可做(突破幅度字段未实现)。"""
    ldir = tmp_path / "ledger"
    ldir.mkdir()
    (ldir / "bb_v1.jsonl").write_bytes((REPO / "docs/sample_usage/bb_v1.jsonl").read_bytes())
    monkeypatch.setenv("TUNE_LEDGER_DIR", str(ldir))
    out = fs.reconcile("bb_v1", "FC-006", change={"bo.exceed_threshold": [0.003, 0.0075]},
                       working={"burst.peak_age_min": 60}, out_dir=tmp_path / "rec", B=50)
    row = {(r["base"], r["year"]): r for r in out["table"]}
    assert abs(row[("工作点", "2024")]["total"] * 100 - 3.09) <= 0.005
    assert row[("工作点", "2024")]["dropped"]["events"] == 33
    assert abs(row[("宽进", "2024")]["total"] * 100 - (-0.16)) <= 0.005
    assert row[("宽进", "2024")]["dropped"]["events"] == 474
    assert out["step3"]["message"] == "bo.exceed_threshold 缺少对应的特征字段，第三步暂不可做"


def test_delta_and_confirm_rows_are_tune_gates_single_source(monkeypatch):
    """δ 的取法与确认窗取数都不在学习端另写一份:fs.resolve_delta 调 tune.resolve_delta,确认窗缺省取数口调 tune.confirm_rows。"""
    tune = fs.RB.load_tune_gates("tune")
    calls = []
    monkeypatch.setattr(tune, "resolve_delta", lambda app, cfg=None: calls.append(("delta", app)) or 0.037)
    monkeypatch.setattr(tune, "confirm_rows", lambda *a, **kw: calls.append(("rows", a, kw)) or "rows")
    assert fs.resolve_delta("fake") == 0.037
    assert fs._confirm_rows("fake", "forward", {"bo.th": 0.2}, ["tb.drop"], manifest_hash="h1") == "rows"
    assert calls == [("delta", "fake"), ("rows", ("fake", "forward", {"bo.th": 0.2}, ["tb.drop"]), {"manifest_hash": "h1"})]
