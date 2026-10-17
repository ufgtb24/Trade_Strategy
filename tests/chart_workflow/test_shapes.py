"""形态卡与操作日志:卡只引用要素编号(角色写在卡上)、来源记录校验(用户来源和系统推荐分得开)、
日志与要素和卡一致(rebuild --verify)、决定文件原子性、after_seeing_outcome 由批次头推出、
账本按要素记每个条件的来源(要素是谁提的、角色是谁定的,own_library 递归到 root)、
复用旧卡只给 from_card、root 由工具从旧卡里抄(会话自带的 root 拒绝)、口径分歧答案是候选要素、
人话打印与待处理汇总(含可能重复的卡)。"""
import copy
import json

import pytest

from chart_workflow import elements, ledger, oplog, shapes, state
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


def el_op(as_, name, definition, *, user=True, needs=None):
    """建一条要素的操作(as_:同一决定文件里后面用 $<as_> 指它)。"""
    who = ({"origin": "user_written", "said_first_match": name} if user else dict(DET))
    v = {"name": {"value": name, "origin": "user_written" if user else "suggested_adopted",
                  **({} if user else {"suggested_by": "detector"})},
         **who, "definition": definition}
    if needs:
        v["needs"] = needs
    return {"act": "create_element", "target": {"as": as_}, "value": v}


PK1 = {"row": "F01", "value": "n_cleared", "cond": "at_least", "user_params": {"x": 1}}
PK1_HIGH = {"row": "F02", "value": "n_cleared", "cond": "at_least", "user_params": {"x": 1}}
DIST = {"row": "F13", "value": "events", "cond": "events_any", "user_params": {"bars": 20}}
ELEMS = [el_op("pk1", "按收盘至少越过一个峰", PK1),
         el_op("dist", "最近 20 根里有派发", DIST, user=False),
         el_op("flat", "突破前一个月横着走", None, needs="现有事实没有「横着走了多久」")]

CARD = {
    "ingredients": [
        {"ing_id": "i1", "element": "$pk1", "role": "must", "origin": "user_written",
         "said_first_match": "连续突破了两个峰值"},
        {"ing_id": "i2", "element": "$dist", "role": "must_not", **DET},
        {"ing_id": "i3", "element": "$flat", "role": "bonus", "origin": "user_written", "said_first_match": "用户说的"},
    ],
    "triggers": [{"trig_id": "t1", "term": "T5", **DET},
                 {"trig_id": "t2", "term": "custom", "text": "放量阳线过前高", "origin": "user_written",
                  "said_first_match": "放量阳线过前高的时候买"}],
    "story": {"value": "突破阻力后抛压被吃掉", "origin": "user_written"},
    "exit_pref": None,
}
CARD_IDS = copy.deepcopy(CARD)                    # 要素建好以后引用编号
for _i, _e in zip(CARD_IDS["ingredients"], ("E001", "E002", "E003")):
    _i["element"] = _e


def _decision(*ops, ctx=None):
    return {"schema": "chart_workflow.decision/1", "actor": "session", "surface": "chat",
            "ctx": ctx or {"list_id": "r1", "list_kind": "bigmoves", "outcome_visible": True},
            "ops": list(ops)}


def _create(card=CARD, name="放量后连续突破两峰", from_ann=("a1",)):
    return {"act": "create_shape",
            "value": {"name": {"value": name, "origin": "suggested_edited", "suggested_by": "session",
                               "suggested_value": "二峰收盘突破"},
                      "card": copy.deepcopy(card), "change": "新建", "from_ann": list(from_ann)}}


def _case(shape_id="$new", ann_id="a1", trig="t1", options=("E001", "E004"), choice="E001"):
    return {"act": "add_case", "target": {"shape_id": shape_id},
            "value": {"ann_id": ann_id, "buy_date": {"value": "2025-07-14", "origin": "user_written"},
                      "trigger_ref": trig, "shape_claim": {"value": "new", "origin": "user_written"},
                      "divergence_answers": [{"dvid": "DV1", "options": list(options),
                                              "choice": {"value": choice, "origin": "user_written",
                                                         "suggested_value": list(options)}}],
                      "facts_ref": "facts/b1.json#a1/2025-07-14"}}


def _base(state_dir, extra=()):
    """标注 a1 + 要素 E001..E003(E004 = 按最高价至少越过一个峰,给口径分歧当另一个候选)+ 卡 s001。"""
    _batch(state_dir, "b1", [_ann("a1")])
    return shapes.apply(_decision(*ELEMS, el_op("pk1h", "按最高价至少越过一个峰", PK1_HIGH),
                                  _create(), *extra))


def _state(state_dir):
    files = sorted(p.relative_to(state_dir).as_posix() for p in state_dir.rglob("*")
                   if p.is_file() and p.parts[-2] in ("oplog", "shapes", "elements"))
    return {f: (state_dir / f).read_text() for f in files}


@pytest.mark.parametrize("mutate,needle", [
    (lambda c: c["ingredients"][2].pop("origin"), "origin 必填"),
    (lambda c: c["ingredients"][0].update(term="F01"), "未知字段"),        # 旧格式:卡上不再写事实行编号
    (lambda c: c["ingredients"][0].update(choices={"measure": {"value": "close"}}), "未知字段"),
    (lambda c: c["ingredients"][0].update(element="E099"), "不在要素库里"),
    (lambda c: c["ingredients"][1].update(element="$pk1"), "只出现一次"),
    (lambda c: c["triggers"][0].update(suggested_by="own_library"), "from_card"),
    (lambda c: c["triggers"][0].update(suggested_by="own_library",
                                       from_card={"shape_id": "s001", "version": 1, "ref": "t1"},
                                       root={"origin": "user_written"}), "不要自带 root"),
    (lambda c: c["triggers"][0].update(from_card={"shape_id": "s001", "version": 1, "ref": "t1"}),
     "只有 suggested_by = own_library"),
    (lambda c: c["triggers"][0].update(suggested_by="llm"), "detector 或 own_library"),
    (lambda c: c["ingredients"][1].update(role="maybe"), "role"),
    (lambda c: c["triggers"][1].pop("text"), "text"),
    (lambda c: c["triggers"][0].update(origin="user_written"), "said_first_match"),
    (lambda c: c["triggers"][1].pop("said_first_match"), "said_first_match"),   # 手写触发记成用户说的
    (lambda c: c["ingredients"][2].pop("said_first_match"), "角色记成用户定的,要带 said_first_match"),
])
def test_origin_rules_reject(state_dir, mutate, needle):
    _batch(state_dir, "b1", [_ann("a1")])
    card = copy.deepcopy(CARD)
    mutate(card)
    with pytest.raises(shapes.ShapeValidationError) as ei:
        shapes.apply(_decision(*ELEMS, _create(card)))
    assert needle in str(ei.value)
    assert _state(state_dir) == {}                                       # 要素也一条都没写


def test_valid_decision_written_and_rendered(state_dir):
    written, touched = _base(state_dir, [_case()])
    assert touched == ["s001"] and len(written) == 6
    assert shapes.touched_elements(written) == ["E001", "E002", "E003", "E004"]
    assert all(w["ts"] and w["op_id"] for w in written)
    card = shapes.load_card("s001")
    ings = card["versions"][0]["card"]["ingredients"]
    assert [i["element"] for i in ings] == ["E001", "E002", "E003"]     # $<as> 换成了编号
    assert not any("term" in i or "choices" in i for i in ings)          # 卡上没有事实行与口径
    assert card["status"] == "draft" and card["current_version"] == 1
    v1 = card["versions"][0]
    assert v1["after_seeing_outcome"] is True and v1["list_kind"] == "bigmoves"
    assert card["cases"][0]["batch_id"] == "b1" and card["cases"][0]["version"] == 1
    assert card["cases"][0]["divergence_answers"][0]["options"] == ["E001", "E004"]
    for eid in ("E001", "E002", "E003", "E004"):
        assert (state_dir / "elements" / f"{eid}.json").exists()
    text = shapes.render(card)
    assert "E001「按收盘至少越过一个峰」：按收盘越过的峰个数至少 1（角色：你自己说的）" in text
    assert "E003「突破前一个月横着走」（待写代码）" in text
    assert "采纳了事实表的推荐" in text and "改过的会话推荐（原为 二峰收盘突破）" in text
    assert "【有它就不买】" in text and "E002「最近 20 根里有派发」" in text
    assert (state_dir / "shapes" / "s001.json").read_text() == shapes.canonical(card)


def test_same_element_different_roles_in_two_shapes(state_dir):
    _base(state_dir)
    card2 = {"ingredients": [{"ing_id": "j1", "element": "E002", "role": "bonus",
                              "origin": "user_written", "said_first_match": "用户说的"}], "triggers": []}
    shapes.apply(_decision(_create(card2, name="派发后再起")))
    roles = {sid: shapes.load_card(sid)["versions"][0]["card"]["ingredients"]
             for sid in ("s001", "s002")}
    assert [i["role"] for i in roles["s001"] if i["element"] == "E002"] == ["must_not"]
    assert [i["role"] for i in roles["s002"]] == ["bonus"]


@pytest.mark.parametrize("over,needle", [
    ({"options": ["E001"]}, "两条以上"),
    ({"options": ["E001", "E009"]}, "不在要素库里"),
    ({"choice": "E002"}, "从 options 里挑"),
])
def test_divergence_answer_picks_a_candidate_element(state_dir, over, needle):
    _base(state_dir)
    before = _state(state_dir)
    case = _case("s001", options=over.get("options", ("E001", "E004")), choice=over.get("choice", "E001"))
    with pytest.raises(shapes.ShapeValidationError) as ei:
        shapes.apply(_decision(case))
    assert needle in str(ei.value)
    assert _state(state_dir) == before


def test_log_and_cards_consistent_and_verify(state_dir, capsys):
    _batch(state_dir, "b1", [_ann("a1"), _ann("a2")])
    _batch(state_dir, "b2", [_ann("a3")], visible=False, kind="contrast_blind")
    shapes.apply(_decision(*ELEMS, el_op("pk1h", "按最高价至少越过一个峰", PK1_HIGH), _create(), _case()))
    shapes.apply(_decision(_create(CARD_IDS, name="回踩收回", from_ann=("a3",))))
    revised = copy.deepcopy(CARD_IDS)
    revised["triggers"].append({"trig_id": "t3", "term": "T1", **DET})
    shapes.apply(_decision({"act": "revise_shape", "target": {"shape_id": "s001"},
                            "value": {"card": revised, "change": "加触发 T1", "from_ann": ["a2"]}},
                           _case("s001", "a2", "t3")))
    shapes.apply(_decision({"act": "rename_shape", "target": {"shape_id": "s001"},
                            "value": {"name": {"value": "二峰突破", "origin": "user_written"}}},
                           {"act": "merge_shape", "target": {"shape_id": "s002"}, "value": {"into": "s001"}},
                           {"act": "alias_element", "target": {"element_id": "E001"},
                            "value": {"text": "收盘站上前高"}, "actor": "user"},
                           {"act": "pick", "target": {"ann_id": "a1", "field": "triggers"}, "value": "T5",
                            "actor": "user"}))
    c1, c2 = shapes.load_card("s001"), shapes.load_card("s002")
    assert c1["current_version"] == 2 and [c["version"] for c in c1["cases"]] == [1, 2]
    assert c1["name"]["value"] == "二峰突破" and c1["aliases"] == ["放量后连续突破两峰"]
    assert c2["status"] == "merged" and c2["merged_into"] == "s001"
    assert c2["versions"][0]["after_seeing_outcome"] is False          # 盲看批次推出来的
    assert len(oplog.read_all()) == 13                                  # pick 只进日志
    assert shapes.rebuild(verify=True) == []
    shapes.main(["rebuild", "--verify"])
    # 手改磁盘上的卡 / 要素 → verify 失败
    p = state_dir / "shapes" / "s001.json"
    p.write_text(p.read_text().replace("二峰突破", "被手改了"))
    e = state_dir / "elements" / "E001.json"
    e.write_text(e.read_text().replace("收盘站上前高", "被手改了"))
    assert shapes.rebuild(verify=True) == ["E001: 磁盘上的要素与日志重算结果不一致",
                                           "s001: 磁盘上的卡与日志重算结果不一致"]
    # 要素文件进水位:删掉一个就停下(像切到了旧分支);显式重置水位后 verify 报缺、rebuild 补回
    (state_dir / "elements" / "E004.json").unlink()
    with pytest.raises(state.StateRootRegressed, match="E004.json"):
        shapes.rebuild(verify=True)
    state.reset_watermark(state_dir, "测试:删了一个要素文件")
    assert "E004: 磁盘上没有这条要素" in shapes.rebuild(verify=True)
    with pytest.raises(SystemExit) as ei:
        shapes.main(["rebuild", "--verify"])
    assert ei.value.code == 1
    shapes.rebuild(verify=False)
    assert shapes.rebuild(verify=True) == []
    assert shapes.load_card("s001")["name"]["value"] == "二峰突破"


def test_decision_is_atomic(state_dir):
    _base(state_dir, [_case()])
    before = _state(state_dir)
    bad_case = _case("s001", "a1", "t9")                                 # 当前版本没有 t9
    with pytest.raises(shapes.ShapeValidationError):
        shapes.apply(_decision({"act": "set_status", "target": {"shape_id": "s001"},
                                "value": {"status": "confirmed"}}, bad_case))
    with pytest.raises(shapes.ShapeValidationError):
        shapes.apply(_decision(_create(CARD_IDS, from_ann=("nope",))))   # 引用不存在的标注
    with pytest.raises(shapes.ShapeValidationError):
        shapes.apply(_decision(_case("s009")))                          # 卡不存在
    with pytest.raises(shapes.ShapeValidationError):                    # 好的建要素 + 坏的卡:都不写
        shapes.apply(_decision(el_op("v3", "买点当天放量", {"row": "F07", "value": "vr", "cond": "at_least",
                                                              "default_params": {"x": 3.0}}),
                               _create({"ingredients": [{"ing_id": "i1", "element": "$v3", "role": "must"}],
                                        "triggers": []})))
    assert _state(state_dir) == before


def test_v1_batch_counts_as_outcome_visible(state_dir):
    _batch(state_dir, "b0", [_ann("old", schema=1)], schema=1)
    shapes.apply(_decision(*ELEMS, _create(from_ann=("old",)),
                           ctx={"list_id": "r0", "outcome_visible": False}))
    v = shapes.load_card("s001")["versions"][0]
    assert v["after_seeing_outcome"] is True and v["list_kind"] is None


@pytest.fixture(autouse=True)
def _stub_rule_check(monkeypatch):
    """本文件只测账本按要素记来源:账本自己跑的规则核对、规则和清单的指纹绑定都换成桩(这里的清单不记规则
    指纹,桩规则的指纹也是空;真的核对与绑定见 test_rulecheck.py)。"""
    from chart_workflow import rulecheck, rules
    monkeypatch.setattr(rulecheck, "check_rule_against_shape",
                        lambda source, cfg, **kw: {"source": source, "declared": [], "stub": True})
    monkeypatch.setattr(rules, "rule_identity", lambda *a, **kw: None)


def _reuse(ing_id, element, ref, shape_id="s001", version=1, **extra):
    return {"ing_id": ing_id, "element": element, "role": "bonus", "origin": "suggested_adopted",
            "suggested_by": "own_library",
            "from_card": {"shape_id": shape_id, "version": version, "ref": ref}, **extra}


def test_ledger_conditions_by_element(state_dir, cw_env):
    """账本按要素记:要素本身是谁提的、它读的事实行是谁提的角度、角色是谁定的(own_library 递归到底)。"""
    cfg, _ = cw_env
    _base(state_dir)                              # s001:i1 用户提的 E001 用户定角色;i2 事实表推荐的 E002
    card2 = {"ingredients": [_reuse("j1", "E002", "i2"), _reuse("j2", "E001", "i1")], "triggers": []}
    shapes.apply(_decision(_create(card2, name="复用")))         # s002 从 s001 复用两条
    s2 = shapes.load_card("s002")["versions"][0]["card"]["ingredients"]
    # root 由工具从旧卡抄:j1 → 事实表推荐,j2 → 用户自己说的(带当初的原话)
    assert s2[0]["root"] == {"origin": "suggested_adopted", "suggested_by": "detector"}
    assert s2[1]["root"] == {"origin": "user_written", "said_first_match": "连续突破了两个峰值"}
    card3 = {"ingredients": [_reuse("k1", "E002", "j1", shape_id="s002")], "triggers": []}
    shapes.apply(_decision(_create(card3, name="再复用")))        # 复用的复用:root 一直到底
    assert shapes.load_card("s003")["versions"][0]["card"]["ingredients"][0]["root"] == \
        {"origin": "suggested_adopted", "suggested_by": "detector"}

    lists = root_dir(cfg) / "lists"
    lists.mkdir(parents=True)
    (lists / "r5-contrast.json").write_text(json.dumps({"list_id": "r5-contrast", "kind": "contrast"}))
    e = add_round(cfg, kind="rule", rule_id="s001", version="v1", source="shape:s001@v1", rule="stub.py",
                  change="首版", list_id="r5-contrast")
    conds = {c["cond_id"]: c for c in e["conditions"]}
    assert set(conds) == {"i1", "i2", "i3", "t1", "t2"}
    i1, i2, i3 = conds["i1"], conds["i2"], conds["i3"]
    assert (i1["element"], i1["element_resolved"], i1["element_version"]) == ("E001", "E001", 1)
    assert i1["element_origin"] == "user_written" and i1["element_has_said"]
    assert i1["fact_rows"] == ["F01"] and i1["angle_by"] == "preset" and i1["angle_ops"] == []
    assert i1["origin"] == "user_written" and i1["has_said_first_match"]          # 角色是用户定的
    assert (i2["element_origin"], i2["element_suggested_by"], i2["role"]) == \
        ("suggested_adopted", "detector", "must_not")
    assert i3["fact_rows"] == [] and i3["angle_by"] is None                      # 待写代码
    assert conds["t1"]["kind"] == "trigger" and conds["t1"]["root_suggested_by"] == "detector"
    assert read_ledger()[-1]["conditions"] == e["conditions"]
    assert "要素 你说的 2 / 你提的角度 0 / 事实表 1 / 会话 0；角色你定的 2/3；触发 你说的 1 / 事实表 1" \
        in render_ledger(read_ledger())
    (lists / "r6-contrast.json").write_text(json.dumps({"list_id": "r6-contrast", "kind": "contrast"}))
    e = add_round(cfg, kind="rule", rule_id="s003", version="v1", source="shape:s003@v1", rule="stub.py",
                  change="复用", list_id="r6-contrast")
    c = e["conditions"][0]
    assert c["suggested_by"] == "own_library" and c["element"] == "E002"
    assert (c["root_origin"], c["root_suggested_by"]) == ("suggested_adopted", "detector")
    # 要素是事实表推荐的、角色是用户定的:两件事分开记
    shapes.apply(_decision(_create({"ingredients": [{"ing_id": "m1", "element": "E002", "role": "bonus",
                                                     "origin": "user_written", "said_first_match": "用户说的"}], "triggers": []},
                                   name="派发也算加分")))
    (lists / "r7-contrast.json").write_text(json.dumps({"list_id": "r7-contrast", "kind": "contrast"}))
    m1 = add_round(cfg, kind="rule", rule_id="s004", version="v1", source="shape:s004@v1", rule="stub.py",
                   change="角色用户定", list_id="r7-contrast")["conditions"][0]
    assert (m1["element_origin"], m1["element_suggested_by"]) == ("suggested_adopted", "detector")
    assert (m1["origin"], m1["root_origin"]) == ("user_written", "user_written")
    with pytest.raises(FileNotFoundError):
        add_round(cfg, kind="rule", rule_id="s001", version="v2", source="shape:s001@v2", rule="stub.py",
                  change="x", list_id="r5-contrast")
    with pytest.raises(FileNotFoundError):
        add_round(cfg, kind="rule", rule_id="s009", version="v1", source="shape:s009@v1", rule="stub.py",
                  change="x", list_id="r5-contrast")


def test_ledger_marks_user_proposed_angle(state_dir, cw_env, monkeypatch):
    """要素读的事实行是用户提的角度:哪怕要素是事实表推荐的,账本记 angle_by = user,不算系统推荐。
    出处指的「提出角度」日志条目要真在、且排在要素建立之前才算。"""
    from chart_workflow import facts
    cfg, _ = cw_env
    oplog.append([{"act": "propose_fact", "actor": "user", "surface": "chat", "op_id": "op-dist",
                   "value": {"said": "看最近一个月有没有派发"}}])
    _base(state_dir)
    src = {"kind": "user", "date": "2026-10-17", "said": "看最近一个月有没有派发", "op_id": "op-dist"}
    monkeypatch.setitem(facts.ROWS, "F13", {**facts.ROWS["F13"], "source": src})
    lists = root_dir(cfg) / "lists"
    lists.mkdir(parents=True)
    (lists / "r5-contrast.json").write_text(json.dumps({"list_id": "r5-contrast", "kind": "contrast"}))
    e = add_round(cfg, kind="rule", rule_id="s001", version="v1", source="shape:s001@v1", rule="stub.py",
                  change="首版", list_id="r5-contrast")
    i2 = next(c for c in e["conditions"] if c["cond_id"] == "i2")
    assert i2["element_suggested_by"] == "detector"
    assert (i2["angle_by"], i2["angle_ops"]) == ("user", ["op-dist"])
    assert "要素 你说的 2 / 你提的角度 1 / 事实表 0" in render_ledger(read_ledger())
    assert "你提的角度" in elements.render(elements.load_all()["E002"])


@pytest.mark.parametrize("when", ["missing", "after", "not_propose"])
def test_user_angle_needs_earlier_propose_entry(state_dir, cw_env, monkeypatch, when):
    """出处指的日志条目不在、排在要素建立之后、或不是「提出角度」:都不算你提的角度,按预设记。"""
    from chart_workflow import facts
    cfg, _ = cw_env
    entry = {"act": "propose_fact" if when != "not_propose" else "type", "actor": "user", "surface": "chat",
             "op_id": "op-dist", "value": {"said": "看最近一个月有没有派发"}}
    if when == "not_propose":
        oplog.append([entry])
    _base(state_dir)
    if when == "after":
        oplog.append([entry])
    src = {"kind": "user", "date": "2026-10-17", "said": "看最近一个月有没有派发", "op_id": "op-dist"}
    monkeypatch.setitem(facts.ROWS, "F13", {**facts.ROWS["F13"], "source": src})
    lists = root_dir(cfg) / "lists"
    lists.mkdir(parents=True)
    (lists / "r5-contrast.json").write_text(json.dumps({"list_id": "r5-contrast", "kind": "contrast"}))
    e = add_round(cfg, kind="rule", rule_id="s001", version="v1", source="shape:s001@v1", rule="stub.py",
                  change="首版", list_id="r5-contrast")
    i2 = next(c for c in e["conditions"] if c["cond_id"] == "i2")
    assert (i2["angle_by"], i2["angle_ops"]) == ("preset", [])
    assert "你提的角度 0" in render_ledger(read_ledger())


@pytest.mark.parametrize("ing,needle", [
    (_reuse("j1", "E004", "i2"), "旧卡那一条引用的是 E002"),       # 引用的要素对不上
    (_reuse("j1", "E002", "i9"), "没有 'i9'"),
    (_reuse("j1", "E002", "i2", version=7), "没有版本 v7"),
    (_reuse("j1", "E002", "i2", shape_id="s042"), "旧卡 s042 不存在"),
    # 洗白路径:会话自己填 root 说「用户自己写的」→ 拒绝
    (_reuse("j1", "E002", "i2", root={"origin": "user_written"}), "不要自带 root"),
])
def test_own_library_reuse_checked_against_old_card(state_dir, ing, needle):
    _base(state_dir)
    before = _state(state_dir)
    with pytest.raises(shapes.ShapeValidationError) as ei:
        shapes.apply(_decision(_create({"ingredients": [ing], "triggers": []}, name="复用")))
    assert needle in str(ei.value)
    assert _state(state_dir) == before


FLAT = {"row": "F11", "value": "segments", "cond": "events_any", "user_params": {"bars": 20}}


def test_own_library_reuse_follows_element_merge(state_dir):
    """旧卡引用的待写代码要素后来写成计算、并进了定义相同的另一条:复用时引用并入的那条,认作同一个东西。"""
    _base(state_dir)                               # s001 的 i3 引用待写代码的 E003
    shapes.apply(_decision(el_op("plat", "最近 20 根里有平台段", FLAT, user=False),
                           {"act": "merge_element", "target": {"element_id": "E003"},
                            "value": {"into": "$plat", "reason": "用户说是同一个意思", "definition": FLAT,
                                      "origin": "suggested_adopted", "suggested_by": "session"},
                            "actor": "user"}))
    shapes.apply(_decision(_create({"ingredients": [_reuse("j1", "E005", "i3")], "triggers": []},
                                   name="复用")))
    j1 = shapes.load_card("s002")["versions"][0]["card"]["ingredients"][0]
    assert j1["root"] == {"origin": "user_written", "said_first_match": "用户说的"}


def test_own_library_reuse_needs_same_kind(state_dir):
    """复用旧卡抄来源只能从同一类的项抄:故事从故事抄,不能从触发或要素项抄。"""
    _base(state_dir)
    story = {"value": "突破后抛压被吃掉", "origin": "suggested_adopted", "suggested_by": "own_library",
             "from_card": {"shape_id": "s001", "version": 1, "ref": "t2"}}
    with pytest.raises(shapes.ShapeValidationError, match="只能从旧卡同一类的项复用来源.*story.*trigger"):
        shapes.apply(_decision(_create({"ingredients": [], "triggers": [], "story": story}, name="复用")))
    story["from_card"]["ref"] = "story"
    shapes.apply(_decision(_create({"ingredients": [], "triggers": [], "story": story}, name="复用")))
    assert shapes.load_card("s002")["versions"][0]["card"]["story"]["root"] == {"origin": "user_written"}


def test_ledger_unchanged_by_merge(state_dir):
    """合并之后,账本给旧卡那一版记的要素项不变:来源、版本、读的事实行都按卡这一版建立时那条要素算。"""
    _base(state_dir)                               # s001 的 i3 引用待写代码的 E003(用户说的)
    before = ledger.shape_conditions("shape:s001@v1")
    shapes.apply(_decision(el_op("plat", "最近 20 根里有平台段", FLAT, user=False),
                           {"act": "merge_element", "target": {"element_id": "E003"},
                            "value": {"into": "$plat", "reason": "用户说是同一个意思", "definition": FLAT,
                                      "origin": "suggested_adopted", "suggested_by": "session"},
                            "actor": "user"}))
    after = ledger.shape_conditions("shape:s001@v1")
    assert after[2].pop("element_resolved") == "E005" and before[2].pop("element_resolved") == "E003"
    assert after == before
    i3 = after[2]
    assert (i3["element"], i3["element_version"], i3["element_origin"]) == ("E003", 1, "user_written")
    assert (i3["fact_rows"], i3["angle_by"], i3["definition_origin"]) == ([], None, None)
    # 新建的卡版本引用 E003:记的是写成计算的那一版,定义是谁定的跟着记(会话定的)
    shapes.apply(_decision(_create({"ingredients": [{"ing_id": "j1", "element": "E005", "role": "must",
                                                     "origin": "user_written", "said_first_match": "用户说的"}], "triggers": []}, name="平台")))
    j1 = ledger.shape_conditions("shape:s002@v1")[0]
    assert (j1["element_origin"], j1["element_suggested_by"], j1["fact_rows"]) == \
        ("suggested_adopted", "detector", ["F11"])


def test_ledger_records_who_wrote_pending_definition(state_dir):
    """待写代码的要素写成计算时记下定义是谁定的;新卡引用写成计算的那一版,账本记这个来源;
    旧卡那一版仍记当时待写代码。"""
    _base(state_dir)                               # E003 待写代码(用户说的)
    shapes.apply(_decision({"act": "revise_element", "target": {"element_id": "E003"},
                            "value": {"definition": FLAT, "change": "写成计算", "origin": "suggested_adopted",
                                      "suggested_by": "session"}}))
    shapes.apply(_decision(_create({"ingredients": [{"ing_id": "j1", "element": "E003", "role": "must",
                                                     "origin": "user_written", "said_first_match": "用户说的"}], "triggers": []}, name="平台")))
    j1 = ledger.shape_conditions("shape:s002@v1")[0]
    assert (j1["element_origin"], j1["element_version"], j1["fact_rows"]) == ("user_written", 2, ["F11"])
    assert (j1["definition_origin"], j1["definition_suggested_by"]) == ("suggested_adopted", "session")
    i3 = ledger.shape_conditions("shape:s001@v1")[2]
    assert (i3["element_version"], i3["definition_origin"], i3["fact_rows"]) == (1, None, [])


VOLD = {"row": "F07", "value": "vr", "cond": "at_least", "default_params": {"x": 3.0}}


def test_card_version_keeps_element_version(state_dir):
    """要素修订后,旧卡那一版仍按当时的要素版本判定、打印、记账;卡的新版本记新的版本号。"""
    _batch(state_dir, "b1", [_ann("a1")])
    vol_ing = {"ingredients": [{"ing_id": "v1", "element": "$vol", "role": "must", "origin": "user_written",
                                "said_first_match": "用户说的"}],
               "triggers": []}
    shapes.apply(_decision(el_op("vol", "放量", VOLD, user=False), _create(vol_ing, name="放量")))
    shapes.apply(_decision({"act": "revise_element", "target": {"element_id": "E001"},
                            "value": {"definition": {**VOLD, "default_params": {"x": 2.5}},
                                      "change": "默认倍数改 2.5"}}))
    card = shapes.load_card("s001")
    assert card["versions"][0]["card"]["ingredients"][0]["element_version"] == 1
    assert ledger.shape_conditions("shape:s001@v1")[0]["element_version"] == 1
    assert "3" in shapes.render(card) and "2.5" not in shapes.render(card)
    snap = {"results": [{"ann_id": "a1", "facts": {"symbol": "AAA", "buy_date": "2025-07-14",
                                                   "rows": [{"fid": "F07", "value": {"vr": 2.8}}]}}]}
    els = elements.load_all()
    assert "否" in elements.render_eval(snap, els, card=card)                   # 按 v1:至少 3 倍
    assert elements.evaluate_element(els, "E001", snap["results"][0]["facts"])[0] == "yes"   # 当前版本
    ids = copy.deepcopy(vol_ing)
    ids["ingredients"][0]["element"] = "E001"
    shapes.apply(_decision({"act": "revise_shape", "target": {"shape_id": "s001"},
                            "value": {"card": ids, "change": "跟上要素新版本"}}))
    card = shapes.load_card("s001")
    assert card["versions"][1]["card"]["ingredients"][0]["element_version"] == 2
    assert "是" in elements.render_eval(snap, els, card=card).split("\n")[1]
    assert ledger.shape_conditions("shape:s001@v2")[0]["element_version"] == 2
    with pytest.raises(shapes.ShapeValidationError, match="未知字段"):           # 版本号由工具填
        bad = copy.deepcopy(ids)
        bad["ingredients"][0]["element_version"] = 1
        shapes.apply(_decision({"act": "revise_shape", "target": {"shape_id": "s001"},
                                "value": {"card": bad, "change": "自己填版本"}}))


def test_decision_file_cannot_carry_ts_op_id_or_element_from_card(state_dir):
    """决定文件不能自带时间和编号;要素不带旧卡指引(要素按编号复用,不抄来源)。"""
    _batch(state_dir, "b1", [_ann("a1")])
    for extra in ({"op_id": "20260101T000000-deadbeef"}, {"ts": "2026-01-01T00:00:00"}):
        with pytest.raises(shapes.ShapeValidationError, match="不要自带 ts / op_id"):
            shapes.apply(_decision({**ELEMS[0], **extra}))
    op = copy.deepcopy(ELEMS[1])
    op["value"]["from_card"] = {"shape_id": "s001", "version": 1, "ref": "i2"}
    with pytest.raises(shapes.ShapeValidationError, match="要素不带 from_card"):
        shapes.apply(_decision(op))
    assert oplog.read_all() == []


def _raw_append(state_dir, entry):
    """绕开工具,直接往日志文件末尾加一行(模拟手写日志)。"""
    f = sorted((state_dir / "oplog").glob("*.jsonl"))[-1]
    with f.open("a") as fh:
        fh.write(json.dumps(entry, ensure_ascii=False) + "\n")


def test_direct_log_writes_of_elements_and_cards_rejected(state_dir):
    """直接写操作日志:入口拒绝要素与卡两类操作;手写进日志文件的,重算时重新走决定文件的校验被抓出来。"""
    _base(state_dir)
    full = {k: None for k in oplog.FIELDS}
    for op in (ELEMS[0], _create(CARD_IDS, name="另一张")):
        with pytest.raises(ValueError, match="只能经决定文件写"):
            oplog.append([{**full, **op, "actor": "session", "surface": "chat", "ctx": {}}])
    assert shapes.rebuild(verify=True) == []
    # 要素记成用户说的,不带原话
    bad_el = {**full, **copy.deepcopy(ELEMS[0]), "actor": "session", "surface": "chat",
              "ctx": {"list_id": "r1"}, "ts": "2026-10-17T00:00:00", "op_id": "20261017T000000-aaaaaaaa",
              "rules_version": oplog.RULES_VERSION}
    bad_el["target"] = {"element_id": "E009"}
    bad_el["value"]["definition"] = {"row": "F13", "value": "events", "cond": "events_any",
                                     "user_params": {"bars": 30}}
    bad_el["value"].pop("said_first_match")
    _raw_append(state_dir, bad_el)
    before = _state(state_dir)
    with pytest.raises(shapes.ShapeValidationError, match="said_first_match"):
        shapes.rebuild(verify=False)
    assert _state(state_dir) == before                                   # 不覆盖磁盘
    assert any("said_first_match" in m for m in shapes.rebuild(verify=True))


def test_tampered_tool_filled_fields_caught(state_dir):
    """工具补的字段(卡上的要素版本号、复用抄来的来源)被手改:重新校验补全后和日志对不上。"""
    _base(state_dir)
    card2 = {"ingredients": [_reuse("j1", "E002", "i2")], "triggers": []}
    shapes.apply(_decision(_create(card2, name="复用")))
    f = sorted((state_dir / "oplog").glob("*.jsonl"))[-1]
    lines = f.read_text().splitlines()
    last = json.loads(lines[-1])
    last["value"]["card"]["ingredients"][0]["root"] = {"origin": "user_written", "said_first_match": "我说的"}
    _raw_append(state_dir, {**last, "op_id": "20261017T000000-bbbbbbbb", "target": {"shape_id": "s003"}})
    assert any("和日志里记的不一样" in m for m in shapes.rebuild(verify=True))


def _strip_versions(rows):
    for r in rows:
        if r["act"] == "create_shape":
            for ing in r["value"]["card"]["ingredients"]:
                ing.pop("element_version")


def _rewrite_log(state_dir, rows):
    f = sorted((state_dir / "oplog").glob("*.jsonl"))[-1]
    f.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows))
    state.reset_watermark(state_dir, "测试:改写日志")


def test_old_cards_without_element_version_still_revalidate(state_dir):
    """第 1 版(没有校验版本号的旧条目)的卡可以没记要素版本号:照常重新校验通过、照常打印。"""
    _base(state_dir)
    f = sorted((state_dir / "oplog").glob("*.jsonl"))[-1]
    rows = [json.loads(x) for x in f.read_text().splitlines()]
    _strip_versions(rows)
    for r in rows:
        r.pop("rules_version")
    _rewrite_log(state_dir, rows)
    assert shapes.rebuild(verify=False) == []
    assert "按收盘至少越过一个峰" in shapes.render(shapes.load_card("s001"))


@pytest.mark.parametrize("when,needle", [
    ("v2", "和日志里记的不一样"),                                  # 第 2 版的卡不记要素版本号
    ("unversioned_after_v2", "校验版本号是第 1 版,比前面的条目"),  # 去掉版本号冒充旧条目
    ("newer", "校验版本号 9 不认识"),
])
def test_missing_element_version_only_forgiven_for_old_entries(state_dir, when, needle):
    """只有第 1 版的条目可以不记要素版本号;排在第 2 版条目后面却没有版本号的不算旧条目;版本号比工具新的不认。"""
    _base(state_dir)
    f = sorted((state_dir / "oplog").glob("*.jsonl"))[-1]
    rows = [json.loads(x) for x in f.read_text().splitlines()]
    _strip_versions(rows)
    for r in rows:
        if r["act"] == "create_shape" and when != "v2":
            r.pop("rules_version")
            if when == "newer":
                r["rules_version"] = 9
    _rewrite_log(state_dir, rows)
    with pytest.raises(shapes.ShapeValidationError, match=needle):
        shapes.rebuild(verify=False)


def _v1_log(state_dir, *ops):
    """按第 1 版的规则写一批操作,再去掉校验版本号(模拟收紧规则之前、旧工具写的日志)。"""
    _batch(state_dir, "b1", [_ann("a1")])
    with oplog.rules_at(1):
        shapes.apply(_decision(*ops))
    f = sorted((state_dir / "oplog").glob("*.jsonl"))[-1]
    rows = [json.loads(x) for x in f.read_text().splitlines()]
    for r in rows:
        r.pop("rules_version")
    _rewrite_log(state_dir, rows)
    return rows


OLD_OK = [el_op("d150", "最近 150 根里有派发", {**DIST, "user_params": {"bars": 150}}),
          el_op("far", "最早越过的峰离买点 10 到 150 根",
                {"row": "F04", "value": "bars", "cond": "between", "variant": "close",
                 "user_params": {"lo": 10, "hi": 150}}),
          {"act": "create_shape", "value": {
              "name": {"value": "老卡", "origin": "user_written"}, "change": "新建", "from_ann": ["a1"],
              "card": {"ingredients": [{"ing_id": "i1", "element": "$d150", "role": "must_not",
                                        "origin": "user_written"}],          # 角色记成用户定的,当时不要原话
                       "triggers": [{"trig_id": "t1", "term": "T5", **DET}], "story": None, "exit_pref": None}}}]


def test_entries_legal_when_written_do_not_lock_tools(state_dir, capsys):
    """第 1 版规则下能写进去的三种条目(最近 150 根、10~150 根、角色不带原话),现在的规则都不再允许:
    只提示、不拦——重算、正常写入、账本取数照常;逐条提示只在 rebuild --verify 里。"""
    _v1_log(state_dir, *OLD_OK)
    assert shapes.rebuild(verify=True) == []
    err = capsys.readouterr().err
    assert err.count("写入时按第 1 版规则合法,现在的规则不再允许") == 3
    assert "不比事实表窗口短" in err and "按现在的规则补全出来的样子不同" in err and "said_first_match" in err
    shapes.apply(_decision(el_op("pk1", "按收盘至少越过一个峰", PK1)))
    assert "操作日志里有 3 条是按旧版校验规则写的" in capsys.readouterr().err
    conds = ledger.shape_conditions("shape:s001@v1")
    assert [(c.get("element"), c["origin"], c["has_said_first_match"]) for c in conds] == \
        [("E001", "user_written", False), (None, "suggested_adopted", False)]
    assert oplog.read_all()[-1]["rules_version"] == oplog.RULES_VERSION


@pytest.mark.parametrize("tamper", [
    lambda rows: rows[0]["value"].pop("said_first_match"),                  # 手改掉了用户原话
    lambda rows: rows[1]["value"]["definition"]["user_params"].update(lo=1, hi=30),   # 第 1 版要求写成 at_most
])
def test_old_entry_tampered_against_its_own_version_blocks(state_dir, tamper):
    """旧条目连自己那一版的规则都不合格:说成可能被改过,拦。"""
    rows = _v1_log(state_dir, *OLD_OK)
    tamper(rows)
    _rewrite_log(state_dir, rows)
    with pytest.raises(shapes.ShapeValidationError, match="连写入时的第 1 版规则都不合格,可能被改过"):
        shapes.apply(_decision(el_op("pk1", "按收盘至少越过一个峰", PK1)))


def test_decision_file_cannot_carry_rules_version(state_dir):
    _batch(state_dir, "b1", [_ann("a1")])
    with pytest.raises(shapes.ShapeValidationError, match="不要自带 ts / op_id / rules_version"):
        shapes.apply(_decision({**el_op("pk1", "按收盘至少越过一个峰", PK1), "rules_version": 1}))


def test_bad_log_blocks_normal_write_and_ledger(state_dir):
    """日志里混进了绕开决定文件的条目:之后正常写入一律拒绝(不能借一次正常写入把它重算落盘),账本也不取数。"""
    _base(state_dir)
    full = {k: None for k in oplog.FIELDS}
    bad_el = {**full, **copy.deepcopy(ELEMS[0]), "actor": "session", "surface": "chat",
              "ctx": {"list_id": "r1"}, "ts": "2026-10-17T23:00:00", "op_id": "20261017T230000-aaaaaaaa",
              "rules_version": oplog.RULES_VERSION}
    bad_el["target"] = {"element_id": "E009"}
    bad_el["value"]["definition"] = {"row": "F13", "value": "events", "cond": "events_any", "user_params": {"bars": 30}}
    bad_el["value"].pop("said_first_match")
    _raw_append(state_dir, bad_el)
    with pytest.raises(shapes.ShapeValidationError, match="可能被改过的条目"):
        shapes.apply(_decision({"act": "alias_element", "target": {"element_id": "E009"}, "value": {"text": "x"}}))
    assert not (state_dir / "elements" / "E009.json").exists()
    with pytest.raises(ValueError, match="可能被改过的条目"):
        ledger.shape_conditions("shape:s001@v1")


def test_ledger_reads_log_not_disk(state_dir):
    """账本按日志重算的卡与要素取数:手改磁盘上的卡文件不影响账本。"""
    _base(state_dir)
    before = ledger.shape_conditions("shape:s001@v1")
    p = state_dir / "shapes" / "s001.json"
    p.write_text(p.read_text().replace('"suggested_adopted"', '"user_written"'))
    assert ledger.shape_conditions("shape:s001@v1") == before


def test_pending_summary_and_possible_duplicates(state_dir, capsys):
    _batch(state_dir, "b1", [_ann("a1"), _ann("a2")])
    shapes.apply(_decision(*ELEMS, el_op("pk1h", "按最高价至少越过一个峰", PK1_HIGH), _create(), _case()))
    text = shapes.render_pending()
    assert "s001" in text and "a2" in text and "a1 AAA" not in text
    assert "累计尝试 0 次" in text and "create_shape" in text
    assert "待写代码 E003「突破前一个月横着走」（待写代码）：现有事实没有「横着走了多久」" in text
    assert "在用 3 条，待写代码 1 条，已合并 0 条" in text
    assert "可能重复" not in text
    shapes.apply(_decision(_create(CARD_IDS, name="另一个说法")))     # 要素、角色、触发全同
    other = copy.deepcopy(CARD_IDS)
    other["ingredients"][0]["role"] = "bonus"                          # 角色不同:不算重复
    shapes.apply(_decision(_create(other, name="角色不同")))
    text = shapes.render_pending()
    assert "可能重复" in text and "  s001、s002" in text and "s003" not in text.split("可能重复")[1].split("\n【")[0]
    assert shapes.load_card("s002")["status"] == "draft"               # 只提示,不合并
    shapes.main(["show", "--pending"])
    shapes.main(["show", "s001"])
    assert "放量后连续突破两峰" in capsys.readouterr().out


def test_cli_apply(state_dir, tmp_path, capsys):
    _batch(state_dir, "b1", [_ann("a1")])
    f = tmp_path / "decision.json"
    f.write_text(json.dumps(_decision(*ELEMS, el_op("pk1h", "按最高价至少越过一个峰", PK1_HIGH),
                                      _create(), _case()), ensure_ascii=False))
    shapes.main(["apply", str(f)])
    out = capsys.readouterr().out
    assert "已写 6 条操作日志" in out and "s001" in out and "样本 1 个" in out
    assert "E001 「按收盘至少越过一个峰」  在用" in out
    bad = _decision(_create(CARD_IDS, from_ann=("nope",)))
    f.write_text(json.dumps(bad, ensure_ascii=False))
    with pytest.raises(SystemExit) as ei:
        shapes.main(["apply", str(f)])
    assert ei.value.code == 2 and len(oplog.read_all()) == 6
