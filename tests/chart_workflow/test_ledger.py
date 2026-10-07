"""账本:轮次自动加 1;盲看清单 summary_all 为 null;show 末尾给累计尝试次数。"""
import json

import pytest

from chart_workflow.ledger import add_round, read_ledger, render


def _list(cfg, list_id, summary=None, kind="contrast"):
    d = cfg_root(cfg) / "lists"
    d.mkdir(parents=True, exist_ok=True)
    doc = {"list_id": list_id, "kind": kind}
    if summary is not None:
        doc["summary"] = summary
    (d / f"{list_id}.json").write_text(json.dumps(doc, ensure_ascii=False))


def cfg_root(cfg):
    from chart_workflow.config import root_dir
    return root_dir(cfg)


SUMMARY = {"rows": [{"scope": "全部", "n_hits": 10, "dir_lead": 0.2, "dir_noise": 0.05,
                     "mag_lead": 0.01, "mag_noise": 0.004}],
           "graduation": {"passed": True, "checks": {}}}


def test_add_and_show(cw_env):
    cfg, _ = cw_env
    _list(cfg, "r1-blind", kind="contrast_blind")
    _list(cfg, "r1-contrast", SUMMARY)
    e1 = add_round(cfg, kind="rule", rule_id="q", version="v1", source="user-text",
                   change="盲看", list_id="r1-blind")
    e2 = add_round(cfg, kind="rule", rule_id="q", version="v1", source="annotation:20261008T101500",
                   change="首版", list_id="r1-contrast")
    assert (e1["round"], e2["round"]) == (1, 2)
    assert e1["summary_all"] is None and e1["graduated"] is None
    assert e2["summary_all"] == {"n_hits": 10, "dir_lead": 0.2, "dir_noise": 0.05,
                                 "mag_lead": 0.01, "mag_noise": 0.004}
    assert e2["graduated"] is True
    rows = read_ledger(cfg)
    assert len(rows) == 2
    text = render(rows)
    assert "累计尝试次数：2" in text and "+0.200" in text


def test_bad_source_and_missing_list(cw_env):
    cfg, _ = cw_env
    _list(cfg, "r1-contrast", SUMMARY)
    with pytest.raises(ValueError):
        add_round(cfg, kind="rule", rule_id="q", version="v1", source="bogus", change="x",
                  list_id="r1-contrast")
    with pytest.raises(FileNotFoundError):
        add_round(cfg, kind="rule", rule_id="q", version="v1", source="mining", change="x",
                  list_id="nope")
