#!/bin/bash
# 票 03 改后的 e2e：与基线同一批 spec（票 02 的 run_e2e.sh），只把改名后的文件名换成 hit-event-disambig。少跑 miss-detection-walkthrough。
# 它的 beforeAll 直接读 datasets/pkls（含 2026 年行情），测试本身也读 datasets/pkls/DGNX.pkl，会越过数据墙（共用执行边界第 5 条）；
# 票 01 基线里它本来就 1 失败 4 跳过，没有信号。
# 前提：configs/path2_web.yaml 的端口已临时改成 8095 / 5195（不提交，跑完复原），e2e_backend.py 已在 8095 上跑，vite 已在 5195 上跑。
# 用法：bash run_e2e.sh <被测 checkout 根目录> <日志文件>
ROOT="$1"; LOG="$2"
curl -s -X POST "http://127.0.0.1:8095/scan" -H 'Content-Type: application/json' \
  -d '{"pattern_ids":["bottom_burst","bb_v1","bo_only","new_step"],"start_date":"2024-01-01","end_date":"2025-12-01","workers":1,"ticker_regex":"^(PLTR|GME|NVDA|AMC|SOFI|AAPL)$","label_horizon":40,"price_min":0.5,"price_max":30,"volume_min":10000}'
echo
for i in $(seq 1 150); do
  n=$(curl -s "http://127.0.0.1:8095/scans/" | "$ROOT/.venv/bin/python" -c 'import sys,json; print(len(json.load(sys.stdin)))' 2>/dev/null)
  [ "${n:-0}" -gt 0 ] && break; sleep 2
done
echo "scans after seed: $n"
cd "$ROOT/path2_web_ui" || exit 1
SPECS="annotate-boxes annotate-compare annotate-direct-links annotate-grouping annotate-open-by-symbol annotate-rally-random annotate-ref-peaks annotate-samples dev-ui-replication flow hit-event-disambig scan-dialog symbol-search"
ARGS=""; for s in $SPECS; do ARGS="$ARGS e2e/$s.spec.ts"; done
PATH2_E2E_PYTHON="$ROOT/.venv/bin/python" npx playwright test --workers=1 --reporter=list $ARGS > "$LOG" 2>&1
echo "playwright exit $?"
