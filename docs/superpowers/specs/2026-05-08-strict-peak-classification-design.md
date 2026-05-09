# Strict Peak Classification: BO-broken vs PK-superseded

## 背景

前两次改动（2026-05-08-scan-output-worktree-isolation 之后的两条）让 dev UI
能在 SU_PK 勾选时显示所有 peak。实现里把 `detector.all_peaks` 整体当
`superseded_peaks` 喂给 canvas，于是凡是"非 active 且未被可见 BO 击穿"的
peak 都被画成实心灰 ▽（style="superseded"）。

这把两类语义不同的 peak 混到了一起：

1. **真正被新 peak 结构性 supersed 的 peak**（`detector.superseded_by_new_peak`）
2. **被某个 BO 击穿，但那个 BO 因为 price filter 被丢弃的 peak**

类别 2 在数据层并不属于 supersed——它在 `BreakoutInfo.broken_peaks` 里。
混到一起后，用户在 chart 上看到的"灰色 ▽"既可能是 1 也可能是 2，无法区分。

## 用户规则

1. 如果一个 bar 是 BO，那么它不可能作为 peak supersed 其他 peak，它只能
   break other peak，并且 broken peak 会**正常显示**——break 覆盖
   supersede。
2. **FT_BO 只控制被过滤 BO 的标签是否显示**，不控制被过滤 BO 击穿的 peak
   是否显示。
3. **SU_PK 只控制被非 BO 路径（即新 peak 结构性 supersede）杀死的 peak**
   的显示。

## detector 层面的现状（已满足规则 1）

`add_bar(N)` 时序：

```
add_bar(N):
  step 1: _detect_peak_in_window(N)   # 看窗口 [N-20, N-1]，N 自身不在窗口
          可能调 _try_add_peak 把窗口里某 idx Y 的新 peak 加入 active；
          若新 peak 高出某旧 active peak ≥3% → 旧 peak 进 superseded_by_new_peak

  step 2: _check_breakouts(N)         # 看 bar N 的 high vs active peaks
          若 high(N) > active peak * 1.005 → BO at idx N，broken_peaks 含该 peak
```

关键：`_try_add_peak` 看的窗口是 `[N-20, N-1]`，bar N 自己永远不会在 step
1 被作为新 peak 加进 active；它要等到 `current_idx >= N + min_side_bars`
那一刻 `_try_add_peak` 才会回头把 N 加为 peak。

所以"bar N 既是 peak 又是 BO"在代码里展开成：

- bar N：step 2 的 `_check_breakouts(N)` 触发 BO，把 active peaks 中能被
  high(N) 击破的 peak 移到 BO.broken_peaks（局部）/superseded_peaks（局部）
- bar N+min_side_bars：step 1 的 `_try_add_peak` 把 idx N 的 peak 加入
  active；此时上面那批 peak 早已不在 active，新 peak（N 处）supersede
  不到它们

**结果**：`superseded_by_new_peak` 与 `BO.broken_peaks` 在数据层互斥。规则 1
天然成立，detector 不用动。

## 改动

### 1. `dev/main.py:_full_computation`

恢复严格语义：

```python
superseded_peaks = detector.superseded_by_new_peak if detector else []
```

去掉之前的 `superseded_peaks = detector.all_peaks`。

### 2. `UI/charts/canvas_manager.py` `update_chart`

`all_broken_peaks` 的收集源从 `breakouts` 扩展为 `breakouts + filtered_breakouts`：

```python
seen_peak_ids = set()
all_broken_peaks = []
sources = list(breakouts)
if filtered_breakouts:
    sources.extend(filtered_breakouts)
for bo in sources:
    if hasattr(bo, "broken_peaks") and bo.broken_peaks:
        for p in bo.broken_peaks:
            if p.id not in seen_peak_ids:
                seen_peak_ids.add(p.id)
                all_broken_peaks.append(p)
```

这一改之后：

- 被过滤 BO 击穿的 peak 通过 `all_broken_peaks` 路径以**正常黑色 ▽** 在
  peak 位置绘制（始终显示，不受 FT_BO/SU_PK 控制）。
- `superseded_only_peaks` 路径回到只画严格的 `superseded_by_new_peak`，且
  仍然由 SU_PK 控制。

注意：`all_broken_peaks` 用于 BO 标签的 `peak_indices` 集合（draw_breakouts
计算偏移），把过滤 BO 的 broken peaks 放进去也不会污染 BO 标签——这个集
合只是用来判断"这根 bar 上是否已有 peak 三角"以做堆叠。

### 3. `markers.py.draw_peaks`

不动。

### 4. FT_BO / SU_PK checkbox

不动。

## BreakoutInfo 的 broken_peaks 必须带 .id

`canvas_manager` 用 `p.id` 做 dedup。`BreakoutInfo.broken_peaks` 来自
`_check_breakouts`，里面的 Peak 对象已在 `_create_peak`（`breakout_detector.py:504-512`）
被赋了 id。filtered_infos 里的 BreakoutInfo 同样持有这些 Peak 对象（同一份引用），所以 id 一定有。

## 不做

- 不动 detector（已天然满足规则 1）
- 不动 markers.py（不引入新 style）
- 不动 FT_BO / SU_PK 的语义（已和规则 2/3 对齐）
- 不重命名变量

## 测试

### 新增

`test_scanner_filtered_bo_skipped_enrich.py`（已存在，复用 fixture）补一条：

`test_arqq_filtered_infos_carry_broken_peaks_with_ids`：

- 收集 `filtered_infos[].broken_peaks` 里所有 peak.id
- 断言这个集合 ⊇ {0, 1, 2, 5, 6, 9, 10, 11}（被过滤 BO 击穿的 peaks）
- 断言每个 peak 的 .id 不为 None

这一条直接覆盖 canvas 端"all_broken_peaks 包含被过滤 BO 击穿的 peak"的前
提：只要数据层契约成立，canvas 改动就是机械变换。

### 现有

- `test_scanner_arqq_all_peaks.py`：仍通过（scanner JSON 行为不变）
- `test_scanner_filtered_bo_skipped_enrich.py`：仍通过
- `analysis/` + `UI/charts/` 全部测试

## 验证

ARQQ 在 dev UI（Use UI Params 模式，避开 JSON cache）：

1. **SU_PK = OFF**：peaks 0、1、2、3、4、5、6、9、10、11 都以**正常黑色 ▽**
   在各自 peak 位置出现（即使它们不在 active 也不在可见 BO 的 broken_peaks
   里）；7、8 是 active，也是黑色 ▽。**整体 12 个 peak 全部黑色显示**。
2. **SU_PK = ON**：在 ARQQ 数据上 `superseded_by_new_peak` 为空集，所以
   勾不勾 SU_PK 显示效果一样。这是 ARQQ 数据的特性，**不是 bug**。
3. **FT_BO = OFF**：过滤 BO 的灰色 `[ids]` 标签全部消失；但 peak 仍在
   peak 位置以黑色 ▽ 显示（验证规则 2）。
4. **FT_BO = ON**：灰色 `[ids]` 标签出现 + max_price 上限线。
