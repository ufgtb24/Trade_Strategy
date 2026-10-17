"""规则来自形态卡时的核对:规则要声明实现了卡上哪些要素与角色,和卡那一版一致;卡的样本上、样本股看图范围内
逐日,规则信号都要和「卡说成立」一致(永远成立、比卡宽的规则过不了);能核对的样本少于最少个数就拒绝并给出
两条出路;账本记账时自己重跑核对,不收调用方传来的结果;对照页开工前就核对,不过什么都不生成。

合成 QMMM(chart_workflow 事实表的金标数据)上,卡 = 按收盘至少越过一个峰(必须有)+ 最近 20 根里有派发
(有它就不买)+ 触发「当天缩量」(T7)。看图下界放到 2025-06-15,逐日核对只跑 6/16~7/14 这一段:
卡在 7/4、7/7、7/9、7/10、7/11、7/14 成立,7/3、7/8(越过了峰但没缩量)和六月各天不成立。"""
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

PK1 = {"row": "F01", "value": "n_cleared", "cond": "at_least", "user_params": {"x": 1}}
DIST = {"row": "F13", "value": "events", "cond": "events_any", "user_params": {"bars": 20}}
SAMPLES = (("a1", "2025-07-14"), ("a2", "2025-07-10"), ("a3", "2025-07-07"))      # 卡在这三天都成立
FLOOR = "2025-06-15"

# 照卡写的规则:逐日按事实表判(只算看图范围这一段,别的日子不成立)。WHEN 换成别的条件就是坏规则。
RULE = '''
import pandas as pd
from chart_workflow import elements as E
from chart_workflow.config import DEFAULTS
from chart_workflow.facts import compute_facts

IMPLEMENTS = {"E001": "must", "E002": "must_not"}
PK = E.normalize_definition(%(pk)r)[0]
DIST = E.normalize_definition(%(dist)r)[0]


def signal(df):
    out = pd.Series(False, index=df.index)
    for d in df.index[(df.index >= "%(floor)s") & (df.index <= "2025-07-31")]:
        f = compute_facts(df, d.strftime("%%Y-%%m-%%d"), None, fcfg=DEFAULTS["facts"],
                          features_cfg=DEFAULTS["features"], m_period=DEFAULTS["m_period"])
        pk, dist = E.evaluate(PK, f)[0] == "yes", E.evaluate(DIST, f)[0] == "no"
        dry = any(t["tid"] == "T7" for t in f["triggers"])
        out[d] = WHEN
    return out
'''


def _rule_text(when="pk and dist and dry", implements='{"E001": "must", "E002": "must_not"}'):
    t = RULE % {"pk": PK1, "dist": DIST, "floor": FLOOR}
    return t.replace("WHEN", when).replace('IMPLEMENTS = {"E001": "must", "E002": "must_not"}',
                                            f"IMPLEMENTS = {implements}" if implements else "")


def _batch(state_dir, cases=SAMPLES):
    d = state_dir / "annotations"
    d.mkdir(parents=True, exist_ok=True)
    anns = [{"ann_id": a, "item_id": f"QMM@{day}", "symbol": "QMM", "range_start": "2025-02-28",
             "range_end": None, "label": "positive", "note": "", "buy_points": [{"date": day, "primary": True}]}
            for a, day in cases]
    (d / "b1.json").write_text(json.dumps({
        "schema": "chart_workflow.annotations/2", "batch_id": "b1", "list_id": "r1", "train_end": "2025-12-31",
        "list_kind": "bigmoves", "outcome_visible": True, "annotations": anns}, ensure_ascii=False))


def _case(ann_id, day):
    return {"act": "add_case", "target": {"shape_id": "$new"}, "value": {
        "ann_id": ann_id, "buy_date": {"value": day, "origin": "user_written"}, "trigger_ref": "t1",
        "shape_claim": {"value": "new", "origin": "user_written"}, "divergence_answers": [],
        "facts_ref": f"facts/b1.json#{ann_id}/{day}"}}


def _card(cases=SAMPLES):
    card = {"ingredients": [{"ing_id": "i1", "element": "$pk", "role": "must", "origin": "user_written",
                             "said_first_match": "越过前高"},
                            {"ing_id": "i2", "element": "$dist", "role": "must_not", **DET}],
            "triggers": [{"trig_id": "t1", "term": "T7", **DET}], "story": None, "exit_pref": None}
    ops = [el_op("pk", "按收盘至少越过一个峰", PK1), el_op("dist", "最近 20 根里有派发", DIST, user=False),
           {"act": "create_shape", "value": {"name": {"value": "越过前高后缩量", "origin": "user_written"},
                                             "card": card, "change": "新建", "from_ann": ["a1"]}}]
    shapes.apply(_decision(*ops, *[_case(a, d) for a, d in cases]))


@pytest.fixture
def env(cw_env, state_dir, tmp_path, monkeypatch):
    cfg, pkl_dir = cw_env
    cfg["view_floor"] = FLOOR
    cfg["rules"]["causal_samples"] = 1
    qmmm_synthetic().to_pickle(pkl_dir / "QMM.pkl")
    _batch(state_dir)
    monkeypatch.setattr(contrast, "load_config", lambda: cfg)
    return cfg, pkl_dir, tmp_path


def _rule(tmp_path, text, name="r.py"):
    p = tmp_path / name
    p.write_text(text)
    return str(p)


def test_rule_written_from_card_passes(env):
    cfg, _, tmp = env
    _card()
    res = rulecheck.check_rule_against_shape("shape:s001@v1", cfg, rule=_rule(tmp, _rule_text()))
    assert (res["samples_checked"], res["samples_skipped"], res["days_disagree"]) == (3, [], 0)
    assert res["days_checked"] >= 20
    assert res["declared"] == [{"element": "E001", "element_resolved": "E001", "role": "must"},
                               {"element": "E002", "element_resolved": "E002", "role": "must_not"}]


@pytest.mark.parametrize("when,needle", [
    ("True", None),                           # 永远成立:样本上都对,卡说不成立的日子露馅
    ("pk and dist", "2025-07-08"),            # 比卡宽(不要触发):越过了峰但没缩量的那天露馅
])
def test_always_true_or_wider_rule_refused(env, when, needle):
    cfg, _, tmp = env
    _card()
    with pytest.raises(rulecheck.RuleShapeMismatch) as ei:
        rulecheck.check_rule_against_shape("shape:s001@v1", cfg, rule=_rule(tmp, _rule_text(when)))
    msg = str(ei.value)
    assert "逐日比" in msg and "天不一致" in msg and "卡说不成立,规则成立" in msg
    if needle:
        assert needle in msg


def test_disagree_tolerance_is_configurable(env):
    cfg, _, tmp = env
    _card()
    cfg["shape_check"] = {"max_disagree_share": 0.5}
    res = rulecheck.check_rule_against_shape("shape:s001@v1", cfg, rule=_rule(tmp, _rule_text("pk and dist")))
    assert res["days_disagree"] == 2 and "2025-07-08" in " ".join(res["disagree_examples"])


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
    with pytest.raises(rulecheck.RuleShapeMismatch, match=needle):
        rulecheck.check_rule_against_shape("shape:s001@v1", cfg, rule=_rule(tmp, _rule_text(implements=decl)))


def test_extra_element_on_rule_refused(env):
    cfg, _, tmp = env
    _card()
    shapes.apply(_decision(el_op("v", "放量", {"row": "F07", "value": "vr", "cond": "at_least",
                                                "default_params": {"x": 3.0}}, user=False)))
    text = _rule_text(implements='{"E001": "must", "E002": "must_not", "E003": "bonus"}')
    with pytest.raises(rulecheck.RuleShapeMismatch, match="规则声明了卡上没有的 E003"):
        rulecheck.check_rule_against_shape("shape:s001@v1", cfg, rule=_rule(tmp, text))


def test_signal_must_agree_with_card_on_samples(env):
    cfg, _, tmp = env
    _card()
    with pytest.raises(rulecheck.RuleShapeMismatch) as ei:
        rulecheck.check_rule_against_shape("shape:s001@v1", cfg, rule=_rule(tmp, _rule_text("False")))
    assert "样本 a1(QMM 买点 2025-07-14):卡说成立,规则信号不成立" in str(ei.value)


def test_too_few_checkable_samples_refused_with_two_ways_out(env, state_dir):
    """三个样本里一个不是交易日、一个早于看图下界,都被跳过,只核对了一个:拒绝,并说清两条出路。"""
    cfg, _, tmp = env
    cases = (("a1", "2025-07-14"), ("a2", "2025-07-05"), ("a3", "2025-06-02"))
    _batch(state_dir, cases)
    _card(cases)
    with pytest.raises(rulecheck.RuleShapeMismatch) as ei:
        rulecheck.check_rule_against_shape("shape:s001@v1", cfg, rule=_rule(tmp, _rule_text()))
    msg = str(ei.value)
    assert "能核对的样本只有 1 个,至少要 3 个" in msg
    assert "样本 a2" in msg and "样本 a3" in msg                              # 跳过的照常列出原因
    assert "先给卡加样本" in msg and "不声明来自形态卡" in msg


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


def test_app_signal_path_compared_day_by_day(env, monkeypatch):
    """app 方式:信号取 app 在这只股票上的命中日;命中日和卡说成立的日子对不上照样拒绝。"""
    cfg, _, _ = env
    _card()
    mod = types.ModuleType("_cw_fake_app2")
    mod.IMPLEMENTS = {"E001": "must", "E002": "must_not"}
    monkeypatch.setitem(sys.modules, "_cw_fake_app2", mod)
    import chart_workflow.rules as rules
    monkeypatch.setattr(rules, "app_module_path", lambda pid: "_cw_fake_app2")
    good = ["2025-07-04", "2025-07-07", "2025-07-09", "2025-07-10", "2025-07-11", "2025-07-14"]
    monkeypatch.setattr(rules, "_app_worker", lambda args: (args[2], [__import__("pandas").Timestamp(d) for d in good], []))
    res = rulecheck.check_rule_against_shape("shape:s001@v1", cfg, app="fake")
    assert res["days_disagree"] == 0 and res["samples_checked"] == 3
    monkeypatch.setattr(rules, "_app_worker",
                        lambda args: (args[2], [__import__("pandas").Timestamp(d) for d in good + ["2025-07-03"]], []))
    with pytest.raises(rulecheck.RuleShapeMismatch, match="2025-07-03"):
        rulecheck.check_rule_against_shape("shape:s001@v1", cfg, app="fake")


def test_ledger_rechecks_itself_and_takes_no_caller_result(env, monkeypatch):
    """账本记账时自己重跑核对:坏规则拒记;手填核对结果的入口不存在;没给规则(手动记账)不收形态卡来源。"""
    cfg, _, tmp = env
    _card()
    lists = root_dir(cfg) / "lists"
    lists.mkdir(parents=True)
    (lists / "r5.json").write_text(json.dumps({"list_id": "r5", "kind": "contrast"}))
    common = dict(kind="rule", rule_id="s001", version="v1", source="shape:s001@v1", change="x", list_id="r5")
    with pytest.raises(TypeError):                                        # 没有收核对结果的参数
        add_round(cfg, **common, implements={"source": "shape:s001@v1", "declared": [{"element": "E001"}]})
    with pytest.raises(ValueError, match="手动记账不收形态卡来源"):
        add_round(cfg, **common)
    with pytest.raises(rulecheck.RuleShapeMismatch, match="逐日比"):
        add_round(cfg, **common, rule=_rule(tmp, _rule_text("True")))
    assert read_ledger() == []
    calls = []
    real = rulecheck.check_rule_against_shape
    monkeypatch.setattr(rulecheck, "check_rule_against_shape", lambda *a, **k: calls.append(1) or real(*a, **k))
    e = add_round(cfg, **common, rule=_rule(tmp, _rule_text()))
    assert calls == [1] and e["rule_implements"]["samples_checked"] == 3
    assert e["rule_implements"]["days_disagree"] == 0


def test_contrast_refuses_before_anything_and_records_declaration(env):
    """对照页:规则和卡对不上就在开工前停,不算面板、不生成清单、不记账;对上了把核对结果记进账本。"""
    cfg, pkl_dir, tmp = env
    for i in range(3):
        make_stock(seed=40 + i).to_pickle(pkl_dir / f"C{i}.pkl")
    _card()
    d = root_dir(cfg) / "lists"
    lists = lambda: sorted(p.name for p in d.glob("*.json")) if d.exists() else []
    with pytest.raises(SystemExit):
        contrast.main(["--list-id", "t-s0", "--rule", _rule(tmp, _rule_text("pk and dist"), "wide.py"),
                       "--source", "shape:s001@v1", "--change", "x", "--blind", "--no-xcheck"])
    assert lists() == [] and read_ledger() == []
    assert not (root_dir(cfg) / "cache").exists()                         # 连面板都没算
    contrast.main(["--list-id", "t-s1", "--rule", _rule(tmp, _rule_text()), "--source", "shape:s001@v1",
                   "--change", "首版", "--blind", "--no-xcheck"])
    r = read_ledger()[-1]
    assert r["source"] == "shape:s001@v1" and r["rule_implements"]["samples_checked"] == 3
    assert [x["element"] for x in r["rule_implements"]["declared"]] == ["E001", "E002"]


def test_contrast_with_scores_rechecks_with_the_rule_itself(env, monkeypatch):
    """对照页普通模式(当场算成绩、当场记账):开工前核对一遍,记账时账本拿同一条规则、同一份 app 参数再核对
    一遍——记账上下文里的清单参数不能顶替 app 参数。"""
    cfg, pkl_dir, tmp = env
    for i in range(3):
        make_stock(seed=40 + i).to_pickle(pkl_dir / f"C{i}.pkl")
    _card()
    calls = []
    real = rulecheck.check_rule_against_shape
    monkeypatch.setattr(rulecheck, "check_rule_against_shape",
                        lambda source, cfg, **kw: calls.append(kw) or real(source, cfg, **kw))
    monkeypatch.setattr(contrast, "check_rule_against_shape", rulecheck.check_rule_against_shape)
    rule = _rule(tmp, _rule_text())
    contrast.main(["--list-id", "t-s2", "--rule", rule, "--source", "shape:s001@v1", "--change", "首版",
                   "--no-xcheck"])
    assert calls == [{"rule": rule, "app": None, "params": None}] * 2
    assert read_ledger()[-1]["rule_implements"]["samples_checked"] == 3
