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
def hits20(dbg):
    """同 hits,但有 20 只合成股(看几张卡、几个版本会不会挤在同一批股票上)。"""
    cfg, pkl_dir, droot = dbg
    write_stocks(pkl_dir, n=20)
    write_batch(droot)
    return cfg, droot, make_card()


@pytest.fixture
def fast(monkeypatch):
    monkeypatch.setattr(rulecheck, "_verdicts", _fake_verdicts)


def revise_card(sid: str) -> None:
    """给卡出一个新版本(内容不变,只改说明)。"""
    _, cards, _ = shapes.checked_state()
    card = cards[sid]["versions"][-1]["card"]
    plain = {**card, "ingredients": [{k: v for k, v in i.items() if k != "element_version"} for i in card["ingredients"]]}
    shapes.apply({"schema": shapes.DECISION_SCHEMA, "mode": mode.DEBUG, "actor": "session", "surface": "chat",
                  "ctx": {"list_id": "dbg-big", "list_kind": "bigmoves", "outcome_visible": True},
                  "ops": [{"act": "revise_shape", "target": {"shape_id": sid},
                           "value": {"card": plain, "change": "改了说明", "from_ann": [SAMPLE[0]]}}]})


def open_list(doc: dict) -> None:
    """像网页那样打开清单:记一条看过(没标的图只画到成立日)。"""
    views.record(surface="web", event="open_list", outcome_visible=False, list_id=doc["list_id"],
                 list_kind=cardhits.KIND, list_doc=doc)


def reveal_and_mark(doc: dict, it: dict, verdict: str = "yes", reason: str = "") -> dict:
    """像网页那样标一张:先记一条露出成立日之后走势的看过,再写标记。"""
    views.record(surface="web", event="show_chart", outcome_visible=True, list_id=doc["list_id"],
                 list_kind=cardhits.KIND, charts=[{"symbol": it["symbol"], "start": it["view_start"],
                                                   "end": it["reveal_end"]}])
    return cardhits.record_mark(doc, it["item_id"], verdict, reason)


def _drawn_after_t(it: dict, drawn: dict) -> bool:
    """drawn(打开过的清单里没标的图,只画到成立日)有没有画到 it 成立日之后、露出终点以前。"""
    return drawn["symbol"] == it["symbol"] and drawn["t"] > it["t"] and drawn["view_start"] <= it["reveal_end"]


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
    for it in doc["items"]:                     # 同一只股票的两张,整段可见范围(图窗起点到露出终点)不交叠
        for o in by_sym.get(it["symbol"], []):
            assert not (o["view_start"] <= it["reveal_end"] and it["view_start"] <= o["reveal_end"]), (o, it)
        by_sym.setdefault(it["symbol"], []).append(it)
        earlier = {d for d, (v, _) in says[it["symbol"]].items() if v is True and it["view_start"] <= d < it["t"]}
        runs = it["card_true_runs"]
        assert all(it["view_start"] <= x <= y < it["t"] for x, y in runs)
        assert {d for d in earlier if any(x <= d <= y for x, y in runs)} == earlier      # 成立日之前卡也成立的天都标出
        assert all(says[it["symbol"]][x][0] is True and says[it["symbol"]][y][0] is True for x, y in runs)
    assert any(it["card_true_runs"] for it in doc["items"])
    assert "每只股票只列一张" in doc["params"]["card_hits"]["note"]
    reg, = cardhits.read_lists()
    assert reg["list_id"] == doc["list_id"] and reg["list_sha12"] == views.list_sha12(
        json.loads(res["path"].read_text())) and len(reg["items"]) == len(doc["items"])
    assert doc["params"]["card_hits"]["card_lines"] == ["必须有:E001「按收盘越过前面的峰」(按收盘越过的峰个数至少 1)"]
    assert digest(state_dir) == before
    assert (droot / "card_review" / "lists.jsonl").exists()


def test_sampling_is_reproducible(fast, hits):
    """种子固定:同一张卡同一版,重跑出来的一样;只列 3 张时就是全量顺序的前 3 张。(每份标完再生成下一份:
    没标的图会挡住下一份里和它交叠的天;这里只记标记、不记看过,所以下一份还能列同样的天。)"""
    cfg, _, sid = hits

    def make_and_mark(lid, **kw):
        doc = cardhits.make(sid, list_id=lid, cfg=cfg, **kw)["doc"]
        for it in doc["items"]:
            cardhits.record_mark(doc, it["item_id"], "yes")
        return doc["items"]
    full = make_and_mark("dbg-hits-a")
    again = make_and_mark("dbg-hits-b")
    few = make_and_mark("dbg-hits-c", max_items=3)
    assert [x["item_id"] for x in again] == [x["item_id"] for x in full]
    assert [x["item_id"] for x in few] == [x["item_id"] for x in full][:3]
    assert len({x["item_id"] for x in full}) == len(full) >= 4


def test_already_seen_days_left_out(fast, hits):
    """以前已经仔细看过后面走势的成立日(比如卡自己的样本、以前标过的)不再列。"""
    cfg, _, sid = hits
    doc = cardhits.make(sid, list_id="dbg-hits-a", cfg=cfg)["doc"]
    for it in doc["items"]:
        cardhits.record_mark(doc, it["item_id"], "yes")
    first = doc["items"][0]
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


def test_summary_counts_and_relation_share(fast, dbg, monkeypatch):
    """四张卡:s001 的「不是」归成先后;s002 的「不是」只缺一个量,引用待写代码的 E002;s003 也引用 E002、没生成
    清单;s004 什么都没有。E002 还没归类时它不算证据:有证据的 2 张里 1 张碰到过关系类问题,连同没证据的 1 / 4;
    还有没归类的、标注也不够数,不给建议,写明差什么。把 E002 归成「挑哪一次」→ s003 也有了证据,有证据的 3 张都
    碰到过(s002、s003 是靠共用的 E002,注明共用);标注数还不够照样不给建议,下限放到 3 下才给「建议改」,
    并写明凭了几下标注。
    不按卡算的两个比例、每张卡「第一下『不是』几张、其中关系类几张、已标几张」都在。"""
    cfg, pkl_dir, droot = dbg
    cfg["shape_check"] = {**cfg["shape_check"], "pool_positive_stocks": 2, "pool_max_stocks": 5}
    write_stocks(pkl_dir)
    write_batch(droot)
    s1 = make_card()
    s2 = make_card(elements=(("pk", "按收盘越过一个峰", "E001", "must"), ("flat", "突破前横着走", None, "bonus")),
                   name="越过前高带横盘")
    s3 = make_card(elements=(("pk", "按收盘越过一个峰", "E001", "must"), ("flat", "突破前横着走", "E002", "bonus")),
                   triggers=("T3",), name="创新高带横盘")
    make_card(elements=(("pk", "按收盘越过一个峰", "E001", "must"),), triggers=("T7",), name="越过前高缩量")
    d1 = cardhits.make(s1, cfg=cfg, max_items=2)["doc"]
    m = [cardhits.record_mark(d1, d1["items"][0]["item_id"], "yes"),
         cardhits.record_mark(d1, d1["items"][1]["item_id"], "no", "先跌后横盘的顺序不对")]
    d2 = cardhits.make(s2, cfg=cfg, list_id="dbg-hits-two")["doc"]        # d1 标完了,不受它限制
    m.append(cardhits.record_mark(d2, d2["items"][0]["item_id"], "no", "量不够大"))
    late = cardhits.record_mark(d1, d1["items"][0]["item_id"], "no", "看完走势改了")      # 看过走势后改的
    cardhits.classify("mark", m[1]["mark_id"], "先后")
    cardhits.classify("mark", m[2]["mark_id"], "缺一个量")
    with pytest.raises(cardhits.CardHitsRefused, match="看过走势后改的"):
        cardhits.classify("mark", late["mark_id"], "先后")
    assert cardhits.pending()["marks"] == []                    # 改的那一下不进统计,也不列进待归类
    s = cardhits.summary()
    assert (s["n_cards"], s["n_cards_with_evidence"]) == (4, 2)
    c1, c2, c3, c4 = s["cards"]
    l1 = c1["lists"][0]
    assert (l1["marked"], l1["n_items"], l1["yes"], l1["no"], l1["no_relation"], l1["changed"]) == (2, 2, 1, 1, 1, 1)
    assert c2["lists"][0]["unmarked"] == len(d2["items"]) - 1 and c2["lists"][0]["no_relation"] == 0
    assert [c["has_evidence"] for c in s["cards"]] == [True, True, False, False]
    assert c1["touched_relation"] and not c2["touched_relation"] and not c3["touched_relation"]
    assert (s["n_cards_touched_relation"], s["share_touched_relation"], s["suggest_switch"]) == (1, 1 / 2, None)
    assert s["n_marks_counted"] == 3 and len(s["not_enough"]) == 2
    text = cardhits.render_summary(s)
    assert ("证据还不够,先不给改不改的建议:还有 0 条「不是」的理由、1 条待写代码的要素没归类" in text
            and f"计入统计的标注一共 3 下,至少要 {cardhits.MIN_MARKS} 下" in text and "建议把" not in text)
    assert s["share_touched_relation_all_cards"] == 1 / 4
    assert s["ratios"]["reasons"] == {"n": 2, "classified": 2, "relation": 1, "share": 0.5}
    assert s["ratios"]["elements"] == {"n": 1, "classified": 0, "relation": 0, "share": None}
    assert [r["reason"] for r in s["by_category"]["relation:sequence"]["reasons"]] == ["先跌后横盘的顺序不对"]
    assert [r["reason"] for r in s["by_category"]["quantity"]["reasons"]] == ["量不够大"]
    assert len(s["unclassified"]["elements"]) == 1 and len(s["changed_after_reveal"]) == 1
    flat = s["unclassified"]["elements"][0]["element_id"]
    cardhits.classify("element", flat, "挑哪一次")
    assert cardhits.summary(save=False)["suggest_switch"] is None              # 归完了,标注数还不够
    monkeypatch.setattr(cardhits, "MIN_MARKS", 3)
    s = cardhits.summary()
    assert (s["n_cards_touched_relation"], s["share_touched_relation"], s["suggest_switch"]) == (3, 1.0, True)
    assert s["not_enough"] == []
    assert [c["has_evidence"] for c in s["cards"]] == [True, True, True, False]
    assert [c["evidence_only_shared"] for c in s["cards"]] == [[], [], [flat], []]       # s003 一下没标,只凭共用的 E002
    assert s["ratios"]["elements"] == {"n": 1, "classified": 1, "relation": 1, "share": 1.0}
    assert any(f"和 {s3} 共用" in t for t in s["cards"][1]["touched_relation"])
    text = cardhits.render_summary(s)
    for needle in ("建了 4 张形态卡", "其中有证据的 3 张", "已标 2 / 2 张", "其中归成关系类的 1 张", "先跌后横盘的顺序不对",
                   "会话归的", "所有第一下「不是」的理由 2 条,归了类的 2 条里关系类 1 条(50%)",
                   "有证据的 3 张里 3 张(100%);连同没证据的是 3 / 4 张", "凭计入统计的 3 下标注、有证据的 3 张卡",
                   "建议把形态卡改成「事件加关系」",
                   "结论由你拍板", "看过走势后改了的 1 张", "每只股票只列一张", f"和 {s3} 共用",
                   f"一下都没标过,只凭和别的卡共用的 {flat} 算作有证据",
                   f"有证据的卡里,{s3} 一下都没标过,只凭和别的卡共用的待写代码要素算作有证据"):
        assert needle in text, needle
    assert len(list((droot / "card_review" / "summaries").glob("*.json"))) == 2


def test_same_name_once_per_debug_ledger_and_summary_dedupes(fast, hits):
    """调试账是各个目录共用的一本:同名清单在别的目录生成过(这里看不到那个文件),再生成就拒;早先重复登记的,
    小结只算一次。"""
    cfg, droot, sid = hits
    res = cardhits.make(sid, list_id="dbg-hits-x", cfg=cfg)
    cardhits.record_mark(res["doc"], res["doc"]["items"][0]["item_id"], "no", "量不够")
    res["path"].unlink()                                        # 像是在另一个目录里生成的
    with pytest.raises(cardhits.CardHitsRefused, match="生成登记里已经有清单 dbg-hits-x"):
        cardhits.make(sid, list_id="dbg-hits-x", cfg=cfg)
    with (droot / "card_review" / "lists.jsonl").open("a") as f:      # 早先的重复登记
        f.write(json.dumps(res["row"], ensure_ascii=False) + "\n")
    s = cardhits.summary(save=False)
    assert len(s["cards"][0]["lists"]) == 1 and s["ratios"]["reasons"]["n"] == 1
    assert cardhits.render_summary(s).count("dbg-hits-x") == 1


def test_list_not_in_this_debug_ledger_refused(fast, hits):
    """调试账清空过(清单文件留在别的目录里)、或者清单内容和登记的不一样:标了进不了小结,拒绝。"""
    cfg, _, sid = hits
    doc = cardhits.make(sid, cfg=cfg)["doc"]
    assert cardhits.is_registered(doc)
    with pytest.raises(cardhits.CardHitsRefused, match="不在现在这本调试账的生成登记里"):
        cardhits.record_mark({**doc, "title": "改过"}, doc["items"][0]["item_id"], "yes")
    debugroot.clear()
    assert (root_dir(cfg) / "lists" / f"{doc['list_id']}.json").exists()       # 清单文件在这个目录里,没被清
    with pytest.raises(cardhits.CardHitsRefused, match="不在现在这本调试账的生成登记里"):
        cardhits.record_mark(doc, doc["items"][0]["item_id"], "yes")


def test_unopened_list_elsewhere_blocks_nothing(fast, hits):
    """必须能过:在别的目录(比如 worktree)生成过一份、没打开也没标,回来换个名字再生成,清单一张不少。"""
    cfg, _, sid = hits
    a = cardhits.make(sid, list_id="dbg-hits-a", cfg=cfg)
    a["path"].unlink()                                          # 像是在另一个目录里生成的
    b = cardhits.make(sid, list_id="dbg-hits-b", cfg=cfg)
    assert b["row"]["n_prior_drawn"] == 0 and b["row"]["prior_blockers"] == []
    assert [x["item_id"] for x in b["doc"]["items"]] == [x["item_id"] for x in a["doc"]["items"]]


def test_second_card_after_first_opened_not_marked(fast, hits):
    """必须能过:第一张卡的清单打开了、一张没标,就生成第二张(共用要素)的卡,张数接近这份数据能给的。
    只去掉成立日之后的走势已经在第一份里画出来过的;去掉的记下是哪份清单挡的、在哪个目录。"""
    cfg, _, sid = hits
    a = cardhits.make(sid, list_id="dbg-hits-a", cfg=cfg)
    open_list(a["doc"])
    s2 = make_card(elements=(("pk", "按收盘越过一个峰", "E001", "must"),), triggers=("T3",), name="越过前高创新高")
    with pytest.MonkeyPatch.context() as m:                     # 参照:不排「已经画出来过」的,这份数据能给几张
        m.setattr(cardhits, "_drawn_by_card_lists", lambda rows: {})
        ref = cardhits.make(s2, list_id="dbg-hits-ref", cfg=cfg)["doc"]["items"]
    c = cardhits.make(s2, list_id="dbg-hits-c", cfg=cfg)
    items = c["doc"]["items"]
    assert len(items) >= len(ref) - 1 and len(items) > 0
    assert not any(_drawn_after_t(x, y) for x in items for y in a["doc"]["items"])
    assert c["row"]["n_prior_drawn"] > 0
    assert c["row"]["prior_blockers"][0]["list_id"] == "dbg-hits-a"
    assert c["row"]["prior_blockers"][0]["lists_dir"] == str(a["path"].parent)


def test_new_version_after_marking_a_few(fast, hits):
    """必须能过:v1 的清单打开、标了 3 张就出 v2 再生成,张数接近这份数据能给的(标过的 3 张露出了全段,和它们交叠的
    由「仔细看过」去掉,那是真看过)。"""
    cfg, _, sid = hits
    a = cardhits.make(sid, cfg=cfg)["doc"]
    open_list(a)
    for it in a["items"][:3]:
        reveal_and_mark(a, it)
    revise_card(sid)
    with pytest.MonkeyPatch.context() as m:
        m.setattr(cardhits, "_drawn_by_card_lists", lambda rows: {})
        ref = cardhits.make(sid, list_id="dbg-hits-ref", cfg=cfg)["doc"]["items"]
    d = cardhits.make(sid, cfg=cfg)
    assert d["doc"]["list_id"] == f"dbg-hits-{sid}-v2"
    assert len(d["doc"]["items"]) >= len(ref) - 1 and len(d["doc"]["items"]) > 0


def test_all_days_already_drawn_gives_notice_with_where(fast, hits, capsys, monkeypatch):
    """成立日之后的走势都已经在打开过的清单里画出来过:不生成,提示写清挡路的是哪份清单、在哪个目录、怎么打开。
    (调试段最后一天的成立日之后没有走势可露,挡不住,这里先去掉。)"""
    cfg, _, sid = hits
    orig = cardhits.episodes
    monkeypatch.setattr(cardhits, "episodes", lambda says: [d for d in orig(says) if d < "2022-09-01"])
    a = cardhits.make(sid, list_id="dbg-hits-a", cfg=cfg)
    views.record(surface="web", event="show_chart", outcome_visible=False, list_id="dbg-hits-a",
                 list_kind=cardhits.KIND,
                 charts=[{"symbol": f"C{i}", "start": mode.DEBUG_START, "end": mode.DEBUG_END} for i in range(6)])
    monkeypatch.setattr(cardhits, "load_config", lambda: cfg)
    cardhits.main(["make", "--shape", sid, "--list-id", "dbg-hits-b"])
    out = capsys.readouterr().out
    row = cardhits.read_lists()[-1]
    assert row["list_id"] is None and row["empty"]["kind"] == "prior_drawn"
    for needle in ("提示:", "dbg-hits-a 挡了", str(a["path"].parent), "wf=dbg-hits-a", "出路"):
        assert needle in out, needle


def _second_card() -> str:
    return make_card(elements=(("pk", "按收盘越过一个峰", "E001", "must"),), triggers=("T3",), name="越过前高创新高")


def _late_marks() -> int:
    return sum(bool(m.get("seen_before_mark")) for m in cardhits.read_marks())


def _syms(doc) -> set:
    return {it["symbol"] for it in doc["items"]}


def test_parallel_lists_take_other_stocks_nothing_wasted(fast, hits20, capsys):
    """必须能过:两张卡的清单连着生成、同一版在两处各生成一份,先标完一份再标另一份——后生成的那份避开前一份
    还没标的股票,张数照样满,事先查不出会白标的,标完也没有揭开后才标的。同一版第二份生成时提醒第一份在哪。"""
    cfg, _, sid = hits20
    l1 = cardhits.make(sid, cfg=cfg, max_items=4)["doc"]
    l2 = cardhits.make(_second_card(), cfg=cfg, max_items=4)["doc"]
    r3 = cardhits.make(sid, list_id="dbg-hits-again", cfg=cfg, max_items=4)
    l3 = r3["doc"]
    assert len(l1["items"]) == len(l2["items"]) == len(l3["items"]) == 4
    assert not (_syms(l1) & _syms(l2)) and not (_syms(l3) & (_syms(l1) | _syms(l2)))
    assert [x["list_id"] for x in r3["row"]["same_version_lists"]] == [l1["list_id"]]
    cardhits._print_make(r3)
    assert f"提醒:这一版卡已经有一份清单 {l1['list_id']}" in capsys.readouterr().out
    for d in (l1, l2, l3):
        open_list(d)
    for d in (l1, l2, l3):
        assert cardhits.late_if_marked(d, set()) == {}
        for it in d["items"]:
            reveal_and_mark(d, it)
    assert _late_marks() == 0


def test_open_first_then_second_mark_both_nothing_wasted(fast, hits20):
    """必须能过:第一份打开了、没标就生成第二份,打开第二份看一眼,回去标完第一份,再标完第二份:没有白标的。"""
    cfg, _, sid = hits20
    l1 = cardhits.make(sid, cfg=cfg, max_items=4)["doc"]
    open_list(l1)
    l2 = cardhits.make(_second_card(), cfg=cfg, max_items=4)["doc"]
    assert len(l2["items"]) == 4
    open_list(l2)
    for d in (l1, l2):
        assert cardhits.late_if_marked(d, set()) == {}
        for it in d["items"]:
            reveal_and_mark(d, it)
    assert _late_marks() == 0


def test_mark_v2_then_rest_of_v1_nothing_wasted(fast, hits20):
    """必须能过:v1 标了 3 张就出 v2,标完 v2 再回头标 v1 剩下的:v2 避开 v1 还没标的股票,没有白标的。"""
    cfg, _, sid = hits20
    v1 = cardhits.make(sid, cfg=cfg, max_items=4)["doc"]
    open_list(v1)
    for it in v1["items"][:3]:
        reveal_and_mark(v1, it)
    revise_card(sid)
    v2 = cardhits.make(sid, cfg=cfg, max_items=4)["doc"]
    assert len(v2["items"]) == 4 and v1["items"][3]["symbol"] not in _syms(v2)
    open_list(v2)
    for it in v2["items"]:
        reveal_and_mark(v2, it)
    assert cardhits.late_if_marked(v1, {it["item_id"] for it in v1["items"][:3]}) == {}
    reveal_and_mark(v1, v1["items"][3])
    assert _late_marks() == 0


def test_revise_card_to_v4_every_version_has_charts(fast, hits20):
    """必须能过:标完一份 → 改卡 → 再出一份,连着改到 v4,每一版都还列得满(沿抽股顺序往下取新股票)。"""
    cfg, _, sid = hits20
    d = cardhits.make(sid, cfg=cfg, max_items=4)["doc"]
    for k in range(2, 5):
        open_list(d)
        for it in d["items"]:
            reveal_and_mark(d, it)
        revise_card(sid)
        r = cardhits.make(sid, cfg=cfg, max_items=4)
        d = r["doc"]
        assert d is not None and d["list_id"] == f"dbg-hits-{sid}-v{k}" and len(d["items"]) == 4, r["row"].get("empty")
    assert _late_marks() == 0


def test_mark_after_seen_elsewhere_counts_apart(fast, hits):
    """标一张之前,这份清单生成以后别的清单已经露出过它的后续:照收,记成「揭开后才标」,不进统计、不用归类,
    小结单独列条数。清单生成以前的接触不算(那由生成时管)。"""
    cfg, _, sid = hits
    a = cardhits.make(sid, list_id="dbg-hits-a", cfg=cfg)["doc"]
    b = cardhits.make(sid, list_id="dbg-hits-b", cfg=cfg)["doc"]          # a 没打开,b 和 a 一样
    x, y = a["items"][0], a["items"][1]
    reveal_and_mark(b, x)                                                 # 先在 b 里标了 x,露出了后续
    views.record(surface="manual", event="show_chart", outcome_visible=False, backfill=True,
                 ts="2020-01-01T00:00:00", note="补记:很早以前看过", charts=[
                     {"symbol": y["symbol"], "start": y["view_start"], "end": y["reveal_end"]}])
    late = reveal_and_mark(a, x, "no", "放量不在突破那天")
    ok = reveal_and_mark(a, y, "yes")
    assert [z["list_id"] for z in late["seen_before_mark"]] == ["dbg-hits-b"]
    assert "seen_before_mark" not in ok
    assert cardhits.pending()["marks"] == []
    with pytest.raises(cardhits.CardHitsRefused, match="揭开后才标"):
        cardhits.classify("mark", late["mark_id"], "先后")
    s = cardhits.summary(save=False)
    la = next(x_ for x_ in s["cards"][0]["lists"] if x_["list_id"] == "dbg-hits-a")
    assert (la["marked"], la["late"], la["counted"], la["yes"], la["no"]) == (2, 1, 1, 1, 0)
    assert s["n_marks_counted"] == 2 and [m["item_id"] for m in s["late_marks"]] == [x["item_id"]]
    text = cardhits.render_summary(s)
    assert "其中揭开后才标 1 张,不进统计" in text and "揭开后才标的 1 张" in text and "先在 dbg-hits-b 看到过后续" in text
    s2 = make_card(elements=(("pk", "按收盘越过一个峰", "E001", "must"),), triggers=("T3",), name="越过前高创新高")
    c = cardhits.make(s2, list_id="dbg-hits-c", cfg=cfg)["doc"]
    views.record(surface="web", event="show_chart", outcome_visible=False, list_id="dbg-hits-zz",
                 list_kind=cardhits.KIND,
                 charts=[{"symbol": f"C{i}", "start": mode.DEBUG_START, "end": mode.DEBUG_END} for i in range(6)])
    assert reveal_and_mark(c, c["items"][0])["seen_before_mark"]
    s = cardhits.summary(save=False)
    assert [x_["has_evidence"] for x_ in s["cards"]] == [True, False]      # 只有揭开后才标的,不算有证据


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
    n = len(doc["items"])
    assert f"已标 {n} / {n} 张" in out and "有证据的 1 张里 1 张(100%);连同没证据的是 1 / 1 张" in out
    assert f"证据还不够,先不给改不改的建议:计入统计的标注一共 {n} 下,至少要 {cardhits.MIN_MARKS} 下" in out
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
