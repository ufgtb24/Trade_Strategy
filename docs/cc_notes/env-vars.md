---
title: Claude Code 环境变量
scope: Claude Code 进程读取的 CLAUDE_CODE_* 环境变量及其作用、生效方式、取值语义。优先记录"踩过/查过/确认过"的，不全量抄官方列表。
category: env-vars
---

# Claude Code 环境变量

> 推荐写在 `~/.claude/settings.json` 的 `env` 块里，Claude Code 启动时自动注入到自己进程。也可写在 shell 配置（`~/.bashrc` 等），效果相同但范围更广。

## CLAUDE_CODE_DISABLE_ALTERNATE_SCREEN

控制渲染模式（fullscreen vs default）。

```json
{
  "env": {
    "CLAUDE_CODE_DISABLE_ALTERNATE_SCREEN": "1"
  }
}
```

- 作用：`"1"` 关闭 fullscreen，会话留在终端原生 scrollback 里 → PyCharm terminal / tmux 等可正常上下滚动；`"0"` 恢复 fullscreen 渲染（备用屏，scrollback 不可用）
- 取值语义：**严格匹配**，`"0"` 和 `"1"` 都被识别为切换值，不是"看存在性"的 flag（已实测）
- 生效：保存后**重启 Claude Code** 才生效；当前进程已加载老配置
- 等价的运行时切换：`/tui default` 或 `/tui fullscreen`（仅本会话，不写入 settings）
- 踩坑：PyCharm terminal 装上 Claude Code 后默认看不到滚动条 → 真因就是 fullscreen 用了 alternate screen buffer

### 踩坑：后台 session 里此变量失效（滚动条又没了）

后台 session（agent view / `/bg` / `claude --bg` / `←` 打开的）**强制 fullscreen**，本变量被忽略，`/tui default` 同样无效。

fullscreen 判定优先级（从高到低，命中即短路）：

```
local-agent → 关
CLAUDE_CODE_SESSION_KIND === "bg" → 强制开   ← 原因码字面量就是 bg_forced_on
screen reader → 关
CLAUDE_CODE_DISABLE_ALTERNATE_SCREEN → 关     ← 本变量排在 bg 之后，够不着
CLAUDE_CODE_NO_FLICKER=1 → 开
tmux -CC / Windows over SSH → 关
settings.json 的 tui: default|fullscreen      ← /tui 命令也在这层，同样够不着
```

后台 session 由 supervisor spawn 时显式塞 `CLAUDE_CODE_SESSION_KIND=bg`，settings 的 env 块被继承进去也没用。`/tui` 切换用的 relaunch 还会主动 `dropEnv` 掉 `CLAUDE_CODE_NO_FLICKER` 和本变量。

后台 session 里改用这些滚动：

- 鼠标滚轮 → 走内建虚拟滚动（`CLAUDE_CODE_DISABLE_VIRTUAL_SCROLL` 关掉它、`CLAUDE_CODE_SCROLL_SPEED` 调速度）
- `Ctrl+E` → 展开完整 transcript
- 非要终端原生 scrollback：别从 agent view attach，改用 `claude --resume <session-id>` 在前台打开（此时 SESSION_KIND 不是 bg，变量恢复生效）。代价是只能读历史、不能继续驱动那个 agent，且最好等它跑完再开，避免两处同时写同一份 transcript
