#!/bin/bash
# 票 14 用来在票 worktree 里单跑几份 e2e、以及重拍 dev-ui-replication 快照的驱动(复制自会话 scratch)。
# 起一个测试后端(标注目录、扫描输出都在给定的临时目录,不碰用户的 annotations/),临时目录里还没有扫描时
# 先种一份和 evidence/13/e2e_run.sh 相同的小扫描,再跑给定的 spec,最后按进程号停后端。
# 前提:被测 checkout 的 configs/path2_web.yaml 端口已临时改成 <后端端口> / 另一个前端端口(skip-worktree,不提交)。
# 用法:[PY=<解释器>] bash run_specs.sh <被测 checkout 根目录> <后端端口> <临时目录> <日志文件> <playwright 参数与 spec…>
# 重拍 dev-ui-replication 快照(要一个新的空临时目录,让历史里只有种子扫描):
#   bash run_specs.sh <checkout> <端口> <新的空目录> <日志> --update-snapshots=changed e2e/dev-ui-replication.spec.ts
ROOT="$1"; PORT="$2"; TMP="$3"; LOG="$4"; shift 4
PY="${PY:-$ROOT/.venv/bin/python}"
mkdir -p "$TMP/ann"
"$PY" "$ROOT/path2_web_ui/e2e/annotationBackend.py" "$PORT" "$TMP/ann" e2e > "$TMP/backend.log" 2>&1 &
BPID=$!
echo "backend pid $BPID"
for i in $(seq 1 60); do curl -sf "http://127.0.0.1:$PORT/scans/" > /dev/null && break; sleep 1; done
n=$(curl -s "http://127.0.0.1:$PORT/scans/" | "$PY" -c 'import sys,json; print(sum(1 for s in json.load(sys.stdin) if not s.get("partial")))')
if [ "${n:-0}" -eq 0 ]; then
curl -s -X POST "http://127.0.0.1:$PORT/scan" -H 'Content-Type: application/json' \
  -d '{"pattern_ids":["bottom_burst","bb_v1","bo_only","new_step"],"start_date":"2024-01-01","end_date":"2025-12-01","workers":2,"ticker_regex":"^(PLTR|GME|NVDA|AMC|SOFI|AAPL)$","label_horizon":40,"price_min":0.5,"price_max":30,"volume_min":10000,"note":"e2e_seed"}'
for i in $(seq 1 150); do
  n=$(curl -s "http://127.0.0.1:$PORT/scans/" | "$PY" -c 'import sys,json; print(sum(1 for s in json.load(sys.stdin) if not s.get("partial")))' 2>/dev/null)
  [ "${n:-0}" -gt 0 ] && break; sleep 2
done
fi
echo "scans: $n"
cd "$ROOT/path2_web_ui" || exit 1
PATH2_E2E_PYTHON="$PY" npx playwright test --workers=1 --reporter=list "$@" > "$LOG" 2>&1
echo "playwright exit $?"
kill "$BPID"
