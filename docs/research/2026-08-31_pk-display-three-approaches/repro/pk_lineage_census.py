"""方案②(递归 reference)覆盖边界实证。

只做 BODetector 子类 instrument,不改任何正式代码。

统计对象:一次 detect() 内**所有登记过的 peak**,按两个正交轴分类:
  轴 A(终局):breakout-supersede 移除 / peak-peak supersede 被吃 / 扫描结束仍 alive
  轴 B(是否曾被突破):ever_broken = pk_id 出现在任一 BOEvent.broken_peak_ids

派生:方案② 可显示 ⟺ 自身 ever_broken,或吞噬森林中某个祖先 ever_broken。
      (吞噬集在 eater 出生那一刻一次性固定,故"祖先曾被突破"无时序歧义,
       见 breakout.py:_detect_peak_in_window 末尾 supersede 块。)
"""
import sys, random, warnings, json
warnings.filterwarnings("ignore")
sys.path.insert(0, "/home/yu/PycharmProjects/Trade_Strategy-tune_v1")
from pathlib import Path
from collections import Counter
import pandas as pd

from path2.atoms.breakout import BODetector
from path2.runner import run
from path2_web.data import slice_window

PKL = Path("/home/yu/PycharmProjects/Trade_Strategy/datasets/pkls")
START, END = "2024-09-19", "2026-03-08"

# 参数一律从各 app 的 params.yaml 加载(SSoT)。
# 陷阱:Params.default() 是纯 dataclass 默认(high/high, tw=10),**不读 yaml**,
# 用它跑 bb_v1 会拿到错的 measure 组合 —— 必须走 load_params()/from_yaml。
from path2_apps.bb_v1.params import load_params as _bb_v1_load
from path2_apps.bo_only.params import load_params as _bo_only_load

BO_KW = _bb_v1_load().bo_kwargs()            # bb_v1 生产真值: peak=high, breakout=close
BO_KW_BO_ONLY = _bo_only_load().bo_kwargs()  # bo_only 生产真值: peak=high, breakout=high


class Lineage(BODetector):
    """记录 peak 全生命周期:登记 / 被吃(parent 边) / 被突破移除 / 存活。"""

    def detect(self, df):
        self.reg = {}          # pk_id -> dict(index, birth_price, birth_bar)
        self.parent = {}       # 被吃者 pk_id -> 吃它的 pk_id
        self.eaten_at = {}     # 被吃者 pk_id -> (bar, price_at_eat)
        self.removed_by_bo = set()
        self._snap_after_pd = None
        return super().detect(df)

    def _detect_peak_in_window(self, df, current_idx):
        before = {p.pk_id: p.price for p in self._active_peaks}
        super()._detect_peak_in_window(df, current_idx)
        after = {p.pk_id for p in self._active_peaks}
        new_ids = after - set(before)
        gone = set(before) - after
        if new_ids:
            nid = next(iter(new_ids))
            np_ = [p for p in self._active_peaks if p.pk_id == nid][0]
            self.reg[nid] = dict(index=np_.index, birth_price=np_.price, birth_bar=current_idx)
            for g in gone:                       # 只有 peak-peak supersede 会在此处移除
                self.parent[g] = nid
                self.eaten_at[g] = (current_idx, before[g])
        else:
            assert not gone, "peak 检测未登记新峰却移除了旧峰(不应发生)"
        self._snap_after_pd = {p.pk_id for p in self._active_peaks}

    def emit(self, df, i):
        ev = super().emit(df, i)
        after = {p.pk_id for p in self._active_peaks}
        self.removed_by_bo |= (self._snap_after_pd - after)
        return ev


def analyse(df, kw):
    det = Lineage(**kw)
    evs = list(run(det, df))

    broken = set()
    ref_sizes = []
    broken_per_bo = []
    for e in evs:
        broken.update(e.broken_peak_ids)
        ref_sizes.append(len(e.referenced_points))
        broken_per_bo.append(e.broken_peak_ids)

    alive = {p.pk_id for p in det._active_peaks}
    eaten = set(det.parent)
    reg = set(det.reg)

    # 终局三分应互斥且穷尽
    assert eaten | alive | det.removed_by_bo == reg, "终局分类不穷尽"
    assert not (eaten & alive) and not (eaten & det.removed_by_bo) and not (alive & det.removed_by_bo)
    assert det.removed_by_bo <= broken, "breakout-supersede 移除者必然 ever_broken"

    # 方案② 可显示性:自身或任一祖先 ever_broken
    def displayable(pid):
        seen = set()
        cur = pid
        while cur is not None and cur not in seen:
            if cur in broken:
                return True
            seen.add(cur)
            cur = det.parent.get(cur)
        return False

    disp = {p for p in reg if displayable(p)}
    missed = reg - disp

    # 漏掉者的归因:自身终局是 alive 还是 eaten
    missed_alive = missed & alive
    missed_eaten = missed & eaten
    assert not (missed & det.removed_by_bo)

    # 方案② 每个 bo 的 referenced_points 膨胀
    def chain_of(pid):
        """pid 出生时吞下的整条(递归)子孙集合。"""
        kids = children.get(pid, [])
        out = []
        for k in kids:
            out.append(k)
            out.extend(chain_of(k))
        return out

    children = {}
    for c, p in det.parent.items():
        children.setdefault(p, []).append(c)

    ref2_sizes = []
    for ids in broken_per_bo:
        tot = 0
        for pid in ids:
            tot += 1 + len(chain_of(pid))
        ref2_sizes.append(tot)

    # 同 bar 多 pk_id(re-registration)
    bar_counter = Counter(v["index"] for v in det.reg.values())
    n_dup_bars = sum(1 for c in bar_counter.values() if c > 1)
    n_dup_pks = sum(c for c in bar_counter.values() if c > 1)

    # ② 下的重复显示:同一 pk 出现在多个 bo 的(链平铺后)referenced_points 中
    appear = Counter()
    for ids in broken_per_bo:
        for pid in ids:
            appear[pid] += 1
            for k in chain_of(pid):
                appear[k] += 1

    return dict(
        n_bars=len(df), n_bo=len(evs), n_pk=len(reg),
        n_broken=len(broken),
        n_removed_by_bo=len(det.removed_by_bo),
        n_eaten=len(eaten), n_alive=len(alive),
        n_eaten_broken=len(eaten & broken), n_eaten_unbroken=len(eaten - broken),
        n_alive_broken=len(alive & broken), n_alive_unbroken=len(alive - broken),
        n_disp=len(disp), n_missed=len(missed),
        n_missed_alive=len(missed_alive), n_missed_eaten=len(missed_eaten),
        ref1_sum=sum(ref_sizes), ref1_max=max(ref_sizes, default=0),
        ref2_sum=sum(ref2_sizes), ref2_max=max(ref2_sizes, default=0),
        n_dup_bars=n_dup_bars, n_dup_pks=n_dup_pks,
        marker_slots_v2=sum(appear.values()),
        n_multi_appear=sum(1 for v in appear.values() if v > 1),
    )


CONFIGS = [
    ("bb_v1/bb_v0/bb_v3/bottom_burst  peak=high breakout=close [params.yaml]", BO_KW),
    ("bo_only                          peak=high breakout=high [params.yaml]", BO_KW_BO_ONLY),
    ("分叉象限(无 app 使用)           peak=close breakout=high",
     dict(BO_KW, peak_measure="close", breakout_measure="high")),
]


def report(d, title):
    tot = d.sum()
    P = int(tot.n_pk)
    nbo = int(tot.n_bo)

    def pc(x): return f"{x:7d} ({x / P:6.2%})"

    print("=" * 78)
    print(title)
    print("=" * 78)
    print(f"N symbols = {len(d)}")
    print(f"总 bar = {int(tot.n_bars)}   总 bo = {nbo}   总登记 pk = {P}")
    print()
    print("-- 终局 x 是否曾被突破(互斥穷尽 5 格) --")
    print(f"  breakout-supersede 移除 (必 broken) : {pc(int(tot.n_removed_by_bo))}")
    print(f"  被吃(eaten) 且 曾被突破             : {pc(int(tot.n_eaten_broken))}")
    print(f"  被吃(eaten) 且 从未被突破           : {pc(int(tot.n_eaten_unbroken))}")
    print(f"  存活(alive) 且 曾被突破             : {pc(int(tot.n_alive_broken))}")
    print(f"  存活(alive) 且 从未被突破           : {pc(int(tot.n_alive_unbroken))}")
    print(f"  -- 小计 ever_broken                 : {pc(int(tot.n_broken))}")
    print()
    print("-- 方案2 覆盖 --")
    print(f"  现状(仅 broken 可见)               : {pc(int(tot.n_broken))}")
    print(f"  方案2 可显示(自身或祖先曾被突破)   : {pc(int(tot.n_disp))}")
    print(f"    其中新增(靠递归链才现身)         : {pc(int(tot.n_disp - tot.n_broken))}")
    print(f"  方案2 漏掉                         : {pc(int(tot.n_missed))}")
    print(f"    漏掉-alive                       : {pc(int(tot.n_missed_alive))}")
    print(f"    漏掉-eaten(链无任一祖先被突破)   : {pc(int(tot.n_missed_eaten))}")
    eat = int(tot.n_eaten)
    if eat:
        print(f"  [eaten 子集内] 靠链现身 {int(tot.n_eaten - tot.n_missed_eaten)}/{eat} = "
              f"{(tot.n_eaten - tot.n_missed_eaten)/eat:.1%}")
    print()
    print("-- referenced_points 膨胀 --")
    print(f"  现状 : 总条目 {int(tot.ref1_sum):6d}  均值/bo {tot.ref1_sum / nbo:5.2f}  单 bo 最大 {int(d.ref1_max.max())}")
    print(f"  方案2: 总条目 {int(tot.ref2_sum):6d}  均值/bo {tot.ref2_sum / nbo:5.2f}  单 bo 最大 {int(d.ref2_max.max())}")
    print(f"  膨胀倍数 = {tot.ref2_sum / tot.ref1_sum:.3f}x")
    print(f"  方案2 marker 槽位总数 {int(tot.marker_slots_v2)}(可显示 pk 数 {int(tot.n_disp)}),"
          f"被重复画的 pk 个数 {int(tot.n_multi_appear)}")
    print()
    print("-- 同 bar 重复登记(re-registration, 背景 2.5) --")
    print(f"  含 >1 个 pk_id 的 bar 数 = {int(tot.n_dup_bars)}   涉及 pk 数 = {pc(int(tot.n_dup_pks))}")
    print()
    print("-- 每股比例分布(median / p10 / p90) --")
    for name, num in [("ever_broken", "n_broken"), ("方案2可显示", "n_disp"),
                      ("方案2漏掉", "n_missed"), ("漏掉-alive", "n_missed_alive"),
                      ("漏掉-eaten", "n_missed_eaten")]:
        r = (d[num] / d.n_pk).dropna()
        print(f"  {name:14s} median={r.median():7.2%}  p10={r.quantile(.1):7.2%}  p90={r.quantile(.9):7.2%}")
    print()


def main():
    n_sym = int(sys.argv[1]) if len(sys.argv) > 1 else 300
    mode = sys.argv[2] if len(sys.argv) > 2 else "window"   # window | full
    random.seed(7)                                          # 固定 seed,可复现
    files = sorted(PKL.glob("*.pkl"))
    sample = random.sample(files, min(n_sym, len(files)))    # 随机取样,不手挑
    wins = []
    for f in sample:
        try:
            df = pd.read_pickle(f)
            if mode == "full":
                win = df                                    # 全历史(约 1250 根),复现 skeptic 口径
            else:
                win = slice_window(df, START, END)          # scan 窗(约 364 根),复现 UI 实际所见
            if win is None or len(win) < 250:
                continue
            wins.append(win.reset_index(drop=True))
        except Exception:
            continue
    span = f"全历史(每股约 {int(sum(len(w) for w in wins)/max(1,len(wins)))} 根)" if mode == "full" \
        else f"scan 窗 {START}..{END}(每股约 {int(sum(len(w) for w in wins)/max(1,len(wins)))} 根)"
    print(f"载入 {len(wins)} 只股票,口径 = {span},seed=7 随机取样\n")
    for title, mkw in CONFIGS:
        kw = dict(mkw)
        rows = []
        for w in wins:
            try:
                rows.append(analyse(w, kw))
            except Exception as ex:
                print("  [skip]", type(ex).__name__, ex)
        report(pd.DataFrame(rows), title)


if __name__ == "__main__":
    main()
