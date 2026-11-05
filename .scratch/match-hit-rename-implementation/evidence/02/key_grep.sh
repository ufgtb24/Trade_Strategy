#!/bin/bash
# 票 02 验收：全仓代码里旧键的残留（git grep，只看受 git 管理的代码文件；.md 是 04、05 的正文）。在仓库根目录运行。
PAT='"matches"|\bmatch_id\b|match_fp_counts|match_windows|dropped_matches|target_matches|\bany_match\b|per_leaf_match|_match_to_dict|MatchDict'
echo "## 代码文件（不含历史与别的系统）"
git grep -nE "$PAT" -- '*.py' '*.ts' '*.vue' '*.mjs' '*.js' '*.json' '*.yaml' '*.yml' '*.sh' \
  ':!.scratch' ':!.scratch-archive' ':!docs/research' ':!docs/tmp' ':!docs/legacy' ':!docs/superpowers' ':!docs/agents' ':!BreakoutStrategy' ':!scripts/experiments' ':!scripts/implementation_board.py' ':!scripts/wayfinder_board.py' | cut -c1-160
echo "## types.ts 的 matches / match_id / MatchDict"
git grep -nE '\bmatches\b|\bmatch_id\b|MatchDict' -- path2_web_ui/src/types.ts | cut -c1-160
echo "## 正文 .md（归 04、05，只列出）"
git grep -lE "$PAT" -- '*.md' ':!.scratch' ':!.scratch-archive' ':!docs/research' ':!docs/tmp' ':!docs/legacy' ':!docs/superpowers' ':!docs/agents'
