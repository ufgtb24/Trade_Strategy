# K 线图数据范围说明（Dev UI / Live UI）

## 术语

- **T**：当天日期（live）或扫描的 end_date（dev UI）
- **scan_start**：扫描起始日期（dev UI = `scan_config.yaml` 的 `start_date`；live = `T - scan_window_days`）
- **scan_end**：扫描结束日期（dev UI = `scan_config.yaml` 的 `end_date`；live = T）
- **技术指标预热 buffer**：`max(MA 200, Volume 63, AnnualVol 252) = 252 交易日 × 1.65 ≈ 415 日历天`。用于 MA rolling / ATR rolling / detector peak 状态累积。由 `scanner.preprocess_dataframe:82-85` 计算。
- **Label buffer**：`label_max_days × 1.5`（dev UI 可配置 label_max_days，默认 20 → 30 天；live 固定 20 → 30 天）。用于回测标签计算（BO 后 N 天最高价）。由 `scanner.preprocess_dataframe:86,92-93` 截取。
- **valid range**：`[valid_start_index, valid_end_index)`。只在此范围内检测 peak / BO。由 `batch_add_bars:375` 的 `enable_detection` 控制。

---

## Dev UI

假设：`start_date=2025-08-01`，`end_date=2026-04-14`，`label_max_days=40`，`ma_periods=[200]`

| 对象 | 起点 | 终点 | 代码位置 | 说明 |
|---|---|---|---|---|
| **detector 喂入的 df** | scan_start - 415 天<br>(≈2024-06-12) | scan_end + 60 天<br>(≈2026-06-13) | `scanner.preprocess_dataframe:88-93` | 前置 = 技术指标预热 buffer (252td×1.65)；后置 = label buffer (40×1.5) |
| **检测有效区间**<br>（peak/BO 可诞生的范围） | scan_start<br>(2025-08-01) | scan_end<br>(2026-04-14) | `main.py:341-355` → `batch_add_bars:375` | `enable_detection=True` 的 idx 范围 |
| **display_df**<br>（图表绑定的 DataFrame） | scan_start<br>(2025-08-01) | scan_end + 60 天<br>(≈2026-06-13) | `main.py:550-592` `_trim_df_for_display` | 前截：裁掉预热 buffer（line 573-577）<br>后不截：df 本身已被 `preprocess_dataframe` 截止（line 591） |
| **图表可访问最大范围**<br>（平移缩放极限） | scan_start<br>(2025-08-01) | scan_end + 60 天<br>(≈2026-06-13) | `canvas_manager.py:294-304` | = display_df 范围。`initial_window_days=None` → 初始全展开 |
| **检测出的 peak/BO** | scan_start<br>(2025-08-01) | scan_end<br>(2026-04-14) | `batch_add_bars:375` + `_detect_peak_in_window:468` | 预热 buffer 区和 label buffer 区**不产出** peak/BO |
| **图表上显示的 peak/BO** | scan_start<br>(2025-08-01) | scan_end<br>(2026-04-14) | `main.py:278-280` `_adjust_breakout_indices` | index 按前截偏移量调整，映射到 display_df 坐标系。不出现在 label buffer 灰色区 |

**数据流**：

```
pkl 文件（全量历史）
   ↓ preprocess_dataframe
df [scan_start - 415天 .. scan_end + label_buffer]  ← 含 MA/ATR 列
   ↓ compute_breakouts_from_dataframe(valid_start_index, valid_end_index)
检测 peak/BO：仅在 [scan_start .. scan_end] 内
   ↓ _trim_df_for_display
display_df [scan_start .. scan_end + label_buffer]  ← 裁掉前置预热 buffer
   ↓ _adjust_breakout_indices(offset)
peak/BO index 映射到 display_df 坐标
   ↓ canvas_manager.update_chart(display_df, ...)
图表渲染（全范围展开，label buffer 区灰色标注）
```

---

## Live UI

假设：`scan_window_days=180`，`label_max_days=20`（默认），当天日期 T

| 对象 | 起点 | 终点 | 代码位置 | 说明 |
|---|---|---|---|---|
| **pkl 文件** | ≈ T - 580 天 | ≈ T | `daily_runner.py:93` | 下载 `scan_window_days + 400 = 580` 日历天数据 |
| **scanner 喂入的 df** | pkl 起点<br>(≈T-580) | pkl 终点<br>(≈T) | `scanner.preprocess_dataframe:88-93` | 前置 buffer 需求 = T-180-415=T-595，早于 pkl 起点（T-580），故不截前；后置 label buffer = T+30，晚于 pkl 末尾（T），故不截后。**scanner df = pkl 全量 + MA/ATR 列** |
| **检测有效区间**<br>（peak/BO 可诞生的范围） | T - 180 天 | T | `daily_runner.py:118-120` → `scanner.py:280-297` | `start_date = T-180`，`end_date = T` |
| **chart df**<br>（图表绑定的 DataFrame） | pkl 起点<br>(≈T-580) | pkl 终点<br>(≈T) | `app.py:254` `pd.read_pickle(pkl_path)` | **直接读 pkl 全量**，不经 preprocess，无 MA/ATR 列 |
| **图表初始视口** | T - 180 天 | T + 右留白 | `canvas_manager.py:291-304` | `initial_window_days=180` → 右对齐最近 180 天 |
| **图表可访问最大范围**<br>（zoom out 极限） | pkl 起点<br>(≈T-580) | T + 右留白 | `canvas_manager.py:301` `data_span_left` | 用户可 zoom out 看 pkl 全量历史 |
| **检测出的 peak/BO** | T - 180 天 | T | 同 dev UI 机制 | 预热 buffer 区（T-580 到 T-180）**不产出** peak/BO |
| **图表上显示的 peak/BO** | T - 180 天 | T | `app.py:259-261` | index **无偏移**（scanner df 和 chart df 行数相同） |

**数据流**：

```
akshare 下载 580 日历天 → pkl 文件
   ↓
[scanner 路径]                          [chart 路径]
preprocess_dataframe                    pd.read_pickle (原始 pkl)
df = pkl 全量 + MA/ATR 列                  ↓
   ↓                                    chart df = pkl 全量（无 MA/ATR）
compute_breakouts_from_dataframe            ↓
valid range = [T-180, T]                canvas_manager.update_chart
   ↓                                    initial_window_days=180
MatchedBreakout(raw_breakout, raw_peaks)   (初始视口 T-180 ~ T)
   ↓                                    (zoom out 可到 pkl 起点)
adapt_peaks / adapt_breakout
   ↓
peak/BO index 直接使用（无偏移）
```

---

## Dev UI vs Live UI 关键差异

| 维度 | Dev UI | Live UI |
|---|---|---|
| **chart df 来源** | `preprocess_dataframe` → `_trim_df_for_display` | 原始 pkl（`pd.read_pickle`） |
| **chart df 是否含 MA/ATR** | 是（preprocess 计算） | 否 |
| **chart df 起点** | scan_start（前置 buffer 被裁掉） | pkl 起点（≈T-580，不裁） |
| **chart df 终点** | scan_end + label buffer | pkl 终点（≈T） |
| **BO index 偏移** | 有（`_adjust_breakout_indices`，补偿前截） | 无（scanner df 与 pkl 行数相同） |
| **初始视口** | 全范围展开 | 最近 180 天右对齐 |
| **zoom out 极限** | scan_start ~ scan_end + label buffer | pkl 起点 ~ pkl 终点 |
| **label buffer 灰色区** | 有（scan_end 之后的区域标灰） | 无（live 无 label buffer 概念） |
| **peak/BO 检测范围** | [scan_start, scan_end] | [T-180, T] |
