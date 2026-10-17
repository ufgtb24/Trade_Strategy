# 看图工作流的记账类文件

这个目录是看图工作流记账类文件唯一的家,受 git 跟踪。工具(`chart_workflow` 的命令行与
path2_web 的看图工作流后端)自动定位主目录(git 仓库的 main worktree)里的这个目录写入,
在任何 worktree 里运行都写到这里。工具只写文件、不自己提交,提交由用户照常做。

不要删除本文件,也不要在 worktree 里另建一个:找不到本文件时工具会报错停下,
不会悄悄新开一本空账(主目录切到没有这些文件的分支时就会出现这种情况,切回来再用)。

进 git 的(记账类,丢了无法重算):

- `annotations/`:原始标注批次
- `views.jsonl`、`viewed_lists/`:看过记录与看过的清单快照
- `facts/`:给用户看过的事实表快照
- `shapes/`:形态卡(由操作日志重算)
- `oplog/`:操作日志(形态卡的唯一真相)
- `ledger.jsonl`:账本
- `rule_archive/`:对照页用过的规则文件存档

不进 git 的(可重算的产物,随各自 worktree 的 `outputs/chart_workflow/`):清单 `lists/`、
缓存 `cache/`、数据错误登记 `data_errors.json`。
