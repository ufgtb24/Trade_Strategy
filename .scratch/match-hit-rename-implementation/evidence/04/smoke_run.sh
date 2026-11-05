#!/bin/bash
# 票 04 冒烟的完整命令（worktree 根目录）：起只读训练段副本的后端 → 网页扫描接口新扫一份小 scan → 照 diagnose-event 走骨架 A。
# 全程带数据墙护栏（wall/sitecustomize.py）：任何进程打开或列 datasets/pkls 都被拒绝并记日志；这次日志没有生成。
# 用法：bash smoke_run.sh <临时目录>（下面放临时标注目录和护栏日志）
TMP="$1"; EV=.scratch/match-hit-rename-implementation/evidence/04; mkdir -p "$TMP/anno"
export PT_TICKET=04 WALL_LOG="$TMP/wall.log" PYTHONPATH="$PWD/$EV/wall"
.venv/bin/python $EV/smoke_backend.py 8097 "$TMP/anno" & BP=$!
for i in $(seq 1 40); do curl -s -o /dev/null http://127.0.0.1:8097/scans/ && break; sleep 1; done
curl -s -X POST http://127.0.0.1:8097/scan -H 'Content-Type: application/json' -d '{"pattern_ids":["bb_v1"],"start_date":"2022-01-01","end_date":"2025-12-01","workers":2,"ticker_regex":"^(PLTR|GME|AMC|SOFI|SNAP|PLUG)$","label_horizon":40,"price_min":0.5,"price_max":30,"volume_min":10000,"note":"t04-smoke"}'
for i in $(seq 1 90); do ls outputs/path2_web/scans/*.json >/dev/null 2>&1 && break; sleep 2; done
kill "$BP"
.venv/bin/python $EV/smoke_diagnose.py
