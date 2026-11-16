#!/bin/bash
# 票 13 的 e2e 全套：起一个读训练段副本的后端（标注目录、扫描输出都在临时目录，不碰用户的 annotations/），
# 先种一份 6 只股票的小扫描（flow、annotate-open-by-symbol 等要「已有扫描历史」），再跑 e2e 全套，最后按进程号停后端。
# 不跑 miss-detection-walkthrough：它的 beforeAll 直接读 datasets/pkls（含 2026 年行情），越过数据墙（共用执行边界第 1 条）。
# 依赖已不存在的历史扫描（2026-06-30 那次扫描、BTMWW 夹具）的 6 个 spec 另跑一轮、单条超时压到 30 秒：
# 它们在任何 checkout 里都找不到那份扫描，按默认 600 秒超时要白等 5 个多小时；30 秒足够一条正常用例跑完。
# 前提：被测 checkout 的 configs/path2_web.yaml 端口已临时改成 <后端端口> / 另一个前端端口（skip-worktree，不提交），
#       前端由 playwright 的 webServer 在配置的 frontend_port 上起。
# 用法：[PY=<解释器>] bash e2e_run.sh <被测 checkout 根目录> <后端端口> <临时目录> <日志文件>
#   PY 默认是被测 checkout 自己的 .venv；基线 checkout 没有 .venv 时借票 worktree 的解释器——
#   annotationBackend.py 把它所在的 checkout 插在 sys.path 最前面，导入的是被测 checkout 的代码（下面核对一遍）。
ROOT="$1"; PORT="$2"; TMP="$3"; LOG="$4"
PY="${PY:-$ROOT/.venv/bin/python}"
(cd "$ROOT" && "$PY" -c 'import sys; sys.path.insert(0, "."); import path2_web; print("path2_web 来自", path2_web.__file__)')
mkdir -p "$TMP/ann"
"$PY" "$ROOT/path2_web_ui/e2e/annotationBackend.py" "$PORT" "$TMP/ann" e2e > "$TMP/backend.log" 2>&1 &
BPID=$!
echo "backend pid $BPID"
for i in $(seq 1 60); do curl -sf "http://127.0.0.1:$PORT/scans/" > /dev/null && break; sleep 1; done
curl -s -X POST "http://127.0.0.1:$PORT/scan" -H 'Content-Type: application/json' \
  -d '{"pattern_ids":["bottom_burst","bb_v1","bo_only","new_step"],"start_date":"2024-01-01","end_date":"2025-12-01","workers":2,"ticker_regex":"^(PLTR|GME|NVDA|AMC|SOFI|AAPL)$","label_horizon":40,"price_min":0.5,"price_max":30,"volume_min":10000,"note":"e2e_seed"}'
echo
for i in $(seq 1 150); do
  n=$(curl -s "http://127.0.0.1:$PORT/scans/" | "$PY" -c 'import sys,json; print(sum(1 for s in json.load(sys.stdin) if not s.get("partial")))' 2>/dev/null)
  [ "${n:-0}" -gt 0 ] && break; sleep 2
done
echo "scans after seed: $n"
cd "$ROOT/path2_web_ui" || exit 1
OLD_FIXTURE='kline-ctrl-wheel-right-anchor|shift-pair-feedback|subchart-band-zoom|subchart-blankclick-yaxis|subchart-scroll-drag|subchart-tooltip-crosshair'
SPECS=$(ls e2e/*.spec.ts | grep -v miss-detection-walkthrough | grep -Ev "$OLD_FIXTURE")
OLD=$(ls e2e/*.spec.ts | grep -E "$OLD_FIXTURE")
PATH2_E2E_PYTHON="$PY" npx playwright test --workers=1 --reporter=list $SPECS > "$LOG" 2>&1
echo "playwright exit $?"
PATH2_E2E_PYTHON="$PY" npx playwright test --workers=1 --reporter=list --timeout=30000 $OLD > "${LOG%.log}-old-fixture.log" 2>&1
echo "playwright (old fixture) exit $?"
kill "$BPID"
