---
title: 用 syncthing 跨机同步 Claude Code chat history
scope: 跨机同步 ~/.claude/projects/（Claude Code chat jsonl + memory）的全套方案——syncthing 版本/channel 选择、folder 关键配置、conflict 处理、桌面 indicator（GNOME extension on Edge）安装与兼容 patch。承载"chat history 跨机持久化"主题的所有踩坑细节。
category: chat-sync
---

# 用 syncthing 跨机同步 Claude Code chat history

跨机同步的对象是 `~/.claude/projects/<encoded>/`，里面是 chat `<UUID>.jsonl` + `memory/*.md`。两台机器 PWD 完全一致（如都 `/home/yu/PycharmProjects/XXX`）时 encoded 一致，直接同步整个 `~/.claude/projects/` 就行，不需要 symlink/抽象层。

## 一键安装：桌面 indicator（Edge 路径）

四步流程：[自动] 装 bridge → [手动] 浏览器装 extension → [自动] v2 patch → [手动] 重启 GNOME Shell。每段为什么这么做，看下面的踩坑分论点。

### Step 1（自动）：装 chrome-gnome-shell + symlink 到 Edge

```bash
sudo apt install -y chrome-gnome-shell
MANIFEST=$(find /etc/chromium /etc/opt /usr/lib -name 'org.gnome.chrome_gnome_shell.json' 2>/dev/null | head -1)
sudo mkdir -p /etc/opt/edge/native-messaging-hosts
sudo ln -sf "$MANIFEST" /etc/opt/edge/native-messaging-hosts/org.gnome.chrome_gnome_shell.json
```

### Step 2（手动）：浏览器三件套

1. **完全关闭 Edge 所有窗口再重开**（关键：扩展启动时才加载 native host）
2. Edge 打开 Chrome Web Store 装 `GNOME Shell integration`：
   `https://chromewebstore.google.com/detail/gnome-shell-integration/gphhapmejobijbbhgpjhcjognlahblep`
   首次会弹 "允许 Chrome Web Store 扩展" → 允许
3. Edge 打开 `https://extensions.gnome.org/extension/1070/syncthing-indicator/` → OFF/ON 开关拨到 ON

### Step 3（自动）：syncthing v2 兼容 patch

```bash
bash "$(git rev-parse --show-toplevel)/docs/cc_notes/chat-sync-patch-indicator-v2.sh"
```

把 extension 里 `syncthing --paths` 改成 v2 语法 `syncthing paths`，自带备份和幂等检查。前置：Step 2 已装好 extension。

### Step 4（手动）：重启 GNOME Shell

按 **Alt+F2** → 输 `r` → 回车（X11 才能这样；Wayland 要 logout+login）。

顶栏出现灰色圆形小图标 = 成功。点开菜单看每个 folder/device 右下角的小绿对勾。

## syncthing channel 选择

apt repo 有两个 channel：

```
stable      ← v1 系列（旧，2025 年的末班车 v1.30）
stable-v2   ← v2 系列（用这个，2026 年起）
```

`/etc/apt/sources.list.d/syncthing.list` 用 `stable-v2`：

```
deb [signed-by=/etc/apt/keyrings/syncthing-archive-keyring.gpg] https://apt.syncthing.net/ syncthing stable-v2
```

- 作用：v2 把内部数据库从 LevelDB 换成 SQLite，性能改进；config.xml 完全向后兼容
- 生效：apt update + apt install 升级；首次启动自动迁移数据库
- 注意：**v1 → v2 单向**，升完不能回退

## folder 关键配置

针对 `~/.claude/projects/` 的 syncthing folder：

| 字段 | 值 | 作用 |
|---|---|---|
| Folder Type | Send & Receive | 双向同步 |
| Ignore Permissions | ON | chat 目录是 `drwx------` 700，跨机权限保险 |
| File Versioning | Trash Can / 30 天 | 被覆盖的旧版本进 `.stversions/` 兜底 |
| Max Conflicts | 0 | 新覆盖旧、不生成 `.sync-conflict-*` 副本，靠 Versioning 兜底 |

**踩坑**：folder 级配置（maxConflicts / Ignore Permissions / Versioning）**不跨机同步**——每台机器必须单独设。如果一台 maxConflicts=10、另一台=0，前者生成的副本会被同步给后者，看起来像"我已经设 0 了还在冒副本"。

`maxConflicts` 在 v2 Web UI 的 folder 编辑面板**没有暴露**，要从右上角 `Actions → Advanced → Folders → claude-projects → Max Conflicts` 进去改；或者直接编辑 `~/.config/syncthing/config.xml`。

## 问题：folder ID 被输入法污染

GNOME 桌面 + 中文输入法时，Web UI 输入 Folder ID 偶尔会被插入不可见字符（保存到 config 时变成 U+FFFD 替换字符）。两台机器 ID 必须字节级一致，否则配不上。

检测：

```bash
grep -oE 'id="[^"]+"' ~/.config/syncthing/config.xml
# 看到 id="claude-projects������..." 就是中招
od -c <(grep -oE 'id="[^"]+"' ~/.config/syncthing/config.xml) | grep '357 277 275'
# UTF-8 编码的 U+FFFD = \357\277\275，连续出现就是污染
```

修复（停 service → Python 清字符 → 启 service）：

```python
import re
p = '/home/yu/.config/syncthing/config.xml'
s = open(p, 'r', encoding='utf-8').read()
s = re.sub(r'(claude-projects)[�]+', r'\1', s)
open(p, 'w', encoding='utf-8').write(s)
```

预防：输 ID 时切英文输入法 / 从纯文本来源复制粘贴。

## conflict 副本机制

文件名格式：`<原名>.sync-conflict-<DATE>-<TIME>-<DeviceID 前7位>.<ext>`

后缀的 DeviceID 是 **败方（mtime 较旧的版本）的 last modifier**：

- `xxx.sync-conflict-...-FXQJQTG.md` = 对端的旧版本被改名为副本（主文件 = 本机的新版本胜出）
- `xxx.sync-conflict-...-SHYKWOH.md` = 本机的旧版本被改名为副本（主文件 = 对端的新版本胜出）

清理策略：

1. **先备份**所有副本到 `~/syncthing-conflicts-backup-<date>/`（保留路径结构）：

```bash
BACKUP=~/syncthing-conflicts-backup-$(date +%F)
mkdir -p "$BACKUP"
cd ~/.claude/projects
find . -name '*.sync-conflict-*' -print0 | while IFS= read -r -d '' c; do
  mkdir -p "$BACKUP/$(dirname "$c")"
  cp "$c" "$BACKUP/$c"
done
```

2. **memory `*.md`**：是用户长期记忆，必须人工裁决保留谁的版本（diff 看哪边内容更全）
3. **chat `*.jsonl`**：append-only，主文件（行数多）几乎一定是副本（行数少）的 superset，直接 `find ... -delete` 删副本即可

## 桌面 indicator（GNOME 顶栏图标）

走 Edge 浏览器 + extensions.gnome.org 路径装 `Syncthing Indicator` (by 2nv2u)，因为：

### 问题：Extension Manager 启动后秒退

Ubuntu 22.04 apt 包 `gnome-shell-extension-manager 0.3.0` 在 `libsoup-3.0.so.0.0.5` 里 segfault。

```bash
dmesg | grep extension-manag
# extension-manag[xxxxx]: segfault at ... in libsoup-3.0.so.0.0.5
```

绕过：不修它，改走浏览器路径（不依赖 Extension Manager）。

### 问题：Edge 装了 GNOME Shell integration 仍连不上 GNOME

`chrome-gnome-shell` apt 包只把 native messaging host manifest 装到 Chrome / Chromium 目录，不动 Edge。Linux Edge 找 manifest 的目录是 `/etc/opt/edge/native-messaging-hosts/`。

修：

```bash
sudo apt install -y chrome-gnome-shell
MANIFEST=$(find /etc/chromium /etc/opt /usr/lib -name 'org.gnome.chrome_gnome_shell.json' | head -1)
sudo mkdir -p /etc/opt/edge/native-messaging-hosts
sudo ln -sf "$MANIFEST" /etc/opt/edge/native-messaging-hosts/org.gnome.chrome_gnome_shell.json
```

完全关闭 Edge 再重开（Edge 启动时才加载 native host）。

### 问题：装完顶栏图标显示红 X

extension 用 `syncthing --paths` 获取 config 路径；**syncthing v2 把这个改成了子命令 `syncthing paths`**（去掉 `--`）。extension 拿不到 config 路径 → API key 为空 → 连不上 syncthing。

patch（`~/.local/share/gnome-shell/extensions/syncthing@gnome.2nv2u.com/syncthing.js`）：

```bash
sed -i "s/'syncthing', '--paths'/'syncthing', 'paths'/" \
  ~/.local/share/gnome-shell/extensions/syncthing@gnome.2nv2u.com/syncthing.js
```

生效：`Alt+F2 → 输 r → 回车` 重启 GNOME Shell（X11 才能这样；Wayland 要 logout+login）。

### indicator 顶栏图标颜色含义

这个 indicator 用图标颜色表示**活动度**，不是 Up to Date 状态：

| 图标 | 含义 |
|---|---|
| 灰色 | idle（包含 Up to Date——一切正常） |
| 蓝色/动画 | syncing |
| 红 X | service 停了或 API 连不上 |

绿对勾在 menu item 的图标**右下角**，很小，凑近看才能发现。
