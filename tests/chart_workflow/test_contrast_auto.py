"""对照页与大涨段自动记账:每生成一次追加一行账本(auto)、规则按内容指纹存档且不重复写、
追加账本失败就不留清单、拿不到状态根什么都不生成、手动 add 对已自动记账的清单拒绝;
清单名用过就拒绝(不覆盖旧清单);脚本里直接调 build_list 也记账;每行带 provenance;
内圈年份:命中只留 2025,summary 逐年行只有 2025,params 记过滤前后命中数;盲看抽样同股不互相露底。"""
import json

import pandas as pd
import pytest

from chart_workflow import bigmoves, contrast
from chart_workflow.config import root_dir
from chart_workflow.contrast import archive_rule, build_list as build_contrast
from chart_workflow.ledger import add_round, read_ledger, render
from chart_workflow.panel import build_panel
from chart_workflow.state import StateRootMissing
from tests.chart_workflow.conftest import make_stock

CTX = {"kind": "rule", "rule_id": "r", "version": "x", "source": "user-text", "change": "测试"}

RULE = '''
def signal(df):
    return df["close"] > df["close"].rolling(20).max().shift(1)
'''


@pytest.fixture
def env(cw_env, tmp_path, monkeypatch):
    cfg, pkl_dir = cw_env
    for i in range(3):
        make_stock(seed=40 + i).to_pickle(pkl_dir / f"C{i}.pkl")
    rule = tmp_path / "breakout20.py"
    rule.write_text(RULE)
    monkeypatch.setattr(contrast, "load_config", lambda: cfg)
    monkeypatch.setattr(bigmoves, "load_config", lambda: cfg)
    return cfg, rule


def _lists(cfg):
    d = root_dir(cfg) / "lists"
    return sorted(p.name for p in d.glob("*.json")) if d.exists() else []


def test_contrast_auto_ledger_and_archive(env, state_dir):
    cfg, rule = env
    contrast.main(["--list-id", "t-c1", "--rule", str(rule), "--source", "user-text",
                   "--change", "首版", "--no-xcheck"])
    rows = read_ledger()
    assert len(rows) == 1
    r = rows[0]
    assert r["auto"] is True and r["kind"] == "rule" and r["list_id"] == "t-c1"
    assert r["rule_id"] == "breakout20" and r["years"] == ["2025"]
    assert r["version"] == contrast.rule_fingerprint(rule)
    arch = state_dir / r["rule_archive"]
    assert arch.read_bytes() == rule.read_bytes()
    assert r["rule_archive"].startswith(f"rule_archive/{r['rule_sha'][:16]}__")
    assert r["app_commit"] is None and r["app_dirty"] is None
    # 同一规则再跑一次(盲看):多一行 blind,不重复存档
    contrast.main(["--list-id", "t-c2", "--rule", str(rule), "--source", "user-text",
                   "--change", "盲看", "--blind", "--no-xcheck"])
    rows = read_ledger()
    assert [x["kind"] for x in rows] == ["rule", "blind"]
    assert len(list((state_dir / "rule_archive").iterdir())) == 1
    assert "累计尝试次数：2" in render(rows)                  # 盲看轮暂按尝试计(保守)
    # 手动 add 对已自动记账的清单拒绝
    with pytest.raises(ValueError, match="已自动记账"):
        add_round(cfg, kind="rule", rule_id="x", version="v", source="user-text", change="x",
                  list_id="t-c1")
    # mining 来源记成 mined
    contrast.main(["--list-id", "t-c3", "--rule", str(rule), "--source", "mining",
                   "--change", "挖掘", "--no-xcheck"])
    assert read_ledger()[-1]["kind"] == "mined"


def test_ledger_failure_leaves_no_list(env, state_dir, monkeypatch):
    cfg, rule = env
    import chart_workflow.ledger as ledger_mod

    def boom(*a, **k):
        raise StateRootMissing("状态根 … 下没有标记文件 STATE_ROOT.md:可能切到了别的分支")
    # 普通模式:成绩算完当场记账,记不进去就不算、不写清单
    monkeypatch.setattr(ledger_mod, "record_round", boom)
    with pytest.raises(SystemExit):
        contrast.main(["--list-id", "t-fail", "--rule", str(rule), "--source", "user-text",
                       "--change", "x", "--no-xcheck"])
    # 盲看模式:写好清单再记账,记不进去就删掉清单
    monkeypatch.setattr(contrast, "add_round", boom)
    with pytest.raises(SystemExit):
        contrast.main(["--list-id", "t-failb", "--rule", str(rule), "--source", "user-text",
                       "--change", "x", "--blind", "--no-xcheck"])
    assert "t-fail.json" not in _lists(cfg) and "t-failb.json" not in _lists(cfg)
    assert read_ledger() == []


def test_duplicate_list_id_refused(env, state_dir):
    cfg, rule = env
    contrast.main(["--list-id", "t-dup", "--rule", str(rule), "--source", "user-text",
                   "--change", "首版", "--no-xcheck"])
    before = (root_dir(cfg) / "lists" / "t-dup.json").read_bytes()
    for extra in ([], ["--blind"]):
        with pytest.raises(SystemExit):
            contrast.main(["--list-id", "t-dup", "--rule", str(rule), "--source", "user-text",
                           "--change", "再来", "--no-xcheck", *extra])
    with pytest.raises(SystemExit):
        bigmoves.main(["--list-id", "t-dup", "--no-xcheck"])
    assert (root_dir(cfg) / "lists" / "t-dup.json").read_bytes() == before   # 旧清单没被覆盖
    assert len(read_ledger()) == 1
    # 清单文件被删了,账本里有过这个名字也不许再用
    (root_dir(cfg) / "lists" / "t-dup.json").unlink()
    with pytest.raises(SystemExit):
        contrast.main(["--list-id", "t-dup", "--rule", str(rule), "--source", "user-text",
                       "--change", "再来", "--no-xcheck"])
    assert len(read_ledger()) == 1


def test_scripted_scoring_still_recorded(env):
    """会话在脚本里直接调 build_list:不给记账上下文就拒绝算;给了就当场记一行。"""
    cfg, rule = env
    panel = build_panel(cfg, verbose=False)
    hits = contrast.hits_from_rule(rule, sorted(panel["symbol"].unique()), cfg)
    with pytest.raises(ValueError, match="记账"):
        build_contrast(panel, hits, cfg, "t-s0", False, "r.py@x")
    assert read_ledger() == []
    doc = build_contrast(panel, hits, cfg, "t-s1", False, "r.py@x", ledger=CTX)
    rows = read_ledger()
    assert len(rows) == 1 and rows[0]["list_id"] == "t-s1"
    assert rows[0]["entry_id"] == doc["summary"]["ledger_entry_id"]


def test_ledger_rows_carry_provenance(env, state_dir):
    cfg, rule = env
    contrast.main(["--list-id", "t-p1", "--rule", str(rule), "--source", "user-text",
                   "--change", "首版", "--no-xcheck"])
    bigmoves.main(["--list-id", "t-p2", "--no-xcheck"])
    for r in read_ledger():
        pv = r["provenance"]
        assert len(pv["commit"]) == 40
        assert set(pv["dirty"]) == {"chart_workflow", "path2"}
        assert all(isinstance(v, bool) for v in pv["dirty"].values())
        archived = json.loads((state_dir / pv["config_archive"]).read_text())
        assert archived["train_end"] == cfg["train_end"]
        assert pv["config_archive"] == f"config_archive/{pv['config_sha']}.json"
        assert len(pv["data_errors_sha"]) == 16
        assert pv["snapshot"]["cutoff"] == "2025-12-31" and len(pv["snapshot"]["sha"]) == 16
        assert pv["snapshot"]["created_at"] == "2026-10-17T00:00:00"
    # 配置相同 → 存档只有一份
    assert len(list((state_dir / "config_archive").iterdir())) == 1


def test_missing_state_root_generates_nothing(env, tmp_path, monkeypatch):
    cfg, rule = env
    monkeypatch.setenv("CHART_WORKFLOW_STATE_ROOT", str(tmp_path / "no_marker"))
    with pytest.raises(SystemExit):
        contrast.main(["--list-id", "t-x", "--rule", str(rule), "--source", "user-text",
                       "--change", "x", "--no-xcheck"])
    with pytest.raises(SystemExit):
        bigmoves.main(["--list-id", "t-b", "--no-xcheck"])
    assert _lists(cfg) == []
    assert not (root_dir(cfg) / "cache").exists()             # 连面板都没算


def test_bad_source_stops_before_anything(env):
    cfg, rule = env
    for src in ("bogus", "shape:s009@v1"):                    # 格式不对 / 形态卡不存在
        with pytest.raises(SystemExit):
            contrast.main(["--list-id", "t-x", "--rule", str(rule), "--source", src,
                           "--change", "x", "--no-xcheck"])
    assert _lists(cfg) == [] and read_ledger() == []


def test_bigmoves_auto_ledger_not_an_attempt(env):
    cfg, _ = env
    cfg["bigmoves"]["rel_min"] = 0.5
    bigmoves.main(["--list-id", "t-big", "--no-xcheck"])
    r = read_ledger()[-1]
    assert (r["kind"], r["source"], r["auto"], r["change"]) == ("bigmoves", "bigmoves", True,
                                                                "生成大涨段清单")
    assert "累计尝试次数：0" in render(read_ledger())
    doc = json.loads((root_dir(cfg) / "lists" / "t-big.json").read_text())
    assert all(it["t"] >= "2025-01-01" and it["view_start"] >= "2025-01-01" for it in doc["items"])


def test_inner_years_only_2025(env):
    cfg, rule = env
    panel = build_panel(cfg, verbose=False)
    hits = contrast.hits_from_rule(rule, sorted(panel["symbol"].unique()), cfg)
    years = set(pd.to_datetime(hits["date"]).dt.year)
    assert {2024, 2025} <= years                              # 合成数据两年都有命中
    doc = build_contrast(panel, hits, cfg, "t-in", False, "r.py@x", ledger=CTX)
    assert [r["scope"] for r in doc["summary"]["rows"]] == ["全部", "2025"]
    assert all(it["t"].startswith("2025") for it in doc["items"])
    p = doc["params"]
    assert p["inner_years"] == ["2025"] and p["n_raw_hits"] == len(hits)
    assert p["n_hits_inner_years"] == int((pd.to_datetime(hits["date"]).dt.year == 2025).sum())
    assert p["n_pool_hits"] <= p["n_hits_inner_years"] < p["n_raw_hits"]
    assert doc["summary"]["rows"][0]["n_hits"] == doc["summary"]["rows"][1]["n_hits"]
    assert list(doc["summary"]["graduation"]["checks"])       # 毕业判定照常给出
    blind = build_contrast(panel, hits, cfg, "t-inb", True, "r.py@x")
    assert blind["items"] and all(it["t"].startswith("2025") for it in blind["items"])


def test_blind_sample_never_reveals_same_stock(env):
    """盲看抽样:同股两条,谁的决策日都不落在另一条的图窗里;抽样顺序只来自种子(与结果无关)。"""
    from chart_workflow.listfile import view_window
    cfg, rule = env
    cfg = {**cfg, "contrast": {**cfg["contrast"], "n_blind": 1000}}
    panel = build_panel(cfg, verbose=False)
    hits = contrast.hits_from_rule(rule, sorted(panel["symbol"].unique()), cfg)
    doc = build_contrast(panel, hits, cfg, "t-bl", True, "r.py@x")
    items = doc["items"]
    assert len({it["symbol"] for it in items}) < len(items)       # 同股多条确实出现
    for a in items:
        s, e = view_window(cfg, a["symbol"], a["t"], blind=True)
        assert a["view_start"] == str(s.date()) and a["view_end"] == str(e.date())
        for b in items:
            if a is not b and a["symbol"] == b["symbol"]:
                assert not (a["view_start"] <= b["t"] <= a["view_end"])


def test_app_archive_records_commit_and_params(state_dir, tmp_path):
    params = tmp_path / "p.yaml"
    params.write_text("bo:\n  total_window: 20\n")
    out = archive_rule(state_dir, None, "bo_only", str(params))
    assert (state_dir / out["rule_archive"]).read_bytes() == params.read_bytes()
    assert len(out["app_commit"]) == 40 and isinstance(out["app_dirty"], bool)
