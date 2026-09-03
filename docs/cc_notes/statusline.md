---
title: 自定义 statusline（多行布局 / 额度窗口 / 跨 session 同步）
scope: statusline 脚本的编写与配置——settings.json 的 statusLine 字段、脚本收到的 stdin JSON 契约（有哪些字段、各字段靠什么更新）、refreshInterval 的触发机制与取值权衡、多行输出、跨 session 共享状态。与 env-vars.md 互斥（那份记 CLAUDE_CODE_* 变量）。
category: settings
---

# 自定义 statusline

## 一键安装

```bash
bash "$(git rev-parse --show-toplevel)/docs/cc_notes/statusline-install.sh"
```

装两行 statusline 到 `~/.claude/statusline.sh` 并写好 `settings.json`。幂等，重复跑即升级。需要 `jq`；`flock` 缺失只影响跨 session 同步的并发安全。**热生效，不用重启 Claude Code。**

效果：

```
Opus 5    effort xhigh    wt Trade_Strategy-tune_v1
ctx 9%    cache 97% (92k/94k)    5h 47% ↻2h10m    7d 14% ↻6d15h
```

多行靠脚本输出真实换行即可，Claude Code 原样渲染，无需配置。

## settings.json 字段

```json
"statusLine": {
  "type": "command",
  "command": "/home/yu/.claude/statusline.sh",
  "refreshInterval": 60
}
```

| 字段 | 说明 |
|---|---|
| `command` | 绝对路径。所有 session 共用同一个脚本文件 |
| `padding` | 可选，左右留白 |
| `refreshInterval` | 可选，每 N 秒重跑一次。**无默认值**，不填就不启定时器；最小 1 |

## stdin JSON 字段速查

脚本从 stdin 收到一坨 JSON。顶层字段：

```
context_window  cost  cwd  effort  exceeds_200k_tokens  fast_mode  model
output_style  prompt_id  rate_limits  session_id  session_name
thinking  transcript_path  version  workspace
```

常用的几个：

| 路径 | 内容 |
|---|---|
| `.model.display_name` | `Opus 5` |
| `.effort.level` | `xhigh` / `high` / … |
| `.workspace.git_worktree`、`.worktree.name` | worktree 名 |
| `.context_window.current_usage` | `input_tokens` / `cache_read_input_tokens` / `cache_creation_input_tokens` |
| `.cost` | `total_cost_usd` / `total_duration_ms` / `total_api_duration_ms` / 增删行数 |
| `.rate_limits.five_hour` | `used_percentage` + `resets_at`（unix 秒） |
| `.rate_limits.seven_day` | 同上 |
| `.session_id` / `.session_name` | 用于区分是哪个 session 在调脚本 |

`rate_limits` 只有 claude.ai 订阅账号有，API key 用户整段缺失——脚本要能优雅省略。

`resets_at` 是**账号级绝对时间戳**，本机所有 session 拿到的值完全相同；`used_percentage` 则各 session 各不相同（见下）。

## refreshInterval：什么时候刷新

两条触发路径，最终**跑的是同一个函数、喂的是同一份内存快照**，内容上没有区别，区别只在这份快照有多新。

**事件驱动**（无需配置）。下列字段任一变化，或 `lastAssistantMessageId` 变化，触发重跑，带 300ms 防抖：

```
tokenUsage  permissionMode  vimMode  mainLoopModel
fastMode  effortValue  thinkingEnabled  prStatus
```

长任务里主力是 `tokenUsage`——每次 API 响应都变。`rate_limits` **不在**列表里，不会自己触发重绘，但它和 `tokenUsage` 同源于 API 响应，搭车一起更新。

**refreshInterval 定时器**（要填才有）。无条件每 N 秒重跑，不管数据变没变。

**窗口重置闹钟**（无需配置）。每次执行完脚本，用当前 `rate_limits` 里较早的那个 `resets_at` 排一次性刷新，到点 + 1 秒触发。所以哪怕挂一夜没人碰，窗口边界那一刻也会自动刷新一次。

### 取值怎么选

interval 唯一实际买到的东西：**让脚本自己算的量（如倒计时）在没有事件流时继续走**。`used_percentage`、`ctx%`、`cache%` 全指望不上它——那些只能等下一次 API 响应。

实测静默期（无 API 请求）连续三次定时刷新，整份 JSON 只有 `cost.total_duration_ms` 变，其余逐字段相同。

所以按**显示粒度**选：倒计时精确到分钟就填 60，填 1 只是把同一个分钟数重算 60 遍。开销 ≈ 单次脚本耗时 ÷ interval × 并发 session 数（脚本约 20–55ms，取决于起了几个 `jq`）。

不填的后果：没有事件流时倒计时**冻住**。实测撤掉 interval 后静默 110 秒，零次刷新。注意「没有事件流」不等于「空闲」——卡在一个 25 秒的长命令里同样零次刷新。

## 跨 session 同步 rate_limit

**问题**：每个 session 是独立进程、各持独立快照。A 消耗的额度不会推给 B；B 想知道，必须 B 自己发一次 API 请求。idle 的 session 数字永远停在它最后一次请求时。

实测 6 个 session 同时采样：

```
tune-tools-77   36%  (busy)      tb-simplify     21%  (idle)
本会话          36%  (busy)      tb-simplify-c0  16%  (idle)
news_sentiment  35%              tune-tools       8%  (idle 很久)
```

同一时刻 8% ~ 36%，**极差 28 个百分点**，真值是最活跃那个。interval 完全帮不上忙——重跑脚本只重算，不取新数据。

**解法**：共享文件存一份四元组，三条规则合并。不需要判断"数据新鲜度"（JSON 里没有"这份快照何时取的"字段），因为同一窗口内 `used_percentage` 单调不减，`resets_at` 又是窗口的唯一分代号：

| 上报的 `resets_at` | 动作 |
|---|---|
| 比存量**大** | 新窗口开了，整份取代（百分比跟着归零） |
| 与存量**相同** | 同代，取 max |
| 比存量**小** | 旧代上报，忽略，用存量 |

存在 `~/.claude/.statusline-ratelimit`（单行 `5h% 5h_resets_at 7d% 7d_resets_at`），`flock` + 写 tmp 后 `mv` 原子替换。**四元组整体同步**，只同步百分比的话 idle session 会拿新百分比配自己过期的 `resets_at`，倒计时算出负数。

效果（清空 store 后让 6 个真实 session 自然刷新一轮）：同步前 `{8, 16, 21, 46}` → 同步后 `{46}`。开销 +3.8ms/次。

**`resets_at` 必须校验上界**。分代规则认「更大 = 更新」，所以一个异常大的 `resets_at` 会被当成新窗口、把正确值顶掉，并**锁死到那个时刻为止**——期间所有真实上报都被判为旧代丢弃，百分比一起冻住。窗口不可能在超过一个窗口长度之后才重置，据此拒收：

```bash
now=$(date +%s); maxr5=$(( now + 18300 )); maxr7=$(( now + 605100 ))
(( r5 > maxr5 || r7 > maxr7 )) && { echo "$h5 $r5 $d7 $r7"; return; }   # 拒收异常上报
... && (( sr5 <= maxr5 && sr7 <= maxr7 )); then                          # 存量同样校验 → 已污染的 store 自愈
```

删掉 `~/.claude/.statusline-ratelimit` 只是清空数据，下一拍重建；要彻底关闭得去掉脚本里 `sync_rate_limits` 的调用。

**局限**：全部 session 都 idle 时仍偏低（谁都没发请求）；只覆盖同一台机器。要准数敲 `/usage`，它主动打接口。

## 踩坑：拿 mock 数据测脚本会污染生产 store

**症状**：状态栏和 `/usage` 对不上——百分比差几十、倒计时差几十分钟。

**原因**：脚本跑一次就会把 `rate_limits` 写进 `~/.claude/.statusline-ratelimit`。用 mock JSON 测脚本时，假数据同样经 `sync_rate_limits` 入库。若 mock 的 `resets_at` 比真实值大（`$((NOW+7000))` 这类随手写的未来时间戳很容易撞上），它被判为新代锁死 store，此后真实上报全部作废。

**两个窗口的暴露程度不同**：

- `five_hour` 百分比和倒计时一起错，一眼看出
- `seven_day` 如果 mock 的百分比恰好撞上真实值（窄区间，容易撞），**污染在百分比上完全不可见**，只有倒计时多出几小时露馅；而百分比其实已经停止更新

**规矩**：

```bash
S=~/.claude/.statusline-ratelimit
cp "$S" /tmp/store.bak            # 测之前备份
... 测试 ...
rm -f "$S" "$S".lock "$S".tmp     # 测完必须清，让真实 session 重建
```

单次 `echo mock | ~/.claude/statusline.sh` 也算测试——它一样写库。测完核对 `cat "$S"`，`resets_at` 换算成时刻应与 `/usage` 说的重置时间吻合。

## 踩坑：百分比出现 `14.000000000000002`

`used_percentage` 是浮点数，会漏出二进制误差。在 jq 层取整，别在 bash 层：

```jq
def i: if type=="number" then round else . end;
[ (.rate_limits.five_hour.used_percentage // "" | i), ... ] | @tsv
```

顺带把 `resets_at` 也套上——后面 `resets_at - $(date +%s)` 走 bash 整数算术，拿到浮点会直接报错。

## 踩坑：往 statusline 脚本里插桩调试

想知道脚本收到什么、被谁在什么时候调用，最直接的办法是在 `input=$(cat)` 之后插一行 dump：

```bash
SP=/tmp/claude-dump
sed -i "s|^input=\$(cat)\$|input=\$(cat)\nprintf '%s' \"\$input\" > $SP/in.json|" ~/.claude/statusline.sh
```

statusline 在工具调用之间就会刷新，**下一个 Bash 调用就能读到文件**，不用等用户输入。

三个坑：

1. **多行插桩不能用单行 `sed` 清理**。`printf '%s\n'` 里如果是真实换行，插进去就是两行，`sed "\|关键词|d"` 只删掉带关键词的那半行，留下未闭合引号 → 脚本语法错误、所有 session 状态栏挂掉。要么插桩只写单行，要么用 python 按完整文本块删除。清理后**必须** `bash -n` 校验。
2. **所有 session 共用同一个脚本**，插桩会收到全部 session 的调用，日志交错。只看自己的就按 `.session_id` 过滤。
3. **多进程并发 append 同一日志文件**行会交错错乱，字段可能串行。要精确统计就每个 session 写独立文件。

## 踩坑：CPU 账要乘 session 数

`refreshInterval` 写在全局 `settings.json`，所有 session 共享。整机开销 = 单 session 开销 × 并发 session 数。开 6 个窗口时是 6 倍。

## 原理：源码里的关键实现

挖自 `~/.local/share/claude/versions/<ver>`（未 strip 的 ELF，`grep -ao` 可读到 minify 后的 JS）：

```js
// 无默认值：不填就是 null，定时器根本不启动
refreshInterval: C().min(1).optional().catch(void 0)
function Q$(e){ let t=e?.refreshInterval; return t===void 0 ? null : Math.max(1,t)*1000 }
#w(){ let e=Q$(this.#t.statusLine); if(e===null) return; ... }

// 定时器回调调的就是事件驱动那个入口 → 两条路径完全同源
o = () => { this.#_(); this.#n = setTimeout(o, t) }

// 窗口重置闹钟：取两个 resets_at 中较早者，到点 + 1000ms 刷新
if (!e.aborted) this.#S(u6e(c));
```

`n6e = 300`（事件防抖 ms），`r6e = 1000`（重置缓冲 ms）。
