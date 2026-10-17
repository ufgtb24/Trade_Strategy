"""形态卡与操作日志:来源记录校验(用户来源和系统推荐分得开)、日志与卡一致(rebuild --verify)、
决定文件原子性、after_seeing_outcome 由批次头推出、账本记下每个条件的来源(own_library 递归到 root)、
人话打印与待处理汇总。"""
import copy
import json

import pytest

from chart_workflow import oplog, shapes
from chart_workflow.ledger import add_round, read_ledger, render as render_ledger
from chart_workflow.config import root_dir

DET = {"origin": "suggested_adopted", "suggested_by": "detector"}


def _batch(state_dir, batch_id, anns, schema=2, visible=True, kind="bigmoves"):
    d = state_dir / "annotations"
    d.mkdir(parents=True, exist_ok=True)
    doc = {"schema": f"chart_workflow.annotations/{schema}", "batch_id": batch_id, "list_id": "r1",
           "train_end": "2025-12-31", "annotations": anns}
    if schema == 2:
        doc.update(list_kind=kind, outcome_visible=visible)
    (d / f"{batch_id}.json").write_text(json.dumps(doc, ensure_ascii=False))


def _ann(ann_id, schema=2):
    a = {"ann_id": ann_id, "item_id": f"AAA@2025-07-14", "symbol": "AAA", "range_start": None,
         "range_end": None, "label": "positive", "note": ""}
    if schema == 2:
        a["buy_points"] = [{"date": "2025-07-14", "primary": True}]
    else:
        a.update(buy_date="2025-07-14", range_start="2025-02-28", range_end="2025-07-14")
    return a


CARD = {
    "ingredients": [
        {"ing_id": "i1", "term": "F01", "role": "must", "origin": "user_written",
         "said_first_match": "连续突破了两个峰值",
         "choices": {"measure": {"value": "close", "origin": "user_written",
                                 "suggested_value": ["close", "high"]}}},
        {"ing_id": "i2", "term": "F13", "role": "must_not", **DET},
        {"ing_id": "i3", "term": "custom", "text": "突破前一个月横着走", "role": "bonus",
         "origin": "user_written"},
    ],
    "triggers": [{"trig_id": "t1", "term": "T5", **DET},
                 {"trig_id": "t2", "term": "custom", "text": "放量阳线过前高", "origin": "user_written"}],
    "story": {"value": "突破阻力后抛压被吃掉", "origin": "user_written"},
    "exit_pref": None,
}


def _decision(*ops, ctx=None):
    return {"schema": "chart_workflow.decision/1", "actor": "session", "surface": "chat",
            "ctx": ctx or {"list_id": "r1", "list_kind": "bigmoves", "outcome_visible": True},
            "ops": list(ops)}


def _create(card=CARD, name="放量后连续突破两峰", from_ann=("a1",)):
    return {"act": "create_shape",
            "value": {"name": {"value": name, "origin": "suggested_edited", "suggested_by": "session",
                               "suggested_value": "二峰收盘突破"},
                      "card": copy.deepcopy(card), "change": "新建", "from_ann": list(from_ann)}}


def _case(shape_id="$new", ann_id="a1", trig="t1"):
    return {"act": "add_case", "target": {"shape_id": shape_id},
            "value": {"ann_id": ann_id, "buy_date": {"value": "2025-07-14", "origin": "user_written"},
                      "trigger_ref": trig, "shape_claim": {"value": "new", "origin": "user_written"},
                      "divergence_answers": [{"dvid": "DV1", "options": ["close", "high"],
                                              "choice": {"value": "close", "origin": "user_written",
                                                         "suggested_value": ["close", "high"]}}],
                      "facts_ref": "facts/b1.json#a1/2025-07-14"}}


def _state(state_dir):
    files = sorted(p.relative_to(state_dir).as_posix() for p in state_dir.rglob("*")
                   if p.is_file() and p.parts[-2] in ("oplog", "shapes"))
    return {f: (state_dir / f).read_text() for f in files}


@pytest.mark.parametrize("mutate,needle", [
    (lambda c: c["ingredients"][2].pop("origin"), "origin 必填"),
    (lambda c: c["ingredients"][0]["choices"]["measure"].update(origin="suggested_edited",
                                                                 suggested_by="detector")
     or c["ingredients"][0]["choices"]["measure"].pop("suggested_value"), "suggested_value"),
    (lambda c: c["ingredients"][0].pop("said_first_match"), "said_first_match"),
    (lambda c: c["triggers"][0].update(suggested_by="own_library"), "root"),
    (lambda c: c["triggers"][0].update(suggested_by="llm"), "detector 或 own_library"),
    (lambda c: c["ingredients"][1].update(role="maybe"), "role"),
    (lambda c: c["ingredients"][2].pop("text"), "text"),
])
def test_origin_rules_reject(state_dir, mutate, needle):
    _batch(state_dir, "b1", [_ann("a1")])
    card = copy.deepcopy(CARD)
    mutate(card)
    with pytest.raises(shapes.ShapeValidationError) as ei:
        shapes.apply(_decision(_create(card)))
    assert needle in str(ei.value)
    assert _state(state_dir) == {}


def test_valid_decision_written_and_rendered(state_dir):
    _batch(state_dir, "b1", [_ann("a1")])
    written, touched = shapes.apply(_decision(_create(), _case()))
    assert touched == ["s001"] and len(written) == 2
    assert all(w["ts"] and w["op_id"] for w in written)
    card = shapes.load_card("s001")
    assert card["status"] == "draft" and card["current_version"] == 1
    v1 = card["versions"][0]
    assert v1["after_seeing_outcome"] is True and v1["list_kind"] == "bigmoves"
    assert v1["from_ann"] == ["a1"]
    assert card["cases"][0]["batch_id"] == "b1" and card["cases"][0]["version"] == 1
    text = shapes.render(card)
    assert "你自己说的" in text and "采纳了事实表的推荐" in text and "改过的会话推荐（原为 二峰收盘突破）" in text
    assert "【有它就不买】" in text and "F13 近期派发" in text
    assert (state_dir / "shapes" / "s001.json").read_text() == shapes.canonical(card)


def test_log_and_cards_consistent_and_verify(state_dir, capsys):
    _batch(state_dir, "b1", [_ann("a1"), _ann("a2")])
    _batch(state_dir, "b2", [_ann("a3")], visible=False, kind="contrast_blind")
    shapes.apply(_decision(_create(), _case()))
    shapes.apply(_decision(_create(name="回踩收回", from_ann=("a3",))))
    revised = copy.deepcopy(CARD)
    revised["triggers"].append({"trig_id": "t3", "term": "T1", **DET})
    shapes.apply(_decision({"act": "revise_shape", "target": {"shape_id": "s001"},
                            "value": {"card": revised, "change": "加触发 T1", "from_ann": ["a2"]}},
                           _case("s001", "a2", "t3")))
    shapes.apply(_decision({"act": "rename_shape", "target": {"shape_id": "s001"},
                            "value": {"name": {"value": "二峰突破", "origin": "user_written"}}},
                           {"act": "merge_shape", "target": {"shape_id": "s002"}, "value": {"into": "s001"}},
                           {"act": "pick", "target": {"ann_id": "a1", "field": "triggers"}, "value": "T5",
                            "actor": "user"}))
    c1, c2 = shapes.load_card("s001"), shapes.load_card("s002")
    assert c1["current_version"] == 2 and [c["version"] for c in c1["cases"]] == [1, 2]
    assert c1["name"]["value"] == "二峰突破" and c1["aliases"] == ["放量后连续突破两峰"]
    assert c2["status"] == "merged" and c2["merged_into"] == "s001"
    assert c2["versions"][0]["after_seeing_outcome"] is False          # 盲看批次推出来的
    assert len(oplog.read_all()) == 8                                   # pick 只进日志
    assert shapes.rebuild(verify=True) == []
    shapes.main(["rebuild", "--verify"])
    # 手改磁盘上的卡 → verify 失败
    p = state_dir / "shapes" / "s001.json"
    p.write_text(p.read_text().replace("二峰突破", "被手改了"))
    assert shapes.rebuild(verify=True) == ["s001: 磁盘上的卡与日志重算结果不一致"]
    with pytest.raises(SystemExit) as ei:
        shapes.main(["rebuild", "--verify"])
    assert ei.value.code == 1
    shapes.rebuild(verify=False)
    assert shapes.rebuild(verify=True) == []
    assert shapes.load_card("s001")["name"]["value"] == "二峰突破"


def test_decision_is_atomic(state_dir):
    _batch(state_dir, "b1", [_ann("a1")])
    shapes.apply(_decision(_create(), _case()))
    before = _state(state_dir)
    bad_case = _case("s001", "a1", "t9")                                 # 当前版本没有 t9
    with pytest.raises(shapes.ShapeValidationError):
        shapes.apply(_decision({"act": "set_status", "target": {"shape_id": "s001"},
                                "value": {"status": "confirmed"}}, bad_case))
    with pytest.raises(shapes.ShapeValidationError):
        shapes.apply(_decision(_create(from_ann=("nope",))))            # 引用不存在的标注
    with pytest.raises(shapes.ShapeValidationError):
        shapes.apply(_decision(_case("s009")))                          # 卡不存在
    assert _state(state_dir) == before


def test_v1_batch_counts_as_outcome_visible(state_dir):
    _batch(state_dir, "b0", [_ann("old", schema=1)], schema=1)
    shapes.apply(_decision(_create(from_ann=("old",)),
                           ctx={"list_id": "r0", "outcome_visible": False}))
    v = shapes.load_card("s001")["versions"][0]
    assert v["after_seeing_outcome"] is True and v["list_kind"] is None


def test_ledger_conditions_follow_own_library_root(state_dir, cw_env):
    cfg, _ = cw_env
    _batch(state_dir, "b1", [_ann("a1")])
    card = copy.deepcopy(CARD)
    card["ingredients"].append({"ing_id": "i4", "term": "F05", "role": "bonus",
                                "origin": "suggested_adopted", "suggested_by": "own_library",
                                "root": {"origin": "suggested_adopted", "suggested_by": "detector"}})
    shapes.apply(_decision(_create(card)))
    lists = root_dir(cfg) / "lists"
    lists.mkdir(parents=True)
    (lists / "r5-contrast.json").write_text(json.dumps({"list_id": "r5-contrast", "kind": "contrast"}))
    e = add_round(cfg, kind="rule", rule_id="s001", version="v1", source="shape:s001@v1",
                  change="首版", list_id="r5-contrast")
    conds = {c["cond_id"]: c for c in e["conditions"]}
    assert set(conds) == {"i1", "i2", "i3", "i4", "t1", "t2"}
    assert conds["i1"]["origin"] == "user_written" and conds["i1"]["has_said_first_match"]
    assert conds["i4"]["suggested_by"] == "own_library"
    assert (conds["i4"]["root_origin"], conds["i4"]["root_suggested_by"]) == ("suggested_adopted", "detector")
    assert conds["t1"]["kind"] == "trigger" and conds["t1"]["root_suggested_by"] == "detector"
    assert read_ledger()[-1]["conditions"] == e["conditions"]
    assert "你说的 3 / 事实表 3 / 会话 0" in render_ledger(read_ledger())
    with pytest.raises(FileNotFoundError):
        add_round(cfg, kind="rule", rule_id="s001", version="v2", source="shape:s001@v2",
                  change="x", list_id="r5-contrast")
    with pytest.raises(FileNotFoundError):
        add_round(cfg, kind="rule", rule_id="s009", version="v1", source="shape:s009@v1",
                  change="x", list_id="r5-contrast")


def test_pending_summary(state_dir, capsys):
    _batch(state_dir, "b1", [_ann("a1"), _ann("a2")])
    shapes.apply(_decision(_create(), _case()))
    text = shapes.render_pending()
    assert "s001" in text and "a2" in text and "a1 AAA" not in text
    assert "累计尝试 0 次" in text and "create_shape" in text
    shapes.main(["show", "--pending"])
    shapes.main(["show", "s001"])
    assert "放量后连续突破两峰" in capsys.readouterr().out


def test_cli_apply(state_dir, tmp_path, capsys):
    _batch(state_dir, "b1", [_ann("a1")])
    f = tmp_path / "decision.json"
    f.write_text(json.dumps(_decision(_create(), _case()), ensure_ascii=False))
    shapes.main(["apply", str(f)])
    out = capsys.readouterr().out
    assert "已写 2 条操作日志" in out and "s001" in out and "样本 1 个" in out
    bad = _decision(_create(from_ann=("nope",)))
    f.write_text(json.dumps(bad, ensure_ascii=False))
    with pytest.raises(SystemExit) as ei:
        shapes.main(["apply", str(f)])
    assert ei.value.code == 2 and len(oplog.read_all()) == 2
