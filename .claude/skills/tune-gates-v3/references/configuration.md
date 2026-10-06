# 配置与命令契约

由 agent 根据实际数据、参数机制和授权准备，不让用户填写参数表。所有项目内路径相对运行时仓库根；共享行情目录沿用项目指定绝对路径。脚本依赖项目现有 numpy、pandas、Optuna、pandas-market-calendars。

## 配置结构

下面日期仅说明字段关系，**不是已获许可的数据区间**。agent 查实际覆盖、现役参数及全部关联使用记录后再生成配置；没有完整未来就等待。

```json
{
  "app": "bottom_burst",
  "data_dir": "/home/yu/PycharmProjects/Trade_Strategy/datasets/pkls",
  "train": {"start": "2024-07-01", "end": "2025-10-31", "label_end": "2025-12-31"},
  "final": {"start": "2027-01-04", "end": "2027-06-30", "label_end": "2027-08-31"},
  "review": {"start": "2028-01-03", "end": "2028-06-30", "label_end": "2028-08-31"},
  "space": {
    "tb.max_rise_k": {"type": "float", "low": 1.0, "high": 2.0},
    "tb.max_span": {"type": "int", "low": 40, "high": 80},
    "tb.anchor_mode": {"type": "categorical", "choices": ["last_bo", "min_bo", "span_min"]}
  },
  "relations": [],
  "parameter_notes": {
    "tb.max_rise_k": "示例：改变反弹幅度容忍，正式范围按机制核对",
    "tb.max_span": "示例：改变检测预算与对应边界",
    "tb.anchor_mode": "示例：改变底部取法，不是单纯松紧"
  },
  "causality_note": "替换为本次买点、祖先、边与where当日可知性的实际核对依据",
  "search": {"trials": 80, "seed": 42},
  "policy": {}
}
```

省略的字段取默认：

- `symbols` 省略（或写 `"all"`）即数据目录下全部股票：名字合法的 `.pkl/.pickle` 文件，展开成列表写进冻结配置。显式列表仍可用，但全部股票是信息量最大的默认。
- 各阶段 `history_start` 省略即自动推算：交易日历上 start 往前「搜索范围内最长回看 + 5」个交易日（待验证）。最长回看取波动尺度窗口、两份对照、以及每个搜索维度单独取到下界/上界/各类别时 `eval_meta` 给出的首部缓冲中的最大值。显式给出时不得少于这个交易日数，否则在读任何数据前报错并写出所需天数。
- `evaluation` 默认 `{"horizon": 40, "k": 5.0}`；`windows` 默认 `{"window_days": 21, "half_life_days": 252, "recent_days": 126}`；`shrinkage` 默认 `{"enabled": true, "tau": 0.1, "bandwidth": 80}`。
- `baseline_params` 省略即冻结 `load_params().to_dict()`；显式给出时必须与现役完整快照完全一致。`bo_params` 省略时，app 有 bo 段就冻结该段构造简单突破，没有就冻结 bo_only 现役完整参数；显式给出会规范化成完整快照。

采用规则固定，配置里出现 `adoption` 会被拒绝。

## 时间与读取范围

- `history_start` 是允许特征回看的最早日，`start/end` 是可产生买点的闭区间，`label_end` 是允许未来标签使用的最后日。必须 `history_start <= start <= end < label_end`。
- 账本按 history_start 至 label_end 保护实际暴露范围。训练 label_end 早于最后检查 history_start；最后检查 label_end 早于复核 history_start。自动推算的回看起点与上一阶段重叠时，报错里写出推算出的回看起点，把后一阶段往后挪即可。
- label_end 须覆盖 end 后至少 H 个交易日，买点日历须至少容纳一个完整评分窗口。行情到齐按整体比例判，规则见 [method.md](method.md#逐日标签)。
- 可显式提供有序唯一 ISO `calendar`；省略则由 NYSE 日历生成 1950 年至复核 label_end，不读价格。其他市场自行给正确日历。
- 标签、股票池、窗口与参数范围第一次看分前固定。

## 搜索范围与要求

float 不传 step 表示连续建议；int 可给整数 step；categorical 给 choices。范围必须含现役值；结构参数按改变的识别含义定范围。log 分布必须满足正值和 step 兼容条件。

`relations` 支持 left/op/right 或 left/op/value（字段路径或常量），只表达代码真实需要的合法关系，须包含现役组合。

`policy` 支持以下键，未知值拒绝：

```json
{
  "min_reference_fraction": 0.5,
  "min_recent_reference_fraction": 0.5,
  "min_median_upside": null,
  "min_median_drawdown": null
}
```

两条比例是相对原参数的机会下限（总买点数、最近 126 交易日买点数），取值 0~1，可相等。`min_median_upside` 是买点前瞻收益中位数下限，`min_median_drawdown` 是盘中回撤中位数下限（负数，−0.2 表示中位数不比 −20% 更差）；未设置就只报告。旧键 `min_buy_days`、`min_recent_buy_days`、`min_direction_score`、`baseline_tolerance` 已删除，出现即报错：机会只用相对原参数的下限，方向不设绝对下限。默认值是工程起点，不代表资金需求或统计证据已充分。

## 统计折扣：关闭写法与含义

统计折扣默认开启，排名分为「只给正的领先打折」的 `min(Δ, λΔ)`。关闭写：

```json
"shrinkage": {"enabled": false}
```

关闭后排名分为不打折的领先 Δ，证据厚薄不再影响排名。只在方法开发对照、或已知合成数据每个窗口的领先恒定（误差不可识别）时关闭。

- enabled 必须是布尔值。tau 是预先固定的差异尺度，须为有限正数且平方可表示；相同误差下较大 tau 保留更多领先。bandwidth 为非负整数，按连续窗口起点相隔的交易日数计，0 表示不纳入相邻起点相关项。
- 开关、tau、bandwidth 在配置中冻结，不作为 Optuna 搜索变量；各阶段按各自数据计算折扣比例。
- 公式与退化规则见 [method.md](method.md#排名分与统计折扣)。

## 输出与接口

配置建议放 `outputs/tune_gates_v3/<app>/<轮次>-input.json`，每轮独立运行目录。

| 产物 | 含义 |
|---|---|
| config.json | 实际完整配置、源码摘要、git 提交与是否干净、运行身份，带内容摘要 |
| study.sqlite3 | 全部尝试、排名分、方向成绩、折扣详情及约束；非精确续跑快照 |
| reference.json | 原参数的评价（含要求） |
| bo.json | 固定 bo 的汇总（方向成绩及两种对照的差） |
| noise.json | 原参数按股票整只重抽的偶然波动 |
| reference-days.csv / candidate-days.csv / bo-days.csv | 训练逐日结果，含前瞻收益、三态、兼容 both=0、M、回撤 |
| manifest.json | 唯一候选、新旧完整参数、评分模式、同模式比较、偶然波动、是否值得检查 |
| final.json / review.json | 一次最后检查或复核及采用状态 |
| final-*.csv / review-*.csv | 对应已获许可阶段的逐日结果 |

训练无结果时不打开留出数据。最后检查无结果则不采用；程序错误保留已记消费，报告未完成。

`daily.DailyEvaluator` 管固定许可范围的日标签及检测缓存，`check_ready` 只读文件末日检查行情到齐，`evaluate_control` 共用标签算固定对照。`scoring.WindowPlan/assess/comparison` 只算给定日表，不读股价、不搜索；`window_statistics` 与 `stock_bootstrap` 供方法开发核查。`governance.UsageLedger` 管使用记录，正式搜索用 reserve+claim，纯开发用 claim_development，二者同账本。
