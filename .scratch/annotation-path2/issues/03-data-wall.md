# 2026 年以后的数据：哪些地方必须挡、哪些地方本来就该读

Type: grilling
Status: open

## Question

### Purpose

整套流程的判决只在 2026 年起的数据上做一次，这道墙一漏，判决就不再诚实，这张票定墙立在哪里。

现状（方向文档第 9 节）：path2_web 的看图、诊断、扫描经 `chart_workflow/loader.py` 读截到 2025-12-31 的副本；`path2_web/eval_runner.py`、`scripts/path2/path2_eval_scan.py`、`scripts/path2/scan-wide.py` 和 tune-gates-v3 直接读完整的 `datasets/pkls`（全部 5778 只都有 2026 年数据）。新流程里的每个环节（标注、写 app、对标注、盲看清单、调参数、最后检查、循环技能、会话里临时跑的分析）各该读哪份数据，挡的办法是什么，哪些环节按设计就该读 2026 年（只有最后检查）以及它怎么只在那一步读到。
