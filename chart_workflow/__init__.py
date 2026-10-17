"""看图找规律工作流:会话反复调用的命令行工具。

一圈的做法:
  0. 每台机器一次  python -m chart_workflow.snapshot          生成截到 2025-12-31 的行情副本
  1. 找大涨段     python -m chart_workflow.bigmoves --list-id <id>          (自动记账,不算尝试)
  2. 标出形态     用户在 path2_web 的「看图工作流」模式里看清单、点买点(可多个)、标判定后发送
                  (打开清单自动记「看过」;会话在聊天里贴的图用 views record 记)
  3. 列事实       python -m chart_workflow.facts --batch <batch_id>     只用买点及以前的 K 线
  4. 写形态卡     python -m chart_workflow.shapes apply <决定.json>     每个值记来源
  5. 对照着看     python -m chart_workflow.contrast --list-id <id> (--rule <py> | --app <pid>)
                      --source <来源> --change "<改了什么>" [--blind]     (自动记账、存档规则)
  6. 收紧或放弃   改规则再跑;python -m chart_workflow.ledger show 看账本
  7. 毕业         清单 summary 里的毕业判定通过

模块分工:
  config(默认值)/ state(状态根:记账类文件唯一的家)/ loader(唯一的读数据口,只读截断副本)/
  snapshot(生成截断副本)/ securities(证券分类与图头类别)/ labels(标签口径)/ features(分组特征)/
  panel(池内股票日面板)/ dataerrors(数据错误登记与排除)/ control(同日对照与毕业判定)/
  rules(取命中)/ listfile(清单文件)/ annotations(标注批次 v1 / v2 统一读取)/
  views(看过记录)/ facts(事实表)/ oplog(操作日志)/ shapes(形态卡)/ ledger(账本)/
  bigmoves、contrast(两个出清单的命令)/ xcheck(跨源比对)。
  智能层(facts / shapes / oplog / views / state / loader / annotations)不 import 标签口径、对照、
  面板、清单模块,不读清单里的结果字段。

文件放哪:
  状态根 = 主目录(git 仓库的 main worktree)的 outputs/chart_workflow/,受 git 跟踪,在任何 worktree
  里运行都经 state.state_root() 写到这一份;里面要有标记文件 STATE_ROOT.md,找不到就报错停下,
  绝不悄悄新开空账(环境变量 CHART_WORKFLOW_STATE_ROOT 可指到临时目录,测试与冒烟用)。
  记账类文件都在状态根:annotations/(原始标注)、views.jsonl 与 viewed_lists/(看过记录)、
  facts/(事实表快照)、shapes/(形态卡)、oplog/(操作日志)、ledger.jsonl(账本)、
  rule_archive/(规则存档)。工具只写文件、不自己 commit,提交由用户做。
  可重算的产物仍随各自 worktree 的 config.root(默认 outputs/chart_workflow,不进 git):
  lists/(清单)、cache/(面板、证券名录、Nasdaq 日线缓存)、data_errors.json(数据错误登记)。

数据出错不按股票特征判定:生成清单时拿 Nasdaq 日线逐日比涨跌幅(xcheck),把两份数据不一致的
日子标在图头;用户确认后标「数据有误」。生成任何清单、计算任何统计之前,先把这些标注汇总成
data_errors.json,并排除受影响的股票日。

红线:只碰训练段(默认 2024-01-01..2025-12-31,见 config)。所有读行情的地方都经 loader 只读
截断副本(datasets/pkls_until_20251231/,带 SNAPSHOT.json),硬上限 loader.HARD_END = 2025-12-31
是代码常量;每只股票读进来再截到训练段末日;标签要求 t+H 存在,于是买点之后的观察日也不会越过
训练段末日;清单写入前再校验一遍所有日期与图窗。验证段的数据不进任何清单、图、统计或事实表。
本轮看图下界 view_floor(默认 2025-01-01,待验证):这一轮只看 2025 年,2024 年留作没看过的那年——
清单图窗起点截到下界,大涨段只取下界之后 floor_context_bars 个交易日以后的决策日,对照页的命中与
统计只给内圈年份(contrast.inner_years,默认 2025);事实表回看可以读到下界之前,但只以数字出现。

默认值全部集中在 config.py 的 DEFAULTS,可由 configs/chart_workflow.yaml 覆盖;
标「待验证」的数值都是先取的默认值。
"""
