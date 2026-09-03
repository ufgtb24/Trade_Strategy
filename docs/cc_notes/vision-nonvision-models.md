---
title: 非原生识图模型的看图能力（vision.js / claude-vision-skill）
scope: 底层模型不具备原生识图能力（如 deepseek）时，让 Claude Code 通过外部 vision.js 脚本代看图片的接线方式与触发场景；含从项目 CLAUDE.md 迁出的原始指令文本
category: hooks-skills-plugins
---

# 识图能力（claude-vision-skill）

> 状态：**2026-08-23 起停用**。统一使用 opus（原生识图），此指令已从 `Trade_Strategy/CLAUDE.md` 移除，原文保留在此备查——换回 deepseek 之类无识图能力的模型时，把下面这段原样贴回 CLAUDE.md 即可。

## 贴回 CLAUDE.md 的原文

底层模型不具备原生识图能力时（如 deepseek），遇到图片**不要用 Read 工具**，改用 `vision.js`（**脚本就在本 worktree 根目录**，直接用相对路径运行，不要 cd 到其他目录）：

```
node vision.js "<图片路径>" "用中文描述这张图片"
node vision.js --url "<图片链接>" "用中文描述这张图片"
```

触发场景：

- 用户分享图片路径（本地或网络 URL）
- 消息中出现 "Saved attachments:" 并列出图片
- 用户要求分析、描述、识别图片内容

配置好之后，用户直接发图片即可自动识图，无需手动打命令。若运行报错找不到 vision.js，检查当前目录是否为本 worktree 根目录。
