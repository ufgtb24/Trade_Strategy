"""参照层 peaks:一只股票在训练段里的峰,给标注图画成水平线。

峰取自 bo 检测(path2.atoms.breakout.BODetector,用它的构造默认参数)产出的 pk 流;峰不是 app
认出的东西,这里只把探测器的输出投影成 JSON,不做二次判定。输入是 data.read_bars 读出的行情
(已截到训练段末日 TRAIN_END),所以截止之后的行情既不会生出峰,也不会让峰的线变短。

每个峰一条线 {date, price, end}:
- date:峰所在那根 K 线的日期(PeakEvent.peak_idx,不是晚几根才确认的登记日);
- price:峰登记时的价(探测器之后因小幅突破抬高的价不算,取 original_price);
- end:线画到哪根为止 = 第一次被突破的那根(第一个在 broken 引用里收了它的 bo),没被突破的画到最后一根。
  被更高的新峰吃掉(superseded)的峰不另算:更高的那根 K 线越过它时,它已经被突破过了。
"""
from __future__ import annotations

import pandas as pd

from path2.atoms.breakout import BODetector
from path2.runner import run_bundle


def peak_lines(df: pd.DataFrame) -> list[dict]:
    """df:data.read_bars 的结果(DatetimeIndex 名 date,按日期升序)。返回按峰日期排序的
    [{date, price, end}],日期是 YYYY-MM-DD;没有行情时返回空表。"""
    if len(df) == 0:
        return []
    bars = df.reset_index()
    dates = bars["date"].dt.strftime("%Y-%m-%d").tolist()
    streams = run_bundle(BODetector(), bars)
    end_idx: dict[int, int] = {}
    for bo in streams["bo"]:                       # bo 流按 K 线先后排,先收到的就是第一次被突破
        for pk in bo.broken_refs:
            end_idx.setdefault(pk.pk_id, bo.start_idx)
    last = len(bars) - 1
    lines = []
    for pk in streams["pk"]:
        price = pk.original_price if pk.original_price is not None else pk.price
        end = end_idx.get(pk.pk_id, last)
        lines.append({"date": dates[pk.peak_idx], "price": float(price), "end": dates[end]})
    lines.sort(key=lambda r: r["date"])
    return lines
