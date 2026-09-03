"""skeptic:T1 边界反例 —— 假设写成 `exceed_threshold <= peak_supersede_threshold` 时定理不成立。

失效机理(与浮点无关的代数根源):两处判据用的是**代数等价但数值不等价**的两种写法——
  peak-peak supersede(登记分支):  (M - p) / p        >= ss     → 吃掉
  breakout(突破分支):             M                  >  p*(1+ex) → 突破
当 ex == ss 时,存在 M 使得 (M-p)/p >= ss 成立、而 M > p*(1+ex) 不成立
(p=100.0, M=101.0, ss=ex=0.01:左边 0.01>=0.01 真;右边 101.0 > 101.00000000000001 假)。
⇒ 旧峰"没被突破"却"被吃掉" ⇒ eaten 非空,T1(带 <=)被证伪。
修法:假设收紧为严格 `exceed_threshold < peak_supersede_threshold`。

本脚本用最小合成序列跑真实 BODetector,不改任何生产代码。
"""
import sys
sys.path.insert(0, "/home/yu/PycharmProjects/Trade_Strategy-tune_v1")
import numpy as np
import pandas as pd
from path2.atoms.breakout import BODetector

TW, MSB = 20, 6

class Probe(BODetector):
    """记录登记与两类死亡。"""
    def __init__(self, **kw):
        super().__init__(**kw)
        self.registered, self.eaten, self.bo_removed = [], [], []

    def _detect_peak_in_window(self, df, i):
        before = {id(p): p for p in self._active_peaks}
        n0 = self._peak_id_counter
        super()._detect_peak_in_window(df, i)
        alive = {id(p) for p in self._active_peaks}
        for oid, p in before.items():
            if oid not in alive:
                self.eaten.append((p.index, p.pk_id, round(p.price, 10), i))
        if self._peak_id_counter > n0:
            p = self._active_peaks[-1]
            self.registered.append((p.index, p.pk_id, round(p.price, 10), i))

    def emit(self, df, i):
        snap = {id(p): p for p in self._active_peaks}
        ev = super().emit(df, i)
        alive = {id(p) for p in self._active_peaks}
        for oid, p in snap.items():
            if oid not in alive:
                self.bo_removed.append((p.index, p.pk_id, i))
        return ev


def build() -> pd.DataFrame:
    """60 根:bar10 高点 100.0(登记为 Q) · bar40 高点 101.0(登记为 P 并吃掉 Q)。
    平台段 high=60 / low=58 ⇒ 相对高度 0.034 < 0.05,平台自身不会登记成峰。"""
    n = 60
    high = np.full(n, 60.0); low = np.full(n, 58.0)
    high[10] = 100.0
    high[40] = 101.0
    close = high - 0.5
    open_ = low + 0.5
    return pd.DataFrame({
        "date": pd.date_range("2024-01-01", periods=n, freq="B"),
        "open": open_, "high": high, "low": low, "close": close,
        "volume": np.full(n, 1e6),
    })


def run(ex, ss):
    d = Probe(total_window=TW, min_side_bars=MSB, min_relative_height=0.05,
              exceed_threshold=ex, peak_supersede_threshold=ss,
              vol_baseline_period=5, peak_measure="high", breakout_measure="high")
    bos = list(d.detect(build()))
    return d, bos


def main():
    print("前提检查 · T1 的两个假设在本配置下都满足:")
    print("  breakout_measure(high) >= peak_measure(high) 逐 bar:成立(同一列)")
    print()
    print("浮点根源:")
    print(f"  (101.0 - 100.0) / 100.0      = {(101.0 - 100.0) / 100.0!r}")
    print(f"  100.0 * (1 + 0.01)           = {100.0 * (1 + 0.01)!r}")
    print(f"  吃掉判据 (M-p)/p >= ss       -> {((101.0 - 100.0) / 100.0) >= 0.01}")
    print(f"  突破判据 M > p*(1+ex)        -> {101.0 > 100.0 * (1 + 0.01)}")
    print()
    for ex, ss, tag in [(0.01, 0.01, "ex == ss  (T1 假设写成 <= 时被涵盖)"),
                        (0.003, 0.01, "ex <  ss  (bb_v1 / bo_only 的真实配置)")]:
        d, bos = run(ex, ss)
        print(f"[{tag}]  ex={ex} ss={ss}")
        print(f"    登记 peak     : {d.registered}")
        print(f"    eaten(被吃)   : {d.eaten}")
        print(f"    bo 移除       : {d.bo_removed}")
        print(f"    bo 事件 bar   : {[e.start_idx for e in bos]}")
        verdict = "★ T1(带 <=) 被证伪:eaten 非空" if d.eaten else "T1 成立:eaten 为空"
        print(f"    => {verdict}\n")


main()
