"""一次性：用改前（HEAD）或改后（工作区）的 new_step 跑 13 只标注股，存下每个 plateau 实例的段起止与字段。

用法：uv run python extract.py old|new
输出：repro/cache_<old|new>.pkl
只读训练段副本（经 path2_web.app_run.run_app）。
"""
import pickle
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE / "oldpkg"))

from path2_web.app_run import run_app  # noqa: E402
from path2_web.annotation.revision import FIRST_DAY, LABEL_HORIZON  # noqa: E402
from path2_web.config import load_config  # noqa: E402
from path2_web.data import TRAIN_END  # noqa: E402

STOCKS = ["IXHL", "QBTS", "CRNC", "INDO", "KULR", "LUMN", "CAPR", "IZM", "TNXP",
          "DXYZ", "GEVO", "RGTI", "SMX"]


def main():
    which = sys.argv[1]
    if which == "old":
        import new_step_old.dag_spec as mod
    else:
        import path2_apps.new_step.dag_spec as mod
    cfg = load_config()
    params = mod.load_params()
    out = {}
    for sym in STOCKS:
        res, win, meta = run_app(mod, cfg, sym, FIRST_DAY, TRAIN_END, params, LABEL_HORIZON)
        day = pd.to_datetime(win["date"]).dt.strftime("%Y-%m-%d").tolist()
        hit_ids = {id(h.node_index["plateau"]) for h in res.hits}
        evs = []
        for e in res.events:
            if e.node_id != "plateau":
                continue
            rec = {k: getattr(e, k) for k in e.__dataclass_fields__
                   if isinstance(getattr(e, k), (int, float, type(None))) and k not in ("node_id",)}
            rec.update(s=e.step.start_idx, e=e.step.end_idx, t=e.today.start_idx,
                       old_s=e.old.start_idx, new_s=e.new.start_idx, new_e=e.new.end_idx,
                       step_rise=e.step.rise, step_max_ret=e.step.max_ret, step_bars=e.step.bars,
                       old_level=e.old.level, hit=id(e) in hit_ids)
            for k in e.step.__dataclass_fields__:
                v = getattr(e.step, k)
                if isinstance(v, (int, float, type(None))) and k not in ("node_id",):
                    rec["step." + k] = v
            evs.append(rec)
        bars = win[["open", "high", "low", "close", "volume"]].to_numpy(dtype=float)
        out[sym] = {"day": day, "bars": bars, "events": evs}
        print(sym, len(day), "events", len(evs), "hits", sum(r["hit"] for r in evs))
    with open(HERE / f"cache_{which}.pkl", "wb") as f:
        pickle.dump(out, f)


if __name__ == "__main__":
    main()
