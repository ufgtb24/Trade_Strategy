#!/bin/bash
# 用法：run_skills.sh <标签>；在 worktree 根目录跑四个 skill 目录与 web-loop，日志写 scratchpad/logs/<标签>-*.log
SP=/tmp/claude-1000/-home-yu-PycharmProjects-Trade-Strategy/168e4fb8-326c-42a4-8936-7bfe2d2b4cec/scratchpad
ROOT=/home/yu/PycharmProjects/Trade_Strategy-04-skills
TAG=$1
cd $ROOT || exit 1
export PT_TICKET=04 WALL_LOG=$SP/logs/$TAG-wall.log PYTHONPATH=$SP/wall PYTHONDONTWRITEBYTECODE=1
: > $WALL_LOG
OUT=$SP/logs/$TAG-skills.log; : > $OUT
for d in tune-gates tune-gates-v3 feature-study diagnose-event; do
  echo "=== $d" >> $OUT
  .venv/bin/python -m pytest -p wall_redirect .claude/skills/$d -q -p no:cacheprovider -rfE >> $OUT 2>&1
  echo "exit=$?" >> $OUT
done
echo "=== web-loop" >> $OUT
node .claude/skills/web-loop/tests/run-all.mjs > $SP/logs/$TAG-web-loop.log 2>&1
echo "exit=$?" >> $OUT
echo DONE >> $OUT
