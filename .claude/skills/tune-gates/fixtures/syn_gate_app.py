# -*- coding: utf-8 -*-
"""合成 app(参数准入 / 定范围 / 定案写入的测试夹具):两个 detector node + 两道 where。

参数覆盖准入表的每一类(正式值见测试里写的 params.yaml;代码默认值见 DEFAULTS):
  a.width     检测参数;99 在参数校验时报错、7 在搭建 pattern 时报错;≥5 的档被截到 5(等价档)
  a.min_n     过滤型(detector 声明 filter_params)
  a.lookback  检测参数;它就是首部缓冲需求
  a.mode      检测参数;取 2 时买点换到 node a 上(尺子)
  b.span      检测参数
  b.gate      where 阈值(>=)
  b.fresh     where 阈值(>=)
make_app 造出的模块 __file__ 指向调用方给的目录(params.yaml 放那里),detector 类定义在本文件,
所以源码指纹能照常算。
"""
from __future__ import annotations

import copy
import sys
import types
from pathlib import Path

import yaml

from path2.dag import where as W

DEFAULTS = {"a": {"width": 4, "min_n": 1, "lookback": 20, "mode": 1},
            "b": {"span": 10, "gate": 3, "fresh": 0.0}}


class DetA:
    filter_params = {"min_n": ("n", ">=")}

    def __init__(self, width, min_n, lookback):
        self.width, self.min_n, self.lookback = width, min_n, lookback


class DetB:
    def __init__(self, span, mode):
        self.span, self.mode = span, mode


class Params:
    def __init__(self, d):
        self.d = d

    @classmethod
    def default(cls):
        return cls(copy.deepcopy(DEFAULTS))

    @classmethod
    def from_dict(cls, d, strict=False):
        out = copy.deepcopy(DEFAULTS)
        for sec, kv in (d or {}).items():
            if sec not in out:
                raise ValueError(f"未知 section {sec}")
            for k, v in (kv or {}).items():
                if k not in out[sec]:
                    raise ValueError(f"未知字段 {sec}.{k}")
                out[sec][k] = v
        if out["a"]["width"] == 99:
            raise ValueError("width 不能取 99")
        return cls(out)

    @classmethod
    def from_yaml(cls, path):
        return cls.from_dict(yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}, strict=True)

    def to_dict(self):
        return copy.deepcopy(self.d)


def build_pattern(p):
    a, b = p.d["a"], p.d["b"]
    if a["width"] == 7:
        raise AssertionError("width=7 违反构造不变式")
    na = types.SimpleNamespace(node_id="a", detector=DetA(min(a["width"], 5), a["min_n"], a["lookback"]),
                               where=(), consumes_stream=None)
    nb = types.SimpleNamespace(node_id="b", detector=DetB(b["span"], a["mode"]),
                               where=(("gate", W.attr("gv", ">=", b["gate"])), ("fresh", W.attr("fv", ">=", b["fresh"]))),
                               consumes_stream="a")
    return types.SimpleNamespace(nodes=[na, nb], edges=())


def eval_meta(params=None):
    p = params or Params.default()
    return {"end_node": "a" if p.d["a"]["mode"] == 2 else "b", "head_buffer_trading_days": p.d["a"]["lookback"]}


FORMAL_YAML = """\
a:
  width: 4        # 历史上试过 6,99 和 7 搭不出来
  min_n: 1
  lookback: 20    # 曾用 40
  mode: 1
b:
  span: 10        # 2026-09-01 定案(原 8):试过 20/30 三档,+1.5 点,买点只掉 8%
  gate: 5         # 关掉时取 0
  fresh: 0.0      # 想加的新闸,阈值 1.5 左右
"""


def make_app(app_dir: Path, name: str, yaml_text: str = FORMAL_YAML):
    """在 app_dir 写 params.yaml,造一个可 import 的合成 app 模块(注册进 sys.modules)。"""
    app_dir = Path(app_dir)
    app_dir.mkdir(parents=True, exist_ok=True)
    (app_dir / "params.yaml").write_text(yaml_text, encoding="utf-8")
    mod = types.ModuleType(name)
    mod.__file__ = str(app_dir / "dag_spec.py")
    mod.Params, mod.build_pattern, mod.eval_meta = Params, build_pattern, eval_meta
    sys.modules[name] = mod
    return mod
