# 没碰过的数据上的检查：沿用 tune-gates-v3，跨次计数怎么补

Type: grilling
Status: open

## Question

### Purpose

训练段随便看以后，pattern 有没有用只能靠在没碰过的数据上的检查来说明，而检查次数一多就会挑出运气，所以这张票定怎么检查、怎么记次数。

现状：tune-gates-v3 的最后检查和复核各在一个 run 里只能跑一次，读取记在 `docs/sample_usage/<app>.v3.jsonl`；但跨 run 一共查过几次没有现成统计，代码版本存在 run 的配置里而不在账本行里（见 `.claude/skills/tune-gates-v3/scripts/run.py`、`governance.py`）。要定：

- 新流程直接用 tune-gates-v3 的最后检查，还是需要别的入口；
- 每个 app（以及它的各个版本、合并出来的 pattern）一共查过几次怎么数、在哪里给用户看；
- 2026 年起的数据只有约九个月，查到第几次应提醒用户、或者应换用更晚攒下来的数据（默认值标「待验证」）。
