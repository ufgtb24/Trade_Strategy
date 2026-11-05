#!/bin/bash
# 票 06 的 e2e：与票 03 同一批 spec。少跑的文件和理由见完成记录。全程带护栏 evidence/04/wall/sitecustomize.py。
# 前提：configs/path2_web.yaml 的端口已临时改成 8095 / 5195（不提交，跑完复原）。
# 用法：bash run_e2e.sh <被测 checkout 根目录> <日志目录>
ROOT="$1"; LOGS="$2"
EV="$(cd "$(dirname "$0")/../.." && pwd)"   # evidence/，随本脚本的位置，worktree 删了也找得到
export PT_TICKET=06 WALL_LOG="$LOGS/e2e-wall.log" PYTHONPATH="$EV/04/wall" PYTHONDONTWRITEBYTECODE=1
: > "$WALL_LOG"
ADIR=$(mktemp -d "$LOGS/ann-XXXX")
"$ROOT/.venv/bin/python" "$EV/02/e2e/e2e_backend.py" "$ROOT" 8095 "$ADIR" > "$LOGS/e2e-backend.log" 2>&1 &
BPID=$!
cd "$ROOT/path2_web_ui" || exit 1
VITE_API_BASE=http://localhost:8095 npm run dev -- --port 5195 --strictPort > "$LOGS/e2e-vite.log" 2>&1 &
VPID=$!
echo "backend $BPID vite $VPID"
for i in $(seq 1 60); do curl -s -o /dev/null "http://127.0.0.1:8095/patterns" && break; read -t 1 < /dev/zero; done
curl -s -X POST "http://127.0.0.1:8095/scan" -H 'Content-Type: application/json' \
  -d '{"pattern_ids":["bottom_burst","bb_v1","bo_only","new_step"],"start_date":"2024-01-01","end_date":"2025-12-01","workers":1,"ticker_regex":"^(PLTR|GME|NVDA|AMC|SOFI|AAPL)$","label_horizon":40,"price_min":0.5,"price_max":30,"volume_min":10000}'
echo
for i in $(seq 1 150); do
  n=$(curl -s "http://127.0.0.1:8095/scans/" | "$ROOT/.venv/bin/python" -c 'import sys,json; print(len(json.load(sys.stdin)))' 2>/dev/null)
  [ "${n:-0}" -gt 0 ] && break; read -t 2 < /dev/zero
done
echo "scans after seed: $n"
SPECS="annotate-boxes annotate-compare annotate-direct-links annotate-grouping annotate-open-by-symbol annotate-rally-random annotate-ref-peaks annotate-samples dev-ui-replication flow hit-event-disambig scan-dialog symbol-search"
ARGS=""; for s in $SPECS; do ARGS="$ARGS e2e/$s.spec.ts"; done
PATH2_E2E_PYTHON="$ROOT/.venv/bin/python" npx playwright test --workers=1 --reporter=list $ARGS > "$LOGS/e2e.log" 2>&1
echo "playwright exit $?"
kill "$BPID" "$VPID"
echo DONE
