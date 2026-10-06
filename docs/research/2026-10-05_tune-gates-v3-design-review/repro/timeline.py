"""bb 一轮 v3 调参的最早出结论日期推算（临时研究脚本）。

假设：最后检查回看起点紧接 bb_v1 向前确认窗之后（2026-08-18）；首部回看 63 交易日；
买点窗 3/4/6 个月；H=40/20；复核回看起点紧接最后检查 label_end 之后。NYSE 日历。
"""
import bisect
import datetime as dt

import pandas_market_calendars as mcal

cal = [d.date() for d in mcal.get_calendar("NYSE").valid_days("2026-01-01", "2030-12-31")]


def add(d, n):
    """d 之后第 n 个交易日。"""
    return cal[bisect.bisect_right(cal, d) + n - 1]


def months_later(d, m):
    y, mo = d.year + (d.month - 1 + m) // 12, (d.month - 1 + m) % 12 + 1
    return dt.date(y, mo, min(d.day, 28))


for H in (40, 20):
    for buy in (3, 4, 6):
        f_start = add(dt.date(2026, 8, 17), 64)
        f_label = add(months_later(f_start, buy), H)
        r_start = add(add(f_label, 1), 63)
        r_label = add(months_later(r_start, buy), H)
        print(f"H={H} 买点窗{buy}个月: 最后检查 >{f_label}  复核 >{r_label}")
