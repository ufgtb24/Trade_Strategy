"""configs/path2_web.yaml 读写。缺文件/缺项回落默认(浅层 + scan 子树 merge)。

标注目录与机器名在配置里存原样(相对路径、null),用的时候经 annotation_dir() / machine_name() 解析:
配置文件进 git,网页改配置时会整份写回,存解析后的值会把本机的绝对路径、主机名带进 git。
"""
from __future__ import annotations

import re
import socket
from pathlib import Path

import yaml

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
}

_REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PATH = _REPO_ROOT / "configs" / "path2_web.yaml"

_MACHINE_RE = re.compile(r"[A-Za-z0-9_]+")


def _merge(default: dict, override: dict) -> dict:
    """两层 merge:顶层键 + scan 子树。override 缺项补 default。"""
    out = {**default, **{k: v for k, v in override.items() if k != "scan"}}
    out["scan"] = {**default["scan"], **(override.get("scan") or {})}
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


def annotation_dir(cfg: dict) -> Path:
    """标注目录:配置的 annotation_dir,相对路径按 repo root 解析。"""
    d = Path(cfg["annotation_dir"])
    return d if d.is_absolute() else _REPO_ROOT / d


def machine_name(cfg: dict) -> str:
    """机器名:配置的 machine,没配(null)取本机主机名。
    只许字母、数字和下划线:spec 的标注文件名与对象编号用 - 分隔各段,机器名里带 - 或 / 会拆错、写错位置。
    不合格 → ValueError。"""
    name = cfg.get("machine") or socket.gethostname()
    if not isinstance(name, str) or not _MACHINE_RE.fullmatch(name):
        raise ValueError(f"机器名不合格: {name!r}(在配置的 machine 里另起一个)")
    return name
