"""看图找规律工作流:会话反复调用的命令行工具。

一圈的做法:
  1. 找大涨段     python -m chart_workflow.bigmoves --list-id <id>
  2. 标出形态     用户在 path2_web 的「看图工作流」模式里看清单、框形态、点买点、标正反例后发送
  3. 对照着看     python -m chart_workflow.contrast --list-id <id> (--rule <py> | --app <pid>) [--blind]
  4. 收紧或放弃   改规则再跑;每一轮用 python -m chart_workflow.ledger add 记进账本
  5. 毕业         清单 summary 里的毕业判定通过

模块分工:config(默认值)/ securities(证券分类)/ labels(标签口径)/ features(分组特征)/
panel(池内股票日面板)/ control(同日对照与毕业判定)/ rules(取命中)/ listfile(清单文件)/
bigmoves、contrast、ledger(三个命令)。

红线:只碰训练段(默认 2024-01-01..2025-12-31,见 config)。每只股票读进来先截到训练段末日;
标签要求 t+H 存在,于是买点之后的观察日也不会越过训练段末日;清单写入前再校验一遍
所有日期与图窗。验证段的数据不进任何清单、图或统计。

默认值全部集中在 config.py 的 DEFAULTS,可由 configs/chart_workflow.yaml 覆盖;
标「待验证」的数值都是先取的默认值。输出在 outputs/chart_workflow/(不受 git 管理)。
"""
