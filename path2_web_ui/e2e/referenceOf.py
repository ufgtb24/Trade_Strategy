"""e2e 专用:后端这一头对同一批 hit 取出的基准 event 起止与一条反馈收进来的 hit,给页面那一头对照。

e2e/feedback.spec.ts 经页面新建一条整族反馈后,用它核对:页面存下的 reference.spans 与后端从同一族 hit 取出的基准
event 起止逐段相同(起止由页面算,算错会永久留在标注里、页面上看不出);页面选中这条反馈时牵出的 hit
(annotate/feedback.ts 的 feedbackHits)与后端判法(path2_web/annotation/match.py 的 feedback_hits)是同一批。

    python path2_web_ui/e2e/referenceOf.py <app> <股票> <基准 node> <族起点日期> <反馈 JSON>

由测试调起、不给人手动运行,所以从命令行取参数。跑 app 的区间同反馈状态接口(全历史到训练段末日、
label_horizon 20),行情经 path2_web/app_run.py 的 run_app 读训练段副本。反馈 JSON 给 {} 时只算族的起止。打印 JSON:
{family_spans: [[start, end], …](起点为族起点日期的那些 hit 的基准 event 起止,去重、按起止排序),
 feedback_hits: [hit_id, …](按 res.hits 的先后)}。不读也不写标注目录。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))


def main() -> None:
    from path2_web.annotation import match
    from path2_web.app_run import app_buys, run_app
    from path2_web.config import load_config
    from path2_web.data import TRAIN_END
    from path2_web.discovery import PatternRegistry

    app, symbol, reference, family_start, fb = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4], json.loads(sys.argv[5])
    mod = PatternRegistry().get(app)
    load = getattr(mod, "load_params", None)
    res, win, meta = run_app(mod, load_config(), symbol, "1900-01-01", TRAIN_END, load() if callable(load) else None, 20)
    buys = app_buys(res, win, meta["end_node"], reference=reference)
    starts = [buys.dates[h.start_idx] for h in res.hits]
    spans = sorted({tuple(sp) for hb, st in zip(buys.hits, starts) if st == family_start for sp in hb.spans})
    print(json.dumps({"family_spans": [list(sp) for sp in spans],
                      "feedback_hits": [res.hits[i].hit_id for i in match.feedback_hits(fb, buys)] if fb else []}))


if __name__ == "__main__":
    main()
