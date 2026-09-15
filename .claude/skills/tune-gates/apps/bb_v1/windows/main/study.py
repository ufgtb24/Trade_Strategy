# -*- coding: utf-8 -*-
"""tune-gates · study 声明(由 tune.install 生成)。

改这个文件会让已有扫描结果作废——它的整份文件哈希是长表准入校验。若要手改
(例如补充 FLAG_RULES:渲染器无法把 lambda 确定性地转成源码,只能留空由人补),
必须在第一次扫描之前改完;扫描之后再改,就等于要开一份新的扫描结果,请重新走
一次接入流程。

FLAG_RULES 的写法:格级机制标记,cell(点号键 dict)→ 标记文本或 None,用于
cells.csv 的 flags 列。cell 是 region_core.cell_coords() 的输出,两套键名不同、
别按直觉都写参数名:
  - combo 轴(来自 SCAN_GRID 的 D 维)用参数名 "<section>.<param>"(与 SCAN_GRID 键一致)
  - pred 轴(F/W 维)用长表列名 "<node_id>.<field>"(classify() 探出来的 detector
    字段名,node_id 是 dag 里的节点名、field 是该 node 上的属性名——通常不等于参数名)
写错会在 cells.csv 阶段裸 KeyError。
"""

APP_MODULE = 'path2_apps.bb_v1.dag_spec'
BASE_YAML = 'params.yaml'

WIDE_OVERRIDES = {'burst': {'distinct_pk_min': 1, 'first_drought_min': 0, 'peak_age_min': 0, 'vol_spike_min': 0}, 'tb': {'max_day_drop_pct': None}}

SCAN_GRID = {('bo', 'exceed_threshold'): [0.0015, 0.003, 0.0045, 0.0075], ('bo', 'min_relative_height'): [0.1, 0.2, 0.3, 0.5], ('burst', 'gap_max'): [4, 8, 12, 20], ('burst', 'min_bos'): [1, 2, 3, 4], ('tb', 'max_rise_k'): [0.75, 1.5, 2.25, 3.75], ('tb', 'max_span'): [10, 20, 30, 50], ('tb', 'stop_confirm_bars'): [1, 2, 3, 4]}

WHERE_LEVELS = {('burst', 'distinct_pk_min'): [1, 3, 5], ('burst', 'first_drought_min'): [0, 40, 80], ('burst', 'peak_age_min'): [0, 60, 120], ('burst', 'vol_spike_min'): [0, 3, 6], ('tb', 'max_day_drop_pct'): [None, 0.2]}

REF_POINT = {'bo.exceed_threshold': 0.003, 'bo.min_relative_height': 0.2, 'burst.gap_max': 8, 'tb.max_rise_k': 1.5, 'tb.max_span': 20, 'tb.stop_confirm_bars': 1}

TIGHT_WHERES = {'FINAL': {('burst', 'distinct_pk_min'): 3, ('burst', 'first_drought_min'): 40, ('burst', 'peak_age_min'): 60, ('burst', 'vol_spike_min'): 3, ('tb', 'max_day_drop_pct'): 0.2}}

FLAG_RULES = [
    # 沉寂期闸 vs 串内间隔的机制交互:chain 簇首必是断点,故 first_drought > gap_max
    # 结构性必然(唯一例外是簇首恰为扫描窗口首根 bo,那时 first_drought 取 drought_floor,
    # 可小于 gap_max——那是首部缓冲不够,不是闸生效)。阈值 <= gap_max 的格,这道闸拦不下
    # 任何东西,读数应视同"未设该闸"。本网格里只有 first_drought_min=0 命中(40/80 均 > 20)。
    lambda c: "first_drought 闸退化恒真(阈值<=gap_max)"
              if c["burst.first_drought"] <= c["burst.gap_max"] else None,
]
