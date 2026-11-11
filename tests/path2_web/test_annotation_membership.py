"""框套框、成员框、骨架、成员链空槽的参照实现(path2_web/annotation/membership.py)。

钉住的要求:
- 参照实现逐例给出 fixtures/membership_examples.json 里写好的答案。这份文件是参照实现与任何另写的实现
  (比如前端本地算的)共用的唯一事实来源,本测试只从它读答案,不另抄;
- 例子至少覆盖这些情形:默认归属到包住它的框里最短的那个;detach 和 attach 互斥;按 GAP 链式扩展到不再新增;
  被成员框包住的框、attach 到成员框上的框都带进来;跨过样本日的框收不进成员框,空槽的两种原因分得清;
  手动点进点出覆盖自动推断;骨架只取顶层框的特征的先后,子框和属性不进;顶层有两段同一特征时标 dup;
  一张图上显示用的框套框,被样本收着的框只在和它同被一个样本收着的框里找;
- 会话读标注时,把存储重放出的状态原样交给参照实现,就能算出骨架与空槽。
"""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import pytest

from path2_web.annotation import membership as m

FIXTURES = Path(__file__).parent / "fixtures"
EXAMPLES = json.loads((FIXTURES / "membership_examples.json").read_text(encoding="utf-8"))
DAYS = EXAMPLES["days"]
GAP, NEAR = EXAMPLES["params"]["gap"], EXAMPLES["params"]["near"]
CASES = EXAMPLES["cases"]

# 例子至少要覆盖的情形(例子 covers 里的标记)
REQUIRED_COVERS = {
    "nest_default_shortest",        # 默认归属到包住它的框里最短的那个
    "attach_detach_exclusive",      # detach 和 attach 互斥
    "gap_chain",                    # 按 GAP 链式扩展,直到不再新增
    "contained_and_attached_join",  # 被成员框包住的框、attach 到成员框上的框都带进来
    "crosses_sample_date",          # 跨过样本日的框收不进成员框,空槽的原因分得清
    "manual_overrides",             # 手动点进点出覆盖自动推断
    "skeleton_top_level_only",      # 骨架只取顶层框的特征的先后,子框和属性不进骨架
    "dup",                          # 顶层有两段同一特征时标出 dup
    "chart_scope",                  # 一张图上的框套框:被样本收着的框只在同被一个样本收着的框里找
}
_DATE_KEYS = ("start", "end", "date")


def _map_positions(x, f):
    """把例子里写成 days 下标的 start / end / date 逐个交给 f,换成 f 的返回值;其余原样。"""
    if isinstance(x, list):
        return [_map_positions(v, f) for v in x]
    if isinstance(x, dict):
        return {k: f(v) if k in _DATE_KEYS and isinstance(v, int) else _map_positions(v, f) for k, v in x.items()}
    return x


def _dated(x):
    """把例子里写成 days 下标的 start / end / date 换成日期(例子文件 about 里的约定)。"""
    return _map_positions(x, DAYS.__getitem__)


def _run(case: dict):
    """按 fn 调参照实现,返回与 expect 同形的结果。"""
    c = _dated(case)
    if c["fn"] == "parents":
        return m.parents(c["boxes"], DAYS)
    if c["fn"] == "chart_parents":
        return m.chart_parents(c["boxes"], c["samples"], DAYS)
    if c["fn"] == "members":
        return m.sample_members(c["date"], c["boxes"], DAYS, stored=c.get("stored"),
                                new_boxes=c.get("new_boxes", ()), manual=c.get("manual"), gap=GAP)
    if c["fn"] == "tree":
        args = (c["members"], c["boxes"], DAYS)
        return {"tree": m.member_tree(*args), "skeleton": m.skeleton(*args), "dup": m.dup_features(*args)}
    if c["fn"] == "slots":
        return m.empty_slots(c["charts"], c["symbol"], c["sample"], DAYS, near=NEAR)
    raise AssertionError(f"例子 {case['name']} 的 fn 未知: {c['fn']}")


@pytest.mark.parametrize("case", CASES, ids=[c["name"] for c in CASES])
def test_example(case):
    """每个例子:有 expect 的,结果逐项相等;有 expect_error 的,报出那个 code。"""
    if "expect_error" in case:
        with pytest.raises(m.MembershipInputError) as e:
            _run(case)
        assert e.value.code == case["expect_error"]
    else:
        assert _run(case) == case["expect"]


def test_examples_cover_required_cases_and_are_well_formed():
    """例子覆盖 REQUIRED_COVERS 的全部情形;每例的 name 不重复、写了为什么、只有 expect 与 expect_error 之一;
    下标都落在 days 里,days 升序且不重复。"""
    names = [c["name"] for c in CASES]
    assert len(names) == len(set(names))
    assert REQUIRED_COVERS <= {tag for c in CASES for tag in c["covers"]}
    for c in CASES:
        assert c["why"].strip(), c["name"]
        assert ("expect" in c) != ("expect_error" in c), c["name"]
    assert DAYS == sorted(set(DAYS))
    positions = []
    _map_positions(CASES, positions.append)
    assert positions and all(0 <= p < len(DAYS) for p in positions)


def test_session_reads_replayed_state_as_is():
    """会话的读法:存储重放出的状态(fixtures/annotation_store_v1/expected.json,存储测试钉住的固定重放结果)
    原样交给参照实现。AAPL 的样本 s-pc-6 收了 b-pc-3(特征 w-pc-1)和 b-pc-4(特征 w-pc-2),两者互不包住,
    骨架是两段;同为 w-pc-1 的 b-pc-7 在样本日之前结束、没被收,留一个画了没收的空槽。days 用这段时间的工作日。"""
    state = json.loads((FIXTURES / "annotation_store_v1" / "expected.json").read_text(encoding="utf-8"))["state"]
    aapl = next(c for c in state["charts"] if c["symbol"] == "AAPL")
    sample = aapl["samples"][0]
    days = [d.isoformat() for d in (dt.date(2024, 2, 1) + dt.timedelta(n) for n in range(90)) if d.weekday() < 5]

    assert m.skeleton(sample["members"], aapl["boxes"], days) == ["w-pc-1", "w-pc-2"]
    assert m.dup_features(sample["members"], aapl["boxes"], days) == []
    assert m.empty_slots(state["charts"], "AAPL", sample["id"], days) == [
        {"box": "b-pc-7", "feature": "w-pc-1", "reason": m.UNCLAIMED}]


def test_unknown_chart_or_sample_is_reported():
    """问的图或样本不存在时报出来,不返回空槽。"""
    charts = [{"symbol": "AAA", "boxes": [], "samples": []}]
    with pytest.raises(m.MembershipInputError) as e:
        m.empty_slots(charts, "BBB", "s1", DAYS)
    assert e.value.code == "unknown_chart"
    with pytest.raises(m.MembershipInputError) as e:
        m.empty_slots(charts, "AAA", "s1", DAYS)
    assert e.value.code == "unknown_sample"
