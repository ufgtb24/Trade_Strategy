# ThrowbackDetectorV1 revert 段负面特征研究（final report）

**日期**：2026-08-18 · **数据**：`outputs/path2_web/scans/20260818T110622.json`（bb_v1，2025 窗口，66 股 / 80 match）· **方法**：主会话底座 + 2 个独立 subagent 交叉验证（rule-searcher / independent-eye）

---

## TL;DR

1. **坏样本 ≈ weak 样本**。80 个买点样本里 45 个 outcome=weak（企稳被下跌打破），它们 median fr 只有 0.268、FP 方向率 0.431（比随机基线 0.554 还差），把整体 median（0.525）和 FP（0.728）严重拖垮。rise 样本（33 个）median 0.987、FP 0.946。但 outcome 是 confirm 之后才发生的事，**不能**拿来做过滤（前瞻）；正当路径是用 confirm 之前的 revert 段特征去预测。
2. **你的 5 类直觉，2 强 1 中 2 弱**（三方独立分析一致）：
   - ✅ **单日大跌幅**（最强信号，AUC 0.70-0.73）、✅ **超长阴线**（AUC 0.71-0.72）；
   - ⚠️ **连续阴线**部分成立（本质是「回踩时间长」的重新表述）；
   - ❌ **超长上影线**证伪（AUC≈0.5，无信号）、❌ **大幅回撤/跌破**证伪（本池 80 样本零个跌破 burst 起点，该维度恒 0；「深度」弱反向且与大阴线共线，无独立增量）。
   - 你担心的「高价分母稀释」方向正确，但本池实测 TR 归一只比原始比例微弱占优（0.728 vs 0.723）——不敏感。
3. **最稳的量化闸：revert 段出现单日跌幅 ≥20% 则整个 tb 不产事件**。match 80→71（删的 9 个来自 9 只不同股，无集中度）：fr 全部 ≤0.31、均值 0.095、买点计数 **0 up / 12 down**（纯毒药）；median 0.5251→0.5588，FP 0.7278→0.7834。bootstrap 双指标 CI 下界为正、66 股 leave-one-out 全正、阈值 ±20% 稳定。
4. **指标天花板（诚实）**：median 最多提到 ~0.57-0.61，FP 最多 +7pt（0.80）。改善集中在 **FP（方向正确率）**而非 median（幅度）——特征判别极端差生有效（尾部 20v20 AUC 0.7），对中段样本排序弱（全样本 Spearman 仅 -0.2，边缘显著）。
5. **能力边界**：坏样本分两型。「烈度型」（BURU/ELBM/GWH 型：单日暴跌+大阴线）可事前捕捉；「阴跌型」（CATO/MYSE/ZENA 型：revert 段温和、confirm 后阴跌不止）用 revert 段特征**无解**——最差 20 个样本里任何规则最多抓 12 个，剩 8 个属于此型。

---

## 1. 背景与口径

### 1.1 任务

对 `path2_apps/bb_v1`（tb node 用 `ThrowbackDetectorV1`）的扫描结果按 r40 降序对比好坏样本，总结坏样本在「回踩下降段」的负面特征并量化为过滤闸，目标是提升 **median(fr)** 或 **FP(首次穿越率)**。

### 1.2 指标口径（与 scan 文件完全一致，已对齐）

- **fr (r40)**：tb 事件 span 内逐买点日 t 的 `max(high[t+1..t+40])/close[t]-1` 均值（label_horizon=40，样本消费窗截到 [2025-01-01, 2026-01-01]）。
- **FP**：逐买点日首次穿越四态（上行线 `P(1+5M)` vs 下行线 `P/(1+5M)`，M=rolling ATR% nanmedian(20)，k=5），**ratio = up/(up+down+both)**，none 不进分母。基线 123/169=0.7278，随机日基线 0.554。
- **基线**：n=80 match（66 股），median_fr=0.5251，FP=0.7278。

### 1.3 数据底座与对齐自检

`repro/build_samples.py` 重放扫描引擎（同切窗 win 2024-09-19..2026-03-08、同参数 p2.yaml、`build_pattern`+`dag analyze`）：

- **80/80 match 的 fr 与 scan 文件精确一致（<1e-12），median 0.5251 ✓**
- **66/66 股 FP 四态计数逐股全对 ✓**

后续所有「删除模拟」都建立在这个精确复现的底座上（重算 label 对齐法，非近似）。

### 1.4 段定义（全部 confirm 时点已知，无前瞻）

- **bo_idx** = burst 串最后一个突破根；**confirm** = tb.start_idx（企稳确认=买点窗起点）；
- **revert_idx** = bo 后第一根「阴线（c<o）或收跌（c<c_prev）」的 bar（用户定义）；
- **下跌段** = [revert_idx, confirm]；**上涨段（参照系）** = burst span [burst_start, bo_idx]。

---

## 2. 坏样本的结构

### 2.1 outcome 分组：问题主要是 weak

| outcome | n | mean fr | median fr | FP | 解读 |
|---|---|---|---|---|---|
| rise | 33 | 1.228 | 0.987 | **0.946** | 健康样本 |
| weak | 45 | 0.583 | 0.268 | **0.431** | 低于随机基线，毒药池 |
| break | 2 | 0.382 | 0.382 | 1.000 | 样本太少 |

FP 的 46 个 down 买点日高度集中：top5 match 占 19 个、top12 占 33 个，全部来自低 fr 样本。

⚠️ 「直接滤掉 weak 样本」不可行：weak 的判定发生在 confirm 之后（收盘跌破 trough 价位），按它过滤=用未来信息选样本（前瞻）。且 weak 里有 16 个 fr>median 的好样本会被误伤。**必须用事前特征**。

### 2.2 两型坏样本

- **烈度型**（可捕捉）：revert 段出现单日暴跌（≥15-20%）、超长阴线（实体 ≥1.5-2×ATR）、深回撤。代表：BURU(-0.13)、ELBM(-0.08)、GWH、YCBD、GIPR、RKDA、NVNXF。
- **阴跌型**（revert 特征无解）：revert 段温和（CATO 单日最大跌幅仅 3%、连阴 1 天），confirm 后照样阴跌不止、FP 全 down。代表：CATO、MYSE、ZENA、CNET、SSP。它们的 revert 特征与好样本几乎无差别——事前维度（burst 质量、量能、市场状态）超出本次 revert 特征范围，是后续课题。

---

## 3. 用户 5 类假设的裁决（主会话 + 2 个独立 subagent 三方一致）

AUC = P(坏样本特征值 > 好样本特征值)，坏=fr bottom20、好=top20；0.5=无信号。

| # | 假设 | 代表特征 | AUC | 裁决 |
|---|---|---|---|---|
| 1 | 超长阴线 | 最大阴线实体/ATR；实体/TR中位数 | 0.71-0.72 | ✅ **成立（最强族之一）** |
| 2 | 超长上影线 | 上影/ATR；上影/全幅 | 0.49-0.58 | ❌ **证伪** |
| 3 | 连续多日阴线 | 阴线天数 n_red；最长连阴 | 0.69 / 0.59 | ⚠️ 部分成立（n_red 与段长 ρ=0.86，大半是「回踩久」的重新表述；段长中位仅 1-2 天，纯连阴受限） |
| 4 | 短期大幅回撤/跌破 | 跌破 burst 起点天数；dd 深度 | 恒 0 / 0.63 | ❌ **基本证伪**（零样本跌破起点；深度弱反向且与大阴线共线 ρ=-0.92，无独立增量） |
| 5 | 单日超大跌幅 | (c[i-1]-c[i])/c[i-1]；/TR 中位数；/ATR | 0.69-0.73 | ✅ **成立（最强）** |

- **分母问题**：TR 中位数归一（0.728）vs 原始比例（0.723）vs ATR 归一（0.713）——你担心的「涨到高价后跌幅被分母稀释」方向正确，但本池三口径几乎无差；用 TR 中位数略优且更稳健（不依赖 ATR 平滑窗口），**建议采用 TR 口径**。
- **「相对上涨趋势」归一**（跌/涨斜率比 slope_ratio 等）：AUC 0.51-0.60，弱于绝对烈度。上涨段本身（up_pct/up_slope/up_days）对好坏无区分度（AUC≈0.5）。
- **独立第二维度=量能**（independent-eye 发现）：`vol_red_ratio` = revert 段阴线日均量 / burst 段日均量，AUC 0.682。好样本回踩阴线几乎无量（中位 0.02），坏样本放量（0.27）。「放量下跌」与「跌幅烈度」是特征空间里仅有的两个有效维度（8 个核心特征实为 ~2 维）。

---

## 4. 量化过滤规则（三档候选）

删除模拟 = 命中规则的 match 整条删除（等价于该 tb 事件不生成，见 §6 等价性论证），重算 median/FP。

| 方案 | 规则 | 保留 match（删） | 股票/买点日 | median | FP | 误删好样本* | 特点 |
|---|---|---|---|---|---|---|---|---|
| 基线 | — | **80**（删 0） | 66 股 / 227 日 | 0.5251 | 0.7278 | — | — |
| **一（推荐）** | revert 段单日跌幅 ≥20% | **71**（删 9，-11%） | 58 股 / 205 日 | **0.5588** (+0.034) | **0.7834** (+5.6pt) | **0** | 纯毒药：删的 9 个 fr 全 ≤0.31（均值 0.095）、买点 0 up/12 down、9 股各 1 条 |
| 二（median 导向） | 一 OR 阴线实体 ≥2×ATR | **64**（删 16，-20%） | 52 股 / 196 日 | **0.5737** (+0.049) | 0.7905 (+6.3pt) | 3（ZEPP 8.19/CRML/LASE） | median 最高，但机制纯度低一档 |
| 三（FP 导向） | 一 OR (实体 ≥0.75×TR中位 AND 放量比 ≥0.15) | **53**（删 27，-34%） | 42 股 / 166 日 | 0.5352 (+0.010) | **0.8000** (+7.2pt) | 3 | FP 最高；B-AND 组件阈值平台稳定（20 网格点 FP 全 0.771-0.794），ZEPP 有 0.84TR 大阴线但量比≈0，不误伤 |

\* 误删好样本 = fr top20 中被删条数。两路独立方法在尾部高度一致：方案一删的 9 个毒药样本有 7 个也被方案三的 B-AND 组件覆盖；最差 20 个样本里方案三抓到 12 个（剩余 8 个=阴跌型，无解）。

**不建议**：OR 大宽组合（如纯 OR 烈度+量能删 53 条，误伤 12/20 好样本，FP/median 双降）；TR 复合窄规则（`max_drop_tr≥1.5 AND down_slope≥3%` FP +8pt 但 median 不稳、误删 8 个中上样本）。

### 稳健性与过拟合的诚实评估

- 方案一：bootstrap（按股整股重采样 2000 次）Δmed CI [+0.005,+0.314]、Δfp CI [+0.007,+0.133] 双正；leave-one-stock-out 66/66 全正；阈值 ±20% 指标稳定；无股票集中度。**统计上最硬**。
- 三方共同的警示：20v20 的 AUC 零假设 std≈0.066，0.72≈3σ，**方向信号大概率非噪声**；但全部样本来自同一 2025 窗、66 只 microcap，无时间外推验证——上线后真实 AUC 更可能落在 0.55-0.65、FP 增益缩水到 2-4pt。**定位应是「弱否决闸」，不是主筛选器**。
- 0.20 恰在样本分布 ~90 分位；换窗建议复核 0.15/0.20/0.25 三档（0.15 时稳健性指标已开始退化，P≈0.82-0.90）。

---

## 5. detector 物化方案（建议，未实施）

闸的判定点：`ThrowbackDetectorV1.detect` 内、`evaluate_throwback` 成功返回后、构造 `ThrowbackEventV1` 前（判定只用 ≤confirm 的数据，无前瞻）。

```python
# throwback_v1.py 新增模块级判定(草案)
def _revert_toxic(df, bo_idx, confirm, tr_med, max_day_drop_pct=0.20):
    """confirm 时点已知的 revert 段毒性闸:段内任一收跌日 (c[i-1]-c[i])/c[i-1] >= 阈值 → True。
    tr_med = median(TR over [revert-13, revert])(可选 TR 口径变体,见下)。"""
```

- **最小改动**：`ThrowbackDetectorV1.__init__` 加参数 `max_day_drop_pct: float = 0.20`（阈值从 params.yaml 的 tb section 走 `TbParams`）；`detect` 里对每个 evaluate 成功的 burst 判 `_revert_toxic`，命中则 skip（不 append 事件）。方案三需再加 `body_tr_max`/`vol_red_ratio_min` 两参数与量能计算。
- **等价性论证（删除模拟 ≈ 真实重扫）**：tb 是 DAG 叶子（无下游消费者）、`evaluate_throwback` 对每个 burst 独立调用——把某个 burst 的 tb 结果丢弃不影响其他事件生成，故「事前闸不产事件」与「从结果中删 match」在指标上严格等价，本文删除模拟数字即真实效果（底座已精确对齐 scan）。
- 顺带的架构红利：该闸同时消灭这些样本贡献的 gate_failures 噪声（BURU/ELBM 型样本 confirm 后大多以 weak 收窗）。

## 6. 局限与后续

1. **阴跌型坏样本**（最差 20 中约 8 个）revert 特征无解。下一步维度：burst 质量细化（如 bo 当根量比/串内量能衰减）、confirm 后 1-2 根的即时反应（注意若用它过滤需要重新定义买点窗起点，属于 detector 结构改动而非追加闸）。
2. 单窗口样本（80）小；建议下一个扫描窗（如 2024）做 out-of-time 复核后再固化阈值。
3. median 的改善天花板由「中段样本 fr 密集」决定——特征对尾部判别强、对中段排序弱（全样本 Spearman -0.2），继续推 median 需要能排序中段的新维度，而非收紧现有闸。

---

## 附录：产物清单（`docs/research/2026-08-18_tb-v1-revert-quality/`）

| 文件 | 内容 |
|---|---|
| `原始问题.md` | 用户原始问题逐字记录 |
| `repro/build_samples.py` | 底座：重放扫描+对齐自检（80/80 fr 精确一致） |
| `repro/features.py` / `features.csv` | 主会话特征工程（22 特征） |
| `repro/analyze.py` / `analysis_report.txt` | 主会话好坏对比+阈值扫描 |
| `repro/agentA_search.py` / `agentA_robust.py` / `agentA_grid.csv` / `agentA_rules.md` | rule-searcher：1905 条组合网格+bootstrap/LOSO |
| `repro/agentB_features.py` / `agentB_features.csv` / `agentB_filter_sim.py` / `agentB_report.md` | independent-eye：独立特征工程（35 特征含量能）+删除模拟 |
