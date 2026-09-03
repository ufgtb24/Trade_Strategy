# ② 区分度试验 · 预注册设计（2026-08-16，跑前锁定，事后不改）

## 决策问题

实盘在 bb 买点确认时拿到 news_score，是否应据此改变交易动作（负向放弃买点）？
试验结果直接作为「是否在实盘交易时使用情感分析」的依据。

## 样本（无拟合参数）

bb_v1 eval（`outputs/path2_eval/bb_v1_eval_20260810-235006.json`，主目录）210 行中
buy_date ≥ 动态标定边界（2026-08-16 标定值 2025-09-07，滚动 12 个月窗口内）的全部行，
预计 ~112 行。每行独立评分（同 symbol 不同 buy_date = 不同窗口不同评分）。

## 分组（跑前定死，不再改切法）

| 组 | 定义 |
|---|---|
| G_neg | score < -0.15（闸的杀除对象） |
| G_mid | -0.15 ≤ score ≤ 0.15 且有覆盖 |
| G_pos | score > 0.15 |
| G_nocov | total_count = 0（无新闻覆盖；混杂对照组） |

## 主指标（用户裁定纪律）

- **FPR_k6**：首次穿越率，几何对称阈值（上 P(1+kM)/下 P/(1+kM)，M=rolling_atr_pct_nanmedian(h,l,c,20) 的 M[t]），
  k=6 主口径，组级 ratio = Σup/(Σup+Σdown)（none/both 剔除）；实现直调 `path2.eval._first_passage_at`，
  买点锚 t = buy_date 行号（与 fr/mfr 口径同锚）。
- **fr median**：fr = forward_return = mfr_high 口径（max(high[t+1..t+40])/close[t]−1），
  重算并与 eval JSON `returns["40"]` 对齐校验（容差 1e-9）。
- win_rate 废弃（基率复读）。

稳健性附检（非主判据）：k=4、k=5 的 FPR 方向是否与 k=6 一致。

## 统计与判定（预注册）

- 组间点估计 + bootstrap 95% CI（percentile，10k 重采样）；不报 p 值。
- 先看 G_nocov vs (G_neg∪G_mid∪G_pos) 的 fr/FPR（覆盖性混杂检查）。
- **作用面上限**：闸对全体的影响上限 = p_neg × (G_rest − G_neg) 指标差；若 p_neg < 5%，
  无论组间差多大，全体指标变化 <5%×Δ——实盘期望价值上界受限。
- **接入实盘判据（同时满足）**：① G_neg vs G_rest 的 fr median 差 CI 不跨 0；
  ② FPR_k6 差方向一致（G_neg 更低）；③ p_neg ≥ 5%。任一不满足 → 不接入，
  结论记录为「样本增长后可复验」或「证伪」。

## 已知 limitation（报告必载）

样本期 2025-09..12 单一市场环境；score 由 deepseek-v4-flash 产出（版本漂移不可控）；
新闻源滚动覆盖（复验时样本会变）；负向组预期很小（30 票 pilot 中 1/19），
FPR 组级比率在 G_neg<10 时功效极低——依赖作用面上限框架给结论。
