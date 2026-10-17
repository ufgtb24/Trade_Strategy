"""要素库:判定函数(合成 QMMM 上的金标、未来扰动一字不差)、定义的规范化、身份看定义不看字面
(同定义拒绝新建、系统默认值不算身份)、别名、在用要素身份不变、待写代码写成计算时查重、显式合并
(别名并过去、旧编号照常解析)、要素文件进水位、查询命令;事实行登记(出处、查重提示)。"""
import json

import pandas as pd
import pytest

from chart_workflow import elements as E
from chart_workflow import facts, oplog, shapes
from chart_workflow.facts import compute_facts
from tests.chart_workflow.conftest import make_stock
from tests.chart_workflow.test_facts import _perturbed, qmmm_synthetic
from tests.chart_workflow.test_shapes import DET, _batch, _ann, _decision, el_op

PK1 = {"cond": "peaks_cleared", "variant": "close", "user_params": {"n": 1}}
PK2 = {"cond": "peaks_cleared", "variant": "close", "user_params": {"n": 2}}
BURST2 = {"cond": "burst_chain", "variant": "close", "user_params": {"n": 2}}
DIST20 = {"cond": "distribution_within", "variant": None, "user_params": {"bars": 20}}
VOL = {"cond": "volume_today_at_least", "variant": None}                 # 放量倍数用系统默认(待验证)


def _norm(d):
    out, errs = E.normalize_definition(d)
    assert errs == []
    return out


def _verdict(d, f):
    return E.evaluate(_norm(d), f)[0]


# ── 判定 ───────────────────────────────────────────────────────────────────

def test_qmmm_golden_verdicts():
    """合成 QMMM(7/14 买点):按收盘至少越过一个峰 是;按收盘连续越过两个峰 是;最近 20 根里有派发 否
    (5/28 那根派发离买点 33 根)。"""
    f = compute_facts(qmmm_synthetic(), "2025-07-14", "2025-02-28")
    assert _verdict(PK1, f) == "yes"
    assert _verdict(BURST2, f) == "yes"
    assert _verdict(DIST20, f) == "no"
    assert _verdict({"cond": "distribution_within", "user_params": {"bars": 33}}, f) == "no"   # 离买点 33 根
    assert _verdict({"cond": "distribution_within", "user_params": {"bars": 34}}, f) == "yes"
    assert _verdict({"cond": "peaks_cleared", "variant": "high", "user_params": {"n": 2}}, f) == "no"
    assert _verdict({"cond": "burst_chain", "variant": "close", "user_params": {"n": 3}}, f) == "no"
    assert _verdict(VOL, f) == "no"                                      # 当天量比 0.6
    verdict, why = E.evaluate(_norm(BURST2), f)
    assert "最长一串连着越过 2 个峰" in why
    r = {x["fid"]: x for x in f["rows"]}
    assert r["F03"]["value"]["close"]["chain"] == 2 and r["F03"]["value"]["high"]["chain"] == 1


def test_burst_chain_counts_longest_run():
    """最长一串连续突破:相邻两次首次越过相隔 ≤ 间隔才算连着,断开就重新数。"""
    class Ctx:
        p = {"burst_gap_bars": 5}
        c = [0.0] * 50
    peaks = [{"fc": i, "cleared": True} for i in (10, 12, 30, 33, 36)] + [{"fc": None, "cleared": False}]
    fcs, burst, pair, chain = facts._burst(Ctx, peaks)
    assert fcs == [10, 12, 30, 33, 36] and burst and chain == 3
    assert facts._burst(Ctx, [{"fc": 7, "cleared": True}])[3] == 1
    assert facts._burst(Ctx, [])[3] == 0


def test_unknown_when_fact_missing_or_pending():
    f = compute_facts(qmmm_synthetic(), "2025-07-14", "2025-02-28")
    no_f13 = {**f, "rows": [r for r in f["rows"] if r["fid"] != "F13"]}
    assert E.evaluate(_norm(DIST20), no_f13) == ("unknown", "事实表里没有 F13")
    old = json.loads(json.dumps(f))                                       # 旧快照:F03 没有 chain
    for r in old["rows"]:
        if r["fid"] == "F03":
            r["value"]["close"].pop("chain")
    assert E.evaluate(_norm(BURST2), old)[0] == "unknown"
    no_vr = json.loads(json.dumps(f))
    next(r for r in no_vr["rows"] if r["fid"] == "F07")["value"]["vr"] = None
    assert E.evaluate(_norm(VOL), no_vr)[0] == "unknown"


ALL_DEFS = [PK1, PK2, {"cond": "peaks_cleared", "variant": "high"}, BURST2,
            {"cond": "burst_chain", "variant": "high", "user_params": {"n": 2}}, DIST20,
            {"cond": "distribution_within"}, VOL, {"cond": "volume_today_at_least", "user_params": {"ratio": 1.2}}]


def test_every_condition_type_is_covered():
    assert {d["cond"] for d in ALL_DEFS} == set(E.CONDITIONS)


@pytest.mark.parametrize("seed,buy,box", [(5, "2025-06-16", None), (7, "2025-03-03", "2024-12-02"),
                                          (11, "2025-09-30", "2025-07-01"), (5, "2025-03-11", None)])
def test_future_perturbation_changes_no_verdict(seed, buy, box):
    df = make_stock(seed=seed, sigma=0.05, end="2025-12-31")
    a = compute_facts(df, buy, box)
    for s in (1, 2):
        b = compute_facts(_perturbed(df, buy, s), buy, box)
        assert [E.evaluate(_norm(d), a) for d in ALL_DEFS] == [E.evaluate(_norm(d), b) for d in ALL_DEFS]


def test_future_perturbation_qmmm():
    df = pd.concat([qmmm_synthetic(), make_stock(start="2025-07-15", end="2025-12-31", price=1.8)])
    for buy in ("2025-07-08", "2025-07-14"):
        a = compute_facts(df, buy, "2025-02-28")
        b = compute_facts(_perturbed(df, buy, 3), buy, "2025-02-28")
        assert [E.evaluate(_norm(d), a) for d in ALL_DEFS] == [E.evaluate(_norm(d), b) for d in ALL_DEFS]


# ── 定义 ───────────────────────────────────────────────────────────────────

def test_normalize_fills_reads_and_defaults():
    d = _norm(VOL)
    assert d == {"reads": ["F07"], "cond": "volume_today_at_least", "variant": None,
                 "user_params": {}, "default_params": {"ratio": 3.0}}
    assert _norm({"cond": "peaks_cleared", "variant": "high"})["reads"] == ["F02"]
    assert _norm({**VOL, "user_params": {"ratio": 3}})["user_params"] == {"ratio": 3.0}
    assert E.definition_text(_norm(BURST2)) == "按收盘连续越过至少 2 个峰"
    assert E.params_text(d) == "系统默认（待验证）：量比倍数 3"


@pytest.mark.parametrize("d,needle", [
    ({"cond": "rises_a_lot"}, "cond 不认识"),
    ({"cond": "peaks_cleared"}, "口径 variant 只能是"),
    ({"cond": "peaks_cleared", "variant": "open"}, "口径 variant 只能是"),
    ({**PK1, "default_params": {"n": 1}}, "只能在 user_params 或 default_params 其中一处"),
    ({**PK1, "user_params": {"k": 1}}, "没有参数"),
    ({**PK1, "user_params": {"n": True}}, "必须是数"),
    ({**PK1, "user_params": {"n": 1.5}}, "必须是整数"),
    ({**PK1, "user_params": {"n": 0}}, "至少是 1"),
    ({**VOL, "user_params": {"ratio": -1}}, "必须大于 0"),
    ({**PK1, "reads": ["F02"]}, "reads 应为"),
    ({**PK1, "role": "must"}, "未知字段"),
])
def test_normalize_rejects(d, needle):
    out, errs = E.normalize_definition(d)
    assert out is None and any(needle in e for e in errs), errs


def test_identity_ignores_wording_and_system_defaults():
    assert E.identity(_norm(PK1)) != E.identity(_norm(PK2))                # 至少一个峰 / 两个峰
    assert E.identity(_norm(PK1)) != E.identity(_norm(BURST2))             # 同读峰,条件不同
    assert E.identity(_norm(BURST2)) != E.identity(_norm({**BURST2, "variant": "high"}))  # 同读 F03,口径不同
    a = _norm({**VOL, "default_params": {"ratio": 3.0}})
    b = _norm({**VOL, "default_params": {"ratio": 4.0}})
    assert E.identity(a) == E.identity(b)                                  # 系统默认值不算身份
    assert E.identity(a) != E.identity(_norm({**VOL, "user_params": {"ratio": 3.0}}))


# ── 建、别名、修订、合并(经决定文件) ───────────────────────────────────────

def _apply(*ops):
    return shapes.apply(_decision(*ops))


def _els():
    return E.replay(oplog.read_all())


def test_same_definition_refused_and_alias_attached(state_dir):
    _apply(el_op("a", "按收盘至少越过一个峰", PK1), el_op("v", "放量", VOL, user=False))
    with pytest.raises(shapes.ShapeValidationError) as ei:                 # 字面不同、定义相同
        _apply(el_op("b", "收盘站上前面的高点", PK1))
    assert "E001" in str(ei.value) and "alias_element" in str(ei.value)
    with pytest.raises(shapes.ShapeValidationError) as ei:                 # 只差系统默认值
        _apply(el_op("w", "明显放量", {**VOL, "default_params": {"ratio": 5}}, user=False))
    assert "E002" in str(ei.value)
    with pytest.raises(shapes.ShapeValidationError) as ei:                 # 同一个文件里建两遍也拦
        _apply(el_op("c", "两个峰", PK2), el_op("d", "越过两个峰", PK2))
    assert "E003" in str(ei.value)
    _apply({"act": "alias_element", "target": {"element_id": "E001"},
            "value": {"text": "收盘站上前面的高点"}, "actor": "user"})
    el = _els()["E001"]
    assert [a["text"] for a in el["aliases"]] == ["收盘站上前面的高点"] and el["aliases"][0]["op_id"]
    with pytest.raises(shapes.ShapeValidationError, match="已经有这个说法"):
        _apply({"act": "alias_element", "target": {"element_id": "E001"},
                "value": {"text": " 收盘站上前面的高点 "}})
    _apply(el_op("e", "越过两个峰", PK2))                                   # 定义不同:另一条
    assert sorted(_els()) == ["E001", "E002", "E003"]
    assert json.loads((state_dir / "elements" / "E002.json").read_text())["versions"][0][
        "definition"]["default_params"] == {"ratio": 3.0}


@pytest.mark.parametrize("op,needle", [
    (el_op("x", "", PK1), "value 不能为空"),
    ({**el_op("x", "说法", PK1), "value": {**el_op("x", "说法", PK1)["value"], "said_first_match": ""}},
     "said_first_match"),
    ({**el_op("x", "说法", PK1, user=False),
      "value": {**el_op("x", "说法", PK1, user=False)["value"], "suggested_by": "own_library"}},
     "suggested_by 只能是"),
    (el_op("x", "说法", None), "needs"),
    ({**el_op("x", "说法", PK1), "target": {"element_id": "X1"}}, "element_id 不合法"),
])
def test_create_element_rejects(state_dir, op, needle):
    with pytest.raises(shapes.ShapeValidationError) as ei:
        _apply(op)
    assert needle in str(ei.value)
    assert oplog.read_all() == []


def test_revise_keeps_identity_and_pending_checked_for_duplicates(state_dir):
    _apply(el_op("v", "放量", VOL, user=False), el_op("p", "两个峰", PK2),
           el_op("t", "突破前横着走", None, needs="现有事实没有横走时长"),
           el_op("q", "越过好几个峰", None, needs="要数越过几个峰"))
    _apply({"act": "revise_element", "target": {"element_id": "E001"},
            "value": {"definition": {**VOL, "default_params": {"ratio": 2.5}}, "change": "默认倍数改 2.5"}})
    el = _els()["E001"]
    assert el["current_version"] == 2 and el["versions"][1]["definition"]["default_params"] == {"ratio": 2.5}
    for bad, needle in (({**VOL, "user_params": {"ratio": 2.5}}, "定义变了就是另一条要素"),
                        (None, "不能改回待写代码")):
        with pytest.raises(shapes.ShapeValidationError, match=needle):
            _apply({"act": "revise_element", "target": {"element_id": "E001"},
                    "value": {"definition": bad, "change": "改"}})
    # 待写代码的写成计算:和已有的相同 → 拒绝,提示合并;不同 → 变成在用
    with pytest.raises(shapes.ShapeValidationError) as ei:
        _apply({"act": "revise_element", "target": {"element_id": "E004"},
                "value": {"definition": PK2, "change": "写成计算"}})
    assert "E002" in str(ei.value) and "merge_element" in str(ei.value)
    _apply({"act": "revise_element", "target": {"element_id": "E004"},
            "value": {"definition": {"cond": "peaks_cleared", "variant": "close", "user_params": {"n": 3}},
                      "change": "写成计算"}})
    assert _els()["E004"]["status"] == "active" and _els()["E003"]["status"] == "pending_code"
    with pytest.raises(shapes.ShapeValidationError, match="change 必填"):
        _apply({"act": "revise_element", "target": {"element_id": "E003"}, "value": {"needs": "还缺"}})


def test_merge_moves_aliases_and_old_ids_resolve(state_dir):
    _batch(state_dir, "b1", [_ann("a1")])
    _apply(el_op("p", "按收盘至少越过一个峰", PK1),
           el_op("t", "收盘站上前高", None, needs="还没想好怎么算"),
           {"act": "alias_element", "target": {"element_id": "$t"}, "value": {"text": "站上前高"}},
           {"act": "create_shape", "value": {
               "name": {"value": "站上前高", "origin": "user_written"}, "change": "新建", "from_ann": ["a1"],
               "card": {"ingredients": [{"ing_id": "i1", "element": "$t", "role": "must",
                                         "origin": "user_written"}], "triggers": []}}})
    _apply({"act": "merge_element", "target": {"element_id": "E002"},
            "value": {"into": "E001", "reason": "用户确认是同一个意思"}, "actor": "user"})
    els = _els()
    assert els["E002"]["status"] == "merged" and els["E002"]["merged_into"] == "E001"
    assert [(a["text"], a.get("from")) for a in els["E001"]["aliases"]] == \
        [("收盘站上前高", "E002"), ("站上前高", "E002")]
    assert els["E002"]["versions"] and els["E002"]["aliases"]               # 什么都不删
    assert E.resolve(els, "E002") == "E001"
    card = shapes.load_card("s001")                                         # 旧卡照常解析
    text = shapes.render(card)
    assert "E002「收盘站上前高」（已合并到 E001「按收盘至少越过一个峰」）：按收盘越过前面的峰至少 1 个" in text
    f = compute_facts(qmmm_synthetic(), "2025-07-14", "2025-02-28")
    assert E.evaluate_element(els, "E002", f)[0] == "yes"                   # 按并入的那条判
    with pytest.raises(shapes.ShapeValidationError, match="已合并到 E001"):  # 新版本不能再引用旧编号
        _apply({"act": "revise_shape", "target": {"shape_id": "s001"}, "value": {
            "change": "x", "card": card["versions"][0]["card"]}})
    for op, needle in (({"act": "merge_element", "target": {"element_id": "E001"}, "value": {"into": "E002"}},
                        "已合并到 E001"),
                       ({"act": "merge_element", "target": {"element_id": "E001"}, "value": {"into": "E001"}},
                        "就是自己"),
                       ({"act": "alias_element", "target": {"element_id": "E002"}, "value": {"text": "x"}},
                        "对 E001 操作")):
        with pytest.raises(shapes.ShapeValidationError, match=needle):
            _apply(op)
    _apply(el_op("two", "两个峰", PK2))                                      # E003
    _apply({"act": "merge_element", "target": {"element_id": "E003"}, "value": {"into": "E001"}})
    with pytest.raises(shapes.ShapeValidationError) as ei:                  # 定义同已合并的 → 报并入的那条
        _apply(el_op("z", "越过两个峰", PK2))
    assert "已有要素 E001" in str(ei.value)


def test_element_files_written_and_in_watermark(state_dir):
    _apply(el_op("p", "按收盘至少越过一个峰", PK1))
    # 写完当场记进水位(先读水位文件,不经任何会重新核对水位的入口)
    wm = json.loads((state_dir / ".watermark.json").read_text())
    assert wm["files"]["elements"] == ["E001.json"]
    p = state_dir / "elements" / "E001.json"
    assert p.read_text() == E.canonical(_els()["E001"])
    p.unlink()
    from chart_workflow.state import StateRootRegressed, state_root
    with pytest.raises(StateRootRegressed):
        state_root()


# ── 查询命令 ───────────────────────────────────────────────────────────────

def test_cli_show_conds_find_eval(state_dir, capsys):
    _batch(state_dir, "b1", [_ann("a1")])
    _apply(el_op("p", "按收盘至少越过一个峰", PK1), el_op("b", "按收盘连续越过两个峰", BURST2),
           el_op("d", "最近 20 根里有派发", DIST20, user=False),
           el_op("t", "突破前横着走", None, needs="现有事实没有横走时长"),
           {"act": "create_shape", "value": {
               "name": {"value": "二峰", "origin": "user_written"}, "change": "新建", "from_ann": ["a1"],
               "card": {"ingredients": [{"ing_id": "i1", "element": "$b", "role": "must", **DET},
                                        {"ing_id": "i2", "element": "$d", "role": "must_not", **DET}],
                        "triggers": []}}})
    E.main(["show", "E001"])
    out = capsys.readouterr().out
    assert "E001 「按收盘至少越过一个峰」  在用" in out and "读 F01「按收盘越过的峰」" in out
    assert "你定的：峰的个数 1" in out and "谁提的：你自己说的" in out
    E.main(["conds"])
    out = capsys.readouterr().out
    assert all(c in out for c in E.CONDITIONS) and "待验证" in out
    E.main(["find", "--cond", "peaks_cleared", "--variant", "close", "--param", "n=1"])
    assert "已有：E001「按收盘至少越过一个峰」" in capsys.readouterr().out
    E.main(["find", "--cond", "peaks_cleared", "--variant", "close", "--param", "n=2"])
    out = capsys.readouterr().out
    assert "没有定义相同的要素" in out and "相近" in out and "E001" in out
    with pytest.raises(SystemExit):
        E.main(["find", "--cond", "nope"])
    snap = facts.write_snapshot("b1", [{"ann_id": "a1", "item_id": "QMMM@2025-07-14",
                                        "facts": {**compute_facts(qmmm_synthetic(), "2025-07-14", "2025-02-28"),
                                                  "symbol": "QMMM"}}])
    rel = snap.relative_to(state_dir).as_posix()
    E.main(["eval", "--facts", rel])
    out = capsys.readouterr().out
    assert "QMMM 买点 2025-07-14（标注 a1）" in out
    assert "E001「按收盘至少越过一个峰」：是" in out and "E002「按收盘连续越过两个峰」：是" in out
    assert "E003「最近 20 根里有派发」：否" in out and "E004" not in out    # 默认只判在用的
    E.main(["eval", "--facts", str(snap), "--element", "E004"])
    assert "E004「突破前横着走」（待写代码）：无法判定（待写代码（现有事实没有横走时长））" in capsys.readouterr().out
    E.main(["eval", "--facts", rel, "--shape", "s001"])
    out = capsys.readouterr().out
    assert "【必须有】E002「按收盘连续越过两个峰」：是" in out and "【有它就不买】E003「最近 20 根里有派发」：否" in out


# ── 事实行登记 ─────────────────────────────────────────────────────────────

def test_fact_rows_registry_and_sources():
    assert facts.check_rows() == []
    assert all(d["source"] == facts.PRESET for d in facts.ROWS.values())
    bad = {"F99": {"group": "x", "title": "按收盘越过的峰", "reads": ("peaks_close",),
                   "source": {"kind": "user", "date": "2026-10-17"}}}
    errs = facts.check_rows({**facts.ROWS, **bad})
    assert any("said、op_id" in e for e in errs) and any("标题和 F01 重复" in e for e in errs)


def test_check_new_row_hints():
    hints = facts.check_new_row(" 买点当天量倍数 ", ["vol_ratio"])
    assert hints[0] == "同名：F07「买点当天量倍数」"
    assert any(h.startswith("读的量完全相同：F05") for h in hints)
    hints = facts.check_new_row("回踩深度", ["low", "gap_fill"])
    assert any(h.startswith("也读 low：F15") for h in hints)
    assert any("现有行都没读过的量：gap_fill" in h for h in hints)
    assert facts.check_new_row("全新", ["brand_new"]) == [
        f"现有行都没读过的量：brand_new（现有的量：{'、'.join(sorted({x for d in facts.ROWS.values() for x in d['reads']}))}）"]


def test_user_proposed_row_labeled_and_op_checked(state_dir, monkeypatch, capsys):
    src = {"kind": "user", "date": "2026-10-17", "said": "看最近一个月有没有派发", "op_id": "op-1"}
    monkeypatch.setitem(facts.ROWS, "F13", {**facts.ROWS["F13"], "source": src})
    assert facts.source_warnings([]) == ["F13: 出处写的操作日志条目 op-1 不在日志里(或不是 propose_fact)"]
    with pytest.raises(ValueError, match="said"):
        oplog.append([{"act": "propose_fact", "actor": "user", "surface": "chat", "value": {"said": " "}}])
    oplog.append([{"act": "propose_fact", "actor": "user", "surface": "chat", "op_id": "op-1",
                   "value": {"said": "看最近一个月有没有派发"}}])
    assert facts.source_warnings(oplog.read_all()) == []
    oplog.append([{"act": "type", "actor": "user", "surface": "chat", "op_id": "op-2", "value": "随口一句"}])
    monkeypatch.setitem(facts.ROWS, "F05", {**facts.ROWS["F05"], "source": {**src, "op_id": "op-2"}})
    assert facts.source_warnings(oplog.read_all()) == [          # 指到的不是「提出角度」那一条
        "F05: 出处写的操作日志条目 op-2 不在日志里(或不是 propose_fact)"]
    monkeypatch.setitem(facts.ROWS, "F05", {**facts.ROWS["F05"], "source": facts.PRESET})
    facts.main(["--rows"])
    out = capsys.readouterr().out
    assert "F13 派发／近期派发" in out and "你提的角度（2026-10-17，原话「看最近一个月有没有派发」，操作日志 op-1）" in out
    assert "⚠" not in out
    f = compute_facts(qmmm_synthetic(), "2025-07-14", "2025-02-28")
    assert next(r for r in f["rows"] if r["fid"] == "F13")["source"] == src
    assert "⟨你提的角度，2026-10-17⟩" in facts.render({**f, "symbol": "QMMM"})
    facts.main(["--check-row", "近期派发", "--reads", "distribution"])
    assert "同名：F13" in capsys.readouterr().out
