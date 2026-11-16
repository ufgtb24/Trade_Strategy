"""票 17 真数据核一次接通(一次性核对,随 app 改版会变,不进例子文件)。

把票 16 Question「实测」表里 4 条整族反馈的旧阶跃起止当作存下的 reference,连同它们的日期范围(取自 new_step 第 1、2 轮
的改版报告与清单,不读标注目录)直接喂给判法:当前 new_step(经 path2_web/app_run.py 的 run_app 读训练段副本,
全历史区间、label_horizon 20,同反馈状态接口)下应得 QBTS matched、IXHL unmatched、CRNC matched、LUMN matched。
另把每条的范围换成一段没有买点的日子再判一次,看「同一次形状还在买」那一支自己判得对不对。

    .venv/bin/python .scratch/annotation-path2-implementation/evidence/17/real_data_check.py
"""
import json

from path2_web.annotation import match
from path2_web.app_run import app_buys, run_app
from path2_web.app_version import app_ver
from path2_web.config import load_config
from path2_web.data import TRAIN_END
from path2_web.discovery import PatternRegistry

CASES = [  # (反馈, 股票, 范围, 存下的阶跃起止, 应得)
    ("f-pc-92", "QBTS", ("2025-03-18", "2025-03-25"), [["2025-03-14", "2025-03-14"]], "matched"),
    ("f-pc-90", "IXHL", ("2025-08-29", "2025-09-26"), [["2025-08-22", "2025-08-25"]], "unmatched"),
    ("f-pc-74", "CRNC", ("2025-01-07", "2025-01-30"), [["2025-01-03", "2025-01-03"]], "matched"),
    ("f-pc-95", "LUMN", ("2024-08-09", "2024-10-02"), [["2024-08-06", "2024-08-07"]], "matched"),
]


def main():
    mod = PatternRegistry().get("new_step")
    params = mod.load_params()
    out = {"new_step_app_ver": app_ver(mod), "rows": []}
    for fid, sym, (start, end), spans, want in CASES:
        res, win, meta = run_app(mod, load_config(), sym, "1900-01-01", TRAIN_END, params, 20)
        buys = app_buys(res, win, meta["end_node"], reference="step")
        fb = {"id": fid, "target": "family", "start": start, "end": end,
              "reference": {"node": "step", "spans": spans}}
        in_range = [d for d in buys.buy_days if start <= d <= end]
        shape = [{"spans": [list(s) for s in buys.hits[i].spans], "buy_days": list(buys.hits[i].buy_days)}
                 for i in match.feedback_hits(fb, buys)
                 if not any(start <= d <= end for d in buys.hits[i].buy_days)]
        overl = [list(e) for e in buys.ref_spans if any(e[0] <= b[1] and b[0] <= e[1] for b in spans)]
        got = match.feedback_status(fb, buys)
        shape_only = match.feedback_status({**fb, "start": "1900-01-02", "end": "1900-01-02"}, buys)
        out["rows"].append({"feedback": fid, "symbol": sym, "range": [start, end], "stored": spans,
                            "buys_in_range": in_range, "shape_hits_buying_outside_range": shape,
                            "ref_events_sharing_bars": overl, "status": got, "want": want, "ok": got == want,
                            "status_without_range_buys": shape_only})
    print(json.dumps(out, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
