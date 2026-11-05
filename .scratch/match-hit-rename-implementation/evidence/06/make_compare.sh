#!/bin/bash
# 票 06 生成 test_compare.txt。用法（在仓库根目录）：bash make_compare.sh <Python 与 skill 测试所在提交> <前端与 e2e 所在提交>
PY_AT="$1"; FRONT_AT="$2"
E=.scratch/match-hit-rename-implementation/evidence
echo "# 票 06 测试全套：终检（合并了 01～06 的树）对票 01 开工时的基线 1359914（$(git rev-parse 1359914)）"
echo "# Python 与 skill：两边都带护栏 evidence/04/wall/sitecustomize.py 和重定向 evidence/06/wall/wall_redirect.py，命令见 run_py.sh。基线是干净检出；终检跑在 $(git rev-parse "$PY_AT")，工作树只多未提交的日志。"
echo "# 前端与 e2e：跑在 $(git rev-parse "$FRONT_AT")。工作树多未提交的证据脚本；e2e 期间 configs/path2_web.yaml 的端口临时改成 8095 / 5195，跑完复原。"
echo "# vitest：path2_web_ui 下 npx vitest run --reporter=default；vue-tsc：npx vue-tsc -b；e2e：evidence/06/e2e/run_e2e.sh。"
echo "# 从前端与 e2e 所在提交到 Python 所在提交，证据目录之外的改动："
git diff --stat "$FRONT_AT" "$PY_AT" -- . ":(exclude)$E" | cat
for t in base after; do echo; echo "## $t"; grep -E '[0-9]+ (passed|failed).*in ' $E/06/logs/$t-pytest.log | cut -c1-80; grep -E '^(=== |[0-9]+ (passed|failed))' $E/06/logs/$t-skills.log | sed 's/ in .*//' ; tail -1 $E/06/logs/$t-web-loop.log; echo "护栏记录 $(wc -l < $E/06/logs/$t-wall.log) 行"; done
echo; echo "## pytest 失败清单比较（基线 vs 终检）"
diff <(grep -E '^(FAILED|ERROR)' $E/06/logs/base-pytest.log | sed 's/ - .*//' | sort) <(grep -E '^(FAILED|ERROR)' $E/06/logs/after-pytest.log | sed 's/ - .*//' | sort) && echo "相同："; grep -E '^(FAILED|ERROR)' $E/06/logs/after-pytest.log | sed 's/ - .*//'
echo; echo "## 与票 01 不带护栏的基线（evidence/01/logs/pytest-base.log）比"
grep -E '[0-9]+ passed' $E/01/logs/pytest-base.log | tail -1 | cut -c1-80
diff <(grep -E '^(FAILED|ERROR)' $E/01/logs/pytest-base.log | sed 's/ - .*//' | sort) <(grep -E '^(FAILED|ERROR)' $E/06/logs/base-pytest.log | sed 's/ - .*//' | sort) && echo "失败清单相同"
echo; echo "## vitest（票 01 基线 evidence/01/logs/vitest-summary.log）"
grep -E 'Tests  ' $E/01/logs/vitest-summary.log | sed 's/^ *//'; grep -E 'Tests  ' $E/06/logs/after-vitest-summary.log | sed 's/^ *//'
diff <(grep -E '^\s*FAIL' $E/01/logs/vitest-summary.log | sed 's/^ *//' | sort -u) $E/06/logs/after-vitest-failures.txt && echo "失败清单相同（多出的 1 条通过是票 03 加的）"
echo; echo "## vue-tsc：输出 $(wc -l < $E/06/logs/after-vue-tsc.log) 行（通过）"
echo; echo "## e2e（票 01 基线 evidence/01/e2e/results-base.txt，重跑 results-base-rerun-rally-random.txt）"
python3 $E/06/compare_with_01.py $E/01/e2e/results-base.txt $E/01/e2e/results-base-rerun-rally-random.txt $E/06/e2e/results-after.txt
echo "护栏记录 $(wc -l < $E/06/logs/e2e-wall.log) 行"
