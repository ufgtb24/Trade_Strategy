---
name: feature-study
description: 验证某特征/几何量/K线形态/用户直觉与 label(forward_return) 的关系时调——学习端 skill,回答「这个特征该不该信」,产出候选信号供 tune-gates(执行端)定阈值。用户说「验证 XX 是否有利」「XX 和收益什么关系」「排行榜前排都是 XX」「把登记簿里的候选跑一遍」类问题时必读。
---

# feature-study：特征 × label 统计验证（学习端）

## 定位（两层架构）

```
feature-study(学习端)          tune-gates(执行端)
  「这个特征/直觉该不该信」        「特征已定案,阈值放哪」
  产出:候选信号(特征+方向+口径)    消费候选信号定阈值
```

- **假设来源两个**：用户直觉,或 `docs/feature_candidates.md`(研究副产品登记簿,待验证段)。登记簿是本 skill 的假设队列:
  研究中顺手发现的东西由 CLAUDE.md 规则登记进去、状态 `exploratory`,**只有本 skill 换样本验证后才能关闭它**;
- 学习/执行分界 = **是否使用产生假设的同一份数据**(登记簿条目的「发现样本」对该条目已烧掉,验证必须换样本);
- 三关通过 ≠ 可交易：本 skill 最高产出是「**候选信号(样本内三关通过,未经跨期验证)**」，「已确立」一词保留给验证端；
- **多特征批量功能(FDR/控制变量/去簇)只在本端**——tune-gates 执行端一次面对一个特征,不设批量校正;跨期验证属 holdout 预注册,不在本 skill。

本目录自带两个工具,**用它们,不要重写统计代码**:
- `extract_skeleton.py` — 数据构建骨架(重放对齐 + 去重 + 标准控制列 + 自检门)
- `run_battery.py` — 统计电池(关1 FDR / 分箱形状 / 关2 控制秩回归 / 关3 去簇 / 尾部富集 / 三关判定)

## 流程（六步）

### 1. 假设成形（唯一需要创造性的步骤）
- **先 grep `docs/feature_candidates.md`**:要验的特征若已有 FC 条目,沿用其 ID 与公式级口径(别重新定义一遍),并记下其「发现样本」以便换样本;批量验证时直接以待验证段为清单;
- 先写**方向假设**(有利/不利)再动数据,避免事后编故事;
- 每概念 **≥3 种口径**(相对价格 / ATR 归一 / 比例式 / 原始量…):口径间强弱排序本身是机制证据(回撤深度案例:相对价格 > ATR 倍数 > 回吐比例,直接暴露波动率成分);防「定义选择的运气被当成发现」;
- **比值口径必须同时提取分子、分母原始量各一列**——比值出信号时必须能归因到哪一端(缩量回踩案例:信号全在分母 bo 放量,分子裸量 p=0.29);
- 每口径声明「tb.start(买入窗开启)时点已知」;更晚信息 → 列名加 `posthoc_` 前缀,报告单列;
- 声明条件宇宙:样本 = pattern 已成立的 match(幸存者条件化会杀死无条件为真的直觉)。

### 2. 数据构建
复制 `extract_skeleton.py` 到研究目录,**只填 `compute_features`** 与顶部任务参数(换 pattern 同步换 import)。骨架自带:
- 去重键 (symbol, tb_instance, anchor_bo);
- 标准控制列 `m1_burst_runup` / `m2_depth_rel`(关2 用,删了关2 就瞎了;2026-07 tb 几何×label 研究定的已知信号。**更新来源=登记簿已关闭段判定「有信号」的条目**,不另立渠道);
- **自检门(硬闸,不过即 raise)**:match 集逐股对齐(重放 vs scan,防参数/引擎/数据漂移) + label 官方 API 重算逐 match <1e-12。禁止注释掉检查。

### 3. 统计电池
```python
import sys; sys.path.insert(0, "<repo>/.claude/skills/feature-study")
from run_battery import run_battery
verdicts = run_battery("dataset.csv", features=[连续口径列], binaries=[0/1列],
                       controls=["m1_burst_runup", "m2_depth_rel"],
                       time_bucket_days=10)  # 从 scan 的 label_horizon 取整到 5 的倍数
```

桶宽 ≥ label_horizon 才保证 forward window 重叠的 match 归同簇(两笔 match 的 label 随机源共享 ⟺ 窗口重叠)。

### 4. 判定（电池自动输出,禁止另立标准）
三关 = FDR q<0.05 → 控制后 |t|≥2 且同号 → 双维去簇(股内簇/时间桶)各自 p<0.05 且同号。
关 3 死因可区分:个股驱动(少数股票反复观测刷出)/事件驱动(同期跨股共同行情=同一随机源的重复下注);3b 各留首条兼任最保守读数(双维压缩集合,做正式门)。
五类判定:**有信号 / 代理(被控制集吸收) / 反转(suppression,残余反向) / 不稳(去簇死) / 无信号**。
分箱形状(单调/饱和/甜点位置)必须写进结论——相关系数只给方向不给形状。

### 5. 结论纪律
- 局限逐条声明:label 口径上偏不可当收益预期、单窗 in-sample、观测非独立(双维去簇已检:股内防个股复读、时间桶防事件复读)、口径族已 FDR、相关≠可交易;
- 「排行榜前排都是 XX」类肉眼观察必须过 `tail_enrichment`(Fisher vs 基率)再下结论——top20 全阳线案例=基率 88% 的复读,p=1.0;
- 产出物 = **候选信号清单**(特征 + 方向 + 推荐口径 + 分箱形状)→ 交 tune-gates 定阈值。

### 6. 归档（两处产出,缺一不算完成）
1. 按 write-user-doc 规范落 `docs/research/<日期>_feature-study-<slug>/`:
   `final_report.md`(背景+口径表 → 自检 → 电池结果 → 三关判定 → 结论 → 局限)+ `dataset.csv` + 脚本副本。
2. **回写 `docs/feature_candidates.md`**:本次验证过的每个特征,在「已关闭」段追加一行
   `FC-xxx · 名称 · 口径 · 判定(有信号/代理/反转/不稳/无信号) · 验证样本 · → final_report 路径`。
   原来没有 FC 条目的特征先在待验证段登记、再关闭。**不改原条目、不删行**(文件设了 merge=union,改旧行会在合并时静默双份);
   判定「有信号」的同时把它加进本 skill 的标准控制列清单(第 2 步)。报告是可删的,登记簿是持久的——报告路径失效后那一行仍须自足。

## 常见坑（全部为本仓库实证案例）

| 坑 | 现实 |
|---|---|
| 比值口径出信号就当分子的功劳 | 缩量回踩:信号全在分母(bo 放量),分子裸相关 p=0.29 |
| 控制后 \|t\|≥2 就报有信号 | depth_atr:t=−4.88 **反号** = suppression,方向结论会说反 |
| 拿 referenced_points 的 peak 价做几何 | 记录的是 elevation 后价,测不出真实阻力位 |
| 肉眼看排行榜归纳特征 | P(特征\|前排) 只是复读 P(特征),必须对照基率 |
| pd.read_csv 默认 NA 解析 | 有 ticker 叫 "NA",一律 `keep_default_na=False, na_values=[""]` |
| 跳过自检门省时间 | 底座不等价时所有统计静默全错 |
| 只跑一个口径 | 定义选择的运气会被当成发现;≥3 口径且报告强弱排序 |
| 只报 p 不报效应量 | 大样本下芝麻效应 p 也极小;p 与 AUC/spearman 并报 |
| 报 win_rate 类无基线比例 | 高基率 pattern 上是基率复读,对子集区分无增量——报计数或对照基率 |
| 推荐口径只看 AUC 拍板 | 排序略优的口径可硬闸更差——归一轴把不同波动 regime 样本拉到不可比位置,排序统计看不出、硬闸才暴露(TR 归一 vs 绝对 pct:AUC 0.728 vs 0.723 略优,硬闸 FP +1.7pt vs +5.6pt 严格差)——口径结论须注明「待执行端硬闸复核」 |
| 小样本报比例 | 计数比比例诚实;两位数样本的单窗数字噪声主导,别过度反应 |
| 同期跨股 match 当独立样本 | 「那星期小盘股集体反弹」=同一随机源的重复下注,名义 n 虚高;时间桶去簇把关(桶宽锚 label_horizon) |

## 沿革

2026-08-20 从已删的 `label-study`(af903062 最后版)复活并更名——学习对象是 feature 不是 label;思想层(自检门/口径≥3/三关)全部继承;脚本按 instance-id 架构重写(旧 `extract_skeleton` 的 event_id 寻址与手写 label 重算在重构后失效;label 对齐改官方 `match_forward_returns` 含 sample_window)。与 tune-gates 的解耦契约:本端产候选信号,执行端单特征定阈值、不做批量校正。评估纪律五条(①指标契约②底座等价③用途匹配④带对照⑤小样本多窗,①主家在 tune-gates、②主家在本骨架、③④⑤分列两 skill)内联本文件与骨架,原独立 skill eval-discipline 同日解散。

2026-08-20 关3 扩双维去簇(股内簇+时间桶;簇代表去 label 化,tail_enrichment 的 per-symbol 最佳为排行榜语义保留)——同期跨股事件聚集是 symbol 单维去簇的盲区。

2026-08-27 接入 `docs/feature_candidates.md`(研究副产品登记簿):第 1 步先读、第 6 步回写关闭。动机=两轮外部通道研究各自在对照/控制侧顺手发现 feature(ATR%/pos/vol_spike_min 方向反)但只散落在各自 final_report,而 2026-07 tb-geometry-label 报告已整份丢失;登记簿由 CLAUDE.md 推送式捕获、本 skill 拉取式消费。
