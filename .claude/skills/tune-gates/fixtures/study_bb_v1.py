# -*- coding: utf-8 -*-
"""bb_v1 · tune-gates study 声明(自测夹具;底座 = params.yaml)。

2026-08-30: 原底座 p2.yaml 于 41fd193 被删(内容并入 params.yaml),tb 同批换代为方案 C、
删除 8 个旧字段。本夹具据此改底座并重写 tb 三维——它是**通用区测试资产**,只需保证
classify/build_classification/pred_mask 有一份真实可用的 spec 输入,不必与 apps/bb_v1/ 一致。
"""

APP_MODULE = "path2_apps.bb_v1.dag_spec"
BASE_YAML = "params.yaml"

WIDE_OVERRIDES = {"burst": {"first_drought_min": 0, "distinct_pk_min": 1, "vol_spike_min": 0, "peak_age_min": 0},
                  "tb": {"max_day_drop_pct": None}}

SCAN_GRID = {("bo", "min_relative_height"): [0.1, 0.15, 0.2, 0.3],
             ("bo", "exceed_threshold"):    [0.001, 0.003, 0.01, 0.03],
             ("burst", "gap_max"):          [4, 8, 12, 20],
             ("burst", "min_bos"):          [1, 2, 3, 4],
             ("tb", "stop_confirm_bars"):   [1, 2, 3, 4],
             ("tb", "max_rise_k"):          [1.0, 1.5, 2.5, 4.0]}

WHERE_LEVELS = {("burst", "first_drought_min"): [0, 20, 40],
                ("burst", "distinct_pk_min"):   [1, 3, 4],
                ("burst", "vol_spike_min"):     [0, 10, 15],
                ("burst", "peak_age_min"):      [0, 125],
                ("tb", "max_day_drop_pct"):     [None, 0.2]}

REF_POINT = {"bo.min_relative_height": 0.2, "bo.exceed_threshold": 0.003, "burst.gap_max": 8,
             "tb.stop_confirm_bars": 1, "tb.max_rise_k": 1.5}

TIGHT_WHERES = {"FINAL": {("burst", "first_drought_min"): 20, ("burst", "distinct_pk_min"): 4, ("burst", "vol_spike_min"): 15,
                          ("burst", "peak_age_min"): 0, ("tb", "max_day_drop_pct"): 0.2},
                "B":     {("burst", "first_drought_min"): 20, ("burst", "distinct_pk_min"): 3, ("burst", "vol_spike_min"): 10,
                          ("burst", "peak_age_min"): 0, ("tb", "max_day_drop_pct"): 0.2}}

FLAG_RULES = [lambda c: "first_drought 闸恒真" if c["burst.gap_max"] >= c["burst.first_drought"] > 0 else None]
