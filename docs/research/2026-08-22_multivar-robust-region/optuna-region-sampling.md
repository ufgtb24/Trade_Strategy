# optuna 用法重构：从「优化点」到「采样 + 区域识别」（teammate: optuna-usage-redesign）

> 目标：让 optuna 服务「多维稳健区识别」而非「找最优单点」——最有利于外推保持 + 根治 OAT 切片漂移。
> 上一轮缺陷：objective 仍优化单标量（min-fold FP），本质是「找最优 + 稳健正则」，未真正反转。

## 0. 核心反转：optuna 的角色从「优化器」降级为「采样引擎」

区域识别本质是**事后的几何分析**，不是优化。所以：

- **optuna 的真正价值 = QMCSampler 的低差异均匀采样**（Sobol/Halton），比手写随机更均匀地覆盖多维空间。
- **TPE 收缩是敌人**：TPE 对着历史最好观测收缩采样密度，会「锁定」一个它认为好的区域疯狂采样，漏掉「次优但更宽」的平台。这正是切片漂移在多维版的翻版——TPE 找到的「最优区域」本身可能就是训练窗噪声堆出来的。
- **NSGA-II 多目标可不用**：它「在线逼近帕累托前沿」，但事后区域识别更直接、更可控。

## 1. sampler 选择（问题 1）

| sampler | 性质 | 对「区域识别」 |
|---|---|---|
| TPE | 对最优值收缩 | ❌ 漏宽平台，点优化毛病 |
| RandomSampler | 均匀随机 | △ 覆盖均匀但点可能扎堆 |
| **QMCSampler（Sobol）** | 低差异均匀 | ✅ **首选**：均匀覆盖，不漏区域 |
| NSGA-II | 多目标帕累托 | △ 可选，事后识别更直接 |

**结论：QMCSampler + 固定种子。** 均匀覆盖是区域识别的前提（空间被均匀采样到，才能判断哪里聚成好区域）。

## 2. objective 应该返回什么（问题 2）

**指标记录器 + 弱引导**，返回值只为让 optuna 跑：

```python
def objective(trial):
    x = {p: trial.suggest_int(p, lo, hi) for p in MUST_RESCAN}   # 盒子=机制区间
    res = run_full_scan(x, head_buffer=已校准)
    folds = split_by_time(train_window, by="year")
    per_fold = [{fp, fr, count} for fold in folds]
    trial.set_user_attr("per_fold", per_fold)     # ★ 核心：完整指标存进 user_attrs
    trial.set_user_attr("params", x)
    if sum(c) < MIN_MATCH: return -inf            # 功效线：坏点淘汰，不进区域
    return min(f.fp for f in per_fold)            # 弱引导，仅记录用途
```

关键：**采样密度由 QMCSampler 保证均匀，不依赖返回值引导**——返回值是什么不影响「覆盖」，只影响「记录」。识别区域的事后分析全靠 `user_attrs`。

## 3. 事后区域识别（问题 3、5）

**先均匀撒点 → 事后识别区域**（在线 NSGA-II 不必用）：

```
1. 好点集 good = { t | 功效达标 且 分年方向一致 且 FP 超基线 }
2. 在 good 上做连通分量 / DBSCAN（参数空间，机制区间归一化的距离）
3. 稳健区 = {中心点, 各维宽度, 区域内 min FP, 区域内分年一致性}
4. 取最宽/最稳区域的中心（非最优单点）
```

- 分年方向一致 = 硬过滤（不进区域），不是目标轴。
- bootstrap SE 噪声率 = 区域内部稳定性度量（区域内点 SE 应都小；SE 大的点不是平台点）。
- 可视化：2 维画等高线；3-4 维 pairwise 投影（每轴可解释），不降维（PCA/UMAP 破坏参数轴可解释性）。

## 4. 20-40 点够不够识别区域（问题 4）

**不够。4 维空间 Sobol 需 64-128 点才有像样覆盖。** 解法 = 降维 + 分阶段：

1. **一维粗扫缩小盒子**：每个参数单独扫 5-10 档，目的**不是选平台**，而是锁定每个参数的「有希望区间」——避免多维撒点撒进明显坏区。这一步的 OAT 漂移无害（它不产生结论，只缩小搜索盒子）。
2. **缩小的盒子里均匀采样**：2-3 维盒子下 20-40 点够识别区域；4 维需更多点或进一步缩小。

## 5. 完整伪代码（问题 6）

```python
# Phase 0：一维粗扫 → 每个参数的机制区间 [lo_i, hi_i]（可选，成本低）
# Phase 1：均匀采样（QMCSampler，不收缩）
study = optuna.create_study(direction="maximize", sampler=QMCSampler(seed=42))
study.optimize(objective, n_trials=20_40)

# Phase 2：事后区域识别
good = [t for t in study.trials
        if t.value > -inf and all_same_direction(t.user_attrs["per_fold"], baseline)]
regions = cluster_into_regions(good, eps=机制区间归一化)   # 连通分量/DBSCAN
best = pick_widest_robust_region(regions)                 # 最宽/最稳
center = best.centroid                                   # 区域中心，非 argmax

# Phase 3：区域中心 + 同 head_buffer 外推验证（外推差即淘汰）
```

## 6. 上一轮正确部件的保留方式（问题 7）

这些是**对的**，保留，但**不再串成单标量**，而是各司其职：

| 部件 | 上一轮 | 本轮 |
|---|---|---|
| fold-in-scan 伪 CV | objective 的 min | 区域识别的**过滤条件** + 区域稳定性度量 |
| 功效线硬约束 | ConstraintFunc | 硬淘汰（坏点不进区域） |
| 完整检测指标 | objective 用校准 head_buffer | 同（不变） |
| 同缓冲外推 | top-K 外推验证 | 区域中心外推验证 |
| bootstrap SE | 搜索内代理 | 区域**内部**稳定性度量（区域内点 SE 应都小） |

## 7. 为什么区域识别根治切片漂移

OAT 切片漂移根源：固定其他变量 → 切一维 → 平台依赖「其他变量恰好在此值」。

区域识别解法：**不固定任何变量**。均匀采样时所有参数一起变，每个点都是全维坐标。识别区域 = 在全维空间找「一片所有点都好的连通区域」，定义不依赖「固定其他变量」→ 不存在切片漂移。

**额外红利**：区域在各维的宽度 = 该参数的**外推容错**（宽=不敏感，窄=敏感）。这是 OAT 给不了的信息——OAT 只给「固定底座下的平台」，不给「多维联合下的容错」。区域中心如实暴露每个参数的敏感性，而不是隐瞒。

## 8. 结论

**optuna 的正确用法 = QMCSampler 均匀采样（引擎）+ 事后连通区域识别（分析）+ 区域中心选点（决策），全程不找 argmax。**

- 「找平台思路赋能 optuna」= 用 optuna 的低差异采样铺满空间，用事后几何分析找多维平台，而不是用 optuna 找最优再复核。
- 唯一保留的「搜索引导」是一维粗扫缩小盒子（可选，成本低），它只排除坏区、不锁平台，漂移无害。
