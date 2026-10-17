"""规则来自形态卡时的核对:规则要声明实现了卡上哪些要素与角色,和卡那一版一致;卡的样本上规则信号和卡上
要素的判定一致;不一致就拒绝(对照页什么都不生成、不记账);通过后声明记进账本;手动记账不收形态卡来源。"""
import json
import sys
import types

import pytest

from chart_workflow import contrast, rulecheck, shapes
from chart_workflow.config import root_dir
from chart_workflow.ledger import add_round, read_ledger
from tests.chart_workflow.conftest import make_stock
from tests.chart_workflow.test_facts import qmmm_synthetic
from tests.chart_workflow.test_shapes import DET, _decision, el_op

PK1 = {"row": "F01", "value": "n_cleared", "cond": "at_least", "user_params": {"x": 1}}      # QMMM 7/14:是
DIST = {"row": "F13", "value": "events", "cond": "events_any", "user_params": {"bars": 20}}   # QMMM 7/14:否
GOOD = '''
IMPLEMENTS = {"E001": "must", "E002": "must_not"}

def signal(df):
    return df["close"] >= df["close"].rolling(60, min_periods=1).max()
'''


def _batch(state_dir, cases=(("a1", "2025-07-14"),)):
    d = state_dir / "annotations"
    d.mkdir(parents=True, exist_ok=True)
    anns = [{"ann_id": a, "item_id": f"QMM@{day}", "symbol": "QMM", "range_start": "2025-02-28",
             "range_end": None, "label": "positive", "note": "", "buy_points": [{"date": day, "primary": True}]}
            for a, day in cases]
    (d / "b1.json").write_text(json.dumps({
        "schema": "chart_workflow.annotations/2", "batch_id": "b1", "list_id": "r1", "train_end": "2025-12-31",
        "list_kind": "bigmoves", "outcome_visible": True, "annotations": anns}, ensure_ascii=False))


def _card(with_case=True, day="2025-07-14"):
    card = {"ingredients": [{"ing_id": "i1", "element": "$pk", "role": "must", "origin": "user_written",
                             "said_first_match": "越过前高"},
                            {"ing_id": "i2", "element": "$dist", "role": "must_not", **DET}],
            "triggers": [{"trig_id": "t1", "term": "T5", **DET}], "story": None, "exit_pref": None}
    ops = [el_op("pk", "按收盘至少越过一个峰", PK1), el_op("dist", "最近 20 根里有派发", DIST, user=False),
           {"act": "create_shape", "value": {"name": {"value": "越过前高", "origin": "user_written"},
                                             "card": card, "change": "新建", "from_ann": ["a1"]}}]
    if with_case:
        ops.append({"act": "add_case", "target": {"shape_id": "$new"}, "value": {
            "ann_id": "a1", "buy_date": {"value": day, "origin": "user_written"}, "trigger_ref": "t1",
            "shape_claim": {"value": "new", "origin": "user_written"}, "divergence_answers": [],
            "facts_ref": f"facts/b1.json#a1/{day}"}})
    shapes.apply(_decision(*ops))


@pytest.fixture
def env(cw_env, state_dir, tmp_path, monkeypatch):
    cfg, pkl_dir = cw_env
    qmmm_synthetic().to_pickle(pkl_dir / "QMM.pkl")
    _batch(state_dir)
    monkeypatch.setattr(contrast, "load_config", lambda: cfg)
    return cfg, pkl_dir, tmp_path


def _rule(tmp_path, text, name="r.py"):
    p = tmp_path / name
    p.write_text(text)
    return str(p)


def test_consistent_rule_passes_and_records(env):
    cfg, _, tmp = env
    _card()
    res = rulecheck.check_rule_against_shape("shape:s001@v1", cfg, rule=_rule(tmp, GOOD))
    assert res["source"] == "shape:s001@v1" and res["samples_checked"] == 1 and res["samples_skipped"] == []
    assert res["declared"] == [{"element": "E001", "element_resolved": "E001", "role": "must"},
                               {"element": "E002", "element_resolved": "E002", "role": "must_not"}]


@pytest.mark.parametrize("decl,needle", [
    (None, "要在模块顶层声明 IMPLEMENTS"),
    ('{"E001": "must"}', "规则没声明卡上的 E002"),
    ('{"E001": "must", "E002": "bonus"}', "卡上是「有它就不买」,规则声明的是「加分」"),
    ('{"E001": "must", "E002": "must_not", "E003": "bonus"}', "不在要素库里"),
    ('{"E001": "must", "E002": "maybe"}', "格式不对"),
])
def test_declaration_must_match_card(env, decl, needle):
    cfg, _, tmp = env
    _card()
    body = GOOD.replace('IMPLEMENTS = {"E001": "must", "E002": "must_not"}\n',
                        "" if decl is None else f"IMPLEMENTS = {decl}\n")
    with pytest.raises(rulecheck.RuleShapeMismatch, match=needle):
        rulecheck.check_rule_against_shape("shape:s001@v1", cfg, rule=_rule(tmp, body))


def test_extra_element_on_rule_refused(env):
    cfg, _, tmp = env
    _card()
    shapes.apply(_decision(el_op("v", "放量", {"row": "F07", "value": "vr", "cond": "at_least",
                                                "default_params": {"x": 3.0}}, user=False)))
    body = GOOD.replace('"E002": "must_not"}', '"E002": "must_not", "E003": "bonus"}')
    with pytest.raises(rulecheck.RuleShapeMismatch, match="规则声明了卡上没有的 E003"):
        rulecheck.check_rule_against_shape("shape:s001@v1", cfg, rule=_rule(tmp, body))


def test_signal_must_agree_with_card_on_samples(env):
    cfg, _, tmp = env
    _card()
    bad = GOOD.replace('return df["close"] >= df["close"].rolling(60, min_periods=1).max()',
                       'return df["close"] < 0')
    with pytest.raises(rulecheck.RuleShapeMismatch) as ei:
        rulecheck.check_rule_against_shape("shape:s001@v1", cfg, rule=_rule(tmp, bad))
    assert "样本 a1(QMM 买点 2025-07-14):卡上要素判定成立,规则信号不成立" in str(ei.value)


def test_no_checkable_sample_refused(env):
    cfg, _, tmp = env
    _card(with_case=False)
    with pytest.raises(rulecheck.RuleShapeMismatch, match="没有能核对的样本"):
        rulecheck.check_rule_against_shape("shape:s001@v1", cfg, rule=_rule(tmp, GOOD))


def test_app_declares_in_module(env, monkeypatch):
    mod = types.ModuleType("_cw_fake_app")
    mod.IMPLEMENTS = {"E001": "must"}
    monkeypatch.setitem(sys.modules, "_cw_fake_app", mod)
    import chart_workflow.rules as rules
    monkeypatch.setattr(rules, "app_module_path", lambda pid: "_cw_fake_app")
    assert rulecheck.declared_implements(app="fake") == {"E001": "must"}
    del mod.IMPLEMENTS
    with pytest.raises(rulecheck.RuleShapeMismatch, match=r"app fake\(_cw_fake_app\) 要在模块顶层声明"):
        rulecheck.declared_implements(app="fake")


def test_contrast_refuses_unchecked_shape_source_and_records_declaration(env):
    """对照页:规则和卡对不上就停,什么都不生成、不记账;对上了把声明记进账本。"""
    cfg, pkl_dir, tmp = env
    for i in range(3):
        make_stock(seed=40 + i).to_pickle(pkl_dir / f"C{i}.pkl")
    _card()
    d = root_dir(cfg) / "lists"
    lists = lambda: sorted(p.name for p in d.glob("*.json")) if d.exists() else []
    no_decl = GOOD.replace('IMPLEMENTS = {"E001": "must", "E002": "must_not"}\n', "")
    with pytest.raises(SystemExit):
        contrast.main(["--list-id", "t-s0", "--rule", _rule(tmp, no_decl, "nodecl.py"),
                       "--source", "shape:s001@v1", "--change", "x", "--blind", "--no-xcheck"])
    assert lists() == [] and read_ledger() == []
    contrast.main(["--list-id", "t-s1", "--rule", _rule(tmp, GOOD), "--source", "shape:s001@v1",
                   "--change", "首版", "--blind", "--no-xcheck"])
    r = read_ledger()[-1]
    assert r["source"] == "shape:s001@v1" and r["rule_implements"]["samples_checked"] == 1
    assert [d["element"] for d in r["rule_implements"]["declared"]] == ["E001", "E002"]


def test_manual_ledger_refuses_shape_source(env):
    cfg, _, _ = env
    _card()
    lists = root_dir(cfg) / "lists"
    lists.mkdir(parents=True)
    (lists / "r5.json").write_text(json.dumps({"list_id": "r5", "kind": "contrast"}))
    with pytest.raises(ValueError, match="手动记账不收形态卡来源"):
        add_round(cfg, kind="rule", rule_id="s001", version="v1", source="shape:s001@v1",
                  change="x", list_id="r5")
    with pytest.raises(ValueError, match="手动记账不收形态卡来源"):     # 核对结果对不上来源也不收
        add_round(cfg, kind="rule", rule_id="s001", version="v1", source="shape:s001@v1",
                  change="x", list_id="r5", implements={"source": "shape:s001@v2", "declared": [{}]})
    assert read_ledger() == []
