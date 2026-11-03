"""configs/path2_web.yaml 读写。缺文件/缺项回落默认(按 DEFAULT_CONFIG 的结构逐层 merge)。

训练段设置全仓只有一处:train_segment,经 train_segment() 读。找图(股票池、大涨段清单、random、
数据错误登记)的参数在 finder 子树,经 finder_settings() 读。两者都按缺项补默认,测试只给部分配置也能用。

标注目录与机器名在配置里存原样(相对路径、null),用的时候经 annotation_dir() / machine_name() 解析:
配置文件进 git,网页改配置时会整份写回,存解析后的值会把本机的绝对路径、主机名带进 git。
"""
from __future__ import annotations

import re
import socket
from pathlib import Path

import yaml

from path2_web.data import TRAIN_END

DEFAULT_CONFIG = {
    "backend_port": 8000,
    "backend_port_dbg": 8002,
    "frontend_port": 5173,
    # 网页数据墙的数据来源:K 线、诊断、单股预览、扫描只读这个目录,必须指向截到训练段末日的那份副本
    # (相对 repo root;scripts/data/make_train_snapshot.py 生成)。读的时候另有代码常量把行截到
    # 2025-12-31(data.read_bars),这里配错也读不出 2026 年的行情。
    "view_dataset_dir": "datasets/pkls_until_20251231",
    # 完整行情目录:网页不读它;旧版调参流程(.claude/skills/tune-gates)把它当数据来源
    "dataset_dir": "datasets/pkls",
    "scan": {
        "start_date": "2025-01-01",
        "end_date": "2025-12-31",
        "workers": 8,
        "ticker_regex": None,
        "label_horizon": 20,
        "price_min": None,      # 扫描过滤:end_node 事件日收盘价下限(null=不限)
        "price_max": None,      # 扫描过滤:end_node 事件日收盘价上限(null=不限)
        "volume_min": None,     # 扫描过滤:扫描区间内日均成交量下限(null=不限)
        "first_passage_k": 5.0,    # 首次穿越几何对称阈值倍数(上行 P(1+kM)、下行 P/(1+kM))
        "first_passage_enabled": True,   # 首次穿越方向注入开关
    },
    "last_selected_pattern": "bottom_burst",
    # 标注目录:用户的标注文件放这里(相对 repo root)。git 忽略,两台机器用 Syncthing 同步;
    # worktree 里经 .worktree-prep 软链到主目录的同一目录
    "annotation_dir": "annotations",
    # 机器名:区分 pc 与 upc 各自写下的标注,两台机器各用各的。null = 取本机主机名。
    # 别在这份进 git 的配置里写死某台机器的名字,否则另一台拉取后会冒用它
    "machine": None,
    # 训练段设置(全仓唯一一处):找图、大涨段清单、random 等都读它,不各自写死年份。
    # 终点不得晚于训练段末日 data.TRAIN_END(数据墙,代码常量)
    "train_segment": {"start": "2021-10-08", "end": "2025-12-31"},
    # 找图参数(只决定给用户看哪些图,不进任何成绩;数值都待验证)
    "finder": {
        "random_window_bars": 250,      # random 给的一段图有几根 K 线
        # 证券名称表(代码 → 名称,用来认出普通股;scripts/data/fetch_security_names.py 生成,相对 repo root)
        "security_names_file": "configs/security_names.csv",
        # 数据错误登记(相对 repo root;文件不存在当空登记,格式见 path2_web/stock_pool.py)
        "data_errors_file": "configs/data_errors.yaml",
        "pool": {
            "price_max": 20.0,          # 当日收盘价上限(复权价)
            "dv_min": 2_000_000.0,      # 近 dv_window 日成交额中位数下限(含)
            "dv_max": 100_000_000.0,    # 同上,上限(含)
            "dv_window": 20,
            "m_period": 20,             # 波动尺度 M(TR/收盘的滚动中位数)的回看根数
            "m_min": 0.01,              # 当日 M 下限(含),剔除平时几乎不动的股票
            "common_classes": ["common", "adr", "mlp"],     # 算普通股的证券类别
            # SPAC 壳期:往前 window 根收盘中位数在 [price_lo, price_hi]、日振幅中位数 < range_max 的日子;
            # 当日往前 lookback_bars 根(含当日)里有过壳期就不进池
            "spac_shell": {"lookback_bars": 120, "window": 40, "price_lo": 9.5, "price_hi": 12.0,
                           "range_max": 0.006},
            # 数据错误登记的排除窗:当日往前 before_bars 根到往后 after_bars 根,和登记范围有重叠就排除
            "data_error_before_bars": 20,
            "data_error_after_bars": 40,
        },
        "rally": {
            "k": 5.0,                   # 止损距离 = 买入价 ÷ (1 + k·M)
            "horizon": 40,              # 观察期:买入后最多看多少根(截到训练段终点)
            "rel_min": 2.0,             # 相对涨幅门槛:至少涨到几倍止损距离
            "suppress_bars": 20,        # 同一只股票取中一段后,前后这么多根内不再取(同一段行情只取一次)
            "per_week_max": 5,          # 同一 ISO 周最多几段
            "top": 300,                 # 清单总量上限
            "before_bars": 120,         # 图窗从涨前那天往前多少根
        },
    },
}

_REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PATH = _REPO_ROOT / "configs" / "path2_web.yaml"

# 机器名的写法:只许字母、数字和下划线。标注存储的文件名、对象编号也按它拆出机器名
MACHINE_PATTERN = r"[A-Za-z0-9_]+"
_MACHINE_RE = re.compile(MACHINE_PATTERN)


def _merge(default: dict, override: dict) -> dict:
    """按 default 的结构逐层 merge:default 里是 dict 的键,override 也给了 dict 就递归补缺项;
    其余键 override 有就用 override 的。override 缺项补 default。"""
    out = dict(default)
    for k, v in (override or {}).items():
        if isinstance(default.get(k), dict) and isinstance(v, dict):
            out[k] = _merge(default[k], v)
        else:
            out[k] = v
    return out


def load_config(path=DEFAULT_PATH) -> dict:
    path = Path(path)
    if not path.exists():
        return _merge(DEFAULT_CONFIG, {})
    data = yaml.safe_load(path.read_text()) or {}
    return _merge(DEFAULT_CONFIG, data)


def save_config(cfg: dict, path=DEFAULT_PATH) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(cfg, allow_unicode=True, sort_keys=False))


def repo_path(raw) -> Path:
    """配置里的路径:相对路径按 repo root 解析,绝对路径原样。"""
    d = Path(raw)
    return d if d.is_absolute() else _REPO_ROOT / d


def view_dataset_dir(cfg: dict) -> Path:
    """网页读行情的训练段副本目录:配置的 view_dataset_dir。缺这一项 → KeyError。"""
    return repo_path(cfg["view_dataset_dir"])


def annotation_dir(cfg: dict) -> Path:
    """标注目录:配置的 annotation_dir。"""
    return repo_path(cfg["annotation_dir"])


def machine_name(cfg: dict) -> str:
    """机器名:配置的 machine,没配(null)取本机主机名。
    只许字母、数字和下划线:spec 的标注文件名与对象编号用 - 分隔各段,机器名里带 - 或 / 会拆错、写错位置。
    不合格 → ValueError。"""
    name = cfg.get("machine") or socket.gethostname()
    if not isinstance(name, str) or not _MACHINE_RE.fullmatch(name):
        raise ValueError(f"机器名不合格: {name!r}(在配置的 machine 里另起一个)")
    return name


_DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")


def train_segment(cfg: dict) -> tuple[str, str]:
    """训练段设置 (起点, 终点),YYYY-MM-DD。配置缺项补默认。
    日期格式不对、起点晚于终点、终点晚于训练段末日 TRAIN_END → ValueError。"""
    seg = _merge(DEFAULT_CONFIG["train_segment"], cfg.get("train_segment") or {})
    start, end = str(seg["start"]), str(seg["end"])
    if not (_DATE_RE.fullmatch(start) and _DATE_RE.fullmatch(end)):
        raise ValueError(f"训练段日期要写成 YYYY-MM-DD: {start!r}, {end!r}")
    if start > end:
        raise ValueError(f"训练段起点 {start} 晚于终点 {end}")
    if end > TRAIN_END:
        raise ValueError(f"训练段终点 {end} 晚于训练段末日 {TRAIN_END}")
    return start, end


def finder_settings(cfg: dict) -> dict:
    """找图参数(finder 子树),配置缺项补默认。"""
    return _merge(DEFAULT_CONFIG["finder"], cfg.get("finder") or {})
