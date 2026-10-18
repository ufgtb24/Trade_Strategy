"""卡成立日清单(chart_workflow/cardhits.py):只在调试模式下用;在调试段里找出「卡说成立」的天,连续成立算一次取第一天,
抽样种子固定可重现,标之前图窗只到成立日;「是 / 不是」、归类、小结只写调试账;正式模式一律拒绝。

正常使用必须能过的(拦多了比拦少了代价大):建一张正常的卡 → 生成清单 → 标完 → 归类 → 小结 → 清空调试账;
卡在调试段里一天都不成立、卡上有待写代码的要素、有手写触发时,给清楚的提示而不是报错。

合成数据:C0..C5 六只几何随机游走(2021-01-04 起,调试模式读到 2022-09-30 为止);卡 = 按收盘至少越过一个峰
(必须有),没有触发;样本是 C0 在 2022-03-01 的一张标注。随机抽股的下限、上限调小(有成立日的满 2 只、最多 5 只)。
逐日按事实表判卡一只股票要好几秒:只核对清单本身的几个测试(和「必须能过」的整套流程)真算;其余的把逐日卡说换成
「收盘创 20 日新高」(fast),省时间,不影响它们要核对的东西。"""
import json
from pathlib import Path

import pandas as pd
import pytest

from chart_workflow import cardhits, debugroot, listfile, mode, rulecheck, shapes, state, views
from chart_workflow.config import root_dir
from tests.chart_workflow.conftest import make_stock
from tests.chart_workflow.test_debug_mode import _fresh_caches, dbg, digest, main_formal  # noqa: F401
from tests.chart_workflow.test_shapes import DET, el_op

PK1 = {"row": "F01", "value": "n_cleared", "cond": "at_least", "user_params": {"x": 1}}
NONE_CLEARED = {"row": "F01", "value": "n_cleared", "cond": "at_most", "user_params": {"x": 0}}
SAMPLE = ("a1", "C0", "2022-03-01")


def write_stocks(pkl_dir: Path, n: int = 6, seed: int = 60) -> None:
    for i in range(n):
        make_stock(start="2021-01-04", end="2022-12-30", seed=seed + i, sigma=0.03).to_pickle(pkl_dir / f"C{i}.pkl")


def write_batch(droot: Path, anns=(SAMPLE,)) -> None:
    """调试账里一批大涨段标注:(ann_id, 代码, 买点)。"""
    d = droot / "annotations"
    d.mkdir(parents=True, exist_ok=True)
    (d / "b1.json").write_text(json.dumps({
        "schema": "chart_workflow.annotations/2", "batch_id": "b1", "list_id": "dbg-big", "train_end": mode.DEBUG_END,
        "list_kind": "bigmoves", "outcome_visible": True,
        "annotations": [{"ann_id": a, "item_id": f"{s}@{d_}", "symbol": s, "range_start": None, "range_end": None,
                         "label": "positive", "note": "", "buy_points": [{"date": d_, "primary": True}]}
                        for a, s, d_ in anns]}, ensure_ascii=False))


def make_card(elements=(("pk", "按收盘越过前面的峰", PK1, "must"),), triggers=(), custom=None,
              name="越过前高") -> str:
    """调试模式下经决定文件建一张卡(样本 a1),返回卡编号。elements:(as_, 名字, 定义 | None | 已有要素编号, 角色);
    定义写已有要素编号(如 "E001")就直接引用那一条,不新建。"""
    trig = [{"trig_id": f"t{k + 1}", "term": t, **DET} for k, t in enumerate(triggers)]
    if custom:
        trig.append({"trig_id": f"t{len(trig) + 1}", "term": "custom", "text": custom, "origin": "user_written",
                     "said_first_match": custom})
    ops = [el_op(a, nm, d, needs=None if d else "现有事实算不出「横着走了多久」") for a, nm, d, _ in elements
           if not isinstance(d, str)]
    ref = {a: d if isinstance(d, str) else f"${a}" for a, _, d, _ in elements}
    card = {"ingredients": [{"ing_id": f"i{k + 1}", "element": ref[a], "role": role, "origin": "user_written",
                             "said_first_match": nm} for k, (a, nm, _, role) in enumerate(elements)],
            "triggers": trig, "story": None, "exit_pref": None}
    ops.append({"act": "create_shape", "value": {"name": {"value": name, "origin": "user_written"}, "card": card,
                                                 "change": "新建", "from_ann": [SAMPLE[0]]}})
    ops.append({"act": "add_case", "target": {"shape_id": "$new"}, "value": {
        "ann_id": SAMPLE[0], "buy_date": {"value": SAMPLE[2], "origin": "user_written"},
        "trigger_ref": "t1" if trig else None, "shape_claim": {"value": "new", "origin": "user_written"},
        "divergence_answers": [], "facts_ref": f"facts/b1.json#{SAMPLE[0]}/{SAMPLE[2]}"}})
    _, touched = shapes.apply({"schema": shapes.DECISION_SCHEMA, "mode": mode.DEBUG, "actor": "session",
                               "surface": "chat", "ctx": {"list_id": "dbg-big", "list_kind": "bigmoves",
                                                          "outcome_visible": True}, "ops": ops})
    return touched[0]


@pytest.fixture
def hits(dbg):
    """调试模式、临时调试账、六只合成股、一张正常的卡;返回 (cfg, 调试账, 卡编号)。"""
    cfg, pkl_dir, droot = dbg
    cfg["shape_check"] = {**cfg["shape_check"], "pool_positive_stocks": 2, "pool_max_stocks": 5}
    write_stocks(pkl_dir)
    write_batch(droot)
    return cfg, droot, make_card()


def _fake_verdicts(cfg, card, els, df):
    lo, hi = rulecheck._view_range(cfg)
    c = df["close"]
    brk = c > c.rolling(20).max().shift(1)
    return {d.strftime("%Y-%m-%d"): (bool(brk[d]), "" if brk[d] else "没创 20 日新高")
            for d in df.index[(df.index >= lo) & (df.index <= hi)]}


@pytest.fixture
def fast(monkeypatch):
    monkeypatch.setattr(rulecheck, "_verdicts", _fake_verdicts)


def _says(cfg, sid, symbols):
    _, cards, els = shapes.checked_state()
    card = cards[sid]["versions"][-1]["card"]
    return {s: m[1] for s, m in rulecheck.materials(cfg, card, els, symbols, None, None, None).items()}


# ── 生成清单 ─────────────────────────────────────────────────────────────────

def test_episodes_merge_consecutive_days():
    T, F = (True, ""), (False, "x")
    says = {"2022-03-01": T, "2022-03-02": T, "2022-03-03": F, "2022-03-04": T, "2022-03-07": (None, "u"),
            "2022-03-08": T, "2022-03-09": T}
    assert cardhits.episodes(says) == ["2022-03-01", "2022-03-04", "2022-03-08"]
    assert cardhits.episodes({}) == []


def test_make_lists_first_day_of_each_run_inside_debug_segment(hits, state_dir):
    """正常的卡:清单里每张是一段连续成立的第一天;图窗只到成立日,露出终点不越过调试段;同股不互相露底;
    只写调试账和调试模式的清单目录,正式账一个字节不变。"""
    cfg, droot, sid = hits
    before = digest(state_dir)
    res = cardhits.make(sid, cfg=cfg)
    doc, row = res["doc"], res["row"]
    assert res["path"] == root_dir(cfg) / "lists" / f"dbg-hits-{sid}-v1.json" and res["path"].exists()
    assert doc["kind"] == cardhits.KIND and doc["mode"] == mode.DEBUG and doc["title"].startswith("【调试】")
    assert 0 < len(doc["items"]) <= cardhits.MAX_ITEMS and row["n_episodes"] >= len(doc["items"])
    says = _says(cfg, sid, sorted({it["symbol"] for it in doc["items"]}))
    for it in doc["items"]:
        days = sorted(says[it["symbol"]])
        i = days.index(it["t"])
        assert says[it["symbol"]][it["t"]][0] is True
        assert i == 0 or says[it["symbol"]][days[i - 1]][0] is not True        # 是那一段的第一天
        assert it["view_end"] == it["t"] < it["reveal_end"] <= mode.DEBUG_END
        assert mode.DEBUG_START <= it["view_start"] < it["t"]
        assert it["marks"] == {"decision": it["t"]} and it["metrics"] == {} and "xcheck" not in it
    by_sym = {}
    for it in doc["items"]:
        for o in by_sym.get(it["symbol"], []):
            assert not (o["view_start"] <= it["t"] <= o["reveal_end"] or it["view_start"] <= o["t"] <= it["reveal_end"])
        by_sym.setdefault(it["symbol"], []).append(it)
    assert [r["list_id"] for r in cardhits.read_lists()] == [doc["list_id"]]
    assert doc["params"]["card_hits"]["card_lines"] == ["必须有:E001「按收盘越过前面的峰」(按收盘越过的峰个数至少 1)"]
    assert digest(state_dir) == before
    assert (droot / "card_review" / "lists.jsonl").exists()


def test_sampling_is_reproducible(fast, hits):
    """种子固定:同一张卡同一版,重跑出来的一样;只列 3 张时就是全量顺序的前 3 张。"""
    cfg, _, sid = hits
    full = cardhits.make(sid, list_id="dbg-hits-a", cfg=cfg)["doc"]["items"]
    again = cardhits.make(sid, list_id="dbg-hits-b", cfg=cfg)["doc"]["items"]
    few = cardhits.make(sid, list_id="dbg-hits-c", max_items=3, cfg=cfg)["doc"]["items"]
    assert [x["item_id"] for x in again] == [x["item_id"] for x in full]
    assert [x["item_id"] for x in few] == [x["item_id"] for x in full][:3]
    assert len({x["item_id"] for x in full}) == len(full) >= 4


def test_already_seen_days_left_out(fast, hits):
    """以前已经仔细看过后面走势的成立日(比如卡自己的样本、以前标过的)不再列。"""
    cfg, _, sid = hits
    first = cardhits.make(sid, list_id="dbg-hits-a", cfg=cfg)["doc"]["items"][0]
    views.record(surface="manual", event="show_chart", outcome_visible=True, charts=[
        {"symbol": first["symbol"], "start": first["view_start"], "end": first["reveal_end"]}])
    res = cardhits.make(sid, list_id="dbg-hits-b", cfg=cfg)
    assert first["item_id"] not in [x["item_id"] for x in res["doc"]["items"]]
    assert res["row"]["n_seen_excluded"] >= 1


def test_default_name_reused_says_where_it_is(fast, hits):
    cfg, _, sid = hits
    cardhits.make(sid, cfg=cfg)
    with pytest.raises(cardhits.CardHitsRefused, match=f"已经生成过.*dbg-hits-{sid}-v1"):
        cardhits.make(sid, cfg=cfg)


@pytest.mark.parametrize("how", ["never", "pending", "custom"])
def test_cannot_list_gives_clear_notice_not_error(dbg, capsys, monkeypatch, how):
    """一天都不成立、卡上有待写代码的要素、有手写触发:不生成清单,打印为什么和出路(不报错),记一行给小结。"""
    cfg, pkl_dir, droot = dbg
    cfg["shape_check"] = {**cfg["shape_check"], "pool_positive_stocks": 1, "pool_max_stocks": 1}
    write_stocks(pkl_dir, n=2)
    write_batch(droot)
    if how == "never":          # 「至少越过一个峰」和「一个峰都没越过」同时必须有:哪天都不成立
        sid = make_card(elements=(("pk", "越过前面的峰", PK1, "must"), ("none", "一个峰都没越过", NONE_CLEARED, "must")))
    elif how == "pending":
        sid = make_card(elements=(("pk", "越过前面的峰", PK1, "must"), ("flat", "突破前横着走", None, "must")))
    else:
        sid = make_card(custom="放量阳线过前高")
    monkeypatch.setattr(cardhits, "load_config", lambda: cfg)
    cardhits.main(["make", "--shape", sid])                  # 不 SystemExit
    out = capsys.readouterr().out
    want = {"never": "一天都不成立", "pending": "待写代码", "custom": "手写触发"}[how]
    assert out.startswith("提示:") and want in out and "出路" in out
    assert not (root_dir(cfg) / "lists").exists() or not list((root_dir(cfg) / "lists").glob("*.json"))
    row, = cardhits.read_lists()
    assert row["list_id"] is None and row["empty"]["kind"] == {"never": "never", "pending": "pending_code",
                                                                "custom": "custom_trigger"}[how]
    s = cardhits.summary(save=False)
    assert want in cardhits.render_summary(s)


def test_all_too_close_to_segment_start_gives_notice(fast, hits, monkeypatch):
    """成立日都紧挨着调试段开头(图上留不出成立之前的形态):不生成清单,给提示。"""
    cfg, _, sid = hits
    monkeypatch.setattr(cardhits, "_first_allowed", lambda cfg, symbol: "2099-01-01")
    res = cardhits.make(sid, cfg=cfg)
    assert res["path"] is None and res["row"]["empty"]["kind"] == "too_early"
    assert "紧挨着调试段开头" in res["row"]["empty"]["text"] and res["row"]["n_too_early"] > 0


# ── 标「是 / 不是」与归类 ───────────────────────────────────────────────────────

def test_marks_append_only_first_flag(fast, hits, state_dir):
    cfg, droot, sid = hits
    doc = cardhits.make(sid, cfg=cfg)["doc"]
    a, b = doc["items"][0]["item_id"], doc["items"][1]["item_id"]
    before = digest(state_dir)
    with pytest.raises(cardhits.CardHitsRefused, match="写一句为什么"):
        cardhits.record_mark(doc, a, "no", "  ")
    with pytest.raises(cardhits.CardHitsRefused, match="只能标"):
        cardhits.record_mark(doc, a, "maybe")
    with pytest.raises(cardhits.CardHitsRefused, match="没有"):
        cardhits.record_mark(doc, "ZZZ@2022-01-03", "yes")
    m1 = cardhits.record_mark(doc, a, "yes", "理由不收")
    m2 = cardhits.record_mark(doc, b, "no", "放量不在突破那天")
    m3 = cardhits.record_mark(doc, a, "no", "看了后面改主意")
    assert (m1["first"], m2["first"], m3["first"]) == (True, True, False) and m1["reason"] == ""
    got = cardhits.marks_of(doc["list_id"])
    assert got[a]["first"]["verdict"] == "yes" and got[a]["latest"]["verdict"] == "no" and got[a]["n"] == 2
    assert m2["shape_id"] == sid and m2["version"] == 1
    assert digest(state_dir) == before and (droot / "card_review" / "marks.jsonl").exists()


def test_classify_rules(fast, hits):
    cfg, _, sid = hits
    doc = cardhits.make(sid, cfg=cfg)["doc"]
    yes = cardhits.record_mark(doc, doc["items"][0]["item_id"], "yes")
    no = cardhits.record_mark(doc, doc["items"][1]["item_id"], "no", "放量不在突破那天")
    with pytest.raises(cardhits.CardHitsRefused, match="只给「不是」"):
        cardhits.classify("mark", yes["mark_id"], "先后")
    with pytest.raises(cardhits.CardHitsRefused, match="不认识的类别"):
        cardhits.classify("mark", no["mark_id"], "差不多")
    with pytest.raises(cardhits.CardHitsRefused, match="没有标记"):
        cardhits.classify("mark", "nope", "先后")
    with pytest.raises(cardhits.CardHitsRefused, match="没有记成过待写代码"):
        cardhits.classify("element", "E001", "缺一个量")
    cardhits.classify("mark", no["mark_id"], "缺一个量")
    cardhits.classify("mark", no["mark_id"], "relation:same_event", by="user", note="用户说是同一件事")
    cur = cardhits.current_categories()[("mark", no["mark_id"])]
    assert (cur["category"], cur["by"], cur["changes"]) == ("relation:same_event", "user", 2)
    assert cardhits.pending()["marks"] == []


def test_summary_counts_and_relation_share(fast, dbg):
    """两张卡:一张的「不是」归成事件关系、一张只缺一个量 → 碰到过关系类问题 1 / 2 张,不超过一半,不建议改;
    再给第二张卡引用的待写代码要素归成事件关系 → 2 / 2,建议改。原始数字、原话、谁归的都在。"""
    cfg, pkl_dir, droot = dbg
    cfg["shape_check"] = {**cfg["shape_check"], "pool_positive_stocks": 2, "pool_max_stocks": 5}
    write_stocks(pkl_dir)
    write_batch(droot)
    s1 = make_card()
    s2 = make_card(elements=(("pk", "按收盘越过一个峰", "E001", "must"), ("flat", "突破前横着走", None, "bonus")),
                   name="越过前高带横盘")
    d1 = cardhits.make(s1, cfg=cfg)["doc"]
    d2 = cardhits.make(s2, cfg=cfg, list_id="dbg-hits-two")["doc"]
    m = [cardhits.record_mark(d1, d1["items"][0]["item_id"], "yes"),
         cardhits.record_mark(d1, d1["items"][1]["item_id"], "no", "先跌后横盘的顺序不对"),
         cardhits.record_mark(d2, d2["items"][0]["item_id"], "no", "量不够大")]
    cardhits.record_mark(d1, d1["items"][0]["item_id"], "no", "看完走势改了")        # 看过走势后改的
    cardhits.classify("mark", m[1]["mark_id"], "先后")
    cardhits.classify("mark", m[2]["mark_id"], "缺一个量")
    s = cardhits.summary()
    assert s["n_cards"] == 2
    c1, c2 = s["cards"]
    assert (c1["lists"][0]["yes"], c1["lists"][0]["no"], c1["lists"][0]["changed"]) == (1, 1, 1)
    assert c1["lists"][0]["unmarked"] == len(d1["items"]) - 2
    assert c1["touched_relation"] and not c2["touched_relation"]
    assert (s["n_cards_touched_relation"], s["suggest_switch"]) == (1, False)
    assert [r["reason"] for r in s["by_category"]["relation:sequence"]["reasons"]] == ["先跌后横盘的顺序不对"]
    assert [r["reason"] for r in s["by_category"]["quantity"]["reasons"]] == ["量不够大"]
    assert len(s["unclassified"]["elements"]) == 1 and len(s["changed_after_reveal"]) == 1
    flat = s["unclassified"]["elements"][0]["element_id"]
    cardhits.classify("element", flat, "挑哪一次")
    s = cardhits.summary()
    assert (s["n_cards_touched_relation"], s["share_touched_relation"], s["suggest_switch"]) == (2, 1.0, True)
    text = cardhits.render_summary(s)
    for needle in ("建了 2 张形态卡", "先跌后横盘的顺序不对", "会话归的", "建议把形态卡改成「事件加关系」", "结论由你拍板",
                   "看过走势后改了的 1 张"):
        assert needle in text, needle
    assert len(list((droot / "card_review" / "summaries").glob("*.json"))) == 2


def test_normal_use_end_to_end_then_clear(hits, state_dir, monkeypatch, capsys):
    """正常使用必须能过:命令行生成 → 标完 → 归类 → 小结 → 清空调试账;正式账一个字节不变。"""
    cfg, droot, sid = hits
    before = digest(state_dir)
    monkeypatch.setattr(cardhits, "load_config", lambda: cfg)
    cardhits.main(["make", "--shape", sid, "--max", "5"])
    assert "写入" in capsys.readouterr().out
    doc = json.loads((root_dir(cfg) / "lists" / f"dbg-hits-{sid}-v1.json").read_text())
    listfile.validate(doc)
    for k, it in enumerate(doc["items"]):
        cardhits.record_mark(doc, it["item_id"], "yes" if k % 2 else "no", "" if k % 2 else f"理由{k}")
    cardhits.main(["pending"])
    pend = cardhits.pending()["marks"]
    assert len(pend) == (len(doc["items"]) + 1) // 2
    for m in pend:
        cardhits.main(["classify", "--mark", m["mark_id"], "--category", "同一件事"])
    capsys.readouterr()
    cardhits.main(["summary"])
    out = capsys.readouterr().out
    assert f"还没标 0 张" in out and "碰到过关系类问题的卡:1 / 1 张" in out
    debugroot.main(["show"])
    assert "卡成立日的标记与归类" in capsys.readouterr().out
    path, removed = debugroot.clear()
    assert "card_review" in removed and not (droot / "card_review").exists()
    assert digest(state_dir) == before


# ── 正式模式一律拒绝 ─────────────────────────────────────────────────────────

def test_formal_mode_refuses_everything(fast, hits, monkeypatch, state_dir, capsys):
    cfg, _, sid = hits
    doc = cardhits.make(sid, cfg=cfg)["doc"]
    mark = cardhits.record_mark(doc, doc["items"][0]["item_id"], "no", "x")
    monkeypatch.delenv(mode.ENV_VAR)
    before = digest(state_dir)
    for call in (lambda: cardhits.make(sid, cfg=cfg), lambda: cardhits.record_mark(doc, doc["items"][1]["item_id"], "yes"),
                 lambda: cardhits.classify("mark", mark["mark_id"], "先后"), cardhits.summary, cardhits.pending,
                 cardhits.read_marks):
        with pytest.raises(cardhits.CardHitsRefused, match="只在调试模式下用"):
            call()
    untagged = {k: v for k, v in doc.items() if k != "mode"}          # 去掉调试标记、换成正式的名字也不行
    with pytest.raises(listfile.ListValidationError, match="只在调试模式下用"):
        listfile.validate({**untagged, "list_id": "r-hits"})
    for argv in (["make", "--shape", sid], ["summary"], ["pending"]):
        with pytest.raises(SystemExit):
            cardhits.main(argv)
    assert "只在调试模式下用" in capsys.readouterr().err
    assert digest(state_dir) == before


def test_list_validation_keeps_outcome_out(fast, hits):
    """卡成立日清单的条目:图窗终点必须是成立日、露出终点不越过调试段、不带结果字段。"""
    cfg, _, sid = hits
    doc = cardhits.make(sid, cfg=cfg)["doc"]
    it = doc["items"][0]
    for bad in ({"view_end": it["reveal_end"]}, {"reveal_end": "2022-10-31"}, {"metrics": {"rel": 1.0}},
                {"marks": {"decision": it["t"], "peak_date": it["reveal_end"]}}):
        with pytest.raises(listfile.ListValidationError):
            listfile.validate({**doc, "items": [{**it, **bad}]})
