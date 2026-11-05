#!/bin/bash
# 票 01 的 e2e：$1 = 被测 checkout 根目录，$2 = 后端端口，$3 = 日志前缀
# 先用被测代码在 6 只股票上扫一次（主视图的 e2e 要有一份扫描历史），再跑选定的 spec。
# 不跑写死旧 scan 时间戳的 7 个文件与 sidebar-chart-focus（绑在旧扫描里的 BTMWW）：worktree 的 outputs/ 里没有那些扫描，基线上必然等满超时失败。
ROOT="$1"; PORT="$2"; TAG="$3"
S=/tmp/claude-1000/-home-yu-PycharmProjects-Trade-Strategy/bb41a4fd-4350-46f3-b781-d37b145f06a1/scratchpad/t01
PY=/home/yu/PycharmProjects/Trade_Strategy-01-framework-python-api/.venv/bin/python
ADIR=$(mktemp -d "$S/ann-$TAG-XXXX")
"$PY" "$S/e2e_backend.py" "$ROOT" "$PORT" "$ADIR" > "$S/e2e-backend-$TAG.log" 2>&1 &
BPID=$!
echo "backend pid $BPID"
for i in $(seq 1 60); do curl -s -o /dev/null "http://127.0.0.1:$PORT/patterns" && break; sleep 1; done
curl -s -X POST "http://127.0.0.1:$PORT/scan" -H 'Content-Type: application/json' \
  -d '{"pattern_ids":["bottom_burst","bb_v1","bo_only","new_step"],"start_date":"2024-01-01","end_date":"2025-12-01","workers":1,"ticker_regex":"^(PLTR|GME|NVDA|AMC|SOFI|AAPL)$","label_horizon":40,"price_min":0.5,"price_max":30,"volume_min":10000}'
echo
for i in $(seq 1 300); do
  n=$(curl -s "http://127.0.0.1:$PORT/scans/" | "$PY" -c 'import sys,json; d=json.load(sys.stdin); print(len(d) if isinstance(d,list) else len(d.get("items", d)))' 2>/dev/null)
  [ "${n:-0}" -gt 0 ] && break; sleep 2
done
echo "scans after seed: $n"
cd "$ROOT/path2_web_ui" || exit 1
SPECS="${SPECS:-annotate-boxes annotate-compare annotate-direct-links annotate-grouping annotate-open-by-symbol annotate-rally-random annotate-ref-peaks annotate-samples dev-ui-replication flow match-event-disambig miss-detection-walkthrough scan-dialog symbol-search}"
ARGS=""; for s in $SPECS; do ARGS="$ARGS e2e/$s.spec.ts"; done
PATH2_E2E_PYTHON="$PY" npx playwright test --workers=1 --reporter=list $ARGS > "$S/e2e-$TAG.log" 2>&1
echo "playwright exit $?"
kill "$BPID"; wait "$BPID" 2>/dev/null
echo done
