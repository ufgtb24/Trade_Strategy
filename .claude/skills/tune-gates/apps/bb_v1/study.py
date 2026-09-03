# -*- coding: utf-8 -*-
"""tune-gates · study 声明(由 tune.install 生成)。

改这个文件会让已有扫描结果作废——它的整份文件哈希是长表准入校验。若要手改
(例如补充 FLAG_RULES:渲染器无法把 lambda 确定性地转成源码,只能留空由人补),
必须在第一次扫描之前改完;扫描之后再改,就等于要开一份新的扫描结果,请重新走
一次接入流程。
"""

APP_MODULE = 'path2_apps.bb_v1.dag_spec'
BASE_YAML = 'params.yaml'

WIDE_OVERRIDES = {'burst': {'distinct_pk_min': 1, 'first_drought_min': 0, 'peak_age_min': 0, 'vol_spike_min': 0}, 'tb': {'max_day_drop_pct': None}}

SCAN_GRID = {('bo', 'min_relative_height'): [0.1, 0.2, 0.3], ('burst', 'gap_max'): [4, 8, 12]}

WHERE_LEVELS = {('burst', 'first_drought_min'): [0, 20, 40], ('tb', 'max_day_drop_pct'): [None, 0.2]}

REF_POINT = {'bo.min_relative_height': 0.2, 'burst.gap_max': 8}

TIGHT_WHERES = {'FINAL': {('burst', 'first_drought_min'): 20, ('tb', 'max_day_drop_pct'): 0.2}}

FLAG_RULES = []
