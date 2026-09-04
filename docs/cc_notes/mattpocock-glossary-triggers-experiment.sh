#!/bin/bash
# mattpocock-glossary-triggers-experiment.sh
# 用途：验证 fresh session 走 /grill-with-docs 时会不会主动读 CONTEXT.md，
#       并对照三种布局：A1 完整项目配置 / A2 多上下文无 CLAUDE.md / A3 单上下文无 CLAUDE.md。
#       同时度量「读了词表之后是否仍沿用 prompt 里的野词」——验证 R1 不抓异词同义。
#       升级 mattpocock-skills 后重跑一次，看上游有没有把「读词表 / 纠正同义词」补进 skill。
# 幂等：每次运行先清空输出目录；只读源仓库、不写源仓库；每臂跑在独立副本里。
# 用法：bash mattpocock-glossary-triggers-experiment.sh <源仓库根> <输出目录> [prompt 文件]
# 前置：claude CLI 可用；源仓库有 CONTEXT-MAP.md + path2/CONTEXT.md + path2_web/CONTEXT.md。
set -e

SRC="${1:?用法: $0 <源仓库根> <输出目录> [prompt 文件]}"
OUT="${2:?用法: $0 <源仓库根> <输出目录> [prompt 文件]}"
PROMPT_FILE="${3:-}"
# 给 agent 一点可探索的代码；按需改成你仓库里的文件
CODE_FILES="${CODE_FILES:-path2/dag/engine.py path2/core.py}"

rm -rf "$OUT"; mkdir -p "$OUT"

# ---- prompt：默认故意全用自造野词，看 agent 会不会去查词表纠正 ----
if [ -n "$PROMPT_FILE" ]; then
  PROMPT="$(cat "$PROMPT_FILE")"
else
  PROMPT='/mattpocock-skills:grill-with-docs 我想给 path2 引擎的 run_streams 加一个能力：调用方把已经算好的那些流预先塞进去，引擎跳过重算。请把这个设计磨清楚再问我问题。要考虑三件事：流里每个对象身上引擎贴的那些身份字段、对象之间互相引用的那些槽位怎么翻译成身份字符串、以及容器声明的核对还成不成立。'
fi
printf '%s\n' "$PROMPT" > "$OUT/prompt.txt"

copy_code() {  # $1 = 目标臂目录
  for f in $CODE_FILES; do mkdir -p "$1/$(dirname "$f")"; cp "$SRC/$f" "$1/$f"; done
}

# ---- A2：多上下文（CONTEXT-MAP → path2/CONTEXT.md），无 CLAUDE.md、无 docs/agents ----
A2="$OUT/A2_multi"; mkdir -p "$A2/path2" "$A2/path2_web"
cp "$SRC/CONTEXT-MAP.md" "$A2/"
cp "$SRC/path2/CONTEXT.md" "$A2/path2/"
cp "$SRC/path2_web/CONTEXT.md" "$A2/path2_web/"
copy_code "$A2"

# ---- A3：单上下文（根 CONTEXT.md，内容与 path2/CONTEXT.md 逐字相同），无 CONTEXT-MAP ----
A3="$OUT/A3_single"; mkdir -p "$A3"
cp "$SRC/path2/CONTEXT.md" "$A3/CONTEXT.md"
copy_code "$A3"

# ---- A1：复刻完整项目配置（A2 + CLAUDE.md + docs/agents/*） ----
A1="$OUT/A1_repo"; cp -r "$A2" "$A1"
cp "$SRC/CLAUDE.md" "$A1/"
mkdir -p "$A1/docs/agents"; cp "$SRC"/docs/agents/*.md "$A1/docs/agents/" 2>/dev/null || true

diff -q "$A2/path2/CONTEXT.md" "$A3/CONTEXT.md" >/dev/null && echo "[ok] 两种布局的词表内容逐字相同"

# ---- 三臂并行跑 fresh session，抓 stream-json ----
for arm in A1_repo A2_multi A3_single; do
  ( cd "$OUT/$arm" && timeout 900 claude -p "$PROMPT" \
      --output-format stream-json --verbose \
      --permission-mode bypassPermissions \
      > "$OUT/$arm.jsonl" 2> "$OUT/$arm.err"
    echo "$arm exit=$?" >> "$OUT/done.txt" ) &
done
wait
cat "$OUT/done.txt"

# ---- 度量：有没有真正打开词表、第几次工具调用打开、输出用了哪些规范词 ----
python3 - "$OUT" <<'PY'
import json, glob, os, re, sys
out = sys.argv[1]
CANON = ["引用槽", "复合事件", "事件流", "物化", "子结构 node", "只显示 node"]
WILD  = ["身份字段", "身份字符串", "槽位", "容器声明"]   # prompt 里故意用的野词
OPEN = re.compile(r'(cat |Read|sed -n|head).{0,80}CONTEXT\.md')
print(f"\n{'臂':<12}{'工具数':<7}{'打开词表于第N次':<16}{'沿用野词次数':<12}{'输出用了的规范词'}")
for f in sorted(glob.glob(os.path.join(out, "A*.jsonl"))):
    arm = os.path.basename(f)[:-6]; n = 0; first = None; final = ""
    for line in open(f):
        try: o = json.loads(line)
        except Exception: continue
        if o.get("type") == "assistant":
            for c in o["message"].get("content", []):
                if c.get("type") == "tool_use":
                    n += 1
                    if first is None and OPEN.search(json.dumps(c["input"], ensure_ascii=False)): first = n
        if o.get("type") == "result": final = o.get("result", "")
    open(os.path.join(out, arm + ".final.txt"), "w").write(final)
    wild = sum(final.count(w) for w in WILD)
    print(f"{arm:<12}{n:<9}{str(first) if first else '未打开':<18}{wild:<14}{','.join(w for w in CANON if w in final) or '—'}")
PY
# 收尾：删仓库副本，只留 jsonl / final.txt / prompt.txt 作证据
rm -rf "$OUT/A1_repo" "$OUT/A2_multi" "$OUT/A3_single"
echo "[done] 证据在 $OUT"
