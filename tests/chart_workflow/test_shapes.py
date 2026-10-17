"""形态卡与操作日志:卡只引用要素编号(角色写在卡上)、来源记录校验(用户来源和系统推荐分得开)、
日志与要素和卡一致(rebuild --verify)、决定文件原子性、after_seeing_outcome 由批次头推出、
账本按要素记每个条件的来源(要素是谁提的、角色是谁定的,own_library 递归到 root)、
复用旧卡只给 from_card、root 由工具从旧卡里抄(会话自带的 root 拒绝)、口径分歧答案是候选要素、
人话打印与待处理汇总(含可能重复的卡)。"""
import copy
import json

import pytest

from chart_workflow import elements, oplog, shapes, state
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
        {"ing_id": "i3", "element": "$flat", "role": "bonus", "origin": "user_written"},
    ],
    "triggers": [{"trig_id": "t1", "term": "T5", **DET},
                 {"trig_id": "t2", "term": "custom", "text": "放量阳线过前高", "origin": "user_written"}],
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
                              "origin": "user_written"}], "triggers": []}
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
    e = add_round(cfg, kind="rule", rule_id="s001", version="v1", source="shape:s001@v1",
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
    e = add_round(cfg, kind="rule", rule_id="s003", version="v1", source="shape:s003@v1",
                  change="复用", list_id="r6-contrast")
    c = e["conditions"][0]
    assert c["suggested_by"] == "own_library" and c["element"] == "E002"
    assert (c["root_origin"], c["root_suggested_by"]) == ("suggested_adopted", "detector")
    # 要素是事实表推荐的、角色是用户定的:两件事分开记
    shapes.apply(_decision(_create({"ingredients": [{"ing_id": "m1", "element": "E002", "role": "bonus",
                                                     "origin": "user_written"}], "triggers": []},
                                   name="派发也算加分")))
    (lists / "r7-contrast.json").write_text(json.dumps({"list_id": "r7-contrast", "kind": "contrast"}))
    m1 = add_round(cfg, kind="rule", rule_id="s004", version="v1", source="shape:s004@v1",
                   change="角色用户定", list_id="r7-contrast")["conditions"][0]
    assert (m1["element_origin"], m1["element_suggested_by"]) == ("suggested_adopted", "detector")
    assert (m1["origin"], m1["root_origin"]) == ("user_written", "user_written")
    with pytest.raises(FileNotFoundError):
        add_round(cfg, kind="rule", rule_id="s001", version="v2", source="shape:s001@v2",
                  change="x", list_id="r5-contrast")
    with pytest.raises(FileNotFoundError):
        add_round(cfg, kind="rule", rule_id="s009", version="v1", source="shape:s009@v1",
                  change="x", list_id="r5-contrast")


def test_ledger_marks_user_proposed_angle(state_dir, cw_env, monkeypatch):
    """要素读的事实行是用户提的角度:哪怕要素是事实表推荐的,账本记 angle_by = user,不算系统推荐。"""
    from chart_workflow import facts
    cfg, _ = cw_env
    _base(state_dir)
    src = {"kind": "user", "date": "2026-10-17", "said": "看最近一个月有没有派发", "op_id": "op-dist"}
    monkeypatch.setitem(facts.ROWS, "F13", {**facts.ROWS["F13"], "source": src})
    lists = root_dir(cfg) / "lists"
    lists.mkdir(parents=True)
    (lists / "r5-contrast.json").write_text(json.dumps({"list_id": "r5-contrast", "kind": "contrast"}))
    e = add_round(cfg, kind="rule", rule_id="s001", version="v1", source="shape:s001@v1",
                  change="首版", list_id="r5-contrast")
    i2 = next(c for c in e["conditions"] if c["cond_id"] == "i2")
    assert i2["element_suggested_by"] == "detector"
    assert (i2["angle_by"], i2["angle_ops"]) == ("user", ["op-dist"])
    assert "要素 你说的 2 / 你提的角度 1 / 事实表 0" in render_ledger(read_ledger())
    assert "你提的角度" in elements.render(elements.load_all()["E002"])


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


def test_own_library_reuse_follows_element_merge(state_dir):
    """旧卡引用的要素后来并进了另一条:复用时引用并入的那条,认作同一个东西。"""
    _base(state_dir)
    shapes.apply(_decision({"act": "merge_element", "target": {"element_id": "E002"},
                            "value": {"into": "E004", "reason": "用户说是同一个意思"}, "actor": "user"}))
    shapes.apply(_decision(_create({"ingredients": [_reuse("j1", "E004", "i2")], "triggers": []},
                                   name="复用")))
    j1 = shapes.load_card("s002")["versions"][0]["card"]["ingredients"][0]
    assert j1["root"] == {"origin": "suggested_adopted", "suggested_by": "detector"}


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
