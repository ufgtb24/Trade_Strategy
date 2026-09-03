# 任务背景包(teammates 共享上下文)

## 一句话任务

tb v4(post-burst 三态状态机,已实施)在 ABOS 上买点产出太晚(burst 末 257 → 段 263-267,中间 258-263 平稳期未成为买点)。用户提出两个改进方向,要求 agent team 在控制风险的基础上分析:① UP→DOWN 刚性触发是否应柔性化(震荡幅度相对 burst 涨幅可忽略时不应强制等待);② DOWN→UP(V 反弹)不产段是否合理(反弹本身是否即企稳证据、阈值是否过严、STABLE+UP 是否都该是买点)。

## 代码与文档入口(全部相对 repo root)

- 状态机实现:`path2/atoms/throwback_v4.py`(已实施;`enumerate_segments_v4` 为核心)
- 设计 spec(定稿+实施勘误):`docs/superpowers/specs/2026-08-16-tb-v4-state-machine-design.md` —— **必读 §2(状态机判据)、§9(裁决记录)、§12(验证结果)**
- 实施 plan:`docs/superpowers/plans/2026-08-16-tb-v4-state-machine.md`
- bb 接线:`path2_apps/bottom_burst/dag_spec.py`(tb node 消费 burst 流)、`params.yaml`(tb 六参数)
- 新扫描(本次案例):`outputs/path2_web/scans/20260817T142145.json`
- 旧扫描(t1 对照、66 命中、验证原型基底):`outputs/path2_web/scans/20260815T160947.json`
- 个股数据:`datasets/pkls/ABOS.pkl`(index=DatetimeIndex name='date',列 open/high/low/close/volume)
- 切窗函数:`path2_web/data.py::slice_window`(与扫描逐字一致:scan cfg 的 win_start/win_end)

## 状态机当前判据速览(以代码为准,此处仅供入门)

- 每 burst 一机,从 burst 末根(bo)后逐根扫描,预算 max_span=60
- UP:peak 更新;首根阴线(close<open)或收跌(close<close[i-1])→ DOWN(**刚性二元触发,无幅度条件**)
- DOWN:严格新低刷新 trough(计数清零);`close > trough + max_rise_k*vol(i)` 反弹臂(优先)→ UP(**不产段**);count≥stop_confirm_bars(K=1)→ STABLE 开段
- STABLE(= 买点段,段内每 bar 是 eval 样本):`close > trough + max_rise_k*vol(i)` 或 `close > peak` → rise 收段 + ratchet(global_bottom=trough);破 trough → weak 收段回 DOWN
- vol(i) = median TR over [i-14, i-1] 即时滚动中位数;max_rise_k=1.5
- 全局:close < global_bottom(burst 锚 + ratchet 抬升)→ 机器死
- 实施勘误(与 spec §2 伪代码的字面差异,以代码为准):入段=第 K 根不刷新根当根;peak 更新=UP 态逐根 + STABLE rise 收口根补记

## ABOS 案例事实(用户描述 + 识图)

- burst_254_257#0(span 254-257),机器从 258 起跑
- 258-259 缓慢上涨(UP);260 缓慢下跌(转 DOWN);261-263 附近为高位小实体震荡(识图:十字星/小阳线,量能萎缩);264 为长实体阳线、带下影线、无上影线(用户口中的「261 up」与「264(UP)」索引有出入,**以 pkl 重算为准**)
- 产出段 tb_263_267:机器在 263 后才入段
- 用户核心观察:258-263 期间**没有大幅下跌**(相对 burst 上涨幅度几乎不可察觉)——「没有巨大下降惯性需要企稳」,却被 UP→DOWN→等 K 根不刷新的链路强制等待

## 历史研究结论(分析时必须纳入,防重复踩坑)

1. **t1 召回崩塌归因**(2026-07):rise-before-confirm(没等到企稳就大涨→整 bo 判死)杀死 30.6% attempt——「等企稳」过严是历史主教训;t4 的 DOWN→UP 不判死机器正是为此
2. **2026-07 调参定案**:stop_confirm_bars 2→0 是主改动(等待期杀召回);止跌 K 线信号池「近乎装饰品」(证据条件叠加≠有效);outcome 筛选=前瞻偏差
3. **超涨派发研究**(docs/research/2026-08-11_超涨派发过滤/final_report.md):tb 层形态类量条件全证伪,唯一强信号 = tb confirm 后破位(outcome weak|break)——**破位类信号有效、「确认前更早买」类宽松化从未被正面验证过**
4. **app 优化方法论**(2026-07-25 定稿):现有 score 本质是波动率读数(R²=0.92),工作流=否决闸阵非搜索引擎;改进先过「因果可容许闸」
5. **评估纪律**:win_rate 废弃(40日max口径的基率复读,95%+ 无意义);用首次穿越率 + forward_return median;first_passage(去波动看方向)与 mfr(含波动看潜力)正交
6. **B2 去重铁律**:任何逐日收益统计按 (symbol, date) 去重(重叠日=同一物理观测,重复计数=伪复制)——重叠机器(前缀族)的样本统计必须去重
7. **tb v4 验证基线**(spec §12):UP 轮 60% 仅 1 根;83-93% 机器最终 break 死;ratchet 0 次机器 36%;t1 交集仅 11%(语义换代,t1 调参结论不可平移)

## 产出与纪律

- 各自分析文档落盘本目录(`docs/research/2026-08-17_tb-v4-buypoint-timing/`),命名自定
- **不修改正式代码**;验证用临时脚本只放 `docs/research/2026-08-17_tb-v4-buypoint-timing/repro/`
- 读文件省上下文:先 grep 定位再 Read 局部;数据实证优先局部重算(切窗对齐 scan),绝不全量重扫
- lead = main(最终 final_report.md 由 lead 汇总产出)
