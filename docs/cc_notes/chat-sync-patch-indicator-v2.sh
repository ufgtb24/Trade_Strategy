#!/bin/bash
set -e

# 修复 Syncthing Indicator (by 2nv2u) 在 syncthing v2 下拿不到 config 的问题
# 把 extension 里的 'syncthing --paths' 改成 'syncthing paths' (v2 命令语法变化)
# 幂等: 已 patched / extension 未装 / 状态异常 都安全退出

FILE=~/.local/share/gnome-shell/extensions/syncthing@gnome.2nv2u.com/syncthing.js

[ -f "$FILE" ] || { echo "extension 还没装，先去 extensions.gnome.org/extension/1070 拨 ON"; exit 1; }
grep -q "'syncthing', 'paths'" "$FILE" && { echo "已 patched, skip"; exit 0; }
grep -q "'syncthing', '--paths'" "$FILE" || { echo "extension 状态异常，手动检查 $FILE"; exit 1; }

cp "$FILE" "$FILE.bak"
sed -i "s/'syncthing', '--paths'/'syncthing', 'paths'/" "$FILE"
echo "patched: $FILE  (backup: $FILE.bak)"
