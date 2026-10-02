# 配置与命令契约

由 agent 根据实际数据、参数机制和授权准备，不让用户填写参数表。所有项目内路径相对运行时仓库根；共享行情目录沿用项目指定绝对路径。脚本依赖项目现有 numpy、pandas、Optuna、pandas-market-calendars；不新增计算依赖。

## 配置结构

下面日期仅说明字段关系，**不是已获许可的数据区间**。agent 必须查实际覆盖、现役参数及全部关联使用记录再生成配置；没有完整未来则等待，不能直接复制例子跑验证。

```json
{
  "app": "bottom_burst",
  "symbols": ["AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META"],
  "data_dir": "/home/yu/PycharmProjects/Trade_Strategy/datasets/pkls",
  "train": {"history_start": "2024-01-01", "start": "2024-07-01", "end": "2025-10-31", "label_end": "2025-12-31"},
  "final": {"history_start": "2027-01-01", "start": "2027-07-01", "end": "2027-09-30", "label_end": "2027-12-01"},
  "review": {"history_start": "2028-01-01", "start": "2028-07-03", "end": "2028-09-29", "label_end": "2028-12-01"},
  "evaluation": {"horizon": 40, "k": 5.0},
  "windows": {"window_days": 21, "half_life_days": 252, "recent_days": 126},
  "shrinkage": {"enabled": false, "tau": 0.1, "bandwidth": 80},
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
  "policy": {},
  "adoption": {"allow_provisional": true, "review_inconclusive": "rollback"}
}
```

`baseline_params` 可省略，自动冻结 `load_params().to_dict()`；显式给出时必须与现役完整快照完全一致。`bo_params` 可省略：app有bo段时冻结该段构造简单突破，没有时冻结bo_only现役完整参数。显式bo配置会规范化成完整快照，不能随候选调整。

## 时间与读取范围

- `history_start` 是允许特征回看的最早日，`start/end` 是可产生买点的闭区间，`label_end` 是允许未来标签使用的最后日。
- 必须 `history_start <= start <= end < label_end`。省略history_start时等于start，所有回看均限于已登记阶段内部；开头回看不足的买点排除并报告。需要预热时预先显式留足历史，不自动读取更早数据。
- 账本按history_start至label_end保护实际暴露范围。训练的label_end必须早于最后验证history_start；最后验证label_end早于复核history_start。代价是各阶段可能需要额外预热期，不能偷读保留历史补足。
- label_end须覆盖end后至少H个交易日，买点日历须至少容纳一个完整评分窗口；读取每股后、标签计算前，还检查其实际末日达到冻结交易日历中label_end及之前最后交易日；过期文件直接失败，不悄悄缩成较早的一小段来评价。真实个股仍要求实际完整未来。不能用日历日数冒充交易日数。
- 可显式提供有序唯一ISO `calendar`。省略则由NYSE日历生成1950年至复核label_end，不读价格。其他市场须自行给正确日历。
- 标签、股票池、窗口与参数范围第一次看分前固定。旧 `recent_start`、`search.repeats/block_days` 已不属于本算法，输入会被拒绝，不静默解释为新口径。

## 搜索范围与要求

float不传step表示连续建议；int可给整数step；categorical给choices。范围必须含现役值；结构参数不能仅因买点变少就说它更严格。log分布必须满足正值和step兼容条件。

`relations` 支持left/op/right或left/op/value（字段路径或常量），只能表达代码真实需要的合法关系。规则须包含现役组合，未知程序错误不当成低分。

`policy` 支持以下键，未知值拒绝：

```json
{
  "min_buy_days": 30,
  "min_reference_fraction": 0.5,
  "min_recent_buy_days": 1,
  "min_recent_reference_fraction": 0.5,
  "min_direction_score": 0.0,
  "baseline_tolerance": 0.0,
  "min_median_upside": null,
  "min_median_drawdown": null
}
```

方向严格大于min_direction_score，其余下限可相等；允许低于普通对照多少由baseline_tolerance表示，默认不允许。盘中回撤为负数，下限−0.2表示该中位数不比−20%更差，不是所有交易最大损失保证。未设置空间/回撤要求就只报告，不临时用于淘汰候选。默认值是工程起点，不代表资金需求或统计证据已充分。

评价默认H20、k5；窗口默认21日、半衰252日、近期供给126日。上述示例H40是显式设置，不混用两个期限。

## 统计折扣开关

省略 `shrinkage` 或设置 `{"enabled": false}`，保持基础方向评分。启用写：

```json
"shrinkage": {"enabled": true, "tau": 0.1, "bandwidth": 80}
```

- enabled必须是真正的布尔值，不接受字符串或0/1。
- tau是预先固定的差异尺度，须为有限正数且平方可表示；相同误差下，较大tau保留更多差异。默认0.1为待验证工程值，不是实测最优。
- bandwidth为非负整数，默认80，按连续窗口起点之间相隔的交易日数计。0表示不纳入相邻起点相关项；跨度不足时只计算实际存在的项，权重分母仍按配置跨度。此值不是独立样本数量或可信保证。
- 开关、tau、bandwidth在配置中冻结，不作为Optuna搜索变量；搜索、训练入选、最后验证和复核沿用同一设置。各阶段按各自数据计算折扣比例，不能事后根据成绩换开关。
- 机会、原始方向与普通对照要求保持原口径；开启只改变排名主分，不靠折扣把原始不合格者变成合格。
- 原始Z、普通B、差异Δ、实际排名分S、误差估计V、比例lambda及状态均保留。比例不是“结论为真的概率”。当前不自动确认的边界不受开关影响。
- 没有机会仍不可评分；观察差在机器精度范围内为零时S=B；非零差但只有一个活跃窗口、差值恒定或工作误差数值不可辨别时，统一lambda=0、S=B并标明估计不可识别，不逐候选切回Z。这是明确的保守退化规则，不宣称已证明没有优势。

具体公式见 [method.md](method.md#可选的统计折扣)。开关默认关闭时不计算V，不增加相关项汇总开销。

## 输出与接口

配置建议放 `outputs/tune_gates_v3/<app>/<轮次>-input.json`，每轮独立运行目录。

| 产物 | 含义 |
|---|---|
| config.json | 实际完整配置、源码摘要、运行身份，带内容摘要 |
| study.sqlite3 | 全部尝试、所选模式分数、原始分数、折扣详情及约束；非精确续跑快照 |
| reference.json / bo.json | 原参数和固定bo的评价 |
| reference-days.csv / candidate-days.csv / bo-days.csv | 训练逐日结果，含空间、三态、兼容both=0、M、回撤 |
| manifest.json | 唯一候选、新旧完整参数、评分模式、同模式比较、是否值得验证 |
| final.json / review.json | 一次最后检查或复核及采用状态 |
| final-*.csv / review-*.csv | 对应已获许可阶段的逐日结果 |

训练无结果时不打开最终数据。最终无结果则不采用；程序错误保留已记消费，报告未完成，不伪装正常失败。只有少于一个评分窗口时不应临时缩短窗口救回结果。

`daily.DailyEvaluator` 管固定许可范围的日标签及检测缓存，`evaluate_control` 共用标签算固定对照；调用方先登记，直接注入loader不能绕过授权。`scoring.WindowPlan/assess/comparison` 只算给定日表，不读股价、不搜索；`window_statistics` 供方法开发核查。`governance.UsageLedger` 管使用记录，正式搜索用reserve+claim，纯开发用claim_development，二者同账本。

完整结果可重复只读，未完成的最终计算不得更换候选重跑并声称独立。当前证据规则未校准，只能暂用或不采用；复核仍不足撤回，不能把空的改善区间填成漂亮数字。
