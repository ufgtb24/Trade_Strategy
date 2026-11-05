#!/bin/bash
# 票 06 的 Python 全套与 web-loop：带护栏（evidence/04/wall/sitecustomize.py）和重定向（evidence/06/wall/wall_redirect.py）。
# 用法：run_py.sh <被测 checkout 根目录> <标签> <日志目录>；被测 checkout 要有自己的 .venv（uv sync）和 datasets 软链。
ROOT="$1"; TAG="$2"; LOGS="$3"
EV="$(cd "$(dirname "$0")/.." && pwd)"   # evidence/，随本脚本的位置，worktree 删了也找得到
cd "$ROOT" || exit 1
export PT_TICKET=06 WALL_LOG="$LOGS/$TAG-wall.log" PYTHONPATH="$EV/06/wall:$EV/04/wall" PYTHONDONTWRITEBYTECODE=1
: > "$WALL_LOG"
.venv/bin/python -c "open('datasets/pkls/AA.pkl','rb')" > "$LOGS/$TAG-guard-probe.log" 2>&1; echo "护栏探测退出码 $?（应非 0）" >> "$LOGS/$TAG-guard-probe.log"
: > "$WALL_LOG"
.venv/bin/python -m pytest -p wall_redirect tests/path2 tests/path2_apps tests/path2_web tests/scripts -q -p no:cacheprovider -rfEs --tb=line > "$LOGS/$TAG-pytest.log" 2>&1
echo "exit=$?" >> "$LOGS/$TAG-pytest.log"
OUT="$LOGS/$TAG-skills.log"; : > "$OUT"
for d in tune-gates tune-gates-v3 feature-study diagnose-event; do
  echo "=== $d" >> "$OUT"
  .venv/bin/python -m pytest -p wall_redirect ".claude/skills/$d" -q -p no:cacheprovider -rfE --tb=line >> "$OUT" 2>&1
  echo "exit=$?" >> "$OUT"
done
node .claude/skills/web-loop/tests/run-all.mjs > "$LOGS/$TAG-web-loop.log" 2>&1
echo "web-loop exit=$?" >> "$OUT"
echo DONE >> "$OUT"
