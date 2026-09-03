#!/bin/bash
# 安装两行 statusline（身份行 + 用量行，含额度窗口与跨 session 同步）到 ~/.claude/。
# 幂等：重复运行会覆盖 ~/.claude/statusline.sh，并就地更新 settings.json 的 statusLine 键。
set -e

DEST="$HOME/.claude/statusline.sh"
SETTINGS="$HOME/.claude/settings.json"

command -v jq >/dev/null || { echo "缺少 jq，先装：sudo apt install jq"; exit 1; }
command -v flock >/dev/null || echo "警告：无 flock（util-linux），跨 session 同步会退化为无锁写，并发下偶发丢更新"

mkdir -p "$HOME/.claude"
cat > "$DEST" <<'STATUSLINE_EOF'
#!/bin/bash
# Claude Code status line（两行）:
#   行1 身份: <model>    effort <level>    wt <worktree>
#   行2 用量: ctx X%    cache H% (read/total)    5h P% ↻剩余    7d P% ↻剩余
#   effort = current reasoning effort level (only shown if the model supports it)
#   ctx = current conversation context used (input + cache_read + cache_creation) / model_limit
#   cache = prompt cache 命中率 = cache_read / 输入侧总量(input + cache_read + cache_creation)
#   5h/7d = claude.ai 额度窗口已用百分比 + 距重置剩余时间（非订阅账号无此字段则整段省略）
#          百分比跨本机所有 session 同步, 取全局最新值（见 sync_rate_limits）

set -u

input=$(cat)
transcript=$(printf '%s' "$input" | jq -r '.transcript_path // empty')
model_name=$(printf '%s' "$input" | jq -r '.model.display_name // .model.id // "?"')
effort_level=$(printf '%s' "$input" | jq -r '.effort.level // empty')
worktree_name=$(printf '%s' "$input" | jq -r '.worktree.name // .workspace.git_worktree // empty')

# token 数缩写: 1234567 -> 1.2M, 123456 -> 123k, 87 -> 87
fmt_tok() {
  if   (( $1 >= 1000000 )); then awk -v n="$1" 'BEGIN{printf "%.1fM", n/1000000}'
  elif (( $1 >= 1000 ));    then awk -v n="$1" 'BEGIN{printf "%.0fk", n/1000}'
  else printf '%d' "$1"
  fi
}

# 秒数 -> 紧凑倒计时: 572400 -> 6d15h, 17220 -> 4h47m, 2700 -> 45m
fmt_eta() {
  local s=$1
  (( s < 0 )) && s=0
  if   (( s >= 86400 )); then printf '%dd%dh'   $(( s / 86400 )) $(( s % 86400 / 3600 ))
  elif (( s >= 3600 ));  then printf '%dh%02dm' $(( s / 3600 ))  $(( s % 3600 / 60 ))
  else                        printf '%dm'      $(( s / 60 ))
  fi
}

# 跨 session 同步 rate_limit。
# 同一台机器上每个 session 各持独立快照, idle session 的数字停在它最后一次 API 响应时、
# 偏低甚至差几十个百分点。同一窗口内 used_percentage 单调不减、resets_at 是窗口的唯一分代号,
# 故「新代整体取代 / 同代取 max / 旧代采用存量」即可让所有 session 看到全局最新值。
# 四元组一起同步(而非只同步百分比): 否则 idle session 会拿新百分比配自己过期的 resets_at,
# 倒计时算出负数。
RL_STORE="$HOME/.claude/.statusline-ratelimit"
sync_rate_limits() {
  # $1..$4 = 5h% / 5h_resets_at / 7d% / 7d_resets_at (均为整数); 回显同步后的四元组
  local h5=$1 r5=$2 d7=$3 r7=$4
  # resets_at 上界: 窗口不可能在超过一个窗口长度之后才重置。异常值(测试数据误入/服务端异常)
  # 若被当成「新代」写进 store, 会把正确值顶掉并锁死到那个时刻为止, 故先拒收再入库。
  local now maxr5 maxr7
  now=$(date +%s); maxr5=$(( now + 18300 )); maxr7=$(( now + 605100 ))
  (( r5 > maxr5 || r7 > maxr7 )) && { echo "$h5 $r5 $d7 $r7"; return; }
  (
    flock -w 1 9 2>/dev/null || { echo "$h5 $r5 $d7 $r7"; exit 0; }
    # 存量同样校验上界, 已被污染的 store 下次读取即自愈
    if read -r sh5 sr5 sd7 sr7 < "$RL_STORE" 2>/dev/null \
       && [[ "${sh5:-}" =~ ^[0-9]+$ && "${sr5:-}" =~ ^[0-9]+$ \
          && "${sd7:-}" =~ ^[0-9]+$ && "${sr7:-}" =~ ^[0-9]+$ ]] \
       && (( sr5 <= maxr5 && sr7 <= maxr7 )); then
      if   (( r5 <  sr5 ));                  then h5=$sh5; r5=$sr5   # 本 session 停在旧窗口
      elif (( r5 == sr5 )) && (( sh5 > h5 )); then h5=$sh5           # 同窗口, 别人看到的更多
      fi
      if   (( r7 <  sr7 ));                  then d7=$sd7; r7=$sr7
      elif (( r7 == sr7 )) && (( sd7 > d7 )); then d7=$sd7
      fi
    fi
    printf '%s %s %s %s\n' "$h5" "$r5" "$d7" "$r7" > "$RL_STORE.tmp" 2>/dev/null \
      && mv -f "$RL_STORE.tmp" "$RL_STORE" 2>/dev/null
    echo "$h5 $r5 $d7 $r7"
  ) 9>"$RL_STORE.lock" 2>/dev/null || echo "$h5 $r5 $d7 $r7"
}

# 用量快照: 优先取 stdin JSON 的 context_window.current_usage,
# 缺失时回退到 transcript 最后一条带 usage 的消息
in_tok=0; rd_tok=0; wr_tok=0
usage=$(printf '%s' "$input" | jq -c '.context_window.current_usage // empty' 2>/dev/null)
if [[ -z "$usage" && -n "$transcript" && -f "$transcript" ]]; then
  usage=$(tac "$transcript" 2>/dev/null | grep -m1 '"usage"' || true)
  usage=$(printf '%s' "$usage" | jq -c '.message.usage // empty' 2>/dev/null)
fi
total=0
if [[ -n "$usage" && "$usage" != "null" ]]; then
  read -r in_tok rd_tok wr_tok <<< "$(printf '%s' "$usage" | jq -r '
    [ (.input_tokens // 0),
      (.cache_read_input_tokens // 0),
      (.cache_creation_input_tokens // 0) ] | @tsv' 2>/dev/null)"
  total=$(( in_tok + rd_tok + wr_tok ))
fi

# ---- 行1: 身份 ----
line1="$model_name"
if [[ -n "$effort_level" ]]; then
  line1="$line1    effort $effort_level"
fi
if [[ -n "$worktree_name" ]]; then
  line1="$line1    wt $worktree_name"
fi

# ---- 行2: 用量 ----
if (( total > 0 )); then
  ctx=$(( total * 100 / 1000000 ))
  hit=$(( rd_tok * 100 / total ))
  line2="ctx ${ctx}%    cache ${hit}% ($(fmt_tok "$rd_tok")/$(fmt_tok "$total"))"
else
  line2="ctx --"
fi

# 额度窗口（claude.ai 订阅账号才有 rate_limits）
# 百分比取整（服务端可能返回 14.000000000000002 这类浮点值）
read -r h5_pct h5_reset d7_pct d7_reset <<< "$(printf '%s' "$input" | jq -r '
  def i: if type=="number" then round else . end;
  [ (.rate_limits.five_hour.used_percentage // "" | i),
    (.rate_limits.five_hour.resets_at       // "" | i),
    (.rate_limits.seven_day.used_percentage // "" | i),
    (.rate_limits.seven_day.resets_at       // "" | i) ] | @tsv' 2>/dev/null)"
# 四元组齐全才参与跨 session 同步; 缺任一项(如 API key 用户无 rate_limits)则原样显示
if [[ "${h5_pct:-}" =~ ^[0-9]+$ && "${h5_reset:-}" =~ ^[0-9]+$ \
   && "${d7_pct:-}" =~ ^[0-9]+$ && "${d7_reset:-}" =~ ^[0-9]+$ ]]; then
  read -r h5_pct h5_reset d7_pct d7_reset <<< "$(sync_rate_limits "$h5_pct" "$h5_reset" "$d7_pct" "$d7_reset")"
fi
if [[ -n "${h5_pct:-}" ]]; then
  now=$(date +%s)
  seg="5h ${h5_pct}%"
  [[ "${h5_reset:-}" =~ ^[0-9]+$ ]] && seg="$seg ↻$(fmt_eta $(( h5_reset - now )))"
  line2="$line2    $seg"
  if [[ -n "${d7_pct:-}" ]]; then
    seg7="7d ${d7_pct}%"
    [[ "${d7_reset:-}" =~ ^[0-9]+$ ]] && seg7="$seg7 ↻$(fmt_eta $(( d7_reset - now )))"
    line2="$line2    $seg7"
  fi
fi

printf '%s\n%s' "$line1" "$line2"
STATUSLINE_EOF
chmod +x "$DEST"
bash -n "$DEST" || { echo "生成的 statusline.sh 语法错误，中止"; exit 1; }

python3 - "$SETTINGS" "$DEST" <<'PY'
import collections, json, os, sys
p, dest = sys.argv[1], sys.argv[2]
d = json.load(open(p), object_pairs_hook=collections.OrderedDict) if os.path.exists(p) else collections.OrderedDict()
d['statusLine'] = {'type': 'command', 'command': dest, 'refreshInterval': 60}
json.dump(d, open(p, 'w'), ensure_ascii=False, indent=2)
open(p, 'a').write('\n')
print('settings.json 已写入 statusLine（refreshInterval=60）')
PY

echo "完成。热生效，无需重启 Claude Code。"
