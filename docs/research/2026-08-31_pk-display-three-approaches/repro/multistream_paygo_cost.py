"""方案③「按需付费」代价实测：多产一条 pk 流相对基线 BODetector 的边际耗时。

问题：pattern 只声明 bo 一条流时，多流 detector 仍会构造 PeakEvent 并入 list。
      这笔开销到底多大？（设计文档估计「≈ 只是构造对象，可忽略」，此处量它。）

做法：同一批真实股票上跑两遍
  A 基线    = 原生 BODetector.detect
  B 多流模拟 = 子类，在每次成功登记 peak 后额外构造一个 frozen PkEvent 并 append
             （= 多流方案里 peak 流的全部额外工作：对象构造 + Event.__post_init__ 校验 + list.append）
差值即「多一条流」的边际成本。基线对照：背景 §四 实证「峰检测跑两遍 = 1.80×」。

数据：主 checkout /home/yu/PycharmProjects/Trade_Strategy/datasets/pkls（本 worktree 为空）
参数：bb_v1 params.yaml（peak=high / breakout=close），经 Params.from_yaml 加载，不用 Params.default()
"""
from __future__ import annotations

import random
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from path2 import Event                                        # noqa: E402
from path2.atoms.breakout import BODetector                    # noqa: E402
from path2.runner import run                                   # noqa: E402
from path2_apps.bb_v1.params import Params, DEFAULT_YAML_PATH  # noqa: E402

PKL_DIR = Path("/home/yu/PycharmProjects/Trade_Strategy/datasets/pkls")
N_STOCKS = 20
SEED = 20260831
REPEAT = 3


@dataclass(frozen=True)
class PkEvent(Event):
    """多流方案里 peak 流的事件形态（点事件，发在登记那根 bar，真实峰坐标走卫星）。"""
    is_point = True
    pk_id: int = -1
    peak_bar: int = -1
    peak_price: float = 0.0
    relative_height: float = 0.0
    referenced_points: Tuple[Tuple[int, float, str], ...] = ()


class MultiStreamBO(BODetector):
    """模拟多流：登记 peak 时额外构造 PkEvent。不改任何判据，bo 流逐字不变。"""

    def detect(self, df: pd.DataFrame):
        self._pk_stream = []
        yield from super().detect(df)

    def _detect_peak_in_window(self, df, current_idx: int):
        before = self._peak_id_counter
        super()._detect_peak_in_window(df, current_idx)
        if self._peak_id_counter == before:
            return
        new_id = self._peak_id_counter - 1
        for p in self._active_peaks:
            if p.pk_id == new_id:
                self._pk_stream.append(PkEvent(
                    start_idx=current_idx, end_idx=current_idx, confirm_idx=current_idx,
                    pk_id=p.pk_id, peak_bar=p.index, peak_price=float(p.price),
                    relative_height=float(p.relative_height),
                    referenced_points=((p.index, float(p.price), f"pk{p.pk_id}"),),
                ))
                break


def bo_kwargs(p: Params) -> dict:
    return p.bo_kwargs()


def main() -> None:
    if not PKL_DIR.is_dir():
        print(f"数据目录不存在: {PKL_DIR}")
        return
    files = sorted(PKL_DIR.glob("*.pkl"))
    random.Random(SEED).shuffle(files)
    files = files[:N_STOCKS]

    p = Params.from_yaml(DEFAULT_YAML_PATH)
    kw = bo_kwargs(p)
    print(f"BODetector 参数: peak={kw['peak_measure']} breakout={kw['breakout_measure']} "
          f"exc={kw['exceed_threshold']} sup={kw['peak_supersede_threshold']}")

    dfs = []
    for f in files:
        try:
            df = pd.read_pickle(f)
        except Exception:
            continue
        if len(df) < 300:
            continue
        dfs.append((f.stem, df.reset_index(drop=False)))
    print(f"股票数 {len(dfs)}，总 bar 数 {sum(len(d) for _, d in dfs)}")

    t_base = t_multi = float("inf")
    n_bo = n_pk = 0
    for _ in range(REPEAT):
        t0 = time.perf_counter()
        c = 0
        for _, df in dfs:
            c += len(list(run(BODetector(**kw), df)))
        t_base = min(t_base, time.perf_counter() - t0)
        n_bo = c

        t0 = time.perf_counter()
        c, k = 0, 0
        for _, df in dfs:
            det = MultiStreamBO(**kw)
            c += len(list(run(det, df)))
            k += len(det._pk_stream)
        t_multi = min(t_multi, time.perf_counter() - t0)
        n_pk = k

    print(f"\nbo 事件 {n_bo} 个 / pk 事件 {n_pk} 个")
    print(f"A 基线(单流)      : {t_base * 1000:8.1f} ms")
    print(f"B 多流(含 pk 物化): {t_multi * 1000:8.1f} ms")
    print(f"边际倍率          : {t_multi / t_base:.4f}×  (对照：峰检测跑两遍 = 1.80×)")
    print(f"每个 pk 事件均摊  : {(t_multi - t_base) / max(n_pk, 1) * 1e6:.2f} µs")


if __name__ == "__main__":
    main()
