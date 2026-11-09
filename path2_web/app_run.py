"""跑一次 app、取它的买点日(纯 Python,不依赖 FastAPI)。

单股预览(GET /preview)、反馈状态接口与会话的改版报告共用这一份「跑 app」:同一套缓冲窗、同一条读行情的路
(path2_web/data.py 的 read_bars,截到训练段末日),所以三处看到的买点一致。

- require_eval_meta:读 app 的 eval_meta()(买点 node、首部缓冲交易日数);
- run_app:按 eval_meta 拉宽缓冲窗、切 K 线、跑 app.analyze,返回 (结果, 切好的 K 线, 元信息);
- app_buys:从跑出的结果里取买点日、按起点分的族、参与求解的 node 的事件起点、窗口内全部交易日,
  打包成 AppBuys(全是日期字符串,能 JSON 往返,会话的改版报告要存盘);
- 读不到行情时抛 BarsUnavailable 的三个子类(同时是 FileNotFoundError / ValueError),由调用方映射:
  单股预览照原来的 503 / 404 / 400,反馈状态接口把那只股票记成读不到、不整体失败。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

import pandas as pd

from path2.dag._solve import compile_plan
from path2.eval import _resolve_end_events
from path2_web import data as _data
from path2_web import scan as scan_mod
from path2_web.config import view_dataset_dir
from path2_web.data import TRAIN_END, slice_window


# ───────────────────────── 读行情 ─────────────────────────
class BarsUnavailable(Exception):
    """读不到这只股票的行情(下面三种之一)。"""


class NoDataDir(BarsUnavailable, FileNotFoundError):
    """配置的行情目录不存在(单股预览映射成 503)。"""


class NoSymbol(BarsUnavailable, FileNotFoundError):
    """行情目录里没有这只股票(单股预览映射成 404)。"""


class BadSymbol(BarsUnavailable, ValueError):
    """代码名不合格(单股预览映射成 400)。"""


def load_bars(cfg: dict, symbol: str) -> pd.DataFrame:
    """读一只股票截到训练段末日的行情:先查配置的行情目录在不在,再经 data.read_bars 读
    (按模块属性调用,测试把 path2_web.data.read_bars 换成替身时这里同样生效)。"""
    d = view_dataset_dir(cfg)
    if not d.is_dir():
        raise NoDataDir(f"行情目录不存在: {d}(用 scripts/data/make_train_snapshot.py 生成)")
    try:
        return _data.read_bars(d, symbol)
    except FileNotFoundError:
        raise NoSymbol(f"pkl not found: {symbol}") from None
    except ValueError as e:
        raise BadSymbol(str(e)) from None


# ───────────────────────── 跑 app ─────────────────────────
def require_eval_meta(mod, params=None) -> dict:
    """读 app 模块 eval_meta() 协议。params 显式传入时用之(override 场景 head_buffer
    必须按 override 参数算,否则缓冲不足导致漏检伪装成"参数没起效");否则回退 load_params()
    (现状行为)。铁律下 discovery 已闸过滤,api 调到此处不可能 None。
    若仍 None / 字段不全 → ValueError(防御性,非业务路径)。
    """
    fn = getattr(mod, "eval_meta", None)
    if not callable(fn):
        raise ValueError("eval_meta missing or non-callable (discovery gate failed)")
    if params is None:
        load_params = getattr(mod, "load_params", None)
        params = load_params() if callable(load_params) else None
    meta = fn(params) if params is not None else fn()
    if not isinstance(meta, dict) or "end_node" not in meta or "head_buffer_trading_days" not in meta:
        raise ValueError(f"eval_meta returned invalid dict: {meta!r}")
    return meta


def run_app(mod, cfg: dict, symbol: str, start: str, end: str, params, label_horizon: int = 20):
    """单股跑一次 app(复刻 multi-scan worker 的缓冲窗链路,不落盘)。

    参数:mod 是 app 的 dag_spec 模块;cfg 是网页配置(只用其中的行情目录);start / end 是要看的区间
    (YYYY-MM-DD,终点再截到训练段末日);params 是这次用的参数对象(None 时 eval_meta 回退 load_params、
    analyze 用 app 的默认参数,同单股预览原来的行为);label_horizon 是区间终点后要多带的交易日数。

    算法:按 eval_meta 的首部缓冲交易日数把起点往前推、按 label_horizon 把终点往后推(交易日换日历日的
    系数同扫描),终点不越过训练段末日;切出这段 K 线(下标 0 起,与 detector 看到的位置一一对齐)后跑
    mod.analyze。

    返回 (res, win, meta):res 是 analyze 的结果;win 是切好的 K 线(含 date 列);meta 是单股预览的
    scan 元信息 {start_date, end_date, win_start, win_end, label_horizon, end_node}。
    读不到行情 → BarsUnavailable 的子类;eval_meta 不合格 → ValueError;app 自身的异常原样抛出。
    """
    end = min(end, TRAIN_END)
    meta = require_eval_meta(mod, params=params)
    end_node = meta["end_node"]
    head_buf = meta["head_buffer_trading_days"]
    ratio = scan_mod.TRADING_TO_CALENDAR_RATIO
    start_ts, end_ts = pd.to_datetime(start), pd.to_datetime(end)
    buf_start = str((start_ts - pd.Timedelta(days=round(head_buf * ratio))).date())
    buf_end = str((end_ts + pd.Timedelta(days=round(label_horizon * ratio))).date())
    buf_end = min(buf_end, TRAIN_END)   # 行情本来就只读到训练段末日;回给前端的窗口也不越过它

    # 复刻 worker 单 pattern 调用(含样本消费窗截取,口径与 scan worker 一致)
    win = slice_window(load_bars(cfg, symbol), buf_start, buf_end)
    res = mod.analyze(win, params)
    scan_meta = {
        "start_date": start, "end_date": end,
        "win_start": buf_start, "win_end": buf_end,
        "label_horizon": label_horizon, "end_node": end_node,
    }
    return res, win, scan_meta


# ───────────────────────── 取买点日 ─────────────────────────
@dataclass(frozen=True)
class AppBuys:
    """一只股票上 app 的买点(全部是 YYYY-MM-DD 字符串,能 JSON 往返)。

    - families:族起点日期(hit 的起点)→ 这一族全部 hit 的买点日(升序去重);一族的 hit 都没有买点日时为空元组;
    - event_starts:参与求解的 node 的全部事件(不论档位)的起点日期(升序去重),判 family 反馈的 lost 用;
    - dates:窗口内全部交易日(升序),按 K 线根数算距离用。
    """
    families: Mapping[str, tuple]
    event_starts: tuple
    dates: tuple

    @property
    def buy_days(self) -> tuple:
        """全部买点日(各族买点日的并集,升序)。"""
        return tuple(sorted({d for days in self.families.values() for d in days}))

    def to_dict(self) -> dict:
        return {"families": {k: list(v) for k, v in self.families.items()},
                "event_starts": list(self.event_starts), "dates": list(self.dates)}

    @classmethod
    def from_dict(cls, d: Mapping) -> "AppBuys":
        return cls(families={str(k): tuple(v) for k, v in d["families"].items()},
                   event_starts=tuple(d["event_starts"]), dates=tuple(d["dates"]))


def solving_nodes(spec) -> frozenset:
    """参与求解的 node:会出现在 hit 的 node_index 里的那些(引擎编译求解计划时定的求解集)。

    另把与它们共用同一条事件流的 node 一并算上:几个 node 共用一个 detector 的同一条输出流时,流里事件的
    node_id 记的是声明在前的那个,那条流仍是参与求解的 node 的候选。"""
    plan = compile_plan(spec)
    bound = {nid for w in plan.wcc_plans for nid in w.comp}

    def stream_key(n):
        return id(n.detector), n.consumes_stream, n.produces_stream

    keys = {stream_key(n) for n in spec.nodes if n.node_id in bound}
    return frozenset(n.node_id for n in spec.nodes
                     if n.node_id in bound or (n.detector is not None and stream_key(n) in keys))


def app_buys(res, win: pd.DataFrame, end_node: str, spec=None) -> AppBuys:
    """从 run_app 的结果取买点。

    参数:res、win 来自 run_app;end_node 是 eval_meta 声明的买点 node('node' 或 'node.slot');spec 是这次
    跑的 pattern 声明,省略时用 res.spec。

    - 买点日:每个 hit 经 path2.eval 的 _resolve_end_events(与评估、序列化同一个函数)取到买点事件,事件跨度里
      的每一根都是买点日——与前端 render/fold.ts 的 buyDaysOf 同口径(不是序列化里的 buy_date 那一天);
      hit 里解析不到买点 node 时照 _resolve_end_events 抛错(app 声明漂移要响亮);
    - 族:按 hit 的起点分组,值是组内全部 hit 买点日的并集;
    - 事件起点:参与求解的 node(solving_nodes)的全部事件,不论档位;
    - 交易日:win 的全部日期。

    它不按区间筛 hit:缓冲窗里跑出的 hit 全都算。与 compare 图上的买点一致的前提是用全历史区间跑 app
    (run_app 的 start 给 "1900-01-01"、end 给 TRAIN_END、label_horizon 20,同前端 stores/appLink.ts 调单股
    预览的参数)——反馈状态接口(path2_web/api.py 的 /feedback/status)、会话的改版报告都必须这么调。
    """
    if spec is None:
        spec = res.spec
    day = pd.to_datetime(win["date"]).dt.strftime("%Y-%m-%d").tolist() if len(win) else []
    families: dict = {}
    for h in res.hits:
        days = families.setdefault(day[h.start_idx], set())
        for ev in _resolve_end_events(h, end_node):
            days.update(day[ev.start_idx:ev.end_idx + 1])
    nodes = solving_nodes(spec)
    starts = {day[e.start_idx] for e in res.events if e.node_id in nodes}
    return AppBuys(families={k: tuple(sorted(families[k])) for k in sorted(families)},
                   event_starts=tuple(sorted(starts)), dates=tuple(day))
