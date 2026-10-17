"""唯一的读数据口:chart_workflow 里所有读行情的地方(大涨段、对照、面板、跨源比对、事实脚本)
以及网页看图工作流的 K 线都经这里读,只读截断副本。

截断副本由 `python -m chart_workflow.snapshot` 生成(默认 datasets/pkls_until_20251231/),
目录里带清单文件 SNAPSHOT.json。这里读任何 pkl 之前先 check_snapshot:目录不是截断副本、
或副本的截断终点晚于 HARD_END,一律拒绝(NotASnapshot)。读出来的行情再截一次到
min(训练段末日, until, HARD_END),最后再核对一遍最后一天不晚于 HARD_END(显式抛 PastHardEnd,
不用 assert——python -O 会去掉 assert)。副本清单可以伪造、配置可以写错,真正挡得住的是这道硬上限。
代码名先过格式校验(check_symbol:字母数字开头,只含字母数字 . -,不含 ..),防止 ../ 之类的名字
读到副本目录以外的文件。

红线:HARD_END(2025-12-31)之后是验证段,任何研究、看图、工具都不得读到。它是代码常量,
不受配置覆盖;config.load_config 也会拒绝晚于它的 train_end。
本模块不 import 标签口径(labels)和清单(listfile),事实脚本可以放心经它读数据。
"""
from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

import pandas as pd

from chart_workflow.config import dataset_dir

HARD_END = "2025-12-31"
SNAPSHOT_FILE = "SNAPSHOT.json"
SNAPSHOT_SCHEMA = "chart_workflow.snapshot/1"

_MANIFESTS: dict[tuple[str, int], dict] = {}


# 代码名:字母数字开头,只含字母数字 . -,最长 15 个字符;另外不许出现 ..(见 check_symbol)
SYMBOL_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9.\-]{0,14}$")


class NotASnapshot(RuntimeError):
    """数据目录不是截断副本(缺 SNAPSHOT.json,或截断终点晚于 HARD_END)。"""


class PastHardEnd(RuntimeError):
    """读出来的行情晚于 HARD_END(读到了验证段)。截断失效时的最后一道闸。"""


def check_symbol(symbol) -> str:
    """代码名格式校验:不合格(含路径分隔符、..、空白等)→ ValueError。返回原样的代码名。"""
    if not isinstance(symbol, str) or not SYMBOL_RE.fullmatch(symbol) or ".." in symbol:
        raise ValueError(f"非法代码: {symbol!r}")
    return symbol


def check_snapshot(ddir) -> dict:
    """读 ddir/SNAPSHOT.json 并缓存(按文件修改时间);不合格 → NotASnapshot。"""
    ddir = Path(ddir)
    f = ddir / SNAPSHOT_FILE
    try:
        mtime = f.stat().st_mtime_ns
    except OSError:
        raise NotASnapshot(f"数据目录 {ddir} 不是截断副本(缺 {SNAPSHOT_FILE})。"
                           f"先运行 python -m chart_workflow.snapshot") from None
    key = (str(f.resolve()), mtime)
    if key in _MANIFESTS:
        return _MANIFESTS[key]
    try:
        man = json.loads(f.read_text())
    except (OSError, ValueError) as e:
        raise NotASnapshot(f"数据目录 {ddir} 的 {SNAPSHOT_FILE} 读不了({e})") from None
    cutoff = man.get("cutoff") if isinstance(man, dict) else None
    if not isinstance(cutoff, str) or man.get("schema") != SNAPSHOT_SCHEMA:
        raise NotASnapshot(f"数据目录 {ddir} 的 {SNAPSHOT_FILE} 格式不对")
    if cutoff > HARD_END:
        raise NotASnapshot(f"数据目录 {ddir} 的截断终点 {cutoff} 晚于 {HARD_END},不能用")
    _MANIFESTS[key] = man
    return man


def load_bars(ddir, symbol: str, end: str) -> pd.DataFrame:
    """读 ddir/<symbol>.pkl:先校验代码名、check_snapshot;去 tz、按日期排序;截到 min(end, HARD_END)(含)。
    代码名不合格 → ValueError;文件不存在 → FileNotFoundError;截完仍晚于 HARD_END → PastHardEnd。"""
    check_symbol(symbol)
    ddir = Path(ddir)
    check_snapshot(ddir)
    df = pd.read_pickle(ddir / f"{symbol}.pkl")
    if getattr(df.index, "tz", None) is not None:
        df = df.copy()
        df.index = df.index.tz_localize(None)
    df = df.sort_index()
    df = df[df.index <= pd.Timestamp(min(str(end), HARD_END))]
    if len(df) and df.index[-1] > pd.Timestamp(HARD_END):
        raise PastHardEnd(f"{symbol} 读到了验证段({df.index[-1].date()} 晚于 {HARD_END})")
    return df


def read_bars(cfg: dict, symbol: str, until: str | None = None) -> pd.DataFrame:
    """读 dataset_dir(cfg)/<symbol>.pkl,截到 min(cfg["train_end"], until, HARD_END)(含)。"""
    ends = [str(cfg["train_end"]), HARD_END] + ([str(until)] if until else [])
    return load_bars(dataset_dir(cfg), symbol, min(ends))


@lru_cache(maxsize=4096)
def _dates_cached(ddir: str, train_end: str, symbol: str) -> pd.DatetimeIndex:
    return load_bars(ddir, symbol, train_end).index


def trading_dates(cfg: dict, symbol: str) -> pd.DatetimeIndex:
    """一只股票截到训练段末日的交易日序列(图窗按交易日偏移时用)。"""
    return _dates_cached(str(dataset_dir(cfg)), str(cfg["train_end"]), symbol)
