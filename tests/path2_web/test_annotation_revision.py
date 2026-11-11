"""会话侧的定格、这一轮的输入摘要与改版报告(path2_web/annotation/revision.py)。

不读行情:跑 app 的两步(run_app、app_buys)和版本指纹 app_ver 换成合成结果,标注写在临时目录,mapping 改从
临时目录读(<tmp>/mappings/<app>.yaml),不往 path2_apps/ 里写。

钉住的要求:
- start_round:上一轮定格抄成 prev;新快照记 {机器: 连续到齐的序号}、这个 pattern 的样本编号;股票 = 上一轮
  ∪ 这一轮里这个 pattern 有样本或反馈的股票;全历史区间、label_horizon 20 跑 app;打印的 YAML 写进 mapping 后
  会话段形状合格;round 文件已存在时拒绝覆盖;
- 第一轮(没有上一轮定格)且 app 没改:报告写「无变化」;mapping 没写新快照时开头提醒;
- 反馈状态的新旧对照(含上一轮之后新加、删掉的反馈),lost 留一行待会话交代,反馈范围里砍掉的买点只给个数;
  会话段写坏时开头说明、原因标签当作没有,不误报「定格没写」;
- 一条反馈写成「（落在 node）「理由」（编号，issue 值）」,不写 answer、dag;「各 issue 现在」列出有一处还在买、
  有一处 lost、或这一版变了的 issue(只有一处的用反馈编号当名字),其余给个数;带 answer 和不带 answer 的反馈
  混在一起时报告与摘要照常出;
- 还没有 app 时 start_round 照常定格(不跑买点);对这种 round 文件 round_digest 照出,revision_report 在建好
  app 之后出「第一版」报告(各样本的结论),还没有 app 时报错;
- round_digest:定义、mapping、账本、上一轮以来的变化、按 issue 分组的反馈(状态用改之前的买点)、全部样本及其
  成员框,相反的样本排前;
- 范围外砍掉的、新长出来的按族折叠(整族新长、同一族多买几天两种写法),两节合起来细看 12 族,按变化天数从大到小,
  其余给个数;链接格式;
- 样本结论的翻转只数两边都有结论的,按原因拆:app 改的(变坏、变好)、标注改的(改判);新放、挪进的另起一行计数;
  点名经用户改动、样本日落在买点日上的正样本,注明旧版 / 新版 / 两版;
- 删掉、挪走的正样本单列,点名旧版 app 原来就认不出的;
- as_of 缺口:缺号之后已到的批次这一轮不报,下一轮报。
"""
from __future__ import annotations

import json
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit

import pandas as pd
import pytest
import yaml

import path2_apps.bo_only.dag_spec as bo_only
from path2_web import mapping
from path2_web.annotation import revision, store
from path2_web.app_run import AppBuys, NoSymbol

TRAIN_END = "2025-12-31"
D = pd.bdate_range("2024-01-01", "2025-12-31").strftime("%Y-%m-%d").tolist()   # 合成的交易日


def _buys(families: dict, starts=None) -> AppBuys:
    """合成的买点:{族起点: [买点日]};参与求解的事件起点缺省就是各族起点。"""
    return AppBuys(families={k: tuple(sorted(v)) for k, v in sorted(families.items())},
                   event_starts=tuple(sorted(starts if starts is not None else families)), dates=tuple(D))


@pytest.fixture
def env(tmp_path, monkeypatch):
    """临时标注目录 + 临时 mapping 目录 + 假 app。

    返回 SimpleNamespace:cfg、registry、app(buys: {股票: AppBuys},改它就是「改 app」;ver;calls 记每次跑 app
    的参数)、write_mapping(session=None)、round(名字) → scratch 里的 round 文件路径。"""
    adir = tmp_path / "annotations"
    adir.mkdir()
    mdir = tmp_path / "mappings"
    mdir.mkdir()
    monkeypatch.setattr(mapping, "mapping_path", lambda mod: mdir / f"{mod.__name__.split('.')[-2]}.yaml")
    app = SimpleNamespace(buys={}, ver="aaaaaaaaaaaaaaaa", calls=[])

    def run_app(mod, cfg, symbol, start, end, params, label_horizon=20):
        app.calls.append((symbol, start, end, label_horizon))
        if symbol not in app.buys:
            raise NoSymbol(f"pkl not found: {symbol}")
        return symbol, None, {"end_node": "bo"}

    monkeypatch.setattr(revision, "run_app", run_app)
    monkeypatch.setattr(revision, "app_buys", lambda res, win, end_node: app.buys[res])
    monkeypatch.setattr(revision, "app_ver", lambda mod: app.ver)

    def write_mapping(pattern="p", session=None, notes=None):
        doc = {"pattern": pattern, "features": {"w-pc-1": "bo"}}
        if session is not None:
            doc["session"] = session
        if notes is not None:
            doc["notes"] = notes
        (mdir / "bo_only.yaml").write_text(yaml.safe_dump(doc, allow_unicode=True), encoding="utf-8")

    return SimpleNamespace(
        cfg={"annotation_dir": str(adir), "machine": "pc", "frontend_port": 5171}, adir=adir,
        registry=SimpleNamespace(ids=lambda: ["bo_only"], get=lambda a: bo_only if a == "bo_only" else None),
        app=app, write_mapping=write_mapping, round=lambda name="round.json": tmp_path / "scratch" / name)


def _start(env, pattern="p", name="round.json", **kw):
    return revision.start_round(pattern, env.round(name), cfg=env.cfg, registry=env.registry, **kw)


def _finish(env, name="round.json"):
    """会话记完账后存下同名报告:这一轮才算走完,才能再开下一轮。"""
    env.round(name).with_name(env.round(name).stem + ".report.md").write_text("报告\n", encoding="utf-8")


def _report(env, pattern="p", name="round.json", **kw):
    return revision.revision_report(pattern, env.round(name), cfg=env.cfg, registry=env.registry, **kw)


def _printed_session(out: str) -> dict:
    """start_round 打印的 YAML(去掉 # 开头的说明行)→ {snapshot: ...}。"""
    return yaml.safe_load("\n".join(l for l in out.splitlines() if not l.startswith("#")))["session"]


def _sample(oid, symbol, date, judgment="pos", pattern="p", base=None):
    return {"kind": "sample", "id": oid, "base": base,
            "value": {"id": oid, "symbol": symbol, "date": date, "pattern": pattern, "judgment": judgment,
                      "members": []}}


def _fb(oid, symbol, start, end=None, target="point", pattern="p", answer=None, **extra):
    """一条反馈;缺省是 point / 写了理由 / 不带 answer。answer 给了就是带 answer 的那种形状;note=None 表示不带理由。"""
    v = {"id": oid, "symbol": symbol, "pattern": pattern, "app_id": "bo_only", "app_ver": "0123456789abcdef",
         "start": start, "end": end or start, "target": target, "source": "picked", "note": "不该买", **extra}
    if answer is not None:
        v["answer"] = answer
    if v["note"] is None:
        del v["note"]
    return {"kind": "feedback", "id": oid, "base": None, "value": v}


def _save(env, *ops):
    store.append_batch(env.cfg, list(ops))


def _rev(env, kind, oid):
    return store.read_annotations(env.cfg)["revs"][kind][oid]


def _edit_sample(env, oid, **changes):
    """改一个样本的字段(值为 None 即删掉这个样本)。"""
    cur = {s["id"]: {**s, "symbol": c["symbol"]} for c in store.read_annotations(env.cfg)["state"]["charts"]
           for s in c["samples"]}[oid]
    value = None if changes.get("delete") else {**cur, **changes}
    return {"kind": "sample", "id": oid, "base": _rev(env, "sample", oid), "value": value}


def _link(date, symbol="AAA", pattern="p") -> str:
    return f"http://localhost:5171/#symbol={symbol}&date={date}&pattern={pattern}&mode=compare"


def _digest(env, pattern="p", name="round.json", **kw):
    return revision.round_digest(pattern, env.round(name), cfg=env.cfg, registry=env.registry, **kw)


def _fb_parts(sec: str) -> tuple[list[str], list[str], list[str]]:
    """① 一节里的三段「- 」行:(逐条的状态变化, 各 issue 现在, lost 待交代)。"""
    parts, cur = {"rows": [], "issues": [], "lost": []}, "rows"
    for line in sec.splitlines():
        if line.startswith("各 issue 现在"):
            cur = "issues"
        elif line.startswith("`lost` 的反馈"):
            cur = "lost"
        elif line.startswith("- "):
            parts[cur].append(line)
    return parts["rows"], parts["issues"], parts["lost"]


def _section(report: str, title_start: str) -> str:
    """报告里以「## <title_start>」开头的那一节(到下一个 ## 为止)。"""
    parts = report.split("\n## ")
    hits = [p for p in parts if p.startswith(title_start)]
    assert len(hits) == 1, f"找不到节 {title_start}:\n{report}"
    return hits[0]


# ───────────────────────── 开头定格 ─────────────────────────

def test_start_round_snapshot_symbols_and_yaml(env, capsys):
    """prev 抄自 mapping;新快照按连续序号记;股票 = 上一轮 ∪ 这一轮有样本或反馈的(别的 pattern 不算);
    全历史区间跑 app;读不到行情的记下来、不整体失败;打印的 YAML 写进 mapping 后形状合格;不覆盖已有 round 文件。"""
    _save(env, _sample("s-pc-1", "AAA", D[10]), _sample("s-pc-2", "CCC", D[20]),
          _sample("s-pc-3", "ZZZ", D[30], pattern="q"))
    env.write_mapping(session={"snapshot": {"seen": {"pc": 1}, "samples": ["s-pc-1", "s-pc-2"]},
                               "tags": {"f-pc-4": "for_tuning"}})
    _save(env, _edit_sample(env, "s-pc-2", delete=True), _fb("f-pc-4", "BBB", D[40]))
    env.app.buys = {"AAA": _buys({D[9]: [D[10]]}), "BBB": _buys({})}

    rnd = _start(env)
    assert rnd["prev"] == {"seen": {"pc": 1}, "samples": ["s-pc-1", "s-pc-2"]}
    assert rnd["snapshot"]["seen"] == {"pc": 2} and rnd["snapshot"]["samples"] == ["s-pc-1"]
    assert sorted(env.app.calls) == [(s, "1900-01-01", TRAIN_END, 20) for s in ("AAA", "BBB", "CCC")]
    assert set(rnd["buys"]) == {"AAA", "BBB"} and set(rnd["unavailable"]) == {"CCC"}
    assert json.loads(env.round().read_text(encoding="utf-8")) == rnd
    assert AppBuys.from_dict(rnd["buys"]["AAA"]) == env.app.buys["AAA"]

    session = _printed_session(capsys.readouterr().out)
    assert session == {"snapshot": rnd["snapshot"]}
    env.write_mapping(session={**session, "tags": {"f-pc-4": "for_tuning"}})   # 会话照打印的写进 mapping
    (m,) = mapping.read_mappings(env.registry)
    assert m["session_problem"] is None and m["session"]["snapshot"] == rnd["snapshot"]

    with pytest.raises(FileExistsError):
        _start(env)


def test_first_round_unchanged_app_reports_no_change(env, capsys):
    """第一轮(mapping 没有会话段):prev 为空,两边用同一份标注;app 不改 → 「无变化」。mapping 没写这一轮的
    新快照时开头提醒,写上之后不再提醒;读不到行情的股票列在开头。"""
    _save(env, _sample("s-pc-1", "AAA", D[10]), _fb("f-pc-2", "AAA", D[10], D[12], target="range", answer="off_pattern",
                                                  note=None, nodes=["bo"]),
          _sample("s-pc-3", "NOPE", D[30]))
    env.write_mapping()
    env.app.buys = {"AAA": _buys({D[9]: [D[10], D[11]]})}
    rnd = _start(env)
    assert rnd["prev"] is None

    report = _report(env)
    assert "**无变化**" in report and "第一轮" in report
    assert "朱红 1 条" in report and "读不到行情、没比的股票：NOPE" in report
    assert "注意" in report

    env.write_mapping(session=_printed_session(capsys.readouterr().out))
    report = _report(env)
    assert "**无变化**" in report and "注意" not in report
    assert "## " not in report   # 无变化时不出六节


# ───────────────────────── 反馈的状态 ─────────────────────────

def test_feedback_status_changes_lost_and_in_range_count(env):
    """反馈状态新旧对照只列变了的;lost 留一行待会话交代;朱红按原因标签判;反馈范围里砍掉的买点只给个数。"""
    _save(env,
          _fb("f-pc-1", "AAA", D[10]),                                                    # matched → unmatched
          _fb("f-pc-2", "AAA", D[35], D[36], target="family", family_start=D[30]),         # matched → lost
          _fb("f-pc-3", "AAA", D[60], D[62], target="range"),                              # unmatched,没变
          _fb("f-pc-4", "AAA", D[70]),                                                    # matched,定义改过
          _fb("f-pc-5", "AAA", D[72]))                                                    # matched,朱红
    env.write_mapping(session={"tags": {"f-pc-4": "redefined", "f-pc-2": "unhandled"}})
    env.app.buys = {"AAA": _buys({D[9]: [D[10]], D[30]: [D[35], D[36]], D[68]: [D[70], D[72]]})}
    _start(env)
    env.app.buys = {"AAA": _buys({D[68]: [D[70], D[72]]})}   # 改 app:前两族没了,起点也认不出

    sec = _section(_report(env), "① ")
    rows, issues, lost = _fb_parts(sec)
    assert len(rows) == 2 and len(lost) == 1   # 两条变了的 + 一条 lost 待填
    assert "「不该买」（f-pc-1）：`matched` → `unmatched`" in rows[0]
    assert "（f-pc-2）：`matched` → `lost`" in rows[1]
    assert "（f-pc-2）：（待填：改好了 / 认法变了）" in lost[0]
    assert issues == ["- `f-pc-4`「不该买」：1 处，还在买 1 处",                      # 还在买的在前
                      "- `f-pc-5`「不该买」：1 处，还在买 1 处",
                      "- `f-pc-2`「不该买」：1 处，还在买 0 处，`lost` 1 处，这一版变了 1 处",   # lost 其次
                      "- `f-pc-1`「不该买」：1 处，还在买 0 处，这一版变了 1 处"]
    assert "另有 1 个 issue 各处都不买了、这一版没变。" in sec        # f-pc-3
    assert "其余 3 条没变" in sec
    assert "现在 5 条反馈：朱红 1 条、`lost` 1 条、`unmatched` 2 条。" in sec
    assert "共 3 天。" in _section(_report(env), "② ")
    assert "没有。" in _section(_report(env), "③ ")


def test_shared_issue_grouped_with_still_bought_count(env):
    """共享同一个 issue 的几处挨着列、编号后带 issue 值;「各 issue 现在」每个 issue 一行,写标了几处、还在买几处、
    这一版变了几处,共享的用 issue 值当名字、只有一处的用反馈编号;点出的 node 写成「落在」。"""
    _save(env,
          _fb("f-pc-1", "BBB", D[10], issue="i-pc-1", nodes=["bo"]),                      # matched → unmatched
          _fb("f-pc-2", "AAA", D[40]),                                                    # 各写各的,matched → unmatched
          _fb("f-pc-3", "AAA", D[70], issue="i-pc-1", nodes=["bo"]))                      # matched,没变
    env.write_mapping()
    env.app.buys = {"AAA": _buys({D[38]: [D[40]], D[68]: [D[70]]}), "BBB": _buys({D[9]: [D[10]]})}
    _start(env)
    env.app.buys = {"AAA": _buys({D[68]: [D[70]]}), "BBB": _buys({})}

    sec = _section(_report(env), "① ")
    rows, issues, _ = _fb_parts(sec)
    assert len(rows) == 2
    assert "「不该买」（f-pc-2）：`matched` → `unmatched`" in rows[0]          # 各写各的排前
    assert "（落在 bo）「不该买」（f-pc-1，issue i-pc-1）：`matched` → `unmatched`" in rows[1]
    assert issues == ["- `i-pc-1`（落在 bo）「不该买」：2 处，还在买 1 处，这一版变了 1 处",
                      "- `f-pc-2`「不该买」：1 处，还在买 0 处，这一版变了 1 处"]
    assert "另有" not in sec


def test_feedback_added_and_deleted_and_family_grows(env):
    """上一轮之后删掉的反馈、新加的反馈都列进 ①(另一边写「没有这条」);同一族在新版多买了几天,
    ④ 写「X 天变 Y 天」。"""
    _save(env, _fb("f-pc-1", "AAA", D[101]), _fb("f-pc-2", "AAA", D[150]))
    env.write_mapping(session={"snapshot": {"seen": {"pc": 1}, "samples": []}})
    _save(env, {"kind": "feedback", "id": "f-pc-1", "base": _rev(env, "feedback", "f-pc-1"), "value": None},
          _fb("f-pc-3", "AAA", D[103], D[105], target="range"))
    env.app.buys = {"AAA": _buys({D[100]: [D[101], D[102]]})}
    _start(env)
    env.app.buys = {"AAA": _buys({D[100]: D[101:106]})}

    report = _report(env)
    sec = _section(report, "① ")
    rows, issues, _ = _fb_parts(sec)
    assert [l.split(") ", 1)[1] for l in rows] == ["「不该买」（f-pc-1）：`matched` → （没有这条）",
                                                  "「不该买」（f-pc-3）：（没有这条） → `matched`"]
    assert issues == ["- `f-pc-3`「不该买」：1 处，还在买 1 处，这一版变了 1 处"]   # 新标的算变了;删掉的不进这里
    assert "另有 1 个 issue 各处都不买了、这一版没变。" in sec                     # f-pc-2
    assert "其余 1 条没变。" in sec and "现在 2 条反馈：朱红 1 条、`lost` 0 条、`unmatched` 1 条。" in sec
    up = _section(report, "④ ")
    assert "共 3 天、1 族。" in up
    assert f"- [AAA {D[100]} 起的一族]({_link(D[103])})：2 天变 5 天" in up


def test_broken_session_reported_and_tags_ignored(env):
    """改版途中会话段写坏了:报告开头说会话段读不到、原因标签当作没有(挂了「定义改过」的那条照样算朱红),
    不再误报「定格没写」。"""
    _save(env, _fb("f-pc-1", "AAA", D[10]))
    env.write_mapping(session={"tags": {"f-pc-1": "redefined"}})
    env.app.buys = {"AAA": _buys({D[9]: [D[10]]})}
    _start(env)
    assert "朱红 0 条" in _report(env)
    env.write_mapping(session={"tags": {"f-pc-1": "redefined", "f-pc-2": "bogus"}})

    report = _report(env)
    assert "- 会话段读不到（原因：session.tags has unknown tags: bogus），原因标签没读到，朱红按没有标签算" in report
    assert "注意" not in report
    assert "朱红 1 条" in report


# ───────────────────────── 按族折叠、上限、链接 ─────────────────────────

def test_folds_limit_order_and_links(env):
    """③ 范围外砍掉的 10 族、④ 新长出来的 5 族,合起来只细看 12 族(按变化天数从大到小),其余给个数;
    砍在反馈范围里的天数不进③、只在那一族后面带一句;链接落在 compare 那天,pattern 名照查询串编码。"""
    pattern = "阶跃 v2"
    old = {D[i * 40]: D[i * 40 + 5: i * 40 + 25 - i] for i in range(10)}          # 第 i 族 20 - i 天
    grown = {D[420 + j * 10]: D[421 + j * 10: 422 + j * 10 + j] for j in range(5)}  # 第 j 族 j + 1 天
    keep = {D[300]: [D[301]]}
    _save(env, _sample("s-pc-1", "AAA", D[301], pattern=pattern),
          _fb("f-pc-2", "AAA", D[5], D[8], target="range", pattern=pattern))       # 盖住第 0 族头 4 天
    env.write_mapping(pattern=pattern)
    env.app.buys = {"AAA": _buys({**old, **keep})}
    _start(env, pattern)
    env.app.buys = {"AAA": _buys({**keep, **grown})}

    report = _report(env, pattern)
    assert "共 4 天。" in _section(report, "② ")

    cut = _section(report, "③ ")
    assert "共 151 天、10 族。" in cut     # 范围外:155 - 4
    rows = [l for l in cut.splitlines() if l.startswith("- [")]
    want = [(1, 19), (2, 18), (3, 17), (0, 16), (4, 16), (5, 15), (6, 14), (7, 13), (8, 12), (9, 11)]
    assert [l.split("](")[0] for l in rows] == [f"- [AAA {D[i * 40]} 起的一族" for i, _ in want]
    assert rows[3].endswith("20 天剩 0 天，另有 4 天砍在反馈范围里")
    assert rows[0].endswith("19 天剩 0 天")
    assert "另有" not in "\n".join(rows[:3])

    up = _section(report, "④ ")
    assert "共 15 天、5 族。" in up
    rows = [l for l in up.splitlines() if l.startswith("- [")]
    assert [l.split("](")[0] for l in rows] == [f"- [AAA {D[420 + j * 10]} 起的一族" for j in (4, 3)]
    assert rows[0].endswith("新长出的一族，5 天")
    assert "- 另有 3 族（共 6 天）没列出。" in up

    link = cut.split("](")[4].split(")")[0]          # 第 0 族:链接落在第一个范围外砍掉的日子
    parts = urlsplit(link)
    assert f"{parts.scheme}://{parts.netloc}{parts.path}" == "http://localhost:5171/"
    assert parse_qs(parts.fragment) == {"symbol": ["AAA"], "date": [D[9]], "pattern": [pattern], "mode": ["compare"]}
    assert link.split("#")[1] == f"symbol=AAA&date={D[9]}&pattern=%E9%98%B6%E8%B7%83%20v2&mode=compare"

    other = _report(env, pattern, link_base="http://example.test:9000/")
    assert f"(http://example.test:9000/#symbol=AAA&date={D[9]}&" in other


# ───────────────────────── 样本结论的翻转 ─────────────────────────

def test_flips_split_by_cause_new_samples_and_named(env):
    """翻转只数两边都有结论的:app 改的(正样本买点没了、负样本上新长了买点 → 变坏;正样本附近新长了买点 → 变好)、
    标注改的(正样本改判成负样本)。新放、挪进的没有旧结论,不算翻转,另起一行计数。点名经用户改动的正样本里
    样本日落在买点日上的,注明旧版 / 新版 / 两版。"""
    _save(env, _sample("s-pc-1", "AAA", D[10]),                 # 旧 ✓,app 砍掉买点 → ✗(app)
          _sample("s-pc-2", "AAA", D[50]),                      # 旧 ✓,改判成负样本 → ✗(标注)
          _sample("s-pc-3", "AAA", D[80], judgment="neg"),      # 旧 ✓,app 在这天新长买点 → ✗(app)
          _sample("s-pc-4", "AAA", D[120]),                     # 旧 ✗,app 在后一天新长买点 → ✓(app)
          _sample("s-pc-8", "AAA", D[400], pattern="q"))        # 别的 pattern 的,下一批挪进来
    env.write_mapping(session={"snapshot": {"seen": {"pc": 1}, "samples": ["s-pc-1", "s-pc-2", "s-pc-3", "s-pc-4"]}})
    _save(env, _edit_sample(env, "s-pc-2", judgment="neg"),
          _sample("s-pc-5", "AAA", D[200]),                     # 新放,落在新版买点日上 → ✓
          _sample("s-pc-6", "AAA", D[11]),                      # 新放,落在旧版买点日上(新版砍了)→ ✗
          _sample("s-pc-7", "AAA", D[50]),                      # 新放,两版都在这天买 → ✓
          _edit_sample(env, "s-pc-8", pattern="p"))             # 挪进,附近没有买点 → ✗
    env.app.buys = {"AAA": _buys({D[9]: [D[10], D[11]], D[49]: [D[50]]})}
    _start(env)
    env.app.buys = {"AAA": _buys({D[49]: [D[50]], D[79]: [D[80]], D[119]: [D[121]], D[199]: [D[200]]})}

    sec = _section(_report(env), "⑤ ")
    assert "翻了 4 张：app 改的 3、你改标注的 1。" in sec
    app_part, rest = sec.split("你改标注造成的：")
    you_part, rest = rest.split("新放 / 挪进 4 张：✓ 2、✗ 2（没有旧结论，不算翻转）。")
    fresh, named = rest.split("样本日正好是 app 买点日的")
    worse, better = app_part.split("变坏（✓ → ✗）：")[1].split("变好（✗ → ✓）：")
    assert "（s-pc-1）：✓ → ✗（`matched` → `unmatched`）" in worse
    assert "负样本（s-pc-3）：✓ → ✗（`unmatched` → `matched`）" in worse
    assert "（s-pc-4）：✗ → ✓（`unmatched` → `matched`）" in better
    assert [l for l in you_part.splitlines() if l.startswith("- ")] == [
        f"- [AAA {D[50]}]({_link(D[50])}) 负样本（s-pc-2）（改判：正样本 → 负样本）：✓ → ✗（`matched` → `matched`）"]
    fresh_rows = [l for l in fresh.splitlines() if l.startswith("- ")]
    assert [r.split(") ", 1)[1] for r in fresh_rows] == [
        "正样本（s-pc-6）（新放）：✗（`unmatched`）", "正样本（s-pc-7）（新放）：✓（`matched`）",
        "正样本（s-pc-5）（新放）：✓（`matched`）", "正样本（s-pc-8）（挪进这个 pattern）：✗（`unmatched`）"]
    named_rows = [l.split(") ", 1)[1] for l in named.splitlines() if l.startswith("- ")]
    assert named_rows == ["正样本（s-pc-6）（新放）：落在旧版的买点日上", "正样本（s-pc-7）（新放）：落在两版的买点日上",
                          "正样本（s-pc-5）（新放）：落在新版的买点日上"]


def test_removed_and_moved_positive_samples_listed_separately(env):
    """删掉、挪走的正样本单列(不进翻转),点名旧版 app 原来就认不出的;删掉的负样本只给个数。"""
    _save(env, _sample("s-pc-1", "AAA", D[10]),                 # 旧 ✓,删掉
          _sample("s-pc-2", "AAA", D[30]),                      # 旧 ✗(认不出),挪到别的 pattern
          _sample("s-pc-3", "AAA", D[40], judgment="neg"),      # 负样本,删掉
          _sample("s-pc-4", "AAA", D[60]))                      # 挪回 unsorted
    env.write_mapping(session={"snapshot": {"seen": {"pc": 1}, "samples": []}})
    _save(env, _edit_sample(env, "s-pc-1", delete=True), _edit_sample(env, "s-pc-2", pattern="q"),
          _edit_sample(env, "s-pc-3", delete=True), _edit_sample(env, "s-pc-4", pattern=None))
    env.app.buys = {"AAA": _buys({D[9]: [D[10]], D[59]: [D[60]]})}
    _start(env)

    report = _report(env)
    assert "**无变化**" not in report
    assert "没有翻转。" in _section(report, "⑤ ")
    sec = _section(report, "⑥ ")
    rows = [l for l in sec.splitlines() if l.startswith("- [")]
    assert len(rows) == 3
    assert "（s-pc-1）：删掉了；旧版 ✓" in rows[0]
    assert "（s-pc-2）：挪到 q；**旧版 app 原来就认不出**（`unmatched`）" in rows[1]
    assert "（s-pc-4）：挪回 unsorted；旧版 ✓" in rows[2]
    assert "另有删掉、挪走的负样本 1 张。" in sec


# ───────────────────────── as_of 缺口 ─────────────────────────

def _write_raw(adir, seq: int, ops: list[dict]) -> None:
    """绕过保存直接写一个 pc 的批次文件(模拟同步来的、序号有缺口的文件)。"""
    ts = f"20261103T10{seq:02d}00.000Z"
    doc = {"schema": store.SCHEMA, "data_fingerprint": None,
           "ops": [{"ts": ts, "machine": "pc", **op} for op in ops]}
    (adir / f"pc-{ts}-{seq}.json").write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")


def test_as_of_gap_late_batch_reported_next_round(env, capsys):
    """pc 的 3 号还没到、4 号先到:这一轮定格停在 2 号,4 号里新放的样本这一轮不报(那只股票也不跑);
    3 号到了以后下一轮定格到 4 号,新放的样本这时报出来。"""
    _write_raw(env.adir, 1, [_sample("s-pc-1", "AAA", D[10])])
    _write_raw(env.adir, 2, [_fb("f-pc-2", "AAA", D[10])])
    _write_raw(env.adir, 4, [_sample("s-pc-4", "BBB", D[20])])
    env.write_mapping()
    env.app.buys = {"AAA": _buys({D[9]: [D[10]]}), "BBB": _buys({D[19]: [D[20]]})}

    rnd = _start(env, name="r1.json")
    assert rnd["snapshot"] == {**rnd["snapshot"], "seen": {"pc": 2}, "samples": ["s-pc-1"]}
    assert {c[0] for c in env.app.calls} == {"AAA"}
    report = _report(env, name="r1.json")
    assert "**无变化**" in report and "s-pc-4" not in report

    env.write_mapping(session=_printed_session(capsys.readouterr().out))
    _write_raw(env.adir, 3, [_fb("f-pc-3", "AAA", D[40])])
    with pytest.raises(ValueError, match="还有没走完的一轮.*r1.json"):      # 上一轮没存报告:换个文件名也不让定格
        _start(env, name="r2.json")
    assert not env.round("r2.json").exists()
    _finish(env, "r1.json")
    rnd = _start(env, name="r2.json")
    assert rnd["prev"]["seen"] == {"pc": 2} and rnd["snapshot"]["seen"] == {"pc": 4}
    sec = _section(_report(env, name="r2.json"), "⑤ ")
    assert "没有翻转。" in sec and "新放 / 挪进 1 张：✓ 1、✗ 0" in sec
    assert "（s-pc-4）（新放）：✓（`matched`）" in sec


# ───────────────────────── 两种形状的反馈、还没有 app、这一轮的输入摘要 ─────────────────────────

def test_report_and_digest_take_feedback_with_and_without_answer(env):
    """标注里带 answer 的各种写法(neg + 理由、off_pattern 只点 node、off_pattern + dag)和不带 answer 的混在一起,
    还共享同一个 issue:改版报告与摘要照常出,输出里没有 answer、dag 的任何痕迹。"""
    _save(env,
          _fb("f-pc-1", "AAA", D[10], answer="neg"),
          _fb("f-pc-2", "AAA", D[40], answer="off_pattern", note=None, nodes=["bo"]),          # 只点 node、没写理由
          _fb("f-pc-3", "AAA", D[70], answer="off_pattern", note="整体不像", dag=True, issue="i-pc-1"),
          _fb("f-pc-4", "BBB", D[10], note="整体不像", issue="i-pc-1"),                        # 不带 answer,同一个 issue
          _fb("f-pc-5", "BBB", D[40], nodes=["bo"]))
    env.write_mapping()
    env.app.buys = {"AAA": _buys({D[9]: [D[10]], D[38]: [D[40]], D[68]: [D[70]]}),
                    "BBB": _buys({D[9]: [D[10]], D[38]: [D[40]]})}
    _start(env)
    digest = _digest(env)
    env.app.buys = {"AAA": _buys({}), "BBB": _buys({})}
    report = _report(env)

    for text in (report, digest):
        assert "off_pattern" not in text and "`neg`" not in text and "dag" not in text and "answer" not in text
    rows, issues, _ = _fb_parts(_section(report, "① "))
    assert len(rows) == 5
    assert "（落在 bo）（f-pc-2）：`matched` → `unmatched`" in "\n".join(rows)             # 没写理由就没有「」
    assert "「整体不像」（f-pc-3，issue i-pc-1）：`matched` → `unmatched`" in "\n".join(rows)
    assert "- `i-pc-1`「整体不像」：2 处，还在买 0 处，这一版变了 2 处" in issues
    sec = _section(digest, "issue")
    assert "共 4 个 issue、5 处；还在买 5 处、`lost` 0 处。" in sec
    assert "### `i-pc-1`（2 处，还在买 2 处）" in sec and "### `f-pc-2`（1 处，还在买 1 处）" in sec
    assert "- 落在：bo" in sec and "- 落在：没点 node" in sec and "  > （没写）" in sec


def test_start_round_refuses_when_it_cannot_tell_there_is_no_app(env, tmp_path, monkeypatch):
    """分不清这个 pattern 有没有 app 时不定格、不留 round 文件:已注册 app 的 mapping 读不出 pattern;
    没注册上的 app 在磁盘上的 mapping 写的正是这个 pattern,或读不出。别的 pattern 的、读得出的不拦。"""
    _save(env, _sample("s-pc-1", "AAA", D[10]))
    mfile = tmp_path / "mappings" / "bo_only.yaml"

    mfile.write_text("pattern: [p\n", encoding="utf-8")                    # YAML 写坏
    with pytest.raises(ValueError, match="读不出 pattern"):
        _start(env)
    mfile.write_text("features: {w-pc-1: bo}\n", encoding="utf-8")         # pattern 行丢了
    with pytest.raises(ValueError, match="读不出 pattern"):
        _start(env)
    assert not env.round().exists()
    mfile.unlink()

    broken = tmp_path / "broken.yaml"
    monkeypatch.setattr(revision, "_unregistered_mapping_files", lambda registry: [("broken_app", broken)])
    broken.write_text("pattern: p\nfeatures: {}\n", encoding="utf-8")
    with pytest.raises(ValueError, match="broken_app.*没注册上.*写的正是"):
        _start(env, no_app=True)
    broken.write_text("pattern: [p\n", encoding="utf-8")
    with pytest.raises(ValueError, match="broken_app.*没注册上.*读不出"):
        _start(env, no_app=True)
    assert not env.round().exists()

    broken.write_text("pattern: other\nfeatures: {}\n", encoding="utf-8")   # 写的是别的 pattern:兜底不拦
    with pytest.raises(ValueError, match="不一定是还没有 app.*no_app=True"):    # 但没有 app 必须显式确认
        _start(env)
    with pytest.raises(ValueError, match="名字敲错了"):                          # 标注里没有这个名字的任何东西
        _start(env, pattern="typo", no_app=True)
    assert not env.round().exists()
    assert _start(env, no_app=True)["app_id"] is None

    _finish(env)
    env.write_mapping()                                                         # 有 app 的 pattern 传 no_app:拒绝
    with pytest.raises(ValueError, match="已有 app bo_only"):
        _start(env, name="again.json", no_app=True)


def test_start_round_without_app_freezes_then_first_report(env, capsys):
    """这个 pattern 还没有 app(没有哪个 mapping 写它):照常定格、不跑买点,提示建好 app 后再写快照;
    round_digest 照出定义与样本、结论写「没比」;revision_report 在还没有 app 时报错,建好 app 和 mapping 之后
    出第一版报告:没有旧版可比,用现在的 app 逐张给样本的结论(相反的排前、带链接),定格之后新放的样本不算。"""
    _save(env, _sample("s-pc-1", "AAA", D[10]), _sample("s-pc-2", "ZZZ", D[30], pattern="q"),
          _sample("s-pc-3", "AAA", D[100]), _sample("s-pc-4", "AAA", D[40], judgment="neg"),
          _sample("s-pc-5", "NOPE", D[30]),
          {"kind": "pattern", "id": "p", "base": None, "value": {"name": "p", "definition": "横盘后放量突破"}})
    with pytest.raises(ValueError, match="no_app=True"):                       # 没有 app 必须显式确认
        _start(env)
    rnd = _start(env, no_app=True)
    assert (rnd["app_id"], rnd["app_ver"], rnd["prev"], rnd["buys"], rnd["unavailable"]) == (None, None, None, {}, {})
    assert rnd["snapshot"]["seen"] == {"pc": 1}
    assert rnd["snapshot"]["samples"] == ["s-pc-1", "s-pc-3", "s-pc-4", "s-pc-5"]
    assert env.app.calls == []
    out = capsys.readouterr().out
    assert "还没有 app" in out and _printed_session(out) == {"snapshot": rnd["snapshot"]}
    with pytest.raises(FileExistsError):
        _start(env)

    with pytest.raises(ValueError, match="没有 app 可跑"):
        _report(env)
    digest = _digest(env)
    assert "- app：定格时还没有 app" in digest and "- 上一轮：没有（第一轮）" in digest
    assert "> 横盘后放量突破" in _section(digest, "定义")
    assert "还没有 app，也没有 mapping。" in _section(digest, "mapping")
    assert "没有上一轮的定格（第一轮），不比。" in _section(digest, "上一轮以来的变化")
    sec = _section(digest, "样本")
    assert "共 4 张：一致 0、相反 0、没比 4（还没有 app）。" in sec
    assert f"- 没比 [AAA {D[10]}]({_link(D[10])}) 正样本（s-pc-1）" in sec and "s-pc-2" not in digest
    assert "还没有 app，全部没比。" in _section(digest, "没比的")

    env.write_mapping(session=_printed_session(out))                 # 建好 app 和 mapping,写上开头的快照
    _save(env, _sample("s-pc-6", "AAA", D[200]))                     # 定格之后新放的:归下一轮
    env.app.buys = {"AAA": _buys({D[9]: [D[10]], D[38]: [D[40]]})}
    report = _report(env)
    assert report.startswith("# p 改版报告（第一版）") and "没有旧版可比" in report and "注意" not in report
    assert "- 读不到行情、没比的股票：NOPE" in report and "共 2 只股票" in report
    sec = _section(report, "样本结论")
    assert "样本 4 张：一致（✓）1、相反（✗）2、没比 1。" in sec
    assert sec.index("和 app 相反的：") < sec.index("没比的：") < sec.index("一致的：")
    assert f"- [AAA {D[40]}]({_link(D[40])}) 负样本（s-pc-4）：✗（`matched`）" in sec
    assert f"- [AAA {D[100]}]({_link(D[100])}) 正样本（s-pc-3）：✗（`unmatched`）" in sec
    assert f"- [NOPE {D[30]}]({_link(D[30], 'NOPE')}) 正样本（s-pc-5）：读不到行情" in sec
    assert f"- [AAA {D[10]}]({_link(D[10])}) 正样本（s-pc-1）：✓（`matched`）" in sec
    assert "s-pc-6" not in report and "① " not in report


def test_start_round_refuses_pattern_mapped_by_several_apps(env):
    """两个 app 的 mapping 写了同一个 pattern:分不清是哪个 app,定格、摘要、报告都报错(不当成「还没有 app」)。"""
    _save(env, _sample("s-pc-1", "AAA", D[10]))
    env.write_mapping()
    env.registry.ids = lambda: ["bo_only", "bo_only_copy"]
    env.registry.get = lambda a: bo_only
    with pytest.raises(ValueError, match="被几个 app 的 mapping 写了"):
        _start(env)
    assert not env.round().exists()


def test_round_digest_reads_everything_for_the_round(env, capsys):
    """摘要的各节:定义(pattern 定义、对到 node 与没对到的特征)、mapping notes、账本、上一轮以来的变化、issue
    (分组、次序、各处的状态与标签、范围里在买的日子、范围里的正样本、相对上一轮)、样本(相反的排前、带成员框)、
    读不到行情的股票。状态用定格时存下的买点:之后改 app、再改标注,摘要都不变。"""
    op = lambda kind, oid, value: {"kind": kind, "id": oid, "base": None, "value": value}   # noqa: E731
    _save(env,
          op("pattern", "p", {"name": "p", "definition": "横盘后放量突破\n不追高"}),
          op("feature", "w-pc-1", {"id": "w-pc-1", "name": "突破", "definition": "收盘站上平台上沿"}),
          op("feature", "w-pc-2", {"id": "w-pc-2", "name": "放量"}),
          op("feature", "w-pc-3", {"id": "w-pc-3", "name": "没用到的词"}),
          op("box", "b-pc-4", {"id": "b-pc-4", "symbol": "AAA", "feature": "w-pc-1", "start": D[5], "end": D[10],
                               "attrs": {"w-pc-2": True}, "note": "这根很标准"}),
          {**_sample("s-pc-5", "AAA", D[10]), "value": {**_sample("s-pc-5", "AAA", D[10])["value"],
                                                        "members": ["b-pc-4"]}},
          _sample("s-pc-6", "AAA", D[100]),                                              # 正样本没买到:相反
          _sample("s-pc-7", "NOPE", D[30]),                                              # 读不到行情:没比
          _fb("f-pc-8", "AAA", D[40], note="前一天长阴"))
    env.write_mapping(notes={"bo": "放量突破那一根"})
    env.app.buys = {"AAA": _buys({D[9]: [D[10], D[11]], D[38]: [D[40]]})}
    _start(env, name="r1.json")
    env.write_mapping(notes={"bo": "放量突破那一根"},
                      session={**_printed_session(capsys.readouterr().out),
                               "conditions": [{"where": "bo.no_long_black", "from": ["f-pc-8"], "state": "unmeasured"}],
                               "tags": {"f-pc-8": "for_tuning"}})

    _save(env,
          {**_fb("f-pc-8", "AAA", D[40], note="前一天放量长阴"), "base": _rev(env, "feedback", "f-pc-8")},
          _fb("f-pc-9", "AAA", D[9], D[12], target="family", family_start=D[9], note="追高了", nodes=["bo"],
              issue="i-pc-1"),
          _fb("f-pc-10", "BBB", D[20], D[22], target="range", note="追高了", nodes=["bo"], issue="i-pc-1"),
          _edit_sample(env, "s-pc-6", judgment="neg"))
    env.app.buys["BBB"] = _buys({})
    _finish(env, "r1.json")
    _start(env, name="r2.json")
    digest = _digest(env, name="r2.json")

    assert "- app：`bo_only`" in digest and "- 上一轮：有定格" in digest
    assert "- 读不到行情、没比的股票：NOPE" in digest and "- 注意：bo_only 的 mapping.yaml 里的定格不是这一轮开头那份" in digest
    sec = _section(digest, "定义")
    assert "> 横盘后放量突破\n> 不追高" in sec
    assert "对到 node 的特征：\n- `w-pc-1` 突破 → node `bo`\n  > 收盘站上平台上沿" in sec
    assert "还没对到 node 的特征：\n- `w-pc-2` 放量\n  > （没写）" in sec and "w-pc-3" not in digest
    assert "- notes：\n  - `bo`：放量突破那一根" in _section(digest, "mapping")
    sec = _section(digest, "账本")
    assert "- `bo.no_long_black` ← f-pc-8：unmeasured" in sec and "- f-pc-8 `for_tuning`" in sec
    assert "- sample `s-pc-6`（AAA " + D[100] + "）：`judgment`" in _section(digest, "上一轮以来的变化")

    sec = _section(digest, "issue")
    assert "共 2 个 issue、3 处；还在买 2 处、`lost` 0 处。" in sec
    assert sec.index("### `f-pc-8`") < sec.index("### `i-pc-1`")       # 同是还在买的,按名字
    assert "### `i-pc-1`（2 处，还在买 1 处）\n- 落在：bo\n- note：\n  > 追高了\n- 账本：还没有条件" in sec
    assert (f"  - [AAA {D[9]}～{D[12]}]({_link(D[9])}) `family`（起点 {D[9]}） `matched`；范围里在买 2 天：{D[10]}、{D[11]}；"
            f"范围里你的正样本：{D[10]}（s-pc-5）（f-pc-9，上一轮之后新标的）") in sec
    assert (f"  - [BBB {D[20]}～{D[22]}]({_link(D[20], 'BBB')}) `range` `unmatched`；范围里在买 0 天"
            "（f-pc-10，上一轮之后新标的）") in sec
    assert "- note：\n  > 前一天放量长阴\n- 账本：`bo.no_long_black`（unmeasured）" in sec
    assert (f"  - [AAA {D[40]}]({_link(D[40])}) `point` `matched`，标签 `for_tuning`；范围里在买 1 天：{D[40]}"
            "（f-pc-8，内容改过）") in sec

    sec = _section(digest, "样本")
    assert "共 3 张：一致 2、相反 0、没比 1。" in sec          # s-pc-6 改判成负样本后和 app 一致
    rows = [l for l in sec.splitlines() if l.startswith("- ")]
    assert [r.split("（")[-1] for r in rows] == ["s-pc-7）", "s-pc-5）", "s-pc-6）"]   # 没比的排在一致的前面
    assert f"- 一致 [AAA {D[10]}]({_link(D[10])}) 正样本，`matched`（s-pc-5）" in sec
    assert f"  - 框 `b-pc-4` 突破 {D[5]}～{D[10]}；属性：放量 是；note：这根很标准" in sec
    assert "  - （没收框）" in sec
    assert "- NOPE：" in _section(digest, "没比的")

    env.app.buys = {"AAA": _buys({}), "BBB": _buys({})}                                # 改 app、再改标注
    _save(env, _sample("s-pc-11", "AAA", D[200]))
    assert _digest(env, name="r2.json") == digest


def test_round_digest_puts_samples_against_the_app_first(env):
    """和 app 相反的样本(正样本没买到、负样本买了)排在最前并加粗;三个张数对得上。"""
    _save(env, _sample("s-pc-1", "AAA", D[10]), _sample("s-pc-2", "AAA", D[100]),
          _sample("s-pc-3", "AAA", D[40], judgment="neg"))
    env.write_mapping()
    env.app.buys = {"AAA": _buys({D[9]: [D[10]], D[38]: [D[40]]})}
    _start(env)
    sec = _section(_digest(env), "样本")
    assert "共 3 张：一致 1、相反 2、没比 0。" in sec
    rows = [l for l in sec.splitlines() if l.startswith("- ")]
    assert rows[0].startswith(f"- **相反** [AAA {D[40]}]") and "负样本，`matched`（s-pc-3）" in rows[0]
    assert rows[1].startswith(f"- **相反** [AAA {D[100]}]") and "正样本，`unmatched`（s-pc-2）" in rows[1]
    assert rows[2].startswith(f"- 一致 [AAA {D[10]}]")
    assert "这个 pattern 还没有反馈。" in _section(_digest(env), "issue")
