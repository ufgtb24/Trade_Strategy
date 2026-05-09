# Show Filtered Breakouts in Dev UI

## 背景

`configs/user_scan_config.yaml` 配置了 `min_price`/`max_price` BO 价格门。当前实现把过滤放在 enrich + score 完成之后（`scanner.py:399-405` / `dev/main.py:384-390`）：所有 BO 都计算完整因子，然后把不通过价格门的丢掉。

这带来两个问题：

1. **批量扫描浪费 CPU**：被过滤的 BO 也跑了完整 enrich + score。ARQQ 实测 11 个 BO，价格门 [1, 10] 后剩 1 个，10 次 enrich 调用是纯浪费。
2. **dev UI 看不到上下文**：被过滤的 BO 在图上完全消失，用户没法判断"是否仅因为价格门差一点点而被丢掉"——这影响参数调试。

## 原则

- **过滤前置**：BO 之间在 enrich 阶段没有横向依赖（`streak`/`drought` 走 `detector.breakout_history`，与 enrich 无关；其余因子只看自己的 broken_peaks 和 df），所以可以在 enrich 之前 partition，省 CPU 且语义不变。
- **dev UI 可选展示**：增加 `FT_BO` 复选框，与 `SU_PK` 平行——勾上时把被过滤的 BO 以灰色简化样式画出来，并标出 `max_price` 上限线。
- **JSON schema 不变**：scanner 仍只把通过过滤的 BO 写进 JSON。本 spec 不动 JSON cache 路径——cache 模式下 FT_BO 无 filtered_infos 可显示，是 A 方案的明确权衡。

## 改动

### 1. `compute_breakouts_from_dataframe` 重构（`scanner.py:152-268`）

接收 `min_price` / `max_price` 参数；在 enrich 循环前对 `breakout_infos` 做 partition：

```python
def compute_breakouts_from_dataframe(
    ..., min_price=None, max_price=None
) -> tuple[list[Breakout], list[BreakoutInfo], BreakoutDetector]:
    breakout_infos = detector.batch_add_bars(...)

    # Partition before enrich
    kept_infos, filtered_infos = [], []
    for info in breakout_infos:
        if (min_price is None or info.current_price >= min_price) and \
           (max_price is None or info.current_price <= max_price):
            kept_infos.append(info)
        else:
            filtered_infos.append(info)

    # Enrich + score 仅对 kept_infos
    breakouts = [feature_calc.enrich_breakout(df, info, ...) for info in kept_infos]
    breakout_scorer.score_breakouts_batch(breakouts)

    return breakouts, filtered_infos, detector
```

返回类型变更：`(List[Breakout], BreakoutDetector)` → `(List[Breakout], List[BreakoutInfo], BreakoutDetector)`。

### 2. `scanner._scan_single_stock`（`scanner.py:271+`）

- 适配新返回签名（多收一项 `filtered_infos`，丢弃即可）
- 删除现有 line 399-405 的后置过滤
- JSON 写入行为完全不变

### 3. `dev/main.py._full_computation`（line 363-401）

- 把 `min_price`/`max_price` 传进 `compute_breakouts_from_dataframe`
- 删除现有 line 384-390 的后置过滤
- 返回值新增 `filtered_infos`，签名 `(breakouts, active_peaks, all_peaks, filtered_infos)`
- `_load_from_json_cache` 路径返回的 `filtered_infos = []`（JSON 没有此字段）

### 4. `dev/main.py._render_chart`（line ~554+）

- 新增参数 `filtered_breakouts: list[BreakoutInfo]`、`max_price: Optional[float]`
- `adjust_indices(filtered_infos, index_offset)` 与其他列表对齐
- 把 `filtered_breakouts` 和 `max_price` 一起传给 `chart_manager.update_chart`

### 5. `parameter_panel.py` 新增 FT_BO 复选框

- 位置：紧邻现有 SU_PK 复选框
- 变量名：`show_filtered_breakouts_var`，默认 `False`
- 写入 `display_options["show_filtered_breakouts"]`

### 6. `canvas_manager.update_chart`（`canvas_manager.py:82+`）

- 新增参数 `filtered_breakouts: list[BreakoutInfo] = []`、`max_price: Optional[float] = None`
- 当 `display_options["show_filtered_breakouts"]` 为 True：
  - 调 `marker.draw_filtered_breakouts(ax_main, df, filtered_breakouts, colors=colors)`
  - 当 `max_price is not None` 时调 `marker.draw_price_line(ax_main, df, price=max_price, label=f"max_price: {max_price}", color="gray", linestyle="--")`

### 7. `markers.py` 新增 `draw_filtered_breakouts`

```python
@staticmethod
def draw_filtered_breakouts(ax, df, infos, colors=None):
    """灰色简化版：仅画 [broken_peak_ids] 标签框 + 灰色倒三角。
    
    被过滤的 BO 没有 quality_score / label_value（feature 没算），
    所以渲染信息量比 draw_breakouts 少。
    """
```

颜色：`peak_marker_superseded`（与 SU_PK 灰色一致）或新加 key `breakout_filtered`。

### 8. `configs/ui_config.yaml`

`display_options` 增加 `show_filtered_breakouts: false`。

## 测试

### 新增

`BreakoutStrategy/analysis/tests/test_scanner_filtered_bo_skipped_enrich.py`：

- `test_arqq_filtered_bos_partitioned`：ARQQ 在 [1, 10] 价格门下，
  `compute_breakouts_from_dataframe` 返回 `(kept=1, filtered=10)`。
- `test_arqq_filtered_infos_carry_correct_prices`：filtered_infos 中所有 BO 的
  `current_price > 10.0`（被 max_price 过滤）。
- `test_kept_breakouts_have_quality_score`：kept_breakouts 的 `quality_score`
  与改动前一致（防止重构破坏因子计算）。

### 现有

- `test_scanner_arqq_all_peaks.py`：必须仍通过（all_peaks 行为不变）
- `test_scanner_range_meta.py` / `test_per_factor_gating.py`：可能需适配新签名
- `test_scanner_superseded.py`：CVGI fixture 在本 worktree 缺失，跳过

## 验证

1. ARQQ 在 dev UI 加载，FT_BO=ON：
   - 灰色 [3,4]、[1]、[3,5]、[1,2]、[0]、[6]、[6]、[10]、[11]、[9,11]、[8] 共 10 个标签出现
   - 一条灰色虚线在 y=10.0，右侧标 "max_price: 10.0"
2. FT_BO=OFF：行为与改前完全一致（仅 [3,4] 一个 BO 标签）
3. JSON cache 模式 + FT_BO=ON：标签不出现（filtered_infos 为空），是 A 方案的预期行为

## 不做

- 不动 scanner JSON schema
- 不动 BO 计算路径（feature_calc / scorer 完全不变）
- 不在 BO 上加 `is_filtered` 字段
- 不画 `min_price` 下限线
- 不让 FT_BO 在 JSON cache 模式下也生效（A 方案的明确放弃）
- 不重命名现有变量
