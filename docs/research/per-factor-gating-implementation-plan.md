# Per-Factor Gating 改造实施方案

> 团队：per-factor-gate-impl（team-lead + 4 位专家）
> 日期：2026-04-15
> 前置：[per-factor-gate-analysis.md](./per-factor-gate-analysis.md)（tom 的第一性原理论证）
> 目标：将全局 `max_buffer` gate 下沉为每因子级 gate，**改动发生在底部，用户使用不受影响**。

---

## 0. 执行摘要（TL;DR）

### 0.1 架构决策

把 `BreakoutDetector._check_breakouts` 顶端的 `if current_idx < max_buffer: return None` 删除，突破检测始终跑完；每个因子在 `_calculate_xxx` 里按自己的 effective buffer 自检，不足时 `return None`。Scorer 的 `_compute_factor` 对 None 返回 `FactorDetail(unavailable=True, multiplier=1.0)`。模板匹配与挖掘统计统一到 **missing-as-fail** 语义。

### 0.2 总改动量

| 层 | 代码改动 | 行数估计 | 用户可见度 |
|---|---|---|---|
| detector + features | 移除 gate、enrich_breakout 重构、effective buffer | ~80 | 中（BO 数量变化）|
| scorer + UI tooltip | FactorDetail 加 `unavailable` 字段、tooltip "N/A" 渲染 | ~10 | 低（仅 tooltip）|
| mining | data_pipeline 去 fillna、triggered 矩阵加 NaN 保护、yaml 加 gate_mode | ~50 | 零（CLI 无感）|
| live | detail_panel._fmt 加 None 分支 | ~5 | 零 |
| **合计** | | **~145** | **用户基本无感** |

### 0.3 主要收益

1. **概念正交性恢复**：突破判定不再耦合因子 lookback
2. **副产物 bug fix**：`breakout_history`、`active_peaks.right_suppression_days`、drought/streak 在跨 gate 段恢复正确语义
3. **反向因子隐性 bug 提前暴露**：`build_triggered_matrix` 对 lte 因子的 `fillna(0) → <= threshold` 错误触发，per-factor gate 迫使这个 bug 被修
4. **冷启动/短 IPO 股票可被扫描**：新方案下 idx≥20 就能产生 BO（只有 short-buffer 因子有值）

### 0.4 主要代价

- **必须重跑挖掘**：`factor_diag.yaml` / `filter.yaml` 的分布统计基础变化（BO 数量扩大 ~15-20%），旧阈值不能在新 scheme 下直接用
- **跨 scheme 指标不可直接比较**：`baseline_median`、`template_lift` 等因 BO 集合扩大而漂移；需 `gate_mode` 元数据标注
- **短 IPO 股票会产生新 BO**：这个"扩张"可能是期望的（IPO 首破），也可能不是——讨论是否需要 `min_history_days` opt-in 开关

---

## 1. 设计原则

### 1.1 底部改造，用户无感

四层改造的"用户可见性梯度"：

```
detector → features → scorer → UI / CLI
  ↑↑↑       ↑↑        ↑        零
 高污染    中污染    低污染
```

改动集中在 detector / features，scorer 仅加一个布尔字段，UI 仅一个 tooltip 文案分支，CLI 零改动。

### 1.2 类型即契约

- **None = "该因子对该 BO 不可计算"**（lookback 不足/数据缺失）
- **0.0 = "该因子算出来等于零"**（真实值）
- `FactorInfo.nullable=True` 扩展到所有 buffer>0 因子，scorer 的 nullable 分支自动走 `unavailable=True`
- `Breakout` 字段类型 `float=0.0` → `Optional[float]=None`（8 个字段）

### 1.3 显式 missing-as-fail

模板匹配、挖掘的 triggered 矩阵、scorer 的 level 计算——三条路径统一到"unavailable 因子 ≡ 未触发"：
- `template_matcher.match_breakout` 已显式（保持）
- `build_triggered_matrix` / `apply_binary_levels` 需要从"fillna(0) → compare" 显式化为"`~np.isnan(raw) & compare`"（否则反向因子被错判为"完美触发"）

**不支持** abstain（不参与模板）或 partial match（部分匹配）。

### 1.4 向后兼容优先

- FactorDetail 新字段带默认值，构造器不 break
- CachedResults 加 `gate_mode` 字段用 `.get(key, default)` 读
- 旧 JSON 扫描结果能被新代码加载（缺失字段走默认 None）
- 旧 filter.yaml 能被新代码加载，但通过 `check_compatibility` 提示版本 mismatch

---

## 2. 层级改造方案

### 2.1 Detector + Features 层

#### 2.1.1 移除全局 gate

`breakout_detector.py:567-573` 删除 `if current_idx < self.max_buffer: return None`。

**效果**：
- `breakout_history` 包含所有 idx≥total_window 的 BO → drought/streak 恢复诚实
- `active_peaks.right_suppression_days` 对所有 BO 正确更新
- `superseded_peaks` 按真实价格关系归类

**`max_buffer` 参数保留但降级**：不再作为 BO gate，可在 docstring 标记为"数据预处理 buffer 提示"，一个 release cycle 后移除。避免破坏 `test_scanner_superseded.py:51` 的 fixture 签名。

#### 2.1.2 per-factor 自检：集中调度方案

在 `FeatureCalculator.enrich_breakout` 里用 `has_buffer(key) → bool` 守卫函数：

```python
# 伪代码
def enrich_breakout(self, df, bi, symbol, detector=None, atr_series=None, vol_ratio_series=None):
    idx = bi.current_index
    def has_buffer(key: str) -> bool:
        return key not in INACTIVE_FACTORS and idx >= self._effective_buffer(get_factor(key))

    annual_vol = self._calculate_annual_volatility(df, idx) if idx >= 252 else None
    volume   = self._calculate_volume_ratio(df, idx) if has_buffer('volume') else None
    day_str  = self._calculate_day_str(...) if has_buffer('day_str') and annual_vol else None
    overshoot = self._calculate_overshoot(...) if has_buffer('overshoot') and annual_vol else None
    pbm      = self._calculate_pbm(...) if has_buffer('pbm') and annual_vol else None
    pk_mom   = self._calculate_pk_momentum(...) if has_buffer('pk_mom') else None
    pre_vol  = self._calculate_pre_breakout_volume(...) if has_buffer('pre_vol') and vol_ratio_series is not None else None
    ma_pos   = self._calculate_ma_pos(df, idx) if has_buffer('ma_pos') else None
    # age/test/height/peak_vol/streak/drought: buffer=0，永远可算
    return Breakout(..., volume=volume, pbm=pbm, ...)
```

**双保险**：每个 `_calculate_xxx` 的既有"idx 不足 → 0.0"分支改为 `return None`；同时 `_calculate_annual_volatility` 的 `raise ValueError` 改为 `return None`。

#### 2.1.3 Effective buffer（依赖 sub_params）

当前 `FactorInfo.buffer` 是常量，假设 sub_params 取默认值。全局 gate=252 覆盖了这个漏洞；per-factor gate 暴露它。

新增 `FeatureCalculator._effective_buffer(fi: FactorInfo) -> int` 方法：

```python
def _effective_buffer(self, fi: FactorInfo) -> int:
    if fi.key == 'pk_mom':    return self.pk_lookback + self.atr_period
    elif fi.key == 'pre_vol': return 63 + self.pre_vol_window
    elif fi.key == 'ma_pos':  return self.ma_pos_period
    elif fi.key == 'ma_curve': return self.ma_curve_period + 2*self.ma_curve_stride
    elif fi.key == 'dd_recov': return self.dd_recov_lookback
    elif fi.key in {'overshoot','day_str','pbm'}: return 252
    elif fi.key == 'volume':  return 63
    return fi.buffer  # fallback
```

#### 2.1.4 Breakout dataclass 字段类型升级

8 个字段从 `float=0.0` 改为 `Optional[float]=None`：
`volume`, `pbm`, `day_str`, `overshoot`, `pk_mom`, `pre_vol`, `ma_pos`, `annual_volatility`（`dd_recov`/`ma_curve` 同步，即便 INACTIVE）。

不改：`age`/`test`/`height`/`peak_vol`/`streak`（buffer=0，永远可算）、`drought`（已是 Optional）、`stability_score`（非 lookback 因子）。

**联动**：
- `json_adapter.py:268-290` 的 `bo_data.get(x) or 0.0` → `bo_data.get(x)`（None 透传）
- `UI/charts/components/panels.py:100-102` 的 f-string `.2f` 必须加 None 防御
- `analysis/scanner.py:28-39 _serialize_factor_fields` 已按 `fi.nullable` 透传 None，只需确保 registry 设置到位

### 2.2 Scorer + UI 层

#### 2.2.1 FactorDetail 扩展

新增一个布尔字段：

```python
@dataclass
class FactorDetail:
    name: str
    raw_value: float
    unit: str
    multiplier: float
    triggered: bool
    level: int
    unavailable: bool = False   # 新增
```

`_compute_factor` 的 nullable-None 分支设 `unavailable=True`：

```python
if raw_value is None:
    if fi.nullable:
        return FactorDetail(name=fi.key, raw_value=0, unit=fi.unit,
                            multiplier=1.0, triggered=False, level=0,
                            unavailable=True)
    ...
```

**为何不选其他方案**：
- `raw_value: Optional[float]` 会污染下游所有 `f"{raw_value:.2f}"` 代码
- `FactorStatus` 5 态 enum 对当前 UI 需求是过度设计

**multiplier 保持 1.0**（不剔除乘法聚合）：数学等价（`×1.0` 是单位元），但类型保持 `float` 非 Optional，职责由 `unavailable` 独立承担。

#### 2.2.2 Tooltip 显示

`score_tooltip.py` 的 `_build_factor_table`：

| 列 | 旧显示（drought=None）| 新显示（unavailable=True）|
|---|---|---|
| Factor | `drought`（灰 #7C7C7C） | `drought`（浅灰 #B8B8B8）|
| Value | `0d` ❌ 误导 | `N/A` ✅ |
| Multiplier | `×1.00` | `—` (em-dash) |

颜色新增 `styles.py` 的 `factor_unavailable: "#B8B8B8"`。整行统一浅灰褪色，用户扫视能直接抓活跃因子。

**Formula 区保持现状**：`get_formula_string()` 通过 `if f.triggered` 自动省略 UNAVAILABLE 因子（multiplier=1.0 本不该在公式里出现）。

**`markers.py` 无需改动**：图表上 BO 的 quality_score 标注保持简洁（`50`、`72`）。分数歧义（全未触发 vs 全不可算）是乘法模型固有属性，靠 tooltip 承接细节，图表不过载。

#### 2.2.3 API 破坏面

FactorDetail **不入 JSON、不入 mining、不入 template matching**。scorer-ui 这部分改造可**独立发布**，和 detector/mining 改造解耦。

### 2.3 Mining 层

#### 2.3.1 单一污染源修复

**唯一改动点**：`data_pipeline.py:178` 的 `.fillna(0)` 去掉，让 NaN 自然进入 raw_values。

连锁效应：
- `diagnose_direction` / `diagnose_log_scale`（factor_diagnosis.py）已有 `~np.isnan()` 过滤，上游去 fillna 后自动正确
- `analyze_factor`（distribution_analysis.py）已用 `raw_series.isna()` 分组，天然 robust
- `stats_analysis` 的 level_col 特征矩阵 fillna(0) 保留（level=0 本就是"未触发"的正确表达）

**3 处 NaN 保护补丁**：

| 位置 | 改动 |
|---|---|
| `threshold_optimizer.py:28` `build_triggered_matrix` | `(raw >= t)` → `(~np.isnan(raw) & (raw >= t))` |
| `threshold_optimizer.py:295` TPE bounds | `np.quantile(raw, 2%)` 前 `raw = raw[~np.isnan(raw)]` |
| `data_pipeline.py:198` `apply_binary_levels` | 同 build_triggered_matrix，加 NaN 保护 |

**3 处的必要性**：这些是反向因子（`overshoot/age` mode=lte）在 per-factor gate 下的**隐性 bug 触发点**——fillna(0) 后 `0 <= threshold` 几乎恒真，缺失 BO 被判为"完美触发反向条件"。当前被全局 gate 保护；新方案下 overshoot 真实出现 NaN，必须加保护。

#### 2.3.2 factor_diag.yaml 扩展

每因子新增字段：

```yaml
quality_scorer:
  volume_factor:
    enabled: true
    thresholds: [5.0, 10.0]
    values: [1.5, 2.0]
    mode: gte
    # ── per-factor gate 新增 ──
    valid_count: 38214      # 有效 BO 数
    valid_ratio: 0.837      # valid / total
    buffer: 63              # 审计用
```

`_meta` 段新增：

```yaml
_meta:
  gate_mode: per_factor
  total_bo: 45660
  factor_valid_counts: {age: 45660, volume: 38214, day_str: 38811, ...}
```

#### 2.3.3 filter.yaml `_meta.gate_mode`

```yaml
_meta:
  version: 5              # 从 4 升到 5
  gate_mode: per_factor   # 新增
  baseline_median: 0.042
  baseline_scheme: per_factor
```

`template_matcher.check_compatibility` 加 gate_mode 校验，不匹配时 warning 但不拒绝加载。

#### 2.3.4 Template lift 的跨 scheme 硬伤

`template_lift = median(matched) - median(unmatched)`（template_validator.py:370）。`unmatched` 里混入 idx<252 的"必然不匹配"BO，让 `unmatched_median` 偏移，lift 数值跨 scheme 不可直接比较。

**推荐并列双指标**（不破坏现有兼容）：
- `template_lift_global`（现定义）—— 保留用户直观参考
- `template_lift_valid_intersection` —— 仅在"模板所有因子都 valid"的 BO 内计算，跨 scheme 可比

### 2.4 Live 层

#### 2.4.1 必改（唯一）

`live/panels/detail_panel.py:11-14` 的 `_fmt` 加 None 分支：

```python
def _fmt(value) -> str:
    if value is None: return "N/A"
    if isinstance(value, int): return str(value)
    return f"{value:.2f}"
```

**原因**：`daily_runner.py:172` 的 `factors={f: bo[f] for f in template["factors"] if f in bo}` 把 bo dict 的 None 值原样带入。下游 `f"{None:.2f}"` TypeError。5 行以内。

#### 2.4.2 可选增强

`CachedResults` 加 `gate_mode: str = "per_factor"` 字段，`load_cached_results` 用 `.get(key, "bo_level")` 读，旧缓存默认视为旧语义。UI toolbar 可选择提示"legacy cache, suggest refresh"。

#### 2.4.3 零改动（自动继承）

- `ScanManager` 在 scanner.py:555 硬写 `self.max_buffer = get_max_buffer()`，live 通过 `_step2_scan` 复用，detector 层改完自动继承
- Live **不复用** `ScoreDetailWindow` / `FactorDetail` / `score_tooltip`（Grep 证据零匹配）——scorer-ui 改动对 live 透明
- `MatchList` filter、`chart_adapter`、`markers.draw_breakouts_live_mode`、sentiment 集成**全部 None-safe 或不涉及**
- Live 是每日全量重跑（新建 BreakoutDetector），**无增量边界问题**（不存在"昨天的 BO 今天解锁"的奇怪行为）

---

## 3. 集成点与跨层协议

### 3.1 契约矩阵

| 生产方 | 契约 | 消费方 |
|---|---|---|
| detector | `breakout_history` 包含所有 idx≥total_window 的 BO | 无（detector 内部用于 drought/streak）|
| features | `Breakout.{volume,pbm,...}: Optional[float]`，None 语义 = 不可算 | scorer, json_adapter, UI panels, mining, live detail |
| factor_registry | `FactorInfo.nullable=True` 对所有 buffer>0 因子生效 | scorer 的 nullable 分支 |
| scanner | `_serialize_factor_fields` 按 nullable 透传 None（非 fillna 0.0）；`scan_metadata` 加 `gate_mode: per_factor` | mining 的 build_dataframe、live 的 TrialLoader |
| scorer | `FactorDetail.unavailable=True` 仅在 None 因子上；multiplier 保持 1.0 | UI tooltip |
| mining (data_pipeline) | `prepare_raw_values` 不再 fillna；NaN 自然承载 | diagnose, optimizer, validator |
| mining (output) | `factor_diag.yaml` / `filter.yaml` 的 `_meta.gate_mode` 字段 | live TrialLoader, UI 版本检查 |
| live | `MatchedBreakout.factors` 值字典可含 None；`CachedResults.gate_mode` 可选 | UI detail_panel（必须 None-safe）|

### 3.2 关键路径修复顺序

```
factor_registry.nullable 扩展
    ↓
Breakout 字段 Optional 类型
    ↓
features.enrich_breakout 重构（has_buffer + effective_buffer）
    ↓
_check_breakouts 移除 gate
    ↓
scanner._serialize_factor_fields 按 nullable 透传 None
    ↓
[分叉]
    ├─ scorer._compute_factor 加 unavailable 字段 → tooltip "N/A"
    ├─ json_adapter.load 移除 `or 0.0` 垫片
    ├─ UI panels.py 加 None 防御
    ├─ mining.data_pipeline 去 fillna，加 NaN 保护
    ├─ mining 产出 _meta.gate_mode
    └─ live.detail_panel._fmt 加 None 分支
```

**关键点**：factor_registry 的 nullable 扩展是所有下游的触发器，必须最先改。

---

## 4. 实施路线图（按优先级）

### 4.1 P0：必做（挖掘和显示才能正确消费新输出）

- [ ] `factor_registry.py`: buffer>0 因子的 `nullable=True` 全部设置
- [ ] `breakout_detector.py`: 移除 `_check_breakouts` 顶端 gate
- [ ] `breakout_detector.py`: Breakout dataclass 的 8 个字段改 `Optional[float]=None`
- [ ] `features.py`: `_calculate_annual_volatility` 的 raise → return None
- [ ] `features.py`: `enrich_breakout` 重构 + `_effective_buffer`
- [ ] `features.py`: 每个 `_calculate_xxx` 的 idx 短路 `return 0.0 → return None`
- [ ] `analysis/json_adapter.py`: 移除 `or 0.0` 垫片
- [ ] `UI/charts/components/panels.py`: 加 None 防御
- [ ] `breakout_scorer.py`: FactorDetail 加 `unavailable: bool = False`
- [ ] `breakout_scorer.py`: `_compute_factor` 的 nullable-None 分支设 `unavailable=True`
- [ ] `mining/data_pipeline.py`: `prepare_raw_values` 去 `fillna(0)`
- [ ] `mining/data_pipeline.py`: `build_dataframe` 的 `or 0` 改为 None 透传（对因子列）
- [ ] `mining/data_pipeline.py`: `apply_binary_levels` 加 NaN 保护
- [ ] `mining/threshold_optimizer.py`: `build_triggered_matrix` 加 NaN 保护
- [ ] `mining/threshold_optimizer.py`: TPE bounds quantile 去 NaN
- [ ] `mining/param_writer.py` / `template_generator.py`: filter.yaml `_meta.gate_mode` 写入
- [ ] `analysis/scanner.py`: scan_metadata 写入 `gate_mode: per_factor`
- [ ] `live/panels/detail_panel.py`: `_fmt` 加 None 分支

### 4.2 P1：强烈建议

- [ ] `UI/charts/components/score_tooltip.py`: "N/A" / "—" / 浅灰 #B8B8B8 三态渲染
- [ ] `UI/styles.py`: `factor_unavailable: "#B8B8B8"` 颜色
- [ ] `mining/threshold_optimizer.py`: greedy beam 的 mask 加 `valid` 保护
- [ ] `mining/factor_diagnosis.py`: factor_diag.yaml 加 `valid_count`/`valid_ratio`/`buffer`
- [ ] `mining/template_matcher.py`: `check_compatibility` 加 gate_mode 校验
- [ ] `live/pipeline/results.py`: CachedResults 加 `gate_mode` 字段

### 4.3 P2：Nice-to-have

- [ ] `mining/template_validator.py`: 并列输出 `template_lift_valid_intersection`
- [ ] `mining/factor_diagnosis.py`: factor_diag.yaml 加 `cross_factor_valid_intersection`
- [ ] mining CLI 打印 `factor valid counts`
- [ ] `live/panels/toolbar.py`: legacy cache 提示
- [ ] 补充测试（detector gate removed / per-factor availability / drought cross-gate / effective buffer sub_param）

### 4.4 P3：未来演进

- 移除 `max_buffer` 参数（`BreakoutDetector.__init__`、scanner.py 签名、UI/main.py:383）
- 移除 `FactorInfo.has_nan_group`（合并为 `nullable`）
- `FactorInfo.buffer` 升级为 callable（`buffer_fn(config) → int`）

---

## 5. 迁移计划

### 5.1 阶段 A：旧 scheme snapshot

```bash
cp -r outputs/statistics outputs/statistics.bo_level_snapshot
cp configs/params/filter.yaml configs/params/filter.bo_level.yaml
cp configs/params/factor_diag.yaml configs/params/factor_diag.bo_level.yaml
cp configs/params/all_factor.yaml configs/params/all_factor.bo_level.yaml
```

### 5.2 阶段 B：代码改造

按 §4.1 P0 列表推进。每个改动独立 commit 以支持 git revert。

### 5.3 阶段 C：代码兼容 + 新旧并存

- `template_matcher.load_filter_yaml` 读 `gate_mode`，不匹配时 warning 但不拒绝
- Live UI 可同时持两份 filter.yaml（按 gate_mode 标注），过渡一周

### 5.4 阶段 D：全量重挖

```bash
uv run -m BreakoutStrategy.analysis.scanner   # 或 scripts/ 下入口
uv run -m BreakoutStrategy.mining.pipeline
```

产出 `outputs/statistics/<timestamp>_per_factor/`。TPE 预计数小时。

### 5.5 阶段 E：切流量

- 比对新旧 top-K 模板重叠率（同 scheme 内 top-1 thresholds 差距 <10% 视为健康）
- OOS validation verdict 对比：新版 PASS → 切换；新版 FAIL 而旧版 PASS → 回滚到阶段 A snapshot

### 5.6 阶段 F：清理备份

阶段 E 稳定运行 1 周后，删除 `outputs/statistics.bo_level_snapshot` 等备份。

---

## 6. 用户可见性矩阵

| 场景 | 用户看到 | 是否期望 |
|---|---|---|
| 扫描完成后的 BO 列表 | 数量增加 ~15-20%（新增 idx<252 的早期 BO）| 是（新语义真相）|
| 图表上的 BO 标记 | 早期段多出几个标记 | 是 |
| BO 分数角标（markers）| 完全一致（`50`、`72`）| ✅ 无感 |
| Score tooltip（dev UI）| drought=None 等显示 "N/A" 代替 "0d" | 是（修正误导）|
| Live DetailPanel | `volume=N/A` 类显示 | 是（修正误导）|
| Live MatchList | 候选数量可能小幅增加（依赖模板是否含 volatility 因子）| 是 |
| filter.yaml `_meta` | 新增 `gate_mode` 字段 | ✅ 审计可见 |
| factor_diag.yaml | 新增 `valid_count`/`valid_ratio` 字段 | ✅ 审计可见 |
| 挖掘 CLI stdout | 新增 `Factor valid counts` 打印 | ✅ 诊断可见 |
| 用户自定义 scan_config / filter.yaml | **需重挖**，旧阈值分布基础已变 | ⚠️ 需文档提示 |

**核心结论**：正常使用路径（扫描、选股、查看图表、live 告警）用户基本无感；仅在点开 tooltip / 阅读 yaml 时能看到"N/A 代替 0d"和"新增审计字段"——这些都是修正误导，不是新功能学习成本。

---

## 7. 风险清单

### 7.1 架构风险

| 风险 | 可能性 | 影响 | 缓解 |
|---|---|---|---|
| `_effective_buffer` 遗漏某个因子的 sub_param 依赖 | 中 | 短窗场景下该因子 gate 失配 | 新增因子时 SKILL.md 提醒更新 `_effective_buffer`；补测试 |
| 旧 JSON cache 在新代码下加载产生不一致渲染 | 低 | 用户看到 BO 数不稳定 | `gate_mode` 元数据 + UI toolbar 提示 |
| 短 IPO 股票扩大到扫描结果内，用户不期望 | 中 | 结果集变噪 | 讨论是否加 `min_history_days` opt-in（不默认启用）|
| 跨 scheme 比较 `baseline_median` / `template_lift` 产生误判 | 高 | 验证结论跨版本被误读 | yaml 里加 `baseline_scheme` 字段 + validation_report.md 加 disclaimer |

### 7.2 实施风险

| 风险 | 可能性 | 影响 | 缓解 |
|---|---|---|---|
| Breakout Optional 迁移遗漏某个 UI 显示点 | 中 | 某 panel crash on None | 分阶段改，每改一个点跑 smoke test |
| mining 的 NaN 保护漏加某个比较点 | 低 | 反向因子被误触发 | `test_per_factor_availability` 覆盖反向因子 |
| 重挖后 TPE 找不到好的阈值（因 baseline 变化）| 低 | top-1 模板 verdict FAIL | 阶段 E 回滚机制 |
| 用户在迁移过程中混用新旧 trial | 中 | 选股结果异常 | `check_compatibility` 强校验 + toolbar 提示 |

### 7.3 语义风险

| 风险 | 可能性 | 影响 | 缓解 |
|---|---|---|---|
| Template `missing-as-fail` 让含 volatility 因子的模板对短 lookback BO "无判断力" | 高 | 这些 BO 集中落在 unmatched | 这是**期望行为**，不是 bug；report 中说明 |
| drought=None 的 "首次突破" 语义 vs "未观察到前序" 语义混淆 | 低 | 用户可能期望 drought 反映"scan range 内首次" | 本次不改 drought 语义；若需可单独讨论（用户先前提出过）|
| `unavailable=True` 与 `triggered=False` 在 level=0 时的 UI 混淆 | 低 | tooltip 显示不一致 | 浅灰 + "N/A" 视觉区分足够 |

---

## 8. 开放问题（团队建议优先讨论）

1. **短 IPO 股票的扩展行为是否需要 opt-in？** 推荐默认开启（相信 mining trigger_rate 的自然过滤），但保留 scanner 层 `min_history_days` 作为可选开关。
2. **`max_buffer` 参数 deprecation timeline？** 保留一个 release cycle 后再移除，避免破坏 `test_scanner_superseded.py` 和其他测试签名。
3. **Breakout 字段 Optional 是否分阶段？** 推荐一次性全改，否则读端要写垫片（`bo.volume or 0.0`）反而更乱。
4. **`_effective_buffer` 放在哪？** 推荐 `FeatureCalculator._effective_buffer` 方法（访问实例 sub_param attrs），不改 FactorInfo 结构。
5. **`template_lift_valid_intersection` 上不上？** P2 项，若挖掘质量评估在新 scheme 下不够稳再加。

---

## 9. 附录

### 9.1 改动点速查表（按文件）

| 文件 | P0 改动 | P1 改动 | 备注 |
|---|---|---|---|
| `BreakoutStrategy/factor_registry.py` | nullable 扩展 | - | 触发所有下游 |
| `BreakoutStrategy/analysis/breakout_detector.py` | 移除 gate、Breakout Optional | - | - |
| `BreakoutStrategy/analysis/features.py` | enrich_breakout 重构、`_effective_buffer`、`_calculate_xxx` return None | - | - |
| `BreakoutStrategy/analysis/scanner.py` | scan_metadata `gate_mode` | - | `_serialize_factor_fields` 已 OK |
| `BreakoutStrategy/analysis/json_adapter.py` | 移除 `or 0.0` 垫片 | - | - |
| `BreakoutStrategy/analysis/breakout_scorer.py` | FactorDetail `unavailable` 字段 | - | - |
| `BreakoutStrategy/UI/charts/components/panels.py` | None 防御 f-string | - | - |
| `BreakoutStrategy/UI/charts/components/score_tooltip.py` | - | "N/A" / "—" / 灰字 | - |
| `BreakoutStrategy/UI/styles.py` | - | `factor_unavailable` 颜色 | - |
| `BreakoutStrategy/mining/data_pipeline.py` | 去 fillna、apply_binary_levels 加 NaN 保护 | - | 单一污染源 |
| `BreakoutStrategy/mining/threshold_optimizer.py` | build_triggered_matrix + TPE bounds 加 NaN | greedy beam mask | - |
| `BreakoutStrategy/mining/factor_diagnosis.py` | - | factor_diag.yaml 加 valid_count/valid_ratio/buffer | 上游改后自动 robust |
| `BreakoutStrategy/mining/template_generator.py` / `param_writer.py` | filter.yaml `_meta.gate_mode` | - | - |
| `BreakoutStrategy/mining/template_matcher.py` | - | check_compatibility 加 gate_mode | - |
| `BreakoutStrategy/mining/template_validator.py` | - | P2: template_lift_valid_intersection | - |
| `BreakoutStrategy/live/panels/detail_panel.py` | `_fmt` None 分支 | - | 唯一必改的 live 代码 |
| `BreakoutStrategy/live/pipeline/results.py` | - | CachedResults `gate_mode` 字段 | - |

### 9.2 测试清单

**现有测试需更新**：
- `analysis/tests/test_scanner_superseded.py:51` —— `get_max_buffer()` 传参改为不传或 0
- `analysis/test/test_integrated_system.py:139` —— f-string 加 None 防御

**建议补新测试**：
- `test_detector_gate_removed` —— idx=50 的 BO 应出现在 breakout_history
- `test_per_factor_availability` —— idx=100 时 `bo.volume` 非 None 而 `bo.pbm` 为 None
- `test_drought_cross_gate` —— 跨 gate 两个 BO 的 drought 正确反映距离
- `test_effective_buffer_sub_param` —— `ma_pos_period=30` 时 idx=25 的 ma_pos 为 None
- `test_template_matcher_missing_as_fail_reverse_factor` —— overshoot=None 不触发 lte 模板
- `test_json_cache_backward_compat` —— 旧 JSON 能被新代码加载不崩

**Semantic snapshot 回归**：固定 fixture（如 AAPL 2020-2024），对 idx≥252 的 BO 的所有因子值做**bit-for-bit 相等**比对（新方案只是新增 idx<252 BO，不应改变旧 BO 的结果）。

### 9.3 团队工作区清理

本次团队讨论产出在 `docs/research/.per-factor-gate-impl-workspace/` 下的 4 份专家报告：
- detector-arch.md
- scorer-ui.md
- mining-pipeline.md
- live-integration.md

合成本报告后，工作区可以保留作为"专家视角原始材料"（解释本报告某一节时可追溯），或在阶段 F 清理备份时一并删除。

---

*Team per-factor-gate-impl · 2026-04-15*
