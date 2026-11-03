# 训练段副本指纹与标注目录的准备

Status: ready-for-agent
Progress: done
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

## 完成记录

2026-11-03，parallel-tickets ticket-01。合并提交 47205a4（`--no-ff` 合回 `annotation-path2`），测试与审查所在提交 d78570b，合并后的树与之相同。

**做了什么**
- `path2_web/snapshot_fingerprint.py`：指纹只看副本目录下的 `*.pkl`，逐个算 sha256，再把按文件名排好序的「文件名、哈希」整体算一次 sha256。清单文件名 `FINGERPRINT.json`，不以 `.pkl` 结尾。清单里记 `schema`、`fingerprint`、`n_files`、`files`（文件名 → 哈希），内容只由数据决定，不记时间和机器。
- 读指纹：`read_fingerprint(dir)` 读清单里记的指纹；副本里没有清单时抛 `ManifestMissing`（`FileNotFoundError` 的子类），报错信息里写着怎么补写。
- `scripts/data/make_train_snapshot.py` 生成副本时，在临时目录里先写好清单，再整体换名。
- `scripts/data/snapshot_fingerprint.py`：
  - 默认只读：重算指纹，再和清单比对。退出码 0 表示一致；1 表示不一致，同时列出增、删、改的文件；2 表示没有清单。
  - `main()` 开头改成 `WRITE = True` 时，只为还没有清单的副本补写。已有清单一律不重写。
- 配置加了 `annotation_dir`（默认 `annotations`，相对 repo root）和 `machine`（默认 `null`，即取主机名），用的时候经 `path2_web.config.annotation_dir(cfg)`、`machine_name(cfg)` 解析。配置文件里存原值，因为网页改配置时会把整份写回进 git 的 yaml，存解析后的值会把本机主机名带进 git。
- 其余改动：
  - `.gitignore` 加 `/annotations`，`.worktree-prep` 加 `link annotations`；
  - 主目录建了空的 `annotations/`；
  - CLAUDE.md「共享基础设施」加一行讲 `annotations/`，「删除 worktree」那句补上 annotations 链接。

**读指纹的命令**（票 12 让用户在两台机器上自测用）：在 repo 根目录运行 `uv run python scripts/data/snapshot_fingerprint.py`。pc 现在的输出是：

```
指纹 40508e77199b91e351ea09182fe7d3b87aadb2f50c6d82f4ddb30d578cbcf559
文件 5766 个
与清单 FINGERPRINT.json 一致
```

不依赖项目代码、结果相同的算法：`cd datasets/pkls_until_20251231 && LC_ALL=C sha256sum -- *.pkl | LC_ALL=C sort -k2 | awk '{printf "%s\t%s\n", $2, $1}' | sha256sum`。

**写了共享数据**
- 在主目录的 `datasets/pkls_until_20251231/` 里新增了一个 `FINGERPRINT.json`，470814 字节，指纹同上。
- 补写前后，5766 个 pkl 的 sha256 清单 diff 为空，各文件的大小和修改时间也都没变；`SNAPSHOT.json` 没动。证据在 `evidence/01/backfill-evidence.txt`、`pkl-sha256-before.txt`、`pkl-sha256-after.txt`。
- 清单里逐个文件的哈希和 sha256sum 的结果逐一相同。
- 主目录新建了空目录 `annotations/`。

**验收**
- 「同一个目录算两次指纹相同；改一个字节、增删或改名一个文件，指纹都变」：用临时目录测，见 `tests/path2_web/test_snapshot_fingerprint.py`，通过。
- 「补写前后 pkl 哈希逐一不变」：见上一节。
- 「股票列表和 `read_bars` 都不把清单当成股票」：`test_stock_listing_skips_manifest` 测按 `*.pkl` 列股票（`path2_web/scan.py` 里的列举），`test_read_bars_does_not_read_manifest` 测 `read_bars`，都通过。
- 「新 worktree 跑完准备脚本后，`annotations` 是指向主目录的软链，`git status` 里不出现」：见 `evidence/01/worktree-prep-check.txt`。里面附了对照：规则写成带末尾斜杠时，软链会显示成 `?? annotations`。合回后在主目录里也确认它被忽略了。
- 「配置缺省读到默认目录和主机名，改了读到改后的值」：`tests/path2_web/test_config.py` 新增的四个测试通过。其中一个钉住：写回的配置里机器名仍是 `null`，路径仍是相对路径。
- 跑 `uv run pytest tests/path2_web tests/scripts`：369 个通过、2 个跳过、1 个失败。失败的是 `test_serialize_tbseg.py::test_serialize_tbseg_walked_from_container`，它直接读 `datasets/pkls/ACUT.pkl`，而本机没有这个文件，和本票无关。
- 无人审，也没有「未安排人审：」项。V-SYNC-1 要的指纹已经备好，由票 12 收口。

**和票面字面不同的地方**：`.gitignore` 写的是不带末尾斜杠的 `/annotations`，票面写的是 `/annotations/`。原因是 worktree 里的 `annotations` 是软链，带斜杠的规则只匹配真目录，软链会被 git 当成新文件。worktree 准备脚本也要求写成不带斜杠的形式。

**给后续票的接口与限制**（涉及 02、05、08、12）
- 读指纹：`from path2_web.snapshot_fingerprint import read_fingerprint, ManifestMissing`。
  - 它只读清单、不重算。所以清单还在、pkl 却被改过或拷缺了的情况，它看不出来，要靠核对命令兜底，也就是票 12 第 2 步的自测。
  - 要更强的保证，可以在进程启动时调一次 `compute_manifest` 重算，约 1 秒。
- 标注目录用 `annotation_dir(cfg)`，机器名用 `machine_name(cfg)`。
  - 机器名只许字母、数字和下划线，因为 `-` 是 spec 5.9 文件名和编号里的分隔符。pc、upc 都合格。
  - 以后哪台机器的主机名不合格，就得在配置里给它另起名字；但这份配置进 git，不能写死某台机器的名字，到时要另想办法。

**审查**：code-review 的两份报告在 `evidence/01/review-standards.txt`、`review-spec.txt`。
- 已修：
  - CLAUDE.md 和代码注释里写了还不存在的使用方，已删掉；
  - 机器名不再允许 `-` 和 `.`；
  - 给 `_file_sha256` 补了 docstring；
  - 「只读清单不重算」这个取舍写进了模块文档和本记录。
- 没改的坏味道及理由：
  - 清单用 dict、退出码用数字：清单本来就是落盘的 JSON，退出码是脚本对外的约定，再包一层类型也不会减少出错的地方。
  - 保留 `n_files`：人直接打开清单时方便看。
  - 保留 `SCHEMA`：读清单时靠它认出不是这个格式的文件。
  - `read_fingerprint` 只做转发：它是票要求的对外接口，02 和界面只需要指纹这一个值。
  - 副本路径在三处写死：沿用入口脚本的惯例，参数写死在 `main()` 开头。
  - 模块和脚本同名：有意配对，脚本就是这个模块的入口。

**共享机制与复核**：本票新增了上面的配置键、指纹模块、清单文件名，以及 `link annotations`。复核了还没开始的 02、05、08、12，条文都仍然成立，没有改动。spec 自认领以来没有变化。
