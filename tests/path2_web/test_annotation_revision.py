"""会话侧的定格与改版报告(path2_web/annotation/revision.py)。

不读行情:跑 app 的两步(run_app、app_buys)和版本指纹 app_ver 换成合成结果,标注写在临时目录,mapping 改从
临时目录读(<tmp>/mappings/<app>.yaml),不往 path2_apps/ 里写。

钉住的要求:
- start_round:上一轮定格抄成 prev;新快照记 {机器: 连续到齐的序号}、这个 pattern 的样本编号;股票 = 上一轮
  ∪ 这一轮里这个 pattern 有样本或反馈的股票;全历史区间、label_horizon 20 跑 app;打印的 YAML 写进 mapping 后
  会话段形状合格;round 文件已存在时拒绝覆盖;
- 第一轮(没有上一轮定格)且 app 没改:报告写「无变化」;mapping 没写新快照时开头提醒;
- 反馈状态的新旧对照(含上一轮之后新加、删掉的反馈),lost 留一行待会话交代,反馈范围里砍掉的买点只给个数;
  会话段写坏时开头说明、原因标签当作没有,不误报「定格没写」;
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

    def write_mapping(pattern="p", session=None):
        doc = {"pattern": pattern, "features": {"w-pc-1": "bo"}}
        if session is not None:
            doc["session"] = session
        (mdir / "bo_only.yaml").write_text(yaml.safe_dump(doc, allow_unicode=True), encoding="utf-8")

    return SimpleNamespace(
        cfg={"annotation_dir": str(adir), "machine": "pc", "frontend_port": 5171}, adir=adir,
        registry=SimpleNamespace(ids=lambda: ["bo_only"], get=lambda a: bo_only if a == "bo_only" else None),
        app=app, write_mapping=write_mapping, round=lambda name="round.json": tmp_path / "scratch" / name)


def _start(env, pattern="p", name="round.json"):
    return revision.start_round(pattern, env.round(name), cfg=env.cfg, registry=env.registry)


def _report(env, pattern="p", name="round.json", **kw):
    return revision.revision_report(pattern, env.round(name), cfg=env.cfg, registry=env.registry, **kw)


def _printed_session(out: str) -> dict:
    """start_round 打印的 YAML(去掉 # 开头的说明行)→ {snapshot: ...}。"""
    return yaml.safe_load("\n".join(l for l in out.splitlines() if not l.startswith("#")))["session"]


def _sample(oid, symbol, date, judgment="pos", pattern="p", base=None):
    return {"kind": "sample", "id": oid, "base": base,
            "value": {"id": oid, "symbol": symbol, "date": date, "pattern": pattern, "judgment": judgment,
                      "members": []}}


def _fb(oid, symbol, start, end=None, target="point", pattern="p", **extra):
    """一条反馈;缺省是 point / neg / 写了理由。note=None 表示不带理由。"""
    v = {"id": oid, "symbol": symbol, "pattern": pattern, "app_id": "bo_only", "app_ver": "0123456789abcdef",
         "start": start, "end": end or start, "target": target, "source": "picked", "answer": "neg",
         "note": "不该买", **extra}
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
                                                  note=None, segments=["bo"]),
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
    lines = [l for l in sec.splitlines() if l.startswith("- ")]
    assert len(lines) == 3   # 两条变了的 + 一条 lost 待填
    assert "（f-pc-1）：`matched` → `unmatched`" in lines[0]
    assert "（f-pc-2）：`matched` → `lost`" in lines[1]
    assert "（f-pc-2）：（待填：改好了 / 认法变了）" in lines[2]
    assert "其余 3 条没变" in sec
    assert "现在 5 条反馈：朱红 1 条、`lost` 1 条、`unmatched` 2 条。" in sec
    assert "共 3 天。" in _section(_report(env), "② ")
    assert "没有。" in _section(_report(env), "③ ")


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
    rows = [l.split(") ", 1)[1] for l in sec.splitlines() if l.startswith("- ")]
    assert rows == ["`neg`「不该买」（f-pc-1）：`matched` → （没有这条）",
                    "`neg`「不该买」（f-pc-3）：（没有这条） → `matched`"]
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
    rnd = _start(env, name="r2.json")
    assert rnd["prev"]["seen"] == {"pc": 2} and rnd["snapshot"]["seen"] == {"pc": 4}
    sec = _section(_report(env, name="r2.json"), "⑤ ")
    assert "没有翻转。" in sec and "新放 / 挪进 1 张：✓ 1、✗ 0" in sec
    assert "（s-pc-4）（新放）：✓（`matched`）" in sec
