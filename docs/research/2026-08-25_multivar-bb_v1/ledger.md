# multivar_scan 台账 · bb_v1

- 窗:2024-01-01..2026-01-01;HEAD_BUFFER=250;LABEL_HORIZON=40;FIRST_PASSAGE_K=5.0
- 过滤:price [0.5,30.0],volume_min 10000.0;底座 docs/research/2026-08-25_multivar-bb_v1/ref_params.json;宽进 {'burst': {'first_drought_min': 0, 'distinct_pk_min': 1, 'vol_spike_min': 0, 'peak_age_min': 0}, 'tb': {'max_day_drop_pct': None}}
- SCAN_GRID:{'bo.min_relative_height': [0.1, 0.15, 0.2, 0.3], 'bo.exceed_threshold': [0.001, 0.003, 0.01, 0.03], 'burst.gap_max': [4, 8, 12, 20], 'burst.min_bos': [1, 2, 3, 4], 'tb.stop_confirm_bars': [0, 1, 2, 3], 'tb.big_rise_k': [3.0, 5.0, 8.0, 12.0], 'tb.max_day_drop_pct': [None, 0.2]}
- WHERE_LEVELS:{'burst.first_drought_min': [0, 20, 40], 'burst.distinct_pk_min': [1, 3, 4], 'burst.vol_spike_min': [0, 10, 15], 'burst.peak_age_min': [0, 125]}
- 分类:{'bo.min_relative_height': 'D', 'bo.exceed_threshold': 'D', 'burst.gap_max': 'D', 'burst.min_bos': 'F', 'tb.stop_confirm_bars': 'D', 'tb.big_rise_k': 'D', 'tb.max_day_drop_pct': 'F', 'burst.first_drought_min': 'W', 'burst.distinct_pk_min': 'W', 'burst.vol_spike_min': 'W', 'burst.peak_age_min': 'W'}
- where 轴:{'burst.first_drought_min': ('burst', 'first_drought', '>='), 'burst.distinct_pk_min': ('burst', 'distinct_pk', '>='), 'burst.vol_spike_min': ('burst', 'max_bar_vol_ratio', '>='), 'burst.peak_age_min': ('burst', 'peak_age_max', '>=')}
- 检测组合数(detection_combos 实算,F 维不进组合):1024
- 断点续跑:本轮启动时 done 集共 0 股 = 已有 parquet 分片 symbol(0) ∪ random_baseline.csv symbol(0) ∪ filtered_symbols.csv symbol(0);err 不计入 done、下次自动重试;总股数(TICKER_REGEX 命中全宇宙) 8325
- 股数(本轮):待扫 8325 / 进 detector 6720 / 过滤 1605 / 有 match 3985 / 异常 0;累计行(重读全部分片) 7831477
- 股数(累计跨 1 轮 run_stats.jsonl):进 detector 6720 / 过滤 1605 / 有 match 3985 / 异常事件 0 次(同一 symbol 每轮重试各计一次,不去重)
- 耗时(本轮):wall 1217s @ 8 workers;worker 侧 scan_one_stock 累计 9632.3s(≈总计算量,单线程 detector/solve 无 I/O 等待,CPU·s 量级);本进程(编排调度)cpu 68.6s
- 耗时(累计跨 1 轮):wall 1217s;worker 侧累计 9632.3s;本进程 cpu 累计 48.4s
- 每股 scan_one_stock 耗时 ms(本轮 6720 股):p50 1385.2 / p90 2260.1;每检测组合均摊 1.400ms/股
- 每股 scan_one_stock 耗时 ms(累计 6720 股):p50 1385.2 / p90 2260.1;每检测组合均摊 1.400ms/股
- 宽进 where 下真扫格 × 年折的 match 数分布:min 178 / p50 3284 / max 13096
