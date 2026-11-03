# 训练段副本指纹与标注目录的准备

Status: ready-for-agent
Progress: in-progress
Claimed: 2026-11-03 parallel-tickets ticket-01 @ worktree impl/01-snapshot-fingerprint-and-annotation-dir
Blocked by: none

## Purpose

两台机器的标注要能确认看的是同一根 K 线。本票给训练段副本一个可以核对的指纹，并把标注目录、机器名这些存放的前提备好。

## Source

- [spec](../annotation-path2/spec.md) 的这几处：5.9「存放位置」「数据指纹」「训练段副本」；第 8 节「配置」「训练段副本」；1.7 第 1、2 条；第 10 节「标注目录」「训练段副本」两行。
- 决策：[数据和标注在两台机器之间同步](../annotation-path2/issues/07-two-machine-sync.md)的 Answer。
- 共用执行边界与验证责任：[拆分总览](../ticket-breakdown.md)。

## Inherited Direction

- 共用执行边界第 1～9 条。
- **副本以 pc 2026-11-02 生成的那份为准，不随行情下载更新**（spec 1.7）。防的是：两台机器的标注互相打开时，看到的 K 线不一样。所以本票**不能为了写指纹而重新生成副本**。
- 指纹清单不算登记、不记账（spec 5.9）。
- 标注目录放在 git 之外（票 07）。防的是：切换分支、合并时把用户的标注改掉。

## What to build

- `scripts/data/make_train_snapshot.py` 生成副本时，按文件名和内容算哈希，在副本目录里写一个指纹清单文件。清单的文件名不能让它被当成股票。
- 另给一个办法：只为已有的副本补写指纹清单，不动任何数据文件。参数声明在入口 `main()` 开头，不用 argparse（CLAUDE.md「入口脚本」）。
- 一个读指纹的函数，供 02 和界面使用。副本里没有清单时，明确报出来。
- 在 `configs/path2_web.yaml` 和 `path2_web/config.py` 里加两个配置：标注目录，默认是主目录下的 `annotations/`；机器名，默认取主机名。
- `.gitignore` 加 `/annotations/`；`.worktree-prep` 加 `link annotations`；在主目录建一个空的 `annotations/`。
- 为 pc 上现有的副本 `datasets/pkls_until_20251231` 补写指纹清单。这是写共享数据，完成记录里写明。

## Scope and exclusions

- 不重新生成副本，不改任何 pkl，不碰 `datasets/pkls`。
- 不配 Syncthing，不碰 upc，这些在票 12。

## Blocked by

none

## Acceptance criteria

- 同一个目录算两次，指纹相同。改动任一数据文件的一个字节，或者增删一个文件，指纹都变。用临时目录测。
- 为现有副本补写清单前后，全部 pkl 的内容哈希逐一不变。证据是前后两份哈希清单，diff 为空，放进 `evidence/01/`。
- 股票列表和 `read_bars` 都不会把指纹清单当成股票。要有测试。
- 新开一个 worktree 跑完准备脚本后，`annotations` 是指向主目录的软链；`git status` 里不出现 `annotations/` 下的文件。
- 配置缺省时，读到的是默认标注目录和主机名；在配置里改了，读到的是改后的值。
- 完成记录写明读指纹的命令。票 12 让用户在两台机器上用它自测。
- 无人审：全部可机检。

## Validation responsibility

为 V-SYNC-1 提供指纹，由 12 收口（spec 第 7 节「两台机器」）。
