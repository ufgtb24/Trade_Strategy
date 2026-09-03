# 多维稳健区调参工具链 · 设计 spec

> **⚠ 已被取代（2026-08-25）**：本 v1 的 `region_find` 判据（τ 水平集 / Chebyshev / permutation / 中心真跑）与「每格一次 scan」预算模型已由 `2026-08-25-multivar-region-reversed-loop-design.md`（v2：每股反转循环 + 候选长表 + 联合空间）取代；保留仅供沿革参考。
>
> 日期：2026-08-23 · 状态：已取代
> **本 spec 中所有项目内路径均相对 repo root。**
> 研究依据：`docs/research/2026-08-22_multivar-robust-region/`（final_report.md §九 审核结论 + framework-survey.md + region-native-frameworks-survey.md）、`docs/research/2026-08-21_oat-optuna-blend/final_report.md`。
> 实施基线：分支 `worktree-oat-optuna-blend`（本 worktree；tune_v1 已提交内容均为其祖先）。tune_v1 worktree 里尚未提交的编辑（tune-gates SKILL.md 红线、scan-wide.py、scan_tune.py、extract_skeleton None-label 修复、bb_v1 的 peak_age/毒药闸字段）**不在本分支**——本 plan 不依赖它们；Task 7 改 SKILL.md 后与 tune_v1 那份编辑合并时会有一次不重叠的冲突，由用户手动合并。

---

## 0. 目标与非目标

**目标**：给 tune-gates skill 增加「必须真扫参数的多维稳健区调参」环节——在 2-4 维参数空间上全因子网格扫描（≥5 维用 LHS），识别「有体积 + 分 fold 一致」的连通达标区，取 Chebyshev center 作推荐，配 permutation 零假设检验与中心点复跑。工具 **pattern 无关**（通过 `PatternRegistry` + `eval_meta` + `Params.from_dict/to_dict` 协议加载），供后续频繁新建的 pattern 直接复用。

**前置**：修复 ATR 计算的实现低效（宽进 scan 266 s → 约 35 s），否则网格预算不可行。

**非目标**（明确不做）：
- 不引入 optuna / Ax / 任何优化框架——评估便宜 + 找区域不找点 ⟹ 不需要优化器（研究结论）。
- 不做主动学习 / 水平集估计（B1/B2）——留作远期。
- 不改 feature-study 骨架的 pattern 无关化、不重组 tune-gates reference.md 的非多维部分（另起 plan）。
- 不改 `_solve` / dag 引擎。
- 不为旧 scan 文件做兼容（规则 `.claude/rules/scan-file-no-backcompat.md`）。

## 1. 术语

- **可切参数**：只出现在 `NodeSpec.where` 阈值里的参数（bb_v1：`first_drought_min / distinct_pk_min / vol_spike_min / peak_age_min / max_day_drop_pct`）。宽进扫一次、事后零成本切档，**不进多维搜索**。
- **必须真扫参数**：进入 detector 构造（`inspect.signature(detector.__init__)`）、参与事件物化/几何的参数（bb_v1：`gap_max / min_bos / min_relative_height / exceed_threshold / stop_confirm_bars / big_rise_k`）。每个取值组合需一次全宇宙 scan。
- **设计点**：一组必须真扫参数取值；**设计**：设计点集合（网格或 LHS）。
- **fold**：训练窗按时间切块（默认半年）。
- **FP**：首次穿越率 `up / (up + down + both)`，`none` 不计入分母。主指标；字典序 FP > fr_median（`.claude/skills/tune-gates/SKILL.md` 指标契约）。
- **f_robust(θ)** = 各 fold FP 的最小值（任一 fold count 低于功效线 → 该点 fail）。
- **达标区**：`{θ : f_robust(θ) ≥ τ}` 的连通分量；**inradius** = 分量内最大内切球半径；**Chebyshev center** = 取得 inradius 的点。

## 2. 组件与文件

| 文件 | 职责 | 新建/修改 |
|---|---|---|
| `path2/calc/atr.py` | `calculate_atr` Wilder 递推向量化（numpy 标量循环），数值逐值等价 | 修改 |
| `path2/atoms/throwback_v1.py` | `detect` 入口算一次 ATR 序列并下传；`_atr_at` 改为读序列 | 修改 |
| `path2/atoms/throwback_v0.py`、`path2/atoms/throwback.py` | 同上消除 per-candidate 重算（v0 第 294 行、throwback.py 第 317 行附近） | 修改 |
| `path2_web/serialize.py` | match dict 增加 `buy_date`（str）与 `first_passage`（四态 dict 或 None） | 修改 |
| `.claude/skills/tune-gates/multivar_scan.py` | 设计生成 → 逐点 scan → 台账 CSV（断点续跑） | 新建 |
| `.claude/skills/tune-gates/region_find.py` | 台账 → f_robust 网格 → 达标区 → 中心 → permutation → 切片图 → 报告 | 新建 |
| `.claude/skills/tune-gates/reference.md` | 多维稳健区操作卡（pattern 无关主干 + bb_v1 附录） | 新建 |
| `.claude/skills/tune-gates/SKILL.md` | 第 5 步「必须真扫参数调参」升级；新增红线 | 修改 |
| `tests/path2/test_atr_equivalence.py`、`tests/path2_web/test_serialize_match_fp.py`、`tests/skills/test_region_find.py` | 见 §7 | 新建 |

脚本约定：**无 argparse**，全部参数声明在 `main()` 起始处；与 feature-study 工具一致，使用时复制到研究目录 `docs/research/<日期>_<slug>/` 改常量。

## 3. Task 1：ATR 修复（前置）

### 3.1 `calculate_atr` 向量化
保持签名 `calculate_atr(highs, lows, closes, period=14) -> pd.Series`。算法不变：TR = max(H−L, |H−C₋₁|, |L−C₋₁|)（NaN 按 skipna 忽略，与 `pd.concat(...).max(axis=1)` 同语义）；第 period 个 = 前 period 个 TR 的均值；之后 Wilder 递推。实现改为：`to_numpy(float)` → `np.fmax` 算 TR → 预分配 `np.full(n, nan)` → Python 标量循环递推（无 pandas 索引）→ `pd.Series(out, index=closes.index)`。`len < period` 时返回全 NaN（同现状）。

### 3.2 算一次、处处读
- `throwback_v1.py`：`ThrowbackDetectorV1.detect` 入口 `atr = calculate_atr(df['high'], df['low'], df['close'], atr_window)` 一次；`evaluate_throwback` 增加参数 `atr: pd.Series`；`_atr_at(df, idx, period)` 改为 `_atr_at(atr, idx)`（越界/NaN → 0.0 语义不变）。
- `throwback_v0.py`、`throwback.py`：同样消除 per-candidate 调 `calculate_atr`（throwback.py 第 253 行已算一次，第 317 行 `_atr_at` 改读该序列）。
- 因果性：ATR[idx] 只依赖 ≤ idx 的 K 线，预算整条再读与逐候选算到 idx 为止结果相同。

### 3.3 验收
- 单测：旧实现（测试文件内保留一份 pandas 逐行参考实现）与新实现在 ≥3 只真实 pkl × period∈{14,20} 上 `np.allclose(rtol=0, atol=1e-12, equal_nan=True)`。
- 回归：固定 30 只股票子集（`docs/research/2026-08-20_tune-bb-v1/scan_tune.py` 的验证子集思路），修复前后 `run_scan_multi` 的 match 集合逐股相同（按 `(symbol, match_id)` 集合比较）+ `forward_return` 逐 match 相等。
- 性能：宽进 + 2 年窗 + head_buffer=250 全宇宙 scan，workers=24，记录修复前后耗时到 plan 台账（预期 266 s → ≤ 60 s；不设硬阈值）。

## 4. Task 2：scan 文件 per-match 增加 `buy_date` 与 `first_passage`

在 `path2_web/serialize.py` 的 `serialize_per_pattern_result`（`_with_labels` 处）为每个 match dict 增加：
- `"buy_date"`: `str(win["date"].iat[leaf_ev.start_idx].date())`——end_node 事件（eval_meta 声明的买点 node）起始日。
- `"first_passage"`: 该 match 的 `match_first_passage(...)` 返回的 `{up, down, both, none}`；若其 leaf 已被同股前一 match 累加过（现有 `seen_fp_leaves` 去重）则为 `None`；`first_passage_enabled=False` 时恒 `None`。

不变式（测试）：对任一 scan，所有 match 的非 None `first_passage` 四态逐项求和 == 该 pattern 的 `first_passage_stats` 分子分母来源 `match_fp_counts` 累加值（即 `per_pattern[pid].first_passage_stats` 用的计数）。

## 5. Task 3：`multivar_scan.py`

### 5.1 `main()` 常量（示例为 bb_v1）
```python
PATTERN_ID = "bb_v1"
DATA_DIR = "datasets/pkls"                    # 相对 repo root
START_DATE, END_DATE = "2024-01-01", "2026-01-01"
HEAD_BUFFER = 250                             # 完整检测值(训练与外推同值红线)
LABEL_HORIZON = 40
FIRST_PASSAGE_K = 5.0
PRICE_MIN, PRICE_MAX, VOLUME_MIN = 0.5, 30.0, 10000.0
WORKERS = 24
REF_SCAN = "outputs/path2_web/scans/<参照 scan>.json"   # 取 params_snapshot 作底座;None 则用 load_params()
WIDE_OVERRIDES = {"burst": {"first_drought_min": 0, "distinct_pk_min": 1, "vol_spike_min": 0},
                  "tb": {"max_day_drop_pct": None}}      # 可切参数放开
DESIGN = ("grid", {("tb", "stop_confirm_bars"): [0, 1, 2, 3, 4],
                   ("burst", "min_bos"):         [1, 2, 3, 4],
                   ("burst", "gap_max"):         [4, 8, 12, 20]})
# 或 DESIGN = ("lhs", {"dims": {...: (low, high, step|None)}, "n": 300, "seed": 0})
OUT_DIR = "docs/research/<日期>_multivar-<pattern>/"
TICKER_REGEX = None                           # 小样本验证时填子集正则
```

### 5.2 行为
1. `PatternRegistry().get(PATTERN_ID)` 取模块；`Params = mod.Params`；`eval_meta = mod.eval_meta`。
2. **参数分类打印**（帮助选维，不替人选）：遍历 `build_pattern(Params.default())` 的 `PatternSpec.nodes`：`where` 中 `W.attr(field, op, threshold)` 的阈值来源字段 → 可切；`inspect.signature(type(node.detector).__init__)` 的参数名 → 必须真扫候选。打印两张表（section.field → 分类）。分类通过把 `Params` 各 section 字段名与 detector 构造参数名匹配完成；无法匹配的字段标「未知」。
3. 设计生成：`grid` = 各维档位的笛卡尔积；`lhs` = `scipy.stats.qmc.LatinHypercube(d, optimization="random-cd", rng=np.random.default_rng(seed)).random(n)` → 投影（float: `qmc.scale`；int 带 step: `low + floor(u*k).clip(0,k-1)*step`；categorical: 索引）。写 `OUT_DIR/design.csv`（列：`point_id` + 各维）。
4. 逐点（**串行**，scan 内部已多进程）：`snap = deepcopy(参照 snapshot)`；套 `WIDE_OVERRIDES`；套设计点；`p = Params.from_dict(snap)`；`run_scan_multi(...)`，`name=f"mv-{PATTERN_ID}-{point_id}"`；scan JSON 落 `outputs/path2_web/scans/`。**断点续跑**：目标 scan 文件已存在且其 `per_pattern[pid].params_hash == params_hash(snap)` → 跳过 scan、直接读文件。
5. fold 聚合：读 scan JSON 的全部 match，按 `buy_date` 落入 fold（`FOLD = "6M"`：训练窗按 6 个月切；`"Y"`：按年）；fold 命名：`"6M"` → `<年>H1` / `<年>H2`（1-6 月 / 7-12 月），`"Y"` → `<年>`；每 fold：`count` = 非 None `first_passage` 的 match 数、`fp = up/(up+down+both)`（分母 0 → NaN）、`fr_median` = 非 None `forward_return` 中位数。另记全窗行 `fold="ALL"`。
6. 写 `OUT_DIR/ledger.csv`，列：`point_id, <各维>, fold, count, fp_up, fp_down, fp_both, fp_none, fp, fr_median, scan_path`。每点完成即追加（crash 安全）。
7. 结束打印：点数、总耗时、每点平均耗时、各 fold 的 count 分布（min/median）——用于校验功效线是否可达。

## 6. Task 4：`region_find.py`

### 6.1 `main()` 常量
```python
LEDGER = "docs/research/<日期>_multivar-<pattern>/ledger.csv"
DIMS = [("tb","stop_confirm_bars"), ("burst","min_bos"), ("burst","gap_max")]   # 与设计一致,顺序即轴序
FOLDS = ["2024H1", "2024H2", "2025H1", "2025H2"]   # 参与 min 的 fold;"ALL" 不参与
TAU = 0.50                         # 达标线(研究者声明;建议 = 参照点全池 FP 或随机基线 + 裕量)
MIN_COUNT_PER_FOLD = 100           # 功效线(每 fold);不达标 → 该点 fail
R_MIN = 1.0                        # inradius 下限(单位=网格格数);低于此判「无稳健区」
N_PERM = 1000
SEED = 0
OUT_DIR = 同 LEDGER 目录
MODE = "grid"                      # "grid":直接在网格格子上做;"lhs":先 GP 回归落网格
```

### 6.2 算法（grid 模式）
1. 读 ledger，按 `point_id` 汇成 `f_robust = min(fold FP over FOLDS)`；任一 fold `count < MIN_COUNT_PER_FOLD` 或 fp 为 NaN → `f_robust = NaN`（fail）。
2. 建网格张量 `F[i1,…,id]`（轴 = DIMS 档位，升序）；`mask = F >= TAU`（NaN → False）。
3. `mask_p = np.pad(mask, 1, constant_values=False)`（盒外视为 fail，防中心被推向盒边）；`labels, n = scipy.ndimage.label(mask_p)`。
4. 每分量：`edt = scipy.ndimage.distance_transform_edt(comp)`（**单位网格**，inradius 以格数计——各维档位由研究者按机制等距声明，格数即「可容忍多少档偏移」，与参数量纲无关）；`inradius = edt.max()`；`center = argmax` 去 pad 映射回档位；`widths` = 分量在各维的投影跨度（报告同时给格数与实际档位值）；`volume_frac` = 格子数 / 总格子数；`min_fp` = 分量内 F 最小值；逐 fold 在 center 的 FP。
5. 选 inradius 最大的分量为主区；`inradius < R_MIN` → 判「无稳健区」。
6. **permutation 检验**：固定 fail（NaN）格子不动，把其余格子的 `mask` 标签随机重排 `N_PERM` 次，统计「最大分量 inradius ≥ 观测值」的比例 = p 值；同时报告「最大分量格子数 ≥ 观测值」的 p。
7. **τ 灵敏度**：τ 在 `[TAU−0.05, TAU+0.05]` 步 0.01 扫，记主区 inradius / 格子数 / center 位移，出一张折线图。
8. 图（matplotlib，保存 PNG）：① 每维过 center 的一维切片（x=档位，y=f_robust 与各 fold FP，标 TAU 水平线、标 center）；② 每对维度过 center 的二维热力图（f_robust，叠 mask 等高线，标 center）；③ τ 灵敏度。
9. `region_report.md`：设计/ledger 摘要、fail 点数与原因（功效线/NaN）、分量表（inradius / 体积 / widths / min_fp / center / 各 fold FP@center）、permutation p、τ 灵敏度结论、**下一步强制动作**清单（center 真跑全量 scan；同 head_buffer 外推验证）。

### 6.3 lhs 模式
LHS 设计点不在网格上：先用 `sklearn.gaussian_process.GaussianProcessRegressor(Matern(nu=2.5, length_scale=各维量程/2) + WhiteKernel())` 对 `(θ, f_robust)` 拟合（fail 点不参与回归，但在网格上按最近邻标为 fail），在 `GRID_RES`（每维 20）网格上取后验均值为 F，其后同 6.2 第 2 步起。报告额外标注「区域形状来自代理模型，仅中心点可信（调研 §5.5）」。lengthscale 先验按维度量程初始化（Hvarfner 2024 建议）。

## 7. 测试

| 测试 | 内容 |
|---|---|
| `test_atr_equivalence.py` | §3.3 逐值等价；period 14/20；含 `len < period` 与含 NaN 段 |
| 回归脚本（plan 内一次性步骤，不入 tests） | 30 股子集修复前后 match 集 + forward_return 相等 |
| `test_serialize_match_fp.py` | §4 不变式：四态求和 == 聚合计数；`first_passage_enabled=False` 时恒 None；`buy_date` 等于 end_node 起始日 |
| `test_region_find.py` | 合成 3 维网格：已知椭球达标区 + 高斯噪声（σ=0.02）→ center 落在真区内、inradius 与真值相对误差 ≤ 30%；随机标签（无结构）→ permutation p > 0.05 的比例 ≥ 90%（20 个 seed）；全 fail 网格 → 报「无稳健区」不抛异常 |
| `multivar_scan` 冒烟 | `TICKER_REGEX="^A[A-C]"`、2×2 网格、`FOLD="Y"` → design.csv / ledger.csv 形状正确；重复运行第二次全部跳过（断点续跑） |

## 8. SKILL.md 与 reference.md 改动

**SKILL.md 第 5 步「必须真扫参数调参」**：默认 OAT（d=1 或确信独立）→ **升级「多维稳健区」**：参数分类 → 选 2-4 维 + 机制上下界 → `multivar_scan`（grid）→ `region_find` → 人复核（切片图/热力图/fold 表/机制合理性）→ center 真跑 → 外推验证。

**新增红线**：
- 必须真扫参数多维调参**不优化单点、不取 argmax**，取达标区 Chebyshev center。
- 可切参数不进多维设计；设计用全因子网格（≥5 维用 LHS），**不引入优化框架**。
- 达标区成立的双闸：inradius ≥ R_MIN **且** 各 fold 一致（f_robust 用 min）；**permutation p < 0.05** 才能声称「有区域」。
- 推荐 center **必须真跑一次全量 scan**；训练与外推同 head_buffer，外推独立验证。
- τ、功效线、维度选择由研究者声明并写进台账；工具只报告灵敏度。

**reference.md**：多维稳健区操作卡（pattern 无关主干：参数分类 → 定域 → 设计 → scan → 区域识别 → 复核 → 外推；每步命令与常量说明；坑清单：τ 灵敏度、功效线按 fold、非等距档位、lhs 模式代理风险）+ bb_v1 附录（可切闸清单 / 必须真扫候选 / OAT 线索 / 本次教训）。

## 9. 实施顺序与依赖

Task 1（ATR）→ Task 2（serialize）→ Task 3（multivar_scan，依赖 Task 2 字段）→ Task 4（region_find，依赖 Task 3 的 ledger 格式）→ Task 5（SKILL.md + reference.md）→ 端到端：bb_v1 真实 3 维网格（`stop_confirm_bars × min_bos × gap_max`，5×4×4=80 点，约 1 小时）跑通，产出 region_report，结果进 plan 台账（诚实预期：可能「无稳健区」）。

## 10. 风险

- ATR 修复触及 platform.py 共用函数——等价测试兜底。
- bb_v1 已判无 edge，端到端可能报「无稳健区」——这是方法正确的表现，不是实施失败；验收看管线与报告完整性。
- inradius 以格数计：非等距档位（如 gap_max 4/8/12/20）时「一格」在不同位置对应不同参数距离，报告在 widths 表同时给实际档位值，由研究者解读。
- FOLD="6M" 下每 fold count 可能不足——`multivar_scan` 结束打印 count 分布，不足则改 `FOLD="Y"` 或降 `MIN_COUNT_PER_FOLD`（研究者决定，写台账）。
