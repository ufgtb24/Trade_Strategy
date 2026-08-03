---
name: label-study
description: Use when 用户要用数据验证某特征/几何量/K线形态/口径「是否有利或不利于 label(forward_return)」,或研究特征与未来收益的关系,或用「排行榜前排都是XX」类肉眼观察质疑统计结论——输入为自然语言假设 + path2_web 扫描结果文件。只讨论口径定义、不出统计结论的场合不适用。
---

# label-study:特征 × label 统计验证

## Overview

把「XX 是否有利/不利于 label」固化为:多口径提取 → 自检门 → 固定统计电池 → 三关判定 → 归档。
核心原则:**自检不过不进统计;三关不过不叫有信号;判定标准用电池写死的,不现场发明**。

本 skill 目录自带两个已测试工具,**用它们,不要重写统计代码**:
- `extract_skeleton.py` — 数据构建骨架(去重 + 标准控制列 + 自检门硬闸)
- `run_battery.py` — 统计电池(关1 FDR / 分箱形状 / 关2 控制秩回归 / 关3 去簇 / 尾部富集 / 三关判定)

## 流程(六步顺序执行,每步产出为下一步必填输入)

### 1. 假设成形(唯一需要创造性的步骤)
- 先写下**方向假设**(有利/不利)再动数据,避免事后编故事;
- 把概念翻成 **≥3 种口径**(相对价格 / ATR 归一 / 比例式 / 原始量…)。口径间强弱排序本身是机制证据(回撤深度案例:相对价格 > ATR 倍数 > 回吐比例,直接暴露波动率成分);
- **比值口径必须同时提取分子、分母的原始量各成一列**——比值出信号时必须能归因到哪一端(缩量回踩案例:信号全在分母 bo 放量,分子裸量 p=0.29);
- 每口径声明「tb.start(买入窗开启)时点已知」;要用更晚的信息 → 列名加 `posthoc_` 前缀,报告单列;
- 声明条件宇宙:样本 = pattern 已成立的 match。幸存者条件化会杀死无条件为真的直觉(K线形态案例:能预示破位的成分已被 tb detector 筛掉)。

### 2. 数据构建
复制 `extract_skeleton.py` 到研究工作目录(scratchpad),**只填 `compute_features`**,改 SCAN/OUT_CSV 常量。骨架自带的部分勿动:
- 观测去重键 (symbol, tb, anchor_bo);
- 标准控制列 `m1_burst_runup` / `m2_depth_rel`(关2 用,删了关2 就瞎了);
- **自检门(硬闸)**:label 逐观测重算比对 + 引擎不变量(depth_atr ≥ pullback_min_atr)。失败即 raise = 数据链路损坏(窗口/索引/参数不对齐),先修再谈统计。禁止注释掉检查、禁止"先看看结果"。

### 3. 统计电池
```python
import sys; sys.path.insert(0, "<repo>/.claude/skills/label-study")
from run_battery import run_battery
verdicts = run_battery("dataset.csv", features=[连续口径列], binaries=[0/1列],
                       controls=["m1_burst_runup", "m2_depth_rel"])
```
- controls 默认 = 当前最佳已知信号(bottom_burst 为上面两个,出处 `docs/research/2026-07-19_tb-geometry-label/`;注意它们自身也是样本内候选、未经跨期验证——是当前最好的知识,作控制集使用无碍)。后续研究产出新的三关通过候选,更新上一行清单并注明出处;
- 别的 pattern 尚无已知信号 → `controls=[]`,电池会自动把全部判定降级并要求声明。

### 4. 判定(电池自动输出,禁止另立标准)
三关 = FDR q<0.05 → 控制后 |t|≥2 且与原始方向同号 → 去簇后 p<0.05 同号。
产出五类:**有信号 / 代理(被控制集吸收) / 反转(suppression,残余贡献反号) / 不稳(去簇死) / 无信号**。
- 「有信号」在报告与对话中的完整写法 = **「候选信号(样本内三关通过,未经跨期验证)」**——本 skill 是学习端,最高产出是候选;「已确立」一词保留给验证端盖章;
- 分箱形状(单调/饱和/甜点位置)必须写进结论——相关系数只给方向不给形状;
- 比值口径拿到「有信号」时,加验分子、分母裸量各自过三关,归因写进结论。

### 5. 结论纪律
- 局限逐条声明(模板):label 上偏(20日 max-high 口径)不可当收益预期、单窗口 in-sample、观测非独立(去簇已检)、口径族已 FDR、相关≠可交易;
- 回应「排行榜前排都是 XX」类肉眼观察:必须过基率检验(电池 `tail_enrichment`,Fisher vs 基率期望)再下结论——top20 全阳线案例 = 基率 88% 的复读,Fisher p=1.0;
- 边界:跨期验证(换窗口检验候选信号能否外推)属**验证端**,不在本 skill 内——学习与验证的分界 = 是否使用产生假设的同一份数据。需要时另行发起(未来 label-validate;机制参照 `BreakoutStrategy/mining/template_validator.py` 的 baseline shift / 排序留存 / KS+bootstrap CI / 三级阶梯)。

### 6. 归档
按 write-user-doc 规范落 `docs/research/<日期>_label-study-<slug>/`:
`final_report.md`(结构:背景+口径表 → 自检 → 电池结果 → 三关判定 → 结论 → 局限)+ `dataset.csv` + 脚本副本。分析在 scratchpad 做,归档只放最终件。

## 常见坑(全部为本仓库实证案例)

| 坑 | 现实 |
|---|---|
| 比值口径出信号就当分子的功劳 | 缩量回踩:信号全在分母(bo 放量),分子裸相关 p=0.29 |
| 控制后 \|t\|≥2 就报有信号 | depth_atr:t=−4.88 反号 = suppression,方向结论会说反 |
| 拿 referenced_points 的 peak 价做几何 | 记录的是 elevation 后价,55/881 恰=当根 high,测不出真实阻力位 |
| 肉眼看排行榜归纳特征 | P(特征\|前排) 只是复读 P(特征),必须对照基率 |
| pd.read_csv 默认 NA 解析 | 有 ticker 叫 "NA",一律 `keep_default_na=False, na_values=[""]` |
| 跳过自检门省时间 | 索引错位时所有统计静默全错;自检是数据链路唯一的正确性证明 |
| 只跑一个口径 | 定义选择的运气会被当成发现;≥3 口径且报告强弱排序 |
