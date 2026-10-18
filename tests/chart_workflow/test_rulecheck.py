"""规则来自形态卡时的核对:规则要声明实现了卡上哪些要素与角色,和卡那一版一致;卡的样本上、样本股(被排除的
样本所在的股票也算)与随机抽的股票看图范围内逐日,规则信号都要和「卡说成立」一致(永远成立、比卡宽、比卡窄、
永远不成立的规则都过不了);三处都按固定回看判卡,按用户框的窗口判得不同的样本单独列出、不拿来核对;卡上有
手写触发就拒;能核对的样本、其中卡成立的样本、卡判「不成立」的天、有卡成立日的随机股不够就拒;随机抽股的顺序
只由卡的编号定(内容不变的改版抽到同一批),沿顺序抽到有卡成立日的够数为止、有上限;逐日材料在同一次运行里
缓存、可并行;账本记账时自己重跑核对,核对用的规则要和清单实际用的规则指纹相同;对照页开工前就核对,不过什么
都不生成。

合成 QMMM(chart_workflow 事实表的金标数据)上,卡 = 按收盘至少越过一个峰(必须有)+ 最近 20 根里有派发
(有它就不买)+ 触发「当天缩量」(T7)。看图下界放到 2025-06-15,逐日核对只跑 6/16~7/14 这一段(21 天):
卡在 7/4、7/7、7/9、7/10、7/11、7/14 成立,7/3、7/8(越过了峰但没缩量)和六月各天不成立(共 15 天;
本文件把「卡判不成立至少几天」设成 10、「随机股里有卡成立日的至少几只」设成 0(不抽),默认的 20、40 另有
测试)。
框选:从 6/20 或 6/30 起的短框里一个峰都没越过(按框判卡不成立,按固定回看成立);从 2024-09-02 起的长框里,
7/10、7/11 按收盘越过了 2 个峰(按固定回看只越过 1 个)。"""
import json
import sys
import types

import pytest

from chart_workflow import contrast, rulecheck, shapes
from chart_workflow.config import DEFAULTS, root_dir
from chart_workflow.ledger import add_round, read_ledger
from chart_workflow.rules import rule_identity
from tests.chart_workflow.conftest import make_stock
from tests.chart_workflow.test_facts import qmmm_synthetic
from tests.chart_workflow.test_shapes import DET, _decision, el_op

PK1 = {"row": "F01", "value": "n_cleared", "cond": "at_least", "user_params": {"x": 1}}
PK2 = {"row": "F01", "value": "n_cleared", "cond": "at_least", "user_params": {"x": 2}}
DIST = {"row": "F13", "value": "events", "cond": "events_any", "user_params": {"bars": 20}}
BOX = "2025-02-28"
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
        trig = {t["tid"] for t in f["triggers"]}
        dry = "T7" in trig
        c = float(df.loc[d, "close"])
        out[d] = WHEN
    return out
'''


def _rule_text(when="pk and dist and dry", implements='{"E001": "must", "E002": "must_not"}', pk=PK1):
    t = RULE % {"pk": pk, "dist": DIST, "floor": FLOOR}
    return t.replace("WHEN", when).replace('IMPLEMENTS = {"E001": "must", "E002": "must_not"}',
                                            f"IMPLEMENTS = {implements}" if implements else "")


def _batch(state_dir, cases=SAMPLES):
    """cases:(ann_id, 买点[, 框选起点[, 代码]]),框选起点缺省 BOX(写 None 是不框),代码缺省 QMM。"""
    d = state_dir / "annotations"
    d.mkdir(parents=True, exist_ok=True)
    anns = [{"ann_id": c[0], "item_id": f"{(c[3:] or ('QMM',))[0]}@{c[1]}", "symbol": (c[3:] or ("QMM",))[0],
             "range_start": (c[2:] or (BOX,))[0], "range_end": None, "label": "positive", "note": "",
             "buy_points": [{"date": c[1], "primary": True}]}
            for c in cases]
    (d / "b1.json").write_text(json.dumps({
        "schema": "chart_workflow.annotations/2", "batch_id": "b1", "list_id": "r1", "train_end": "2025-12-31",
        "list_kind": "bigmoves", "outcome_visible": True, "annotations": anns}, ensure_ascii=False))


def _case(ann_id, day):
    return {"act": "add_case", "target": {"shape_id": "$new"}, "value": {
        "ann_id": ann_id, "buy_date": {"value": day, "origin": "user_written"}, "trigger_ref": "t1",
        "shape_claim": {"value": "new", "origin": "user_written"}, "divergence_answers": [],
        "facts_ref": f"facts/b1.json#{ann_id}/{day}"}}


def _card(cases=SAMPLES, pk=PK1, triggers=("T7",), custom=None):
    trig = [{"trig_id": f"t{k + 1}", "term": t, **DET} for k, t in enumerate(triggers)]
    if custom:
        trig.append({"trig_id": f"t{len(trig) + 1}", "term": "custom", "text": custom, "origin": "user_written",
                     "said_first_match": custom})
    card = {"ingredients": [{"ing_id": "i1", "element": "$pk", "role": "must", "origin": "user_written",
                             "said_first_match": "越过前高"},
                            {"ing_id": "i2", "element": "$dist", "role": "must_not", **DET}],
            "triggers": trig, "story": None, "exit_pref": None}
    ops = [el_op("pk", "按收盘越过前面的峰", pk), el_op("dist", "最近 20 根里有派发", DIST, user=False),
           {"act": "create_shape", "value": {"name": {"value": "越过前高后缩量", "origin": "user_written"},
                                             "card": card, "change": "新建", "from_ann": [cases[0][0]]}}]
    shapes.apply(_decision(*ops, *[_case(c[0], c[1]) for c in cases]))


@pytest.fixture
def env(cw_env, state_dir, tmp_path, monkeypatch):
    cfg, pkl_dir = cw_env
    cfg["view_floor"] = FLOOR
    cfg["rules"]["causal_samples"] = 1
    cfg["shape_check"] = {**cfg["shape_check"], "min_negative_days": 10, "pool_positive_stocks": 0}
    qmmm_synthetic().to_pickle(pkl_dir / "QMM.pkl")
    _batch(state_dir)
    monkeypatch.setattr(contrast, "load_config", lambda: cfg)
    return cfg, pkl_dir, tmp_path


def _rule(tmp_path, text, name="r.py"):
    p = tmp_path / name
    p.write_text(text)
    return str(p)


def _list(cfg, list_id, rule):
    """账本记账要的清单文件:params.rule_identity 记生成它的规则。"""
    d = root_dir(cfg) / "lists"
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{list_id}.json").write_text(json.dumps({"list_id": list_id, "kind": "contrast",
                                                   "params": {"rule_identity": rule and rule_identity(rule)}}))


def test_rule_written_from_card_passes(env):
    cfg, _, tmp = env
    _card()
    res = rulecheck.check_rule_against_shape("shape:s001@v1", cfg, rule=_rule(tmp, _rule_text()))
    assert (res["samples_checked"], res["samples_skipped"], res["days_disagree"]) == (3, [], 0)
    from chart_workflow.facts import FACTS_CODE
    assert res["facts_code"] == FACTS_CODE                     # 判卡用的事实表代码版本记进账本
    assert res["days_checked"] >= 20
    assert res["declared"] == [{"element": "E001", "element_resolved": "E001", "role": "must"},
                               {"element": "E002", "element_resolved": "E002", "role": "must_not"}]


@pytest.mark.parametrize("when,needle", [
    ("True", None),                           # 永远成立:样本上都对,卡说不成立的日子露馅
    ("pk and dist", "2025-07-08:卡说不成立(要素都成立,当天缺卡上的触发 T7(当天缩量)),规则成立"),   # 比卡宽
])
def test_always_true_or_wider_rule_refused(env, when, needle):
    cfg, _, tmp = env
    _card()
    with pytest.raises(rulecheck.RuleShapeMismatch) as ei:
        rulecheck.check_rule_against_shape("shape:s001@v1", cfg, rule=_rule(tmp, _rule_text(when)))
    msg = str(ei.value)
    assert "逐日比" in msg and "天不一致" in msg and "卡说不成立(" in msg and "),规则成立" in msg
    if needle:
        assert needle in msg


def test_disagree_tolerance_is_configurable(env):
    cfg, _, tmp = env
    _card()
    cfg["shape_check"]["max_disagree_share"] = 0.5
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
    with pytest.raises(rulecheck.RuleShapeMismatch) as ei:
        rulecheck.check_rule_against_shape("shape:s001@v1", cfg, rule=_rule(tmp, _rule_text("True"), "t.py"))
    assert "逐日比" in str(ei.value)          # 卡在样本上都成立,永远成立的规则过了样本核对,逐日露馅


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
    good, wide = _rule(tmp, _rule_text()), _rule(tmp, _rule_text("True"), "always.py")
    common = dict(kind="rule", rule_id="s001", version="v1", source="shape:s001@v1", change="x", list_id="r5")
    _list(cfg, "r5", wide)
    with pytest.raises(TypeError):                                        # 没有收核对结果的参数
        add_round(cfg, **common, implements={"source": "shape:s001@v1", "declared": [{"element": "E001"}]})
    with pytest.raises(ValueError, match="手动记账不收形态卡来源"):
        add_round(cfg, **common)
    with pytest.raises(rulecheck.RuleShapeMismatch, match="逐日比"):
        add_round(cfg, **common, rule=wide)
    assert read_ledger() == []
    _list(cfg, "r5", good)
    calls = []
    real = rulecheck.check_rule_against_shape
    monkeypatch.setattr(rulecheck, "check_rule_against_shape", lambda *a, **k: calls.append(1) or real(*a, **k))
    e = add_round(cfg, **common, rule=good)
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


@pytest.mark.parametrize("cases,pk,when,odd", [
    # 短框:框里一个峰都没越过,按框判卡不成立;按固定回看成立
    (SAMPLES + (("a4", "2025-07-09", "2025-06-30"),), PK1, "pk and dist and dry", "a4"),
    # 长框:7/10 按框越过了 2 个峰,按固定回看只越过 1 个(卡的触发是 T7 或 T3)
    ((("a1", "2025-07-14"), ("a2", "2025-07-09"), ("a3", "2025-07-08"), ("a4", "2025-07-10", "2024-09-02")),
     PK2, "pk and dist and bool(trig & {'T7', 'T3'})", "a4"),
])
def test_samples_judged_with_fixed_lookback_and_box_mismatch_listed(env, state_dir, cases, pk, when, odd):
    """样本按固定回看判卡(和规则、逐日核对同一个口径):照卡忠实写的规则,样本框得比固定回看长或短都通过;
    按框判和按固定回看判不同的样本单独列出,不算进能核对的个数。"""
    cfg, _, tmp = env
    _batch(state_dir, cases)
    _card(cases, pk=pk, triggers=("T7",) if "dry" in when else ("T7", "T3"))
    res = rulecheck.check_rule_against_shape("shape:s001@v1", cfg, rule=_rule(tmp, _rule_text(when, pk=pk)))
    assert res["samples_checked"] == 3 and res["days_disagree"] == 0
    odd_list = res["samples_unexpressible"]
    assert len(odd_list) == 1 and odd_list[0].startswith(f"样本 {odd}(")
    assert "按你框的窗口" in odd_list[0] and "按固定回看(买点前 90 根)" in odd_list[0]


def test_too_few_after_box_mismatch_refused_with_reason(env, state_dir):
    """去掉按框和按固定回看判得不同的样本后能核对的不够:拒绝,报错写清是这个原因。"""
    cfg, _, tmp = env
    cases = (("a1", "2025-07-14"), ("a2", "2025-07-10", "2025-06-30"), ("a3", "2025-07-07", "2025-06-20"))
    _batch(state_dir, cases)
    _card(cases)
    with pytest.raises(rulecheck.RuleShapeMismatch) as ei:
        rulecheck.check_rule_against_shape("shape:s001@v1", cfg, rule=_rule(tmp, _rule_text()))
    msg = str(ei.value)
    assert "能核对的样本只有 1 个" in msg and "其中 2 个样本按你框选的窗口和按固定回看判得不同" in msg
    assert "这张卡在固定回看下表达不了你框选时的意思" in msg


@pytest.mark.parametrize("when", ["pk and dist", "pk and dist and dry"])
def test_card_with_handwritten_trigger_refused(env, when):
    """卡上有手写触发(T7 加一个自己写的):核对不了规则哪天该成立,宽规则、照表里触发写的规则都拒,
    报错点名那个触发并给出路。"""
    cfg, _, tmp = env
    _card(custom="放量站上年线")
    with pytest.raises(rulecheck.RuleShapeMismatch) as ei:
        rulecheck.check_rule_against_shape("shape:s001@v1", cfg, rule=_rule(tmp, _rule_text(when)))
    msg = str(ei.value)
    assert "t2「放量站上年线」 是手写触发,没有能算的定义" in msg
    assert "在事实表加一行" in msg and "换成表里的触发" in msg
    assert "这个触发要改写成卡上的要素" in msg                     # 加事实行的代价:意思从「任一个」变成「都要」
    assert "「几个触发里出现任一个就算」变成「这一项也必须满足」" in msg
    assert "要在触发表里加一项,这需要改代码" in msg


def test_too_few_negative_days_refused(env):
    """卡判「不成立」的天不够(默认至少 20 天,待验证):看不出规则是不是比卡宽,拒绝并说明原因。"""
    cfg, _, tmp = env
    _card()
    cfg["shape_check"]["min_negative_days"] = DEFAULTS["shape_check"]["min_negative_days"]
    with pytest.raises(rulecheck.RuleShapeMismatch) as ei:
        rulecheck.check_rule_against_shape("shape:s001@v1", cfg, rule=_rule(tmp, _rule_text()))
    assert "卡判「不成立」的只有 15 天(卡能判定 21 天),至少要 20 天" in str(ei.value)


def test_no_decidable_day_refused(env, state_dir):
    """一天都判定不了(最少样本数配成 0、样本都被跳过,看图范围里样本股一天行情都没有):按反例不够拒绝。"""
    cfg, _, tmp = env
    cases = (("a1", "2025-07-05"), ("a2", "2025-06-02"))
    _batch(state_dir, cases)
    _card(cases)
    cfg["view_floor"] = "2025-07-20"
    cfg["shape_check"].update(min_samples=0, min_positive_samples=0)
    with pytest.raises(rulecheck.RuleShapeMismatch, match=r"卡判「不成立」的只有 0 天\(卡能判定 0 天\)"):
        rulecheck.check_rule_against_shape("shape:s001@v1", cfg, rule=_rule(tmp, _rule_text()))


def test_ledger_check_rule_bound_to_list_rule(env):
    """账本拿来核对的规则要和清单实际用的规则同一条(按指纹):清单是别的规则生成的、或清单没记指纹,拒绝。"""
    cfg, _, tmp = env
    _card()
    good, other = _rule(tmp, _rule_text()), _rule(tmp, _rule_text("pk and dist"), "other.py")
    common = dict(kind="rule", rule_id="s001", version="v1", source="shape:s001@v1", change="x", list_id="r8")
    _list(cfg, "r8", other)
    with pytest.raises(ValueError, match="和清单实际用的规则.*对不上"):
        add_round(cfg, **common, rule=good)
    _list(cfg, "r8", None)
    with pytest.raises(ValueError, match="清单没记规则指纹"):
        add_round(cfg, **common, rule=good)
    _list(cfg, "r8", good)
    assert add_round(cfg, **common, rule=good)["rule_implements"]["days_negative"] == 15


def _declining(start=2.0, end=1.0):
    """一路下跌、从不越过峰的合成股(日期同 QMMM):卡在它身上每天都不成立。"""
    import numpy as np

    df = qmmm_synthetic().copy()
    close = np.linspace(start, end, len(df))
    df["close"], df["open"] = close, np.r_[close[0], close[:-1]]
    df["high"], df["low"] = np.maximum(df["open"], df["close"]) * 1.01, np.minimum(df["open"], df["close"]) * 0.99
    return df


def _scaled(k=0.8):
    """QMMM 价格整体乘 k(成交量不变):卡成立的日子和 QMMM 相同,收盘都低于 1.5。"""
    df = qmmm_synthetic().copy()
    df[["open", "high", "low", "close"]] *= k
    return df


# 一个样本框得比固定回看短(按框没越过峰、按固定回看越过了,被排除),剩下三个都在一路下跌的股票上
FRAMED_AND_DECLINING = (("q1", "2025-07-14", "2025-05-29"), ("d1", "2025-06-20", None, "DEC"),
                        ("d2", "2025-06-27", None, "DEC"), ("d3", "2025-07-02", None, "DEC"))


@pytest.mark.parametrize("when,needle", [
    ("pk and dist", "QMM 2025-07-08:卡说不成立"),            # 宽规则(不管触发)
    ("False", "QMM 2025-07-14:卡说成立"),                     # 永远不成立
])
def test_excluded_sample_stock_still_checked_day_by_day(env, state_dir, when, needle):
    """被排除的样本所在的股票照常参加逐日核对:QMM 的样本因框选被排除、剩下的样本都在 DEC 上时,宽规则和
    永远不成立的规则都在 QMM 的日子上露馅。随机抽股、卡成立的样本下限都关掉,只看这一条。"""
    cfg, pkl_dir, tmp = env
    _declining().to_pickle(pkl_dir / "DEC.pkl")
    cfg["shape_check"].update(pool_positive_stocks=0, min_positive_samples=0)
    _batch(state_dir, FRAMED_AND_DECLINING)
    _card(FRAMED_AND_DECLINING)
    with pytest.raises(rulecheck.RuleShapeMismatch) as ei:
        rulecheck.check_rule_against_shape("shape:s001@v1", cfg, rule=_rule(tmp, _rule_text(when)))
    assert "逐日比" in str(ei.value) and needle in str(ei.value)
    res = rulecheck.check_rule_against_shape("shape:s001@v1", cfg, rule=_rule(tmp, _rule_text(), "good.py"))
    assert res["sample_stocks"] == ["DEC", "QMM"] and len(res["samples_unexpressible"]) == 1
    assert res["days_checked"] == 42 and res["days_positive"] == 6


def test_too_few_positive_samples_refused(env, state_dir):
    """能核对的样本里买点当天卡成立的不够(默认至少 2 个,待验证):样本都在 DEC 上时,永远不成立的规则过得了
    样本核对,在这一步拒绝。"""
    cfg, pkl_dir, tmp = env
    assert DEFAULTS["shape_check"]["min_positive_samples"] == rulecheck.DEFAULTS["min_positive_samples"] == 2
    _declining().to_pickle(pkl_dir / "DEC.pkl")
    cases = FRAMED_AND_DECLINING[1:]
    _batch(state_dir, cases)
    _card(cases)
    with pytest.raises(rulecheck.RuleShapeMismatch) as ei:
        rulecheck.check_rule_against_shape("shape:s001@v1", cfg, rule=_rule(tmp, _rule_text("False")))
    assert "能核对的 3 个样本里,买点当天卡成立的只有 0 个,至少要 2 个(待验证)" in str(ei.value)


def test_narrower_rule_caught_on_pool_stocks(env):
    """比卡窄的规则(照卡,再加收盘高于 1.5):样本股上卡成立的那几天收盘都高于 1.5,只看样本股会放过;
    随机抽到的 QMH(QMMM 价格乘 0.8)上卡成立的日子收盘都低于 1.5,露馅。照卡忠实写的规则在随机股上照样通过,
    两次核对抽到同一批。"""
    cfg, pkl_dir, tmp = env
    assert DEFAULTS["shape_check"]["pool_positive_stocks"] == rulecheck.DEFAULTS["pool_positive_stocks"] == 40
    assert DEFAULTS["shape_check"]["pool_max_stocks"] == rulecheck.DEFAULTS["pool_max_stocks"] == 300
    assert "min_positive_days" not in rulecheck.DEFAULTS and "min_positive_days" not in DEFAULTS["shape_check"]
    cfg["shape_check"]["pool_positive_stocks"] = 1
    _scaled().to_pickle(pkl_dir / "QMH.pkl")
    _card()
    narrow = _rule(tmp, _rule_text("pk and dist and dry and c > 1.5"), "narrow.py")
    with pytest.raises(rulecheck.RuleShapeMismatch) as ei:
        rulecheck.check_rule_against_shape("shape:s001@v1", cfg, rule=narrow)
    msg = str(ei.value)
    assert "样本股和随机抽的 1 只股票" in msg and "QMH 2025-07-14:卡说成立,规则不成立" in msg
    first = rulecheck.check_rule_against_shape("shape:s001@v1", cfg, rule=_rule(tmp, _rule_text()))
    again = rulecheck.check_rule_against_shape("shape:s001@v1", cfg, rule=_rule(tmp, _rule_text(), "same.py"))
    assert first["pool_stocks"] == again["pool_stocks"] == ["QMH"] and first["sample_stocks"] == ["QMM"]
    assert first["pool_positive_stocks"] == ["QMH"]
    assert (first["days_checked"], first["days_positive"], first["days_disagree"]) == (42, 12, 0)
    cfg["shape_check"]["pool_positive_stocks"] = 0            # 对照:不抽随机股,窄规则就过了
    assert rulecheck.check_rule_against_shape("shape:s001@v1", cfg, rule=narrow)["days_checked"] == 21


def _rare_pool(pkl_dir):
    """触发少见的情形:随机股里 8 只一路下跌(价格 0.5 到 0.3,卡从不成立),只有 H1、H2(QMMM 价格乘 0.8)
    有卡成立日。"""
    for i in range(8):
        _declining(0.5, 0.3).to_pickle(pkl_dir / f"D{i}.pkl")
    for k in ("H1", "H2"):
        _scaled().to_pickle(pkl_dir / f"{k}.pkl")


def test_rare_card_keeps_drawing_until_enough_stocks_with_card_days(env, monkeypatch):
    """有卡成立日的随机股要满 2 只(本测试的设置):前 2 只里不够就沿固定顺序往下抽,抽到第 2 只有卡成立日的
    为止;抽过但没有卡成立日的股票也进逐日比较(规则在上面成立就拒);抽到哪只为止和分批方式、进程数无关。"""
    cfg, pkl_dir, tmp = env
    monkeypatch.setattr(rulecheck, "_CACHE", {})
    _rare_pool(pkl_dir)
    _card()
    cfg["shape_check"].update(pool_positive_stocks=2, pool_max_stocks=10)
    order = rulecheck.pool_order(cfg, "s001", ["QMM"])
    upto = max(order.index("H1"), order.index("H2")) + 1
    assert upto > 2                                            # 前 2 只里不够,要往下抽
    res = rulecheck.check_rule_against_shape("shape:s001@v1", cfg, rule=_rule(tmp, _rule_text()))
    assert res["pool_stocks"] == order[:upto] and sorted(res["pool_positive_stocks"]) == ["H1", "H2"]
    assert res["days_checked"] == 21 * (1 + upto)
    cfg["workers"] = 3                                         # 分批方式变了,抽到的照样是同一批
    again = rulecheck.check_rule_against_shape("shape:s001@v1", cfg, rule=_rule(tmp, _rule_text()))
    assert again["pool_stocks"] == res["pool_stocks"]
    cfg["workers"] = 1
    with pytest.raises(rulecheck.RuleShapeMismatch) as ei:     # 没有卡成立日的随机股上规则成立:拒
        rulecheck.check_rule_against_shape("shape:s001@v1", cfg,
                                           rule=_rule(tmp, _rule_text("pk and dist and dry or c < 0.6"), "low.py"))
    assert "卡说不成立" in str(ei.value) and any(f"D{i} 20" in str(ei.value) for i in range(8))


def test_rare_card_refused_when_cap_reached(env):
    """抽到上限还凑不够有卡成立日的随机股:拒,报错写明找到几只、上限多少、在哪调高、这次用了多久。"""
    cfg, pkl_dir, tmp = env
    _rare_pool(pkl_dir)
    _card()
    order = rulecheck.pool_order(cfg, "s001", ["QMM"])
    cap = max(order.index("H1"), order.index("H2"))             # 第 2 只有卡成立日的正好抽不到
    cfg["shape_check"].update(pool_positive_stocks=2, pool_max_stocks=cap)
    with pytest.raises(rulecheck.RuleShapeMismatch) as ei:
        rulecheck.check_rule_against_shape("shape:s001@v1", cfg, rule=_rule(tmp, _rule_text()))
    msg = str(ei.value)
    assert f"沿固定顺序抽了 {cap} 只(上限 {cap} 只),其中有卡成立日的只有 1 只,至少要 2 只(待验证)" in msg
    assert "shape_check.pool_max_stocks" in msg and f"这次抽 {cap} 只用了 " in msg and "等比例增加" in msg


def test_draw_pool_stops_exactly_where_count_is_reached(cw_env, monkeypatch):
    """抽到第几只为止只看顺序:截到凑满的那一只(第 3 只有卡成立日的排在第 10 位),和每批算几只(进程数)无关。"""
    import pandas as pd

    cfg, _ = cw_env
    cfg["view_floor"] = FLOOR
    names = [f"Z{i:02d}" for i in range(20)]
    monkeypatch.setattr("chart_workflow.securities.local_symbols", lambda cfg: names)
    monkeypatch.setattr("chart_workflow.loader.trading_dates", lambda cfg, s: pd.DatetimeIndex(["2025-07-01"]))
    order = rulecheck.pool_order(cfg, "s001", [])
    hits = {order[i] for i in (1, 6, 9)}
    monkeypatch.setattr(rulecheck, "materials", lambda cfg, card, els, batch, *a, **k:
                        {s: (None, {"2025-07-01": (s in hits, "")}, {}) for s in batch})
    cfg["shape_check"] = {**cfg["shape_check"], "pool_positive_stocks": 3, "pool_max_stocks": 20}
    for workers in (1, 4, 16):
        cfg["workers"] = workers
        got = rulecheck.draw_pool(cfg, {}, {}, "s001", [], None, None, None)
        assert got["stocks"] == order[:10] and got["positive"] == [order[1], order[6], order[9]]


def test_pool_order_from_shape_id_only(cw_env, tmp_path):
    """抽股顺序只由卡的编号定(不含版本),和排除名单的顺序无关;样本股不在里面;看图范围里一天行情都没有的
    股票抽的时候跳过。"""
    cfg, pkl_dir = cw_env
    cfg["view_floor"] = FLOOR
    for i in range(12):
        make_stock(seed=i, end="2025-12-31").to_pickle(pkl_dir / f"S{i:02d}.pkl")
    make_stock(seed=99, end="2025-03-31").to_pickle(pkl_dir / "OLD.pkl")          # 看图下界之前就没了
    a = rulecheck.pool_order(cfg, "s001", ["S00", "S01"])
    assert a == rulecheck.pool_order(cfg, "s001", ["S01", "S00"]) and not {"S00", "S01"} & set(a)
    assert rulecheck.pool_order(cfg, "s002", ["S00", "S01"]) != a
    import inspect
    assert "version" not in str(inspect.signature(rulecheck.pool_order)) and "n" not in inspect.signature(
        rulecheck.pool_order).parameters
    cfg["shape_check"] = {**cfg["shape_check"], "pool_positive_stocks": 100, "pool_max_stocks": 100}
    never = _rule(tmp_path, "import pandas as pd\n\ndef signal(df):\n    return pd.Series(False, index=df.index)\n")
    got = rulecheck.draw_pool(cfg, {"ingredients": [], "triggers": []}, {}, "s001", ["S00"], never, None, None)
    assert got["stocks"] == [x for x in rulecheck.pool_order(cfg, "s001", ["S00"]) if x != "OLD"]


def test_unchanged_revision_draws_same_pool(env):
    """内容不变的改版:抽到的随机股和上一版是同一批(换版本号挑不了股票)。"""
    cfg, pkl_dir, tmp = env
    _rare_pool(pkl_dir)
    _card()
    cfg["shape_check"]["pool_positive_stocks"] = 1
    card = shapes.load_card("s001")["versions"][0]["card"]
    shapes.apply(_decision({"act": "revise_shape", "target": {"shape_id": "s001"},
                            "value": {"card": {**card, "ingredients": [
                                {k: v for k, v in i.items() if k != "element_version"} for i in card["ingredients"]]},
                                "change": "只改了说明", "from_ann": ["a1"]}}))
    rule = _rule(tmp, _rule_text())
    v1 = rulecheck.check_rule_against_shape("shape:s001@v1", cfg, rule=rule)
    v2 = rulecheck.check_rule_against_shape("shape:s001@v2", cfg, rule=rule)
    assert v1["pool_stocks"] == v2["pool_stocks"] and v1["pool_positive_stocks"] == v2["pool_positive_stocks"]


def test_daily_materials_cached_within_run_and_keyed_by_inputs(env, monkeypatch):
    """同一次运行里第二次核对不重算逐日卡说和规则文件信号;数据文件、规则文件或配置变了就重算。"""
    import os

    cfg, pkl_dir, tmp = env
    monkeypatch.setattr(rulecheck, "_CACHE", {})
    calls = {"says": 0, "signal": 0}
    real_v, real_s = rulecheck._verdicts, rulecheck._signal
    monkeypatch.setattr(rulecheck, "_verdicts", lambda *a: calls.__setitem__("says", calls["says"] + 1) or real_v(*a))
    monkeypatch.setattr(rulecheck, "_signal", lambda *a: calls.__setitem__("signal", calls["signal"] + 1) or real_s(*a))
    _card()
    rule = _rule(tmp, _rule_text())

    def run():
        calls.update(says=0, signal=0)
        rulecheck.check_rule_against_shape("shape:s001@v1", cfg, rule=rule)
        return dict(calls)

    assert run() == {"says": 1, "signal": 1}
    assert run() == {"says": 0, "signal": 0}
    st = os.stat(pkl_dir / "QMM.pkl")
    os.utime(pkl_dir / "QMM.pkl", ns=(st.st_atime_ns, st.st_mtime_ns + 10**9))      # 数据文件变了
    assert run() == {"says": 1, "signal": 1}
    with open(rule, "a") as f:                                                        # 规则文件变了
        f.write("\n# 改了一行注释\n")
    assert run() == {"says": 0, "signal": 1}
    cfg["facts"] = {**cfg["facts"], "recent_dist_bars": cfg["facts"]["recent_dist_bars"]}
    cfg["m_period"] = cfg["m_period"] + 0                                            # 配置没变:照样命中
    assert run() == {"says": 0, "signal": 0}
    cfg["shape_check"]["pool_max_stocks"] = 299                                       # 配置变了
    assert run() == {"says": 1, "signal": 1}


def test_parallel_daily_check_matches_serial(env, monkeypatch):
    """逐日核对按股票并行(workers > 1)时逐日判卡真在子进程里跑,结果和单进程相同。"""
    import os

    cfg, pkl_dir, tmp = env
    monkeypatch.setattr(rulecheck, "_CACHE", {})
    _scaled().to_pickle(pkl_dir / "QMH.pkl")
    _scaled(0.7).to_pickle(pkl_dir / "QMG.pkl")
    _card()
    cfg["shape_check"]["pool_positive_stocks"] = 2
    rule = _rule(tmp, _rule_text())
    serial = rulecheck.check_rule_against_shape("shape:s001@v1", cfg, rule=rule)
    pids, real = tmp / "pids.txt", rulecheck._verdicts

    def spy(*a):                                   # 子进程是 fork 出来的,带着这个替换
        with open(pids, "a") as f:
            f.write(f"{os.getpid()}\n")
        return real(*a)

    monkeypatch.setattr(rulecheck, "_verdicts", spy)
    cfg["workers"] = 2
    assert rulecheck.check_rule_against_shape("shape:s001@v1", cfg, rule=rule) == serial
    seen = set(pids.read_text().split())
    assert seen - {str(os.getpid())}                           # 随机股那一批在子进程里判卡
