# 两台机器的环境准备与首次往返（V-SYNC-1）

Status: ready-for-human
Progress: not-started
Blocked by: 05

## Purpose

让 upc 上也能标注，并且确认两台机器的标注和 K 线确实一致。

## Source

- [spec](../annotation-path2/spec.md) 的这几处：1.7；5.9；第 7 节 V-SYNC-1；第 13 节「upc」「一次性准备」。
- 决策：[数据和标注在两台机器之间同步](../annotation-path2/issues/07-two-machine-sync.md)的 Answer。
- 前置交付：[05](05-boxes-and-vocabulary.md)。第 1～3 步只要 [01](01-snapshot-fingerprint-and-annotation-dir.md) 完成就能做；第 4 步要用 05 的界面。

## Inherited Direction

- **cc 不碰用户的环境配置**（Syncthing、upc），由用户自己做，或者由用户在 upc 上开的 cc 会话来做。
- **upc 上的旧标注，删之前先列出来请用户确认**（用户 11-03）。
- **副本以 pc 那份为准，一次性拷到 upc**，不在 upc 上重新生成（spec 1.7）。

## What to build（人手步骤）

1. **Syncthing**：让 pc 和 upc 共享主目录下的 `annotations/`，打开文件版本保留。
   - 自测：在 pc 的 `annotations/` 里放一个临时文件，等它出现在 upc 上之后删掉。
2. **训练段副本**：把 pc 的 `datasets/pkls_until_20251231/`（含 01 写的指纹清单）拷到 upc。upc 上的旧副本先改名留底，确认无误后再删。
   - 自测：两台各跑一次 01 完成记录里给出的读指纹命令，输出相同。
3. **upc 上的旧标注**：在 upc 上开 cc，让它列出旧看图工具留下的文件（至少包括 `outputs/chart_workflow/` 下没进 git 的文件）。用户确认后再删。
4. **首次往返**：
   - 在 upc 上拉取已经合进 01～05 的 `annotation-path2`，运行 `uv sync`，启动网页，标一个框；
   - 等 Syncthing 同步完，在 pc 上刷新，看三件事：框在不在，有没有冲突提示，有没有指纹不符的提示。

## Blocked by

05

## Acceptance criteria

- V-SYNC-1 按 spec 第 7 节判：
  - pc 重放出的状态和 upc 一致，两边指纹相同，没有冲突提示；
  - 如果有冲突，提示要能说清是哪个对象。
- 结果记进 `evidence/12/`。
- 本票由用户亲自做：它要另一台机器、Syncthing 和人工操作。

## Validation responsibility

本票收口 V-SYNC-1。
