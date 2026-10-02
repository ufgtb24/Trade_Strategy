# v3 逐日标签与固定对照实现核对

日期：2026-10-02。范围：正式修改仅限 `.claude/skills/tune-gates-v3/scripts/daily.py` 和对应 `tests/test_daily.py`；未改 `path2/`、app 参数或正式买点定义。本报告的检查全部使用合成完整数据，没有读取市场价格文件。

## 已交付接口

- `DailyEvaluator.baseline`：本次允许日期内全部可评价股票日，一股一次生成标签；返回副本，修改不会污染缓存。
- `evaluate(changes)`：按原参数递归叠加候选参数，股票与日期去重；精确浮点参与缓存，不做取整合并。
- `evaluate_control(app_module, params)`：新增。`params` 为固定对照 app 的完整参数；复用相同标签、已加载数据和检测日期截断，不重复计算未来标签。对照有自己的买点节点和首部缓冲；缓存区分 app 和完整参数。
- 构造器新增末尾可选 `history_start`。显式提供时，在计算 M 和检测前裁至 `[history_start, label_end]`；不晚于买点 `start`。不提供表示调用方已许可输入的全部早期历史或 loader 已裁切，因此不改变本轮研究 loader 的行为。缓存键、数据摘要和结果 attrs 反映该边界。
- 构造器末尾另有可选 `required_price_end`。正式编排从冻结交易日历给出不晚于 `label_end` 的末交易日；每股实际输入必须至少更新到此日，否则标签计算前明确报股名、最新日、要求日。周末截止不要求周末虚构行情；研究默认不传，不改变既定实验的数据口径。
- 表列保留 `symbol/date/upside/up/down/both/none/M`，增加 `drawdown`。`both` 恒为零，只为表结构兼容；正式标签是先上、先下、未触线三态。

固定 bo 的口径须在实验协议中写明：`bo_only` 默认 `breakout_measure=high`，bb 当前 `breakout_measure=close`。若希望固定对照与 bb 的原始突破定义相同，应显式传入 `{"bo": baseline_params["bo"]}`；接口不会擅自选择。

## 标签口径与计算优化

买点收盘为入场价。M 沿用最近 20 根（含入场日）的 `TR/close` 中位数；上线 `close[t]*(1+k*M[t])`、下线 `close[t]/(1+k*M[t])` 在 t 固定。以后第 1 至 H 根只用收盘价判断首次方向，等于目标线也算触及。盘中双触、收盘回到线内应为未触线。先触及后再反转不改方向。

空间仍为未来 H 根最高 high / 入场 close − 1；回撤为最低 low / 入场 close − 1。二者均保留盘中信息，`drawdown` 不截成非正值。即使早期已经触线，仍要求完整 H 根未来价格，不能用短尾样本冒充完整结果。

M 使用等价的 pandas 滚动中位数，替代逐窗口 Python 回调。未来最高、最低和有效价格计数使用滚动计算，替代每个起点的 DataFrame 切片。首次穿越按未来偏移批量比较尚未触线的起点，触线后移出活动集合；不建立“起点数 × H”的完整矩阵。复杂度上界 O(NH)、额外空间 O(N)，没有加入新依赖。

## bb 因果性审计

结论：当前 bb 声明使用的字段及买点日集合没有发现依赖未来筛选的问题。完整容器尾部较晚、关闭原因后来才知道，并不等于已出现的企稳买点日需要等到尾部才能成立。此结论有下述源代码与正样本前缀测试支撑，不推广成任意 app 均无前瞻的承诺。

1. `path2/atoms/breakout.py` 的 `BODetector.detect` 按日处理；峰扫描只取 `[current_idx-total_window, current_idx)` 历史，登记、突破确认都发生在当前根。活动峰的 `price/original_price` 的确可在后来演化，但当前 bb 筛选不读取它们后来变动的价格。突破引用的峰身份、当时 drought 等不靠未来确定。
2. `BurstDetector.detect` 对每个新增突破生成一个前缀实例（`seq[head:k+1]`），`confirm_idx` 为该前缀末突破。当前 bb 的 where 只读取 first_drought、distinct_pk、max_bar_vol_ratio；第三项取该前缀已出现区间，量比基线是向后看的滚动均值并 shift(1)。没有等待整个突破簇最终结束再计算当前前缀的最大量比。
3. `ThrowbackDetectorV4` 的 anchor 只取已确认突破之前或其区间；波动尺度 `calculate_tr_median` 用到 i−1 为止。状态机当天进入 STABLE，当天成为买点。下一天 rise/weak/break 时关闭到 i−1；如果数据就截止在前一天，timeout 也包含到前一天，因此不会撤销历史买点。
4. `path2_apps/bottom_burst/dag_spec.py` 的唯一时序边只比较末突破与首段 enter 的间隔并核对 anchor；where 不读取 tb outcome、machine_outcome 或最终段尾。`eval_meta` 的买点仍为 `tb.segments`。
5. 生成固定 seed=2 的 400 根合成完整历史：当前默认参数产生 8 个买点日。对从第 21 根到第 400 根的 380 个前缀，逐次完整运行真实 bb 检测与约束求解；“完整历史买点截到此前缀”与“只读此前缀重新检测”逐一相等。另以更松的突破与 burst 要求、较短 max_span 重做同样 380 次，仍全部相等。相关测试保留在正式测试文件。

`result.attrs["causality"]` 仍写 `event-confirm-only`，因为评价器本身只负责过滤未确认买点，不会把上述对当前 bb 的审计冒充对未来所有 app 的通用证明。

## 验证结果

命令：`.venv/bin/python -m pytest .claude/skills/tune-gates-v3/tests/test_daily.py -q`

结果：36 passed，约 5.1 秒。包括收盘与盘中差异、首触先后与几何线等号、完整未来与未来无效值、三种 H 下逐值对照原 M 和标量收盘判定、精确浮点缓存、固定对照复用标签/加载次数、日期许可上下界裁切、行情未更新至要求末端时拒绝、周末截止、首部回看，以及上述 760 次正样本前缀一致性。

## 编排独立复审与修正

复审 run/governance 时合成复现了一项早期历史范围漏洞：只登记买点 start 至 label_end，但检测器可能读到 start 之前仍被旧版预留的历史。例如旧版预留 2020-01-08 至 10，开发登记 2020-01-29 至 02-28 可通过，未设下界的检测输入仍包含 01-08。没有读取真实预留数据。

按协调者要求新增上述 `history_start`，正式编排负责冻结并登记包括它在内的完整暴露范围；评价器负责在 M/检测前真正裁切。新回归测试用较早极端价格验证其既不会进入检测，也不会影响入场 M 和已许可数据摘要。不能只在报告写“未使用预留日期”而实际继续向检测器提供它们。

独立验收成员另复现：系统日期虽已超过预定截止，价格文件可能仍只更新到较早月份。单独排除缺 H 根未来的买点，会使剩余较早标签被误当成完整最终检查。按协调者要求增加 `required_price_end`，正式编排必须传冻结日历的要求末交易日；评价器在标签前验证每股已到齐，不以未触线替代缺末端，不静默缩短检查区间。该修复只针对末端未更新，不扩大到其它数据异常处理。

没有符合研究副产品登记条件的新市场发现，因此不改 `docs/feature_candidates.md`。没有遗留临时实验脚本；检查通过 shell 内联 Python 完成。
