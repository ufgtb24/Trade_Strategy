#!/bin/bash
# 低负载复跑全部计时实验(串行,避免互相抢核);输出带 .quiet 后缀,不覆盖原文件
cd /home/yu/PycharmProjects/Trade_Strategy-tune_v1
R=docs/research/2026-08-24_region-search-budget/repro
echo "load at start: $(cat /proc/loadavg)"
for f in grid_cost generic_grid_cost microbench; do
  echo "=== $f $(date +%H:%M:%S)"; uv run python $R/$f.py > $R/${f}_out.quiet.txt 2>&1; echo "exit=$?"
done
echo "=== profile_stages gates on $(date +%H:%M:%S)"
uv run python -c "import sys; sys.path.insert(0,'$R'); import profile_stages as p; p.main(ATTACH_GATES=True, RUNTIME_CHECKS=True)" > $R/profile_stages_out.quiet.txt 2>&1
echo "=== profile_stages gates off $(date +%H:%M:%S)"
uv run python -c "import sys; sys.path.insert(0,'$R'); import profile_stages as p; p.main(ATTACH_GATES=False, RUNTIME_CHECKS=True)" >> $R/profile_stages_out.quiet.txt 2>&1
for W in 8 24; do
  echo "=== time_scan_multi ^A w$W $(date +%H:%M:%S)"
  uv run python -c "import sys; sys.path.insert(0,'$R'); import time_scan_multi as t; t.main(TICKER_REGEX='^A', WORKERS=$W)" >> $R/time_scan_multi_out.quiet.txt 2>&1
done
echo "load at end: $(cat /proc/loadavg)"; echo "ALL DONE $(date +%H:%M:%S)"
