# 票 08 独立审查 · Standards 轴

审查对象：`impl/08-rally-random-pool`，固定点 cb6dbb968b1800432664a4da56c4b381a9d5def6（与 annotation-path2 的分叉点），由 code-review skill 派出的子代理完成，原文如下。

**硬违反（成文规范）**
1. **`path2_web/finder.py`、`path2_web/stock_pool.py` 整体放错层**：CLAUDE.md「代码地图·path2_web」的边界红线写的是「后端是纯投影层……不含走势语义、不做二次判定」。这两个模块却把新判定放进了后端：大涨段怎么算（止损线、`rel_min` 门槛），股票池、SPAC 壳期怎么认。票 02 当时在红线括号里为标注读写加了例外，本票没加。要么挪出后端，要么同样在红线里补上例外。
2. **`stock_pool.volatility_scale` 的 docstring 写了开发历史**：「改用 pandas 自带的滚动中位数，整池算一遍快几倍」，违反「注释只写现状」。

**判断题（坏味道）**
- **Speculative Generality**：`rally_labels` 的 `low` 参数从没用到。`pool_mask` 的 `common` 参数在生产代码里恒为 True，因为 `build_index` 已经先按类别过滤过。
- **Duplicated Code**：
  - `_DATE_RE` 和「日期格式 + 起点 ≤ 终点」的校验，在 `config.py` 和 `stock_pool.py` 各写了一份。
  - rally 的七个字段在 `_RALLY_FIELDS`、`rally_items`、`load_index`、`types.ts`、e2e 里各写一遍。
  - `select_rally` 里同一组排序键写了两次。
  - `DEFAULT_CONFIG` 的训练段终点直接写死 `'2025-12-31'`，没用 `TRAIN_END`；`configs/path2_web.yaml` 又抄了一份 `train_segment` 和 `rally` 的默认值，和注释里的「全仓唯一一处」自相矛盾。
- **Data Clumps / Primitive Obsession**：`segment`、`settings`、`names`、`errors` 四样总是一起传。`settings` 是裸 dict，`int()` / `float()` 强转散在各处。
- **Mysterious Name**：TopBar 的 `status`（testid 叫 `symbol-status`）同时承担了 random 的 loading / empty 状态。`openSymbol` 的参数名 `window` 遮蔽了全局 `window`。
- **配色（color-vision.md）**：清单行悬停底色 `#fafafa` 放在白底上几乎看不出。
