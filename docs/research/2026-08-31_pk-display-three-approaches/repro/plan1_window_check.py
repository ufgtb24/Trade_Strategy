"""决定性对拍:三态标签(现状真值 vs 方案①-a vs 纯峰域),用 app 生产 yaml 参数。

现状真值直接从 BODetector 内部取:
  eaten_true  = 在 _detect_peak_in_window 的 peak-peak supersede 里被移除的 pk_id
  broken_true = 进过 broken_peaks 的 pk_id
方案①-a = PeakRegistrar(纯几何) + BOConsumer(bo 域重算 supersede,锚 elevated 价)
纯峰域   = PeakRegistrar 自己的 supersede 裁决(skeptic 用的那个口径)

三态判定采用**优先级 broken > eaten > alive**(用户对 eaten 的定义原文就是
「被其他 pk 吃掉、**未被突破**的 pk」,所以既被突破又被吃的必须归 broken)。
"""
from __future__ import annotations

import pickle
import random
import sys
from pathlib import Path

import pandas as pd
import yaml

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parents[3]))

from plan1_prototype import PeakRegistrar, BOConsumer          # noqa: E402
from path2.atoms.breakout import BODetector                     # noqa: E402
from path2_web.data import slice_window                         # noqa: E402

REPO = HERE.parents[3]
PKL = Path("/home/yu/PycharmProjects/Trade_Strategy/datasets/pkls")
START, END = "2024-09-19", "2026-03-08"
SEED = 20260831


def load_bo_params(app: str) -> dict:
    with open(REPO / "path2_apps" / app / "params.yaml") as fh:
        return dict(yaml.safe_load(fh)["bo"])


class TruthBO(BODetector):
    """现状实现的真值记录仪:登记 / peak-peak supersede 移除 / 被突破。"""

    def detect(self, df):
        self.registered = []
        self.eaten_true = set()
        self.broken_true = set()
        yield from super().detect(df)

    def emit(self, df, i):
        ev = super().emit(df, i)
        if ev is not None:
            self.broken_true.update(ev.broken_peak_ids)
        return ev

    def _detect_peak_in_window(self, df, current_idx):
        before_ids = {p.pk_id for p in self._active_peaks}
        before_n = self._peak_id_counter
        super()._detect_peak_in_window(df, current_idx)
        if self._peak_id_counter > before_n:
            p = self._active_peaks[-1]
            self.registered.append((p.index, current_idx, p.pk_id))
            gone = before_ids - {q.pk_id for q in self._active_peaks}
            self.eaten_true |= gone          # 只有 supersede 会在本函数里移除


def label(ids, broken, eaten):
    """优先级 broken > eaten > alive。"""
    out = {}
    for i in ids:
        out[i] = "broken" if i in broken else ("eaten" if i in eaten else "alive")
    return out


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 80
    apps = sys.argv[2:] or ["bb_v1", "bo_only"]
    files = sorted(PKL.glob("*.pkl"))
    random.Random(SEED).shuffle(files)
    wins = []
    for f in files:
        if len(wins) >= n:
            break
        try:
            with open(f, "rb") as fh:
                raw = pickle.load(fh)
            if not isinstance(raw, pd.DataFrame):
                continue
            w = slice_window(raw, START, END)
        except Exception:
            continue
        if len(w) >= 300:
            wins.append((f.stem, w))

    for app in apps:
        kw = load_bo_params(app)
        agg = dict(pk=0, cur_b=0, cur_e=0, cur_a=0, a_b=0, a_e=0, a_a=0,
                   pure_e_raw=0, pure_b=0, pure_e=0, pure_a=0,
                   mismatch_a=0, mismatch_pure=0, eaten_raw_cur=0, cm_a={}, cm_p={})
        for sym, w in wins:
            ref = TruthBO(**kw)
            list(ref.detect(w))
            peaks = PeakRegistrar(**kw).detect(w)
            reg = PeakRegistrar(**kw)
            peaks = reg.detect(w)
            con = BOConsumer(replicate_supersede=True, **kw)
            con.detect(peaks, w)
            con_broken = {pid for b in con.bos for pid in b[3]}

            ids = {p.pk_id for p in peaks}
            assert [(r[0], r[1]) for r in ref.registered] == [(p.index, p.reg_idx) for p in peaks], sym

            L_cur = label(ids, ref.broken_true, ref.eaten_true)          # 现状真值
            L_a = label(ids, con_broken, con.superseded_in_bo)           # 方案①-a
            L_pure = label(ids, con_broken, set(reg.eaten_by))           # 纯峰域裁 eaten

            agg["pk"] += len(ids)
            agg["eaten_raw_cur"] += len(ref.eaten_true)
            agg["pure_e_raw"] += len(reg.eaten_by)
            for k, L in (("cur", L_cur), ("a", L_a), ("pure", L_pure)):
                for st, key in (("broken", "_b"), ("eaten", "_e"), ("alive", "_a")):
                    agg[k + key] += sum(1 for v in L.values() if v == st)
            agg.setdefault("raw_eq_a", 0)
            agg.setdefault("raw_sym_a", 0)
            agg["raw_eq_a"] += int(ref.eaten_true == con.superseded_in_bo)
            agg["raw_sym_a"] += len(ref.eaten_true ^ con.superseded_in_bo)
            agg.setdefault("raw_broken_eq", 0)
            agg["raw_broken_eq"] += int(ref.broken_true == con_broken)
            for i in ids:
                agg["cm_a"][(L_cur[i], L_a[i])] = agg["cm_a"].get((L_cur[i], L_a[i]), 0) + 1
                agg["cm_p"][(L_cur[i], L_pure[i])] = agg["cm_p"].get((L_cur[i], L_pure[i]), 0) + 1
            agg["mismatch_a"] += sum(1 for i in ids if L_cur[i] != L_a[i])
            agg["mismatch_pure"] += sum(1 for i in ids if L_cur[i] != L_pure[i])

        print(f"\n===== app={app}  参数={kw['peak_measure']}/{kw['breakout_measure']} "
              f"exc={kw['exceed_threshold']} sup={kw['peak_supersede_threshold']} =====")
        print(f"样本 {len(wins)} 股(随机 seed={SEED}),窗口 {START}~{END},pk 总数 {agg['pk']}")
        print(f"未施优先级的裸 eaten 集: 现状真值={agg['eaten_raw_cur']}  "
              f"纯峰域={agg['pure_e_raw']}  (倍数 "
              f"{agg['pure_e_raw']/max(1,agg['eaten_raw_cur']):.2f}×)")
        print("施 broken>eaten>alive 优先级后的三态:")
        for k, name in (("cur", "现状真值"), ("a", "方案①-a  "), ("pure", "纯峰域裁定")):
            print(f"  {name}: broken={agg[k+'_b']:6d} eaten={agg[k+'_e']:6d} alive={agg[k+'_a']:6d}")
        print(f"裸集合直比(不施优先级): ①a 的 supersede 移除集 == 现状 eaten_true 的股数 = "
              f"{agg['raw_eq_a']}/{len(wins)}, 对称差合计 = {agg['raw_sym_a']}; "
              f"broken 集全等股数 = {agg['raw_broken_eq']}/{len(wins)}")
        for key, nm in (("cm_a", "方案①-a"), ("cm_p", "纯峰域裁定")):
            print(f"  混淆矩阵 现状(行) × {nm}(列),单位=pk 个数:")
            print(f"    {'':8s}{'broken':>8s}{'eaten':>8s}{'alive':>8s}")
            for r in ("broken", "eaten", "alive"):
                row = "".join(f"{agg[key].get((r, c), 0):8d}" for c in ("broken", "eaten", "alive"))
                print(f"    {r:8s}{row}")
        print(f"  逐 pk 标签与现状不一致: 方案①-a = {agg['mismatch_a']}   "
              f"纯峰域 = {agg['mismatch_pure']}")


if __name__ == "__main__":
    main()
