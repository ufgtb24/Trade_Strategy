# Detector-Arch 改造方案：突破检测与因子计算层

> 作者：tom（per-factor-gate-impl 团队，detector-arch 专家）
> 范围：`BreakoutStrategy/analysis/breakout_detector.py`、`features.py`、`factor_registry.py`、`analysis/scanner.py`、`analysis/tests/`
> 定位：per-factor gate 的"底部改造"层 —— 把 BO-level gate 拆解为因子级自检，并修复 detector 状态被 gate 污染的问题。
> 前置阅读：`docs/research/per-factor-gate-analysis.md`（第一性原理可行性论证）

---

## 1. 当前实现关键路径

### 1.1 Gate 生效路径（从 scanner 到 detector）

- `factor_registry.get_max_buffer()`（factor_registry.py:243-255）：扫描 `_ACTIVE_FACTORS` 返回 `max(fi.buffer)`。当前活跃集含 `overshoot/day_str/pbm`（buffer=252），所以 `max_buffer=252`。
- `ScanManager.__init__` scanner.py:555：`self.max_buffer = get_max_buffer()`，随后随参数向下游传。
- `compute_breakouts_from_dataframe` scanner.py:122, 159：把 `max_buffer` 传给 `BreakoutDetector(max_buffer=...)`。
- `BreakoutDetector.__init__` breakout_detector.py:226, 273：存为 `self.max_buffer`。
- `BreakoutDetector._check_breakouts` breakout_detector.py:567-573：**全局硬门槛**。`current_idx < self.max_buffer` 时直接 `return None`。

### 1.2 Gate 被污染的副作用

门槛之前，`_detect_peak_in_window`（add_bar:339-340）仍然照常检测并累积 `active_peaks`。**门槛之后**的 `_check_breakouts`：
- pre-gate BO 不产生 `BreakoutInfo` → 上层 `all_breakouts` 缺失该事件。
- `self.breakout_history` 不追加（breakout_detector.py:609-614）→ `get_recent_breakout_count` 对 idx∈[252, 252+streak_window) 的 BO 偏小；`get_days_since_last_breakout` 对同区间 BO 偏大或返回 None。
- `active_peaks` 的 `right_suppression_days` 不被更新；若 pre-gate BO 本该让 peak 超越 3%，该 peak 仍被当作 active 保留（breakout_detector.py:585-604）。**阻力状态被扭曲**。

### 1.3 因子计算的严格契约

- `FeatureCalculator.enrich_breakout` features.py:134 无条件调用 `_calculate_annual_volatility(df, idx)`。
- `_calculate_annual_volatility` features.py:523-529：**唯一**在生产路径上 `raise ValueError` 的严格契约点。`day_str/overshoot/pbm` 复用其返回值但自己不检查 idx（features.py:564-617，都只判 `annual_volatility <= 0`）。
- 其余方法各自有隐式 idx 保护（但不严格）：
  - `_calculate_gain_5d` features.py:490-491：`idx < self.gain_window` 返回 0.0（**不是 None**）。
  - `_calculate_volume_ratio` features.py:251-285：`max(0, index - 63)` 直接截断，窗口不足不警告（`DEBUG_VOLUME` 会打 `INCOMPLETE_WINDOW`）。
  - `_calculate_ma_pos` features.py:736-737：`idx < period - 1` 返回 0.0。
  - `_calculate_ma_curve` features.py:814-815：`idx < period + 2*k` 返回 0.0。
  - `_calculate_pk_momentum` features.py:450-454：`delta_t > pk_lookback or delta_t <= 0` 或 `atr_value<=0` 返回 0.0。
  - `_calculate_pre_breakout_volume` features.py:866-873：`vol_ratio_series` 的短窗自行返回 0.0。

**证据结论**：features 层 "0.0 = 缺失" 已经是事实上的语义，只有 `_calculate_annual_volatility` 用 `raise`。Gate 移除后需要统一到 `return None`。

---

## 2. 改造方案

### 2.1 总体策略

1. **Detector 层**：删掉 `_check_breakouts` 顶端 gate；保留 `max_buffer` 参数但降级为"仅作数据预处理 buffer 提示"（或完全移除）。
2. **Features 层**：每个 `_calculate_xxx` 方法自带 `idx < effective_buffer` 短路 → `return None`。
3. **Registry 层**：`FactorInfo.buffer` 从常量升级为 "函数式 effective buffer"，允许根据 `sub_params` 动态计算。
4. **Dataclass 层**：`Breakout` 的 lookback 因子字段从 `float=0.0` 改为 `Optional[float]=None`。

### 2.2 Detector Gate 移除

```python
# breakout_detector.py _check_breakouts，替换 567-573
def _check_breakouts(self, current_idx, current_date):
    # 删除全局 gate。突破是纯局部事实（仅依赖 active_peaks 与当前 bar），
    # 因子 lookback 不足由下游 _calculate_xxx 各自判断。
    breakout_price = self._get_measure_price(current_idx, self.breakout_mode)
    ...
```

**效果**：
- `breakout_history` 对所有 idx≥total_window 的 BO 完整；drought/streak 在短 lookback 段重新诚实。
- `active_peaks.right_suppression_days` 对所有 BO 正确更新；peak 生命周期与价格事件同步。
- `superseded_peaks` 按真实价格关系归类，不被 gate 遮蔽。

**风险点**：`self.max_buffer` 字段变为 dead code。建议**保留参数入口**但在 docstring 标记 deprecated，留一个 release cycle 的 backward-compat，避免破坏 `test_scanner_superseded.py` 的参数传递签名。

### 2.3 Per-factor 自检：统一调度方案

三种候选：

| 方案 | 位置 | 优点 | 缺点 |
|---|---|---|---|
| **A. enrich_breakout 集中调度** | features.py:130-188 | 一处修改，行为明确；短路条件显式传入 | 每增一个因子要改 `enrich_breakout` |
| B. 每个 `_calculate_xxx` 内部短路 | features.py:500-874 | 修改分散但职责单一 | `day_str/overshoot/pbm` 依赖 `annual_volatility`，需 None 传播 |
| C. 装饰器 + registry 查表 | 新基础设施 | 因子声明式 | 抽象成本高、调试链变长 |

**推荐方案 A + B 混合**（避免过度抽象，与奥卡姆剃刀对齐）：
- `enrich_breakout` 在调用前先查 effective buffer，若不满足 **直接传 None 给 Breakout 字段**，不调 `_calculate_xxx`。
- `_calculate_xxx` 的既有"idx 不足→0.0"分支改为 return None，作为**双保险**。

伪代码（集中调度核心）：

```python
# features.py enrich_breakout 重构后骨架
def enrich_breakout(self, df, breakout_info, symbol, detector=None,
                    atr_series=None, vol_ratio_series=None):
    idx = breakout_info.current_index
    inactive = INACTIVE_FACTORS
    reg = {fi.key: fi for fi in get_active_factors()}

    def has_buffer(key: str) -> bool:
        """判断某因子在该 idx 下是否满足 effective buffer。"""
        if key in inactive or key not in reg:
            return False
        return idx >= self._effective_buffer(reg[key])

    # 关键共享中间变量：只有 annual_volatility 够时才算
    annual_vol = self._calculate_annual_volatility(df, idx) if idx >= 252 else None

    volume  = self._calculate_volume_ratio(df, idx)  if has_buffer('volume')  else None
    day_str = self._calculate_day_str(...)           if has_buffer('day_str') and annual_vol else None
    overshoot = self._calculate_overshoot(...)       if has_buffer('overshoot') and annual_vol else None
    pbm     = self._calculate_pbm(df, idx, annual_vol) if has_buffer('pbm') and annual_vol else None
    pk_mom  = self._calculate_pk_momentum(...)       if has_buffer('pk_mom') else None
    pre_vol = self._calculate_pre_breakout_volume(...) if has_buffer('pre_vol') and vol_ratio_series is not None else None
    ma_pos  = self._calculate_ma_pos(df, idx)        if has_buffer('ma_pos')  else None
    # age/test/height/peak_vol/streak/drought: buffer=0，无需门控
    ...
    return Breakout(..., volume=volume, pbm=pbm, day_str=day_str, ...)
```

**关键设计决策**：`annual_volatility` 本身不是注册因子，但它是三个因子的共享前置依赖。保留 "idx<252 → None" 的一次性短路，避免三个因子重复计算 idx 判断。

### 2.4 Effective Buffer（依赖 sub_params）

当前 `FactorInfo.buffer` 是常量，假设 sub_params 取默认值。问题清单：

| factor | 默认 buffer | 依赖的 sub_params | 若 sub_param 改大 |
|---|---|---|---|
| overshoot | 252 | `gain_window=5` | 不影响（252 来自 annual_vol） |
| pbm | 252 | `continuity_lookback=5` | 不影响 |
| pk_mom | 44 | `pk_lookback=30` | **应为 pk_lookback + atr_period** |
| pre_vol | 73 | `pre_vol_window=10` | **应为 63 + pre_vol_window** |
| ma_pos | 20 | `ma_pos_period=20` | **应等于 ma_pos_period** |
| dd_recov | 252 | `dd_recov_lookback=252` | **应等于 dd_recov_lookback** |
| ma_curve | 50 | `ma_curve_period=50`, `ma_curve_stride=5` | **应为 period + 2*stride** |

当前 gate=252 覆盖了全部，所以 sub_param 调大不会立刻暴露。但 per-factor gate 之后每个因子独立判断，必须计算**正确的 effective buffer**。

**推荐方案**：给 `FactorInfo` 加一个可选字段 `buffer_fn`，或把 `buffer` 改成 callable。为了最小改动，建议在 `FeatureCalculator` 内建一个方法：

```python
def _effective_buffer(self, fi: FactorInfo) -> int:
    """根据实际 sub_params 计算该因子在当前 config 下的最少历史 bar 需求。"""
    if fi.key == 'pk_mom':
        return self.pk_lookback + self.atr_period
    elif fi.key == 'pre_vol':
        return 63 + self.pre_vol_window
    elif fi.key == 'ma_pos':
        return self.ma_pos_period
    elif fi.key == 'ma_curve':
        return self.ma_curve_period + 2 * self.ma_curve_stride
    elif fi.key == 'dd_recov':
        return self.dd_recov_lookback
    elif fi.key in {'overshoot', 'day_str', 'pbm'}:
        return 252  # annual_volatility 硬编码
    elif fi.key == 'volume':
        return 63   # VOLUME_LOOKBACK 硬编码
    return fi.buffer  # fallback to registry default
```

**更纯粹的替代**：`FactorInfo.buffer` 改为 `str | int`，当是 str 时以 `FeatureCalculator` 的 attr 名解析（如 `"pk_lookback+14"`）。但这样引入 mini-DSL，过度设计。当前硬编码映射清晰可读。

### 2.5 Breakout Dataclass 字段 None 语义扩展

影响清单详见 §3.1，这里先给方案。

**保守方案**：字段类型保持 `float`，用 0.0/None 二值化（依赖 `FactorInfo.nullable` 决定写 None 还是 0.0）。**缺点**：json_adapter 与 scorer 必须同步理解二值语义，容易误解。

**推荐方案**：所有 lookback 因子字段改为 `Optional[float] = None`，`Optional[int] = None`。含：
- `volume: Optional[float] = None`
- `pbm: Optional[float] = None`
- `day_str: Optional[float] = None`
- `overshoot: Optional[float] = None`
- `pk_mom: Optional[float] = None`
- `pre_vol: Optional[float] = None`
- `ma_pos: Optional[float] = None`
- `annual_volatility: Optional[float] = None`
- `dd_recov: Optional[float] = None`（即便 INACTIVE，类型应一致）
- `ma_curve: Optional[float] = None`
- `atr_value: Optional[float] = None`（可选，若 ATR 短窗也视为 unavailable）

**不改**：`age/test/height/peak_vol/streak` 的 buffer=0，永远可算，保持 `int/float`。`drought` 已是 `Optional[int]`。`stability_score` 是"评估指标"不是 lookback 因子，保持 float。

---

## 3. 受影响代码清单

### 3.1 必改（detector + features 责任域）

| 文件 | 位置 | 改动 | 原因 |
|---|---|---|---|
| `breakout_detector.py` | 567-573 | 删除 `if current_idx < self.max_buffer: return None` | 核心解耦 |
| `breakout_detector.py` | 226, 250-253, 273 | `max_buffer` 字段 deprecate（保参数但 docstring 标记不再生效） | 避免破坏测试签名 |
| `breakout_detector.py` | Breakout @dataclass 131-176 | 字段类型 `float=0.0`→`Optional[float]=None`（§2.5 清单） | per-factor None 语义 |
| `features.py` | 523-529 `_calculate_annual_volatility` | `raise ValueError` → `return None`；补 docstring 说明新契约 | 顺应新语义 |
| `features.py` | 130-188 `enrich_breakout` | 按 §2.3 重构调度逻辑；引入 `has_buffer` helper 与 `_effective_buffer` 方法 | 集中 gate 实现 |
| `features.py` | 每个 `_calculate_xxx` 的隐式 idx 保护 | `return 0.0` → `return None`（双保险；490, 736-737, 814-815 等） | 语义统一 |
| `factor_registry.py` | FactorInfo 55-68 | 保留 `buffer` 常量作为 fallback；effective 逻辑交给 `FeatureCalculator._effective_buffer` | 避免 registry 耦合 calculator |
| `factor_registry.py` | 243-255 `get_max_buffer` | 保留函数（UI/scanner 的数据预处理 buffer 仍可用它算"最长预热期"）；docstring 更新 "不再作为 BO gate" | 仅语义改变 |

### 3.2 可选改善

| 文件 | 位置 | 改动 | 原因 |
|---|---|---|---|
| `factor_registry.py` | FactorInfo | 新增 `buffer_fn: Optional[Callable]` 字段 | 若 §2.4 的硬编码映射不够优雅 |
| `features.py` | `_calculate_ma_pos` | 移除 `idx < period - 1` 隐式短路，让上层 gate 统一处理 | 单一职责 |
| `features.py` | `_calculate_volume_ratio` | 短窗时 `return None` 而非 `ratio=1.0` | 当前 "无基线→1.0" 是降级行为，应改 |
| `breakout_detector.py` | `__init__` | 删除 `max_buffer` 参数 | 若确认无 backward-compat 需求 |

### 3.3 联动影响（由其他成员处理，但我需要标注）

| 文件 | 影响 | 相关成员 |
|---|---|---|
| `analysis/json_adapter.py:268-290` | `bo_data.get("volume") or 0.0` 把 None 降级为 0.0，新语义下需 `bo_data.get("volume")`（None 透传） | scorer-ui |
| `analysis/scanner.py:28-39 _serialize_factor_fields` | 已根据 `fi.nullable` 透传 None，只要 registry 把 lookback 因子全设 `nullable=True` 即自动适配 | scorer-ui（调整 nullable） |
| `analysis/scanner.py:243-245` 注释 | 目前声称"BO 级 max_buffer gate"，需重写为"per-factor gate" | scorer-ui / self |
| `analysis/breakout_scorer.py:181-221` | `_compute_factor` 的 None 分支已存在，但 tooltip/解释需扩展 unavailable 语义 | scorer-ui |
| `UI/charts/components/panels.py:100-102` | `f"{breakout.volume:.2f}x"`——`None.:.2f` 会崩，必须加 None 分支 | scorer-ui |
| `BreakoutStrategy/UI/main.py:383` | `max_buffer=get_max_buffer()` 的注释需更新（仍可用作数据 buffer 估计） | live-integration |

---

## 4. 用户可见性评估

### 4.1 完全无感（底部改造，不泄漏到用户界面）

- **扫描窗口语义**：用户指定 `start_date='2025-10-15'` 时，behavior 不变——数据仍加载足量历史。
- **因子计算契约**：`_calculate_annual_volatility` 从 raise 改 return None 是内部实现细节。
- **gate 移除本身**：从用户视角，唯一可感知的是"同一股票多出几个早期 BO"（见下）。

### 4.2 有残留 surface（需明确标注）

1. **BO 数量会增加**
   - 原 pre-gate BO 现在会出现在 `all_breakouts`、`breakouts.json`、chart 上。
   - **新旧扫描结果无法直接对比**。`scan_metadata` 需加 `gate_mode: 'per_factor'` 字段（这是 scorer-ui / live-integration 的工作）。

2. **drought/streak 数值变化**
   - idx∈[252, 252+streak_window) 区间的 BO 的 drought/streak 会**变诚实**（能看到 pre-252 的近邻突破）。
   - **这是 bug fix，不是回归**。但若用户有根据旧 drought 值设定的自定义 filter.yaml，结果会偏移——**需要重跑挖掘**。

3. **因子值 None 暴露到 Breakout 字段**
   - 用户代码如果直接 `bo.volume * 2` 会 TypeError。
   - 影响扇面：`UI/charts/components/panels.py:100-102` 的 f-string 会炸（`None.:.2f`）。
   - **这是 scorer-ui 的兜底责任**，但 detector-arch 侧需要文档化该 surface。

4. **短 IPO 股票行为变化**
   - 只有 50 天历史的股票，旧架构因为 max_buffer=252 永远不产生 BO；新架构 idx≥20 就可能产生（只有 age/height 等短 buffer 因子有值）。
   - **意料之外的扩大**：对冷启动股票，扫描结果会从 0 BO 变成若干 BO。可能是用户期望的（新 IPO 有初次突破），也可能不是。**团队需讨论是否在 scanner 层加"全局最低样本量"门槛**作为独立开关，以保留用户对冷启动数据的过滤权。

### 4.3 无法完全透明的结论

**明确"不可完全透明"的点**：#1（BO 数量）+ #2（drought/streak 变化）。这是语义修复带来的预期收益，不是 bug。应在 release note 与 `gate_mode` 元数据中标注。

---

## 5. 测试影响清单

### 5.1 现有测试

搜索到的相关测试：

- `BreakoutStrategy/analysis/tests/test_scanner_superseded.py`
  - **不会因 gate 移除而断裂**：该测试聚焦 superseded peak 序列化，CVGI 扫描窗口是 2025-10-15 到 2026-04-14，需要足够 lookback 才能产生 BO；`get_max_buffer()` 传给 scanner 之后，per-factor gate 下扫描范围内 idx 都已 >>252，BO 集合与旧行为基本一致。
  - **需更新**：行 51 传 `get_max_buffer()`，新语义下 `max_buffer` 参数已 deprecated。最好改为不传或传 0，显式表达 "per-factor gate 取代 BO-level gate"。

- `BreakoutStrategy/analysis/test/test_integrated_system.py`
  - 老式 smoke test，不用 pytest；直接跑 AAPL.pkl 印统计。
  - **行 139** `f"{bo.volume:.2f}倍, PBM: {bo.pbm*1000:.2f}"` 在新语义下 bo.volume 可能 None → 会崩。
  - **需更新**：加 None 防御 `f"{bo.volume:.2f}" if bo.volume is not None else "N/A"`。

- `BreakoutStrategy/live/tests/test_daily_runner_matched_fields.py` 行 64-65：只断言 `raw_breakout["index"]`，不触及因子值。**无影响**。

### 5.2 跨 gate 场景的新测试建议

建议补的单元测试（但**本次 scope 不写**，留给实施阶段）：

1. `test_detector_gate_removed`：构造 300-bar 合成数据，verify idx=50 的 BO 出现在 breakout_history（旧行为会被 gate 掉）。
2. `test_per_factor_availability`：idx=100 的 BO，verify `bo.volume` 有值（63≤100）、`bo.pbm` 为 None（100<252）。
3. `test_drought_cross_gate`：构造 idx=100 和 idx=260 两个 BO，verify idx=260 的 drought=160（旧行为：None 因 idx=100 不在 history）。
4. `test_effective_buffer_sub_param`：`ma_pos_period=30` 时，idx=25 的 BO 的 `ma_pos` 应为 None（30>25）。

### 5.3 跨套件回归建议

在 CI 里增加一个"**semantic snapshot**"：固定 fixture (如 AAPL 2020-2024) 在 per-factor gate 下，对**idx≥252** 的 BO 的所有因子值与旧实现 **bit-for-bit 相等**（只是新增 idx<252 的 BO）。这是验证"不引入意外偏移"的最强保护。

---

## 6. 数据迁移（detector 层的输出契约变化）

### 6.1 扫描结果 JSON 集合会扩展

- 同一 symbol、同一扫描参数，新扫描会产生**更多** BO（包含原 pre-gate 的 idx<252 区段）。
- 这些新 BO 的因子字段会混合 `None`（依赖 annual_vol 的三个因子 + buffer 不足的其他因子）与真实值。
- 下游 mining 成员需要：
  - `prepare_raw_values` 不再 `fillna(0)`，按 factor-wise valid_mask 统计分位数。
  - `threshold_optimizer` 的 trigger_rate 分母使用有效样本集。
  - 详见 per-factor-gate-analysis.md §3.2，由 mining-pipeline 成员细化。

### 6.2 scan_metadata 需标记 gate_mode

**detector-arch 不直接写 metadata**（scanner.py 里写），但强烈要求 scorer-ui / live-integration 成员在 `_scan_single_stock` 的输出 dict 加：
```python
"scan_metadata": {..., "gate_mode": "per_factor"}
```
旧 JSON 里没有此字段，可按 `gate_mode = meta.get("gate_mode", "bo_level")` 兼容。

### 6.3 breakout_history 缓存

`BreakoutDetector._save_cache` breakout_detector.py:669-735 把 `breakout_history` 序列化到 .pkl。旧 cache 在新代码下会被加载（`_load_cache` 对 max_buffer 不做验证），但 history 条目仍是旧 gate 语义（缺失 idx<252 段）。建议：
- **live 场景**（detector 持续累积）：建议**一次性 flush 旧 cache**，重跑 bootstrap。
- **回测场景**：use_cache=False 是默认路径，无影响。

---

## 7. 留给团队的开放问题

1. **冷启动股票的扩展行为是否需要 opt-in？**
   短 IPO 股票在新架构下会产生大量"部分 unavailable factors"的 BO。是否需要 scanner 层保留 `min_history_days` 开关让用户显式启用？还是完全信任 mining 的 trigger_rate 自然过滤？
   → 倾向于"完全信任下游"，但需要 mining-pipeline 成员确认其 valid_mask 逻辑能吸收这种极端情况。

2. **`max_buffer` 参数的 deprecation timeline？**
   立即删还是保留一个 release cycle？影响 `test_scanner_superseded.py` fixture（行 51）、`scanner.py` 的参数传递签名、`UI/main.py:383`。建议保留参数但降级为"数据预处理 buffer 估计器"，完全移除推迟到下一次大重构。

3. **`_effective_buffer` 应该放在 FeatureCalculator 还是 FactorInfo？**
   方案 A：FeatureCalculator 方法（访问 sub_param attrs）——当前推荐。
   方案 B：FactorInfo.buffer_fn callable 字段（接受一个 config dict）——更声明式但需要改 registry 结构。
   → 建议 A（最小改动）；若后续新增因子需要复杂 buffer 逻辑再升级。

4. **Breakout 字段类型的 breaking change 边界？**
   `Optional[float] = None` 会影响所有读取 `bo.volume` 等字段的下游代码（scorer / UI / json_adapter / tests）。这个 surface 是否要求**全量同步改**还是分阶段？
   → 分阶段的话需要在读端做 `bo.volume or 0.0` 兼容垫片；scorer-ui 成员主责。

5. **`_calculate_annual_volatility` 是否应保留 raise 作为 debug 模式？**
   改 return None 后，配置错误（比如 idx 传错）不再立刻炸。可以加 `if DEBUG_VOLATILITY: raise ValueError(...)` 环境变量开关。
   → 不必，per-factor trigger_rate 监控已足够暴露配置错误（per-factor-gate-analysis.md §4.3）。

---

## 附录 A：需下游成员同步确认的 contract

- **scorer-ui**：`Breakout.volume/pbm/day_str/overshoot/pk_mom/pre_vol/ma_pos/annual_volatility` 全部可能是 None；`_compute_factor` 的 nullable 分支需对所有 lookback 因子生效。
- **mining-pipeline**：`_serialize_factor_fields` 已按 `fi.nullable` 写 None；mining 侧把 `nullable` 语义 fully wired 进分位数/阈值搜索。
- **live-integration**：`max_buffer` 参数可能被 deprecated；live 的 `BreakoutDetector` 持续累积场景需一次性重建 cache。

## 附录 B：改动点速查表（detector-arch 责任域）

| 文件 | 行号 | 改动类型 | 具体 |
|---|---|---|---|
| breakout_detector.py | 567-573 | 删除 | 全局 gate |
| breakout_detector.py | 131-176 | 类型修改 | Breakout lookback 字段改 Optional |
| breakout_detector.py | 226-273 | 语义降级 | max_buffer 参数保留但无效 |
| features.py | 130-188 | 重构 | enrich_breakout 集中调度 |
| features.py | 523-529 | 契约修改 | raise → return None |
| features.py | 各 _calculate_xxx | 语义统一 | idx 不足时 return None |
| features.py | 新增方法 | 新增 | `_effective_buffer(fi)` |
| factor_registry.py | 243-255 | docstring 更新 | get_max_buffer 不再作为 BO gate |
