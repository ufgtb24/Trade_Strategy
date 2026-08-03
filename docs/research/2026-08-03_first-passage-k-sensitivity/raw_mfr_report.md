# bb vs bo_only 的 mfr(最大上行潜力)增量验证

> 临时实验报告 · 2026-08-03 · 脚本 `/tmp/mfr_analysis.py` · 数据 `/tmp/mfr_results.json`

## 1. 锚点与口径

- **买点锚点** = `m.node_index[end_node].start_idx`(end_node event 的 start_idx)。
  - bb → `tb` / bo_only → `bo`(scan file `per_pattern[pid].end_node`)。
- **mfr_high** = `max(high[t+1..t+N])/close[t]-1`,买点窗 `[start_idx,end_idx]` 内逐 t 取均值 → 每 match 一个值。
  - 这就是 `path2/eval.py::match_forward_returns` 本身(scan file 的 `forward_return` 字段;见 eval.py:8 / serialize.py:335 / scan.py:309 注释),**既有研究用的 forward_return 已经是 mfr high 版,不是终点值**——用户背景里"终点值"的表述是误解,本报告直接以 mfr 重测并标注此点。
- **mfr_close**(对照)= 同公式把 `high` 换 `close`(收盘实体最大值,去掉影线噪声)。
- N = label_horizon = 40。M = `rolling_atr_pct_nanmedian(20)`;M_t = 买点窗内 ATR% 的 nanmedian。
- 样本(零重跑 dag,直接从 scan file 取 match + 读 pkl 补算):**bo_only 18119 matches / 3416 sym**,**bb 168 matches / 134 sym**(bb⊆bo,bb 命中的 symbol 都有 bo match)。

## 2. 原始统计(未控制波动率)

| 对比 | 口径 | n | median | mean | q25 | q75 | q90 |
|---|---|---|---|---|---|---|---|
| **A 整体** bo_only | mfr_high | 18119 | 0.203 | 0.449 | 0.082 | 0.452 | 0.912 |
| **A 整体** bb | mfr_high | 168 | 0.374 | 0.740 | 0.127 | 0.906 | 1.447 |
| **A 整体** bb | Δmedian | | **+84.4%** | | | | |
| **A 整体** bo_only | mfr_close | 18119 | 0.152 | 0.343 | 0.045 | 0.369 | 0.755 |
| **A 整体** bb | mfr_close | 168 | 0.444 | 0.812 | 0.155 | 0.943 | 1.865 |
| **A 整体** bb | Δmedian | | **+192.5%** | | | | |

整体看 bb 大幅领先,但 bb 命中的是高波动标的池(整体 bo median 0.203 → 同池 bo 0.318),属标的池偏差,必须控制。

## 3. 控制波动率后

### B 同池(134 个 bb-symbol 内的 bo vs bb)—— 控制标的池

| 口径 | bo median | bb median | Δmedian |
|---|---|---|---|
| mfr_high | 0.318 | 0.374 | **+17.7%** |
| mfr_close | 0.232 | 0.444 | **+91.7%** |

同池后 high 版从 +84% 缩到 +18%(大部分增量是池偏差);**close 版仍 +92%,存活显著**。

### 方法 1 · M 分层(同池,再按波动率 M_t 切三档 q33=6.78% / q66=9.14%)

| 档 | n_bo / n_bb | mfr_high bo→bb | Δ | mfr_close bo→bb | Δ |
|---|---|---|---|---|---|
| 低波动 | 305 / 46 | 0.300 → 0.313 | **+4%** | 0.222 → 0.284 | **+28%** |
| 中波动 | 294 / 57 | 0.330 → 0.531 | **+61%** | 0.240 → 0.617 | **+157%** |
| 高波动 | 286 / 65 | 0.339 → 0.296 | **-13%** | 0.230 → 0.402 | **+75%** |

**high 版(影线)分裂**:低档消失、高档反转——影线维度的增量不稳定。
**close 版(实体)三档全存活**:尤其中档 +157%——收盘价持续新高的能力跨波动率稳健。

### 方法 2 · 归一化 mfr_high / M_t(单位波动的最大上行)

| scope | bo median | bb median | Δmedian |
|---|---|---|---|
| 整体 | 3.77 | 4.97 | +31.9% |
| 同池 | 4.07 | 4.97 | **+22.0%** |

归一化后 bb 单位波动的最大上行仍 +22%(与同池 mfr_high +17.7% 互证)。

## 4. 结论

**(1) bb 的 mfr 增量在控制波动率后部分存活,且维度分化明显**:
- 影线维度(mfr_high):整体 +84% 主要是池偏差,同池缩到 +18%,M 分层后分裂(低档归零、高档反转)——**不稳定**。
- 收盘实体维度(mfr_close):同池 +92%,M 分层三档全存活(+28 / +157 / +75%)——**稳健**。
- 归一化 mfr/M 同池 +22%,确认不是纯波动率幻觉。

**(2) 与 first_passage 的关系**:first_passage 有信号(大 k 下 ratio 66% 先上行)+ mfr 有信号(尤其 close 版)→ **bb 不是"先反弹但潜力平庸",而是"先反弹 + 最大上行潜力也确实更高"**,且潜力体现在收盘实体持续新高(扎实突破),而非盘中影线瞬间刺穿(噪声)。

**(3) caveat**:
- bb 仅 168 matches,分档后每档 46-65,统计噪音不小;高波动档 high 版反转可能是小样本波动也可能是真实现象(高波动股影线噪声大,bb 选点反而不优)。
- mfr 只看涨(盲区=先涨后跌回),需配合 forward_drawdown(已在 scan file)才能看完整风险——但本任务只问上行潜力,不展开。
- 既有结论"无方向优势"需修正:**那是针对 mfr_high 同池 +17% 这一量级而言的"弱优势"**;一旦看 mfr_close(实体)+92%,方向优势其实存在,只是被影线维度稀释了。
