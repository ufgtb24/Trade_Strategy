"""反馈状态判法、样本 match 的 Python 版、app 版本指纹与「跑 app 取买点日」(spec 6.13「状态判法」「检查·判法」、
`app_ver` 条)。

钉住的要求:
- 样本 match:sample_match 逐例给出 fixtures/match_examples.json 里写好的答案(前端 compareRead.ts 的 matchOf
  过同一份文件,见 path2_web_ui/tests/annotate.match-examples.spec.ts);距离按 K 线根数算,样本日不是交易日 → unmatched;
- 反馈状态:point 当天有买点 matched、只有前后一天有 unmatched;range 边界内外;family 范围外同起点 hit 还在买
  matched、起点认不出 lost、起点事件还在但不买 unmatched;朱红 = matched 且没挂「定义改过」;
- app_ver:改 `.py`、改默认参数文件、增删 `.py` 会变;改 mapping.yaml、另存的参数文件、增删 __pycache__ 不变;
- app_buys:买点日 = 每个 hit 的买点事件跨度里的每一根(与前端 buyDaysOf 同口径,含 'node.slot' 的写法),
  族按 hit 起点分;事件起点只取参与求解的 node(含与它共用一条流、记在兄弟名下的事件);能 JSON 往返;
- run_app:读的行情不晚于训练段末日;读不到行情时抛的异常分得清目录缺、股票缺、代码不合格。
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from path2_web import app_run
from path2_web.annotation import match as m
from path2_web.app_run import AppBuys, app_buys, run_app, solving_nodes
from path2_web.app_version import app_ver
from tests.path2_web.conftest import TRAIN_END, data_cfg

FIXTURES = Path(__file__).parent / "fixtures"
EXAMPLES = json.loads((FIXTURES / "match_examples.json").read_text(encoding="utf-8"))
DAYS = EXAMPLES["days"]
TOL = EXAMPLES["params"]


# ───────────────────────── 样本 match:例子文件 ─────────────────────────
def _example_args(c: dict):
    date = DAYS[c["day"]] if "day" in c else c["date"]
    buy_days = [DAYS[i] for h in c["hits"] for i in h]
    return date, c["judgment"], buy_days


@pytest.mark.parametrize("case", EXAMPLES["cases"], ids=[c["name"] for c in EXAMPLES["cases"]])
def test_sample_match_examples(case):
    date, judgment, buy_days = _example_args(case)
    assert m.sample_match(date, judgment, buy_days, DAYS, tol=TOL) == case["expect"], case["why"]


def test_examples_cover_both_judgments_both_answers_and_non_trading_day():
    cases = EXAMPLES["cases"]
    assert len({c["name"] for c in cases}) == len(cases)
    assert {(c["judgment"], c["expect"]) for c in cases} == {
        ("pos", "matched"), ("pos", "unmatched"), ("neg", "matched"), ("neg", "unmatched")}
    assert any("date" in c and c["date"] not in DAYS for c in cases)


def test_sample_match_default_tolerance_is_module_constants():
    """省略 tol 时用本模块的 POS_TOL / NEG_TOL。"""
    days = DAYS[:20]
    for judgment, lim in (("pos", m.POS_TOL), ("neg", m.NEG_TOL)):
        assert m.sample_match(days[5], judgment, [days[5 + lim]], days) == "matched"
        assert m.sample_match(days[5], judgment, [days[5 + lim + 1]], days) == "unmatched"
    with pytest.raises(ValueError):
        m.sample_match(days[5], "maybe", [days[5]], days)


# ───────────────────────── 反馈状态 ─────────────────────────
D = pd.bdate_range("2025-01-02", periods=30).strftime("%Y-%m-%d").tolist()
#                 族起点   → 买点日
BUYS = AppBuys(families={D[0]: (D[6], D[7]),          # 一族在买:第 6、7 根
                         D[12]: ()},                   # 一族有 hit、但一天都不买
               event_starts=(D[0], D[12], D[20]),      # 第 20 根起的事件没进任何 hit
               dates=tuple(D))


def _fb(target, start, end, family_start=None):
    v = {"id": "f-pc-1", "target": target, "start": start, "end": end}
    if family_start is not None:
        v["family_start"] = family_start
    return v


def test_point_on_buy_day_matched_neighbours_unmatched():
    assert m.feedback_status(_fb("point", D[6], D[6]), BUYS) == "matched"
    assert m.feedback_status(_fb("point", D[5], D[5]), BUYS) == "unmatched"   # 买点前一天
    assert m.feedback_status(_fb("point", D[8], D[8]), BUYS) == "unmatched"   # 买点后一天


def test_range_boundaries():
    assert m.feedback_status(_fb("range", D[7], D[10]), BUYS) == "matched"    # 起点正好是买点
    assert m.feedback_status(_fb("range", D[2], D[6]), BUYS) == "matched"     # 终点正好是买点
    assert m.feedback_status(_fb("range", D[8], D[15]), BUYS) == "unmatched"  # 紧挨着买点之后
    assert m.feedback_status(_fb("range", D[1], D[5]), BUYS) == "unmatched"   # 紧挨着买点之前


def test_family_states():
    # 范围外,但起点相同的那一族还在买 → matched
    assert m.feedback_status(_fb("family", D[9], D[11], family_start=D[0]), BUYS) == "matched"
    # 起点认不出(参与求解的 node 没有一个事件起于这天)→ lost
    assert m.feedback_status(_fb("family", D[25], D[27], family_start=D[24]), BUYS) == "lost"
    # 起点那一族还在、但不买 → unmatched;起点事件还在、没有 hit → unmatched
    assert m.feedback_status(_fb("family", D[13], D[15], family_start=D[12]), BUYS) == "unmatched"
    assert m.feedback_status(_fb("family", D[21], D[23], family_start=D[20]), BUYS) == "unmatched"
    # 只看日期:范围里有买点就 matched,不管是不是这一族的、起点认不认得出
    assert m.feedback_status(_fb("family", D[4], D[6], family_start=D[3]), BUYS) == "matched"


def test_feedback_status_bad_input():
    with pytest.raises(ValueError):
        m.feedback_status(_fb("week", D[1], D[2]), BUYS)
    with pytest.raises(ValueError):
        m.feedback_status(_fb("family", D[9], D[11]), BUYS)   # family 缺 family_start


def test_is_red():
    assert m.is_red("matched", None)
    assert m.is_red("matched", "for_tuning")
    assert not m.is_red("matched", m.TAG_REDEFINED)
    assert not m.is_red("unmatched", None)
    assert not m.is_red("lost", None)
    # 页面上显示的:lost 并进 unmatched;标签只在 matched 或 lost 时挂
    assert [m.shown_status(x) for x in ("matched", "unmatched", "lost", None)] == ["matched", "unmatched", "unmatched", None]
    assert [m.shown_tag(x, "for_tuning") for x in ("matched", "lost", "unmatched", None)] == ["for_tuning", "for_tuning", None, None]
    assert m.shown_tag("lost", None) is None
    assert not m.is_red(None, None)       # 行情读不到的股票


# ───────────────────────── app_ver ─────────────────────────
def _mk_app(root: Path):
    app = root / "fake_app"
    (app / "sub").mkdir(parents=True)
    (app / "__init__.py").write_text("", encoding="utf-8")
    (app / "dag_spec.py").write_text("X = 1\n", encoding="utf-8")
    (app / "sub" / "helper.py").write_text("Y = 2\n", encoding="utf-8")
    (app / "params.yaml").write_text("a: 1\n", encoding="utf-8")
    (app / "mapping.yaml").write_text("pattern: p\n", encoding="utf-8")
    (app / "params_tuned.yaml").write_text("a: 2\n", encoding="utf-8")
    mod = SimpleNamespace(__file__=str(app / "dag_spec.py"), DEFAULT_YAML_PATH=app / "params.yaml")
    return app, mod


def test_app_ver_changes_with_code_and_default_params(tmp_path):
    app, mod = _mk_app(tmp_path)
    base = app_ver(mod)
    assert re.fullmatch(r"[0-9a-f]{16}", base)
    assert app_ver(mod) == base

    helper = app / "sub" / "helper.py"      # 子目录里的 .py 也算
    helper.write_text("Y = 3\n", encoding="utf-8")
    assert app_ver(mod) != base
    helper.write_text("Y = 2\n", encoding="utf-8")
    assert app_ver(mod) == base

    (app / "params.yaml").write_text("a: 9\n", encoding="utf-8")
    assert app_ver(mod) != base
    (app / "params.yaml").write_text("a: 1\n", encoding="utf-8")
    assert app_ver(mod) == base

    (app / "extra.py").write_text("", encoding="utf-8")   # 增一个 .py
    assert app_ver(mod) != base
    (app / "extra.py").unlink()
    assert app_ver(mod) == base


def test_app_ver_ignores_mapping_saved_params_and_pycache(tmp_path):
    app, mod = _mk_app(tmp_path)
    base = app_ver(mod)
    (app / "mapping.yaml").write_text("pattern: p\nsession: {tags: {f-pc-1: for_tuning}}\n", encoding="utf-8")
    (app / "params_tuned.yaml").write_text("a: 3\n", encoding="utf-8")
    (app / "params_new.yaml").write_text("a: 4\n", encoding="utf-8")
    cache = app / "__pycache__"
    cache.mkdir()
    (cache / "dag_spec.cpython-312.pyc").write_bytes(b"\x00\x01")
    (cache / "stray.py").write_text("Z = 1\n", encoding="utf-8")
    (app / "sub" / "__pycache__").mkdir()
    (app / "sub" / "__pycache__" / "helper.py").write_text("W = 1\n", encoding="utf-8")
    assert app_ver(mod) == base


def test_app_ver_reads_default_params_from_params_submodule(tmp_path):
    """DEFAULT_YAML_PATH 不在 dag_spec 上、在它的 params 子模块上时照样取到(同 _params_dir 的取法)。"""
    app, mod = _mk_app(tmp_path)
    alt = SimpleNamespace(__file__=mod.__file__, params=SimpleNamespace(DEFAULT_YAML_PATH=mod.DEFAULT_YAML_PATH))
    assert app_ver(alt) == app_ver(mod)
    bare = SimpleNamespace(__file__=mod.__file__)      # 没有默认参数文件:只认 .py
    assert app_ver(bare) != app_ver(mod)


def test_app_ver_of_real_app_is_stable():
    import path2_apps.bo_only.dag_spec as bo_only
    v = app_ver(bo_only)
    assert re.fullmatch(r"[0-9a-f]{16}", v) and app_ver(bo_only) == v


# ───────────────────────── app_buys(假结果:'node.slot' 买点、族、事件起点) ─────────────────────────
class _Ev:
    """假事件:起止下标、node_id,和按槽名给 child 的 child_slots()(_resolve_end_events 只用这些)。"""

    def __init__(self, node_id, s, e, slots=None):
        self.node_id, self.start_idx, self.end_idx = node_id, s, e
        self._slots = slots or {}

    def child_slots(self):
        return self._slots


def test_app_buys_slot_path_families_and_event_starts(monkeypatch):
    win = pd.DataFrame({"date": pd.to_datetime(D[:15])})
    p1 = _Ev("plat", 0, 7, {"today": (_Ev("today", 5, 5),)})
    p1b = _Ev("plat", 0, 8, {"today": (_Ev("today", 6, 6), _Ev("today", 8, 9))})   # 同一族另一次 hit
    p2 = _Ev("plat", 3, 10, {"today": ()})                                           # 一天都不买
    lone = _Ev("plat", 11, 13, {"today": ()})                                        # 没进 hit 的事件
    other = _Ev("other", 2, 4)                                                       # 不参与求解的 node
    hits = [SimpleNamespace(start_idx=0, node_index={"plat": p1}),
            SimpleNamespace(start_idx=0, node_index={"plat": p1b}),
            SimpleNamespace(start_idx=3, node_index={"plat": p2})]
    res = SimpleNamespace(hits=hits, events=(p1, p1b, p2, lone, other), spec=None)
    monkeypatch.setattr(app_run, "solving_nodes", lambda spec: frozenset({"plat"}))

    b = app_buys(res, win, "plat.today")
    assert b.families == {D[0]: (D[5], D[6], D[8], D[9]), D[3]: ()}
    assert b.buy_days == (D[5], D[6], D[8], D[9])
    assert b.event_starts == (D[0], D[3], D[11])        # other 起于 D[2],不算
    assert b.dates == tuple(D[:15])

    again = AppBuys.from_dict(json.loads(json.dumps(b.to_dict())))
    assert again == b

    with pytest.raises(KeyError):                        # hit 里没有买点 node:响亮失败
        app_buys(res, win, "nope")


def test_solving_nodes_excludes_display_only_and_keeps_shared_stream():
    """只显示不求解的 node 不算;几个 node 共用一条流时,流里事件记在声明在前的兄弟名下,兄弟一并算上。"""
    import path2_apps.bo_only.dag_spec as bo_only
    from path2.atoms.breakout import BODetector
    from path2.dag.nodes import NodeSpec
    from path2.dag.spec import PatternSpec

    p = bo_only.load_params()
    assert solving_nodes(bo_only.build_pattern(p)) == {"bo"}          # pk 只显示

    det = BODetector(**p.bo_kwargs())
    spec = PatternSpec(pattern_id="shared", edges=(), nodes=(
        NodeSpec("a", det, produces_stream="bo", solve=False),         # 声明在前,事件记在它名下
        NodeSpec("b", det, produces_stream="bo"),
        NodeSpec("pk", det, produces_stream="pk", solve=False)))
    assert solving_nodes(spec) == {"a", "b"}
    df = _oscillating_bars().loc[:TRAIN_END].reset_index()
    from path2.dag.engine import analyze
    res = analyze(spec, df, p)
    assert res.hits and {e.node_id for e in res.events} == {"a", "pk"}
    b = app_buys(res, df, "b", spec)
    bo_days = {df["date"].iat[e.start_idx].strftime("%Y-%m-%d") for e in res.events if e.node_id == "a"}
    assert set(b.event_starts) == bo_days


# ───────────────────────── run_app + app_buys(真 app,合成行情) ─────────────────────────
def _oscillating_bars() -> pd.DataFrame:
    """来回波动、慢慢抬升、每 37 根放一次量的合成股票(2024-06 ~ 2026-03),bo_only 跑得出好几次 hit。"""
    idx = pd.bdate_range("2024-06-03", "2026-03-31", name="date")
    n = len(idx)
    close = 10 + 1.5 * np.sin(np.arange(n) / 9.0) + np.random.default_rng(0).normal(0, 0.15, n) \
        + np.linspace(0, 4, n)
    vol = 1e6 * (1 + (np.arange(n) % 37 == 0) * 3)
    return pd.DataFrame({"open": close, "high": close + 0.3, "low": close - 0.3, "close": close,
                         "volume": vol}, index=idx)


def _front_buy_days(hit: dict, by_id: dict, end_node: str) -> set:
    """前端 render/fold.ts 的 buyDaysOf 照抄成 Python(只读序列化结果),作对照。"""
    node, _, slot = end_node.partition(".")
    parent = by_id.get(hit["node_index"].get(node))
    if parent is None:
        return set()
    evs = [by_id[i] for i in (parent.get("child_refs") or {}).get(slot, [])] if slot else [parent]
    return {i for e in evs for i in range(e["start_idx"], e["end_idx"] + 1)}


def test_run_app_and_app_buys_match_front_end_reading(tmp_path):
    import path2_apps.bo_only.dag_spec as bo_only
    from path2_web.serialize import serialize_analysis

    _oscillating_bars().to_pickle(tmp_path / "AAA.pkl")
    cfg = data_cfg(tmp_path)
    res, win, meta = run_app(bo_only, cfg, "AAA", "1900-01-01", "2026-06-30", bo_only.load_params(), 20)
    assert meta["end_date"] == TRAIN_END and meta["win_end"] <= TRAIN_END and meta["end_node"] == "bo"
    assert set(meta) == {"start_date", "end_date", "win_start", "win_end", "label_horizon", "end_node"}
    assert win["date"].max() <= pd.Timestamp(TRAIN_END)

    b = app_buys(res, win, meta["end_node"])
    assert b.dates == tuple(win["date"].dt.strftime("%Y-%m-%d"))
    assert max(b.dates) <= TRAIN_END and b.buy_days

    # 与前端读同一份序列化结果算出的买点日、族一致
    ser = serialize_analysis(res)
    by_id = {e["instance_id"]: e for e in ser["events"]}
    fam: dict = {}
    for h in ser["hits"]:
        fam.setdefault(b.dates[h["start_idx"]], set()).update(
            b.dates[i] for i in _front_buy_days(h, by_id, meta["end_node"]))
    assert b.families == {k: tuple(sorted(v)) for k, v in fam.items()}

    # 事件起点只有参与求解的 bo,只显示的 pk 不进
    starts = {n: {b.dates[e["start_idx"]] for e in ser["events"] if e["node_id"] == n} for n in ("bo", "pk")}
    assert set(b.event_starts) == starts["bo"]
    assert starts["pk"] - starts["bo"]                     # pk 有 bo 没有的起点,确实被排除了
    assert not (starts["pk"] - starts["bo"]) & set(b.event_starts)


def test_run_app_bars_unavailable(tmp_path):
    import path2_apps.bo_only.dag_spec as bo_only
    p = bo_only.load_params()
    with pytest.raises(app_run.NoDataDir) as e:
        run_app(bo_only, data_cfg(tmp_path / "missing"), "AAA", "1900-01-01", TRAIN_END, p)
    assert isinstance(e.value, FileNotFoundError) and isinstance(e.value, app_run.BarsUnavailable)
    with pytest.raises(app_run.NoSymbol) as e:
        run_app(bo_only, data_cfg(tmp_path), "NOPE", "1900-01-01", TRAIN_END, p)
    assert isinstance(e.value, FileNotFoundError) and "pkl not found" in str(e.value)
    with pytest.raises(app_run.BadSymbol) as e:
        run_app(bo_only, data_cfg(tmp_path), "../x", "1900-01-01", TRAIN_END, p)
    assert isinstance(e.value, ValueError)
