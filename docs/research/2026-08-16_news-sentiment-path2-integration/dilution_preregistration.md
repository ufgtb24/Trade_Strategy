# ②-b 稀释事件标记区分度 · 预注册设计（2026-08-16，跑前锁定）

## 决策问题

bb 买点确认时（只读 ≤ buy_date 的信息），「买点前 30 天内该票存在 8-K item 3.02（未注册
股权出售 = 稀释）」这一硬事件标记，是否携带 fr 的增量信息、足以作为实盘否决闸？

与已判死的极性评分（experiment_discrimination_report.md）的区别：稀疏硬事件、语义法定、
不经 LLM 极性度量——上次失效分析的「残差通道」假说。

## 样本

同一批 112 行（bb_v1 eval 窗口内买点，2025-08-17 后），fr/FPR 直接复用
`repro/full_metrics_20260816-193657.json`（重算单点锚口径），不重跑。

## 标记定义（预注册，跑前定死）

- **DIL**：EDGAR submissions 中，filing_date ∈ (buy−30 天, buy_date] 且 form=8-K 且
  items 含 "3.02"。
- 附检标记（不进主判定）：items 含 "3.03"（股东权利修改，toxic preferred 常见伴随）；
  窗口稳健性 60 天 / 14 天。
- 无 CIK 映射（non-reporting OTC）票：计入 DIL=0，但单独披露其数量与 fr
  （防「无义务壳票」污染对照组）。

## 分组与主检验

- G_dil（DIL=1）vs G_nodil（DIL=0，含 nocik）
- 主检验（实盘闸语义）：fr median(G_nodil − G_dil) 的 bootstrap 95% CI（10k，seed=42）；
  FPR_k6 差同口径。主指标沿用用户纪律：FPR_k6 + fr median；win_rate 废弃。

## 判定（预注册三条件，任一不满足 → 不接入）

1. fr median 差 CI 不跨 0 且方向为 G_dil 更低；
2. FPR_k6 差方向一致（G_dil 更低）；
3. DIL 标记率 ≥ 5%（作用面上限：标记率 × Δ ≥ 有意义量级）。

## 预期与风险（跑前写明）

- 30 天窗稀释率预期 10-25%（micro-cap 融资频繁），样本量应可行；
- 风险：burst 期的票融资更活跃（公司在股价热度时增发）→ DIL 可能与「涨得猛」正相关，
  混杂方向与直觉相反；报告需附 DIL 标记 vs G_pos（新闻覆盖）的交叉表。
