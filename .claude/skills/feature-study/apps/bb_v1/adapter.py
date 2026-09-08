# -*- coding: utf-8 -*-
"""feature-study · bb_v1 app adapter。

把骨架 extract.py 里原本硬编码的 pattern-特异部分(tb/bo/burst 节点名、
bo→tb 几何算式、已知信号列)搬到这一个文件;骨架本身只认 observe() 的返回值 +
四个常量,不认任何具体走势的节点名。

本文件的 observe() = 骨架旧版第 129-161 行三段(去重 / 边界过滤 / 几何计算)的整体
搬迁:流式去重降级为 DEDUP_COLS 声明(由骨架事后 drop_duplicates);tb_start/tb_date
两列改由骨架统一以 entry_idx/entry_date 注入,本文件不再产出。

换 app 时新建 apps/<app>/adapter.py(复制 apps/_template/adapter.py 起手),本文件
保持不动——它是 bb_v1 专属声明,不是别的 app 的参照对象。
"""

import numpy as np

# 提供 Params / build_pattern / eval_meta 的模块(是模块,不是包)
APP_MODULE = "path2_apps.bb_v1.dag_spec"

# ⚠ 这是「某一次 scan 快照」的属性,不是「bb_v1 这个 app」的属性:Params.from_dict
# 对快照里缺失的键会注入「当前代码默认值」,scan 早于某参数引入时该参数会被静默
# 启用,重放 match 集必失配。当前配套的 scan(outputs/path2_web/scans/20260908T113225.json)
# 的 params_snapshot 里 tb.max_day_drop_pct = 0.2 确实存在,所以这里必须是空 dict——
# 换 scan 必须重核这个常量(骨架那边会提供一个可选入参临时覆盖它)。
PARAM_OVERRIDES = {}

# 去重键 = (symbol, tb 实例身份, 锚定 bo 身份)——对应旧骨架 kept 循环里手写的
# seen/key 三行(已删),改由骨架事后 drop_duplicates 做等价去重。
DEDUP_COLS = ("symbol", "tb_id", "bo_id")

# bb 系当前的已知信号:来源 = docs/feature_candidates.md 已关闭段判定「有信号」的
# 条目;关闭一条就在这里加一条列名,并在 observe() 里实现其计算。
KNOWN_SIGNALS = ["m1_burst_runup", "m2_depth_rel"]


def observe(m, evs, win, cols) -> dict | None:
    """从一条 bb_v1 match 里取出 tb/bo/burst 几何观测列。

    参数:
      m: 一条 match(res.matches 的元素)。
      evs: {instance_id: event} 全事件字典。
      win: 切好的 OHLCV DataFrame(本 app 未直接用到,tb_date 已改由骨架的
        entry_date 注入)。
      cols: 骨架每股预算一次的 types.SimpleNamespace,字段 = high/low/close/open/
        volume/atr/n——前五个是整列 ndarray,atr 是 calculate_atr(...,14) 的整列
        ndarray,n = len(win)。

    返回:
      dict:仅 bb_v1 特异的列。骨架另行注入 symbol / label / entry_idx / entry_date /
        c0_atr_pct,本函数不再产出它们。
      None:这条 match 不进样本(bo 在窗口首根之前、tb 起点越界、或锚点 ATR 非正)。
    """
    tb = m.node_index["tb"]
    burst = m.node_index["burst"]
    bo = evs[tb.anchor_bo_id]
    # members 存完整 BOEvent 对象(breakout.BurstEvent.members)——直接属性访问,
    # 架构再变让它炸 AttributeError,不要 getattr 吞漂移
    first_bo = burst.members[0] if burst.members else bo
    b, t0, t1 = bo.end_idx, tb.start_idx, tb.end_idx
    if b < 1 or t0 >= cols.n:
        return None
    a = cols.atr[b - 1]
    if not np.isfinite(a) or a <= 0:
        return None
    o = dict(tb_id=tb.instance_id, bo_id=tb.anchor_bo_id,
             bo_idx=b, tb_end=t1,
             first_bo_idx=first_bo.end_idx,
             burst_count=getattr(burst, "count", None),
             bo_drought=getattr(bo, "drought", None),
             bo_vol_ratio=getattr(bo, "vol_ratio", None),
             atr=a)
    # bb 系当前的已知信号(来源 = docs/feature_candidates.md 已关闭段判定「有信号」
    # 的条目;2026-07 tb 几何×label 研究所定),对应 KNOWN_SIGNALS 声明
    peak_high = cols.high[b:t0 + 1].max()
    depth = peak_high - cols.low[t0]
    o["m2_depth_rel"] = depth / peak_high if peak_high > 0 else np.nan
    o["m2_depth_atr"] = depth / a
    fb = o["first_bo_idx"]
    o["m1_burst_runup"] = (cols.close[b] / cols.close[fb - 1] - 1.0
                           if fb >= 1 else np.nan)
    return o
