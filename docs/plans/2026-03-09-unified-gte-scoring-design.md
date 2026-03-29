# 评分统一 gte + 挖掘方向覆盖 — 实施计划

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 评分系统移除 gte/lte/sweet_spot 概念统一用 `>=` 触发，挖掘系统支持 mining_mode 覆盖 Spearman 方向。

**Architecture:** YAML 保留 mode 字段供挖掘管道使用，评分系统忽略 mode 始终用 `>=`，通过 values >1/<1 编码奖惩。FactorInfo 增加 mining_mode 字段允许覆盖 Spearman 推断。

**Tech Stack:** Python dataclasses, PyYAML, SciPy (spearmanr)

---

### Task 1: factor_registry.py — 增加 mining_mode 字段

**Files:**
- Modify: `BreakoutStrategy/mining/factor_registry.py:20-56`

**Step 1: 给 FactorInfo 增加 mining_mode 字段**

```python
# 在 has_nan_group 之后增加：
mining_mode: str | None = None  # None=Spearman自动, 'gte'/'lte'=强制覆盖
```

**Step 2: 给 overshoot 设置 mining_mode='lte'**

```python
# 第55行，overshoot 注册改为：
FactorInfo('overshoot', 'Overshoot', '超涨比', (4.0, 5.0), (0.80, 0.60), mining_mode='lte'),
```

**Step 3: Commit**

```
feat: add mining_mode field to FactorInfo for direction override
```

---

### Task 2: factor_diagnosis.py — 尊重 mining_mode 覆盖

**Files:**
- Modify: `BreakoutStrategy/mining/factor_diagnosis.py:14,18-60,114-141`

**Step 1: 导入 get_factor**

```python
# 第14行，增加 get_factor 导入：
from BreakoutStrategy.mining.factor_registry import get_active_factors, get_factor, LABEL_COL
```

**Step 2: diagnose_direction() 中增加覆盖逻辑**

在第33行 `for key, raw in raw_values.items():` 循环体最前面，valid_mask 之前插入：

```python
        # mining_mode 覆盖：跳过 Spearman 决策，仍计算用于日志
        fi = get_factor(key)
        if fi.mining_mode is not None:
            valid_mask = ~np.isnan(raw) & ~np.isnan(labels)
            valid_raw = raw[valid_mask]
            valid_labels = labels[valid_mask]
            r, p = (None, None)
            if len(valid_raw) > 10:
                r, p = spearmanr(valid_raw, valid_labels)
                r, p = round(float(r), 4), round(float(p), 6)
            results[key] = {
                'direction': 'override',
                'mode': fi.mining_mode,
                'spearman_r': r,
                'spearman_p': p,
            }
            continue
```

**Step 3: main() 中日志显示 override 标记**

第126行 action 判断逻辑后增加 override 识别：

```python
        action = "FLIP" if recommended != current else "OK"
        if d.get('direction') == 'override':
            action = "OVERRIDE"
```

**Step 4: Commit**

```
feat: factor_diagnosis respects mining_mode override
```

---

### Task 3: breakout_scorer.py — 移除方向概念

**Files:**
- Modify: `BreakoutStrategy/analysis/breakout_scorer.py`

**Step 1: 简化 _get_factor_value()（第294-341行）**

移除 mode 参数、lte 分支、sweet_spot 分支：

```python
    def _get_factor_value(
        self,
        value: float,
        thresholds: List[float],
        factor_values: List[float],
    ) -> tuple:
        """
        根据阈值获取 factor 值（始终使用 >= 比较）

        通过 values 编码方向：values > 1.0 为奖励，< 1.0 为惩罚。
        YAML 中的 mode 字段仅供挖掘管道使用，评分系统不读取。

        Returns:
            (multiplier, level): factor 乘数和触发级别
        """
        multiplier = 1.0
        level = 0

        for i, threshold in enumerate(thresholds):
            if value >= threshold:
                multiplier = factor_values[i]
                level = i + 1
            else:
                break

        return multiplier, level
```

**Step 2: 移除 __init__ 中所有 self.xxx_factor_mode 属性**

删除以下11行（第125, 132, 139, 146, 153, 160, 167, 174, 186, 193, 200行）：

```python
# 删除每个因子配置块中的这一行：
self.xxx_factor_mode = xxx_cfg.get('mode', 'gte')
```

**Step 3: 移除所有 _get_xxx_factor 方法中的 mode 传参**

11个调用点（第365-369, 403-407, 441-445, 479-483, 517-521, 550-554, 583-587, 650-654, 688-692, 727-731, 770-774行），统一改为3参数调用：

```python
# 之前：
multiplier, level = self._get_factor_value(
    value, self.xxx_factor_thresholds, self.xxx_factor_values, self.xxx_factor_mode,
)
# 之后：
multiplier, level = self._get_factor_value(
    value, self.xxx_factor_thresholds, self.xxx_factor_values,
)
```

**Step 4: 统一 triggered 判定为 level > 0**

3处特殊判定需修改：
- 第562行 `triggered=(level > 0)` → 已经正确，保持
- 第700行 `triggered=(multiplier < 1.0)` → 改为 `triggered=(level > 0)`
- 其余9处 `triggered=(multiplier > 1.0)` → 改为 `triggered=(level > 0)`

**Step 5: 更新模块 docstring（第1-33行）**

移除对 sweet_spot/lte 的描述，说明评分统一使用 `>=` + values 编码。

**Step 6: Commit**

```
refactor: remove gte/lte/sweet_spot from scorer, unify to >= with value-based reward/penalty
```

---

### Task 4: configs/params/all_factor.yaml — lte 因子 values 迁移

**Files:**
- Modify: `configs/params/all_factor.yaml:17-27,80-88,99-108`

lte 因子在 scorer 中将用 `>=` 触发，values 需从奖励型翻转为惩罚型：

**Step 1: age_factor values 反转（第24-27行）**

```yaml
# 之前: lte + 奖励 → "年轻好"
# 之后: >= + 惩罚 → "年老罚"
  age_factor:
    enabled: true
    mode: lte          # 保留，供挖掘管道使用
    thresholds:
    - 42
    - 63
    - 252
    values:
    - 0.98
    - 0.97
    - 0.95
```

**Step 2: peak_vol_factor values 反转（第84-88行）**

```yaml
# 之前: lte + 奖励 → "低峰量好"
# 之后: >= + 惩罚 → "高峰量罚"
  peak_vol_factor:
    enabled: true
    mode: lte
    thresholds:
    - 3.0
    - 5.0
    values:
    - 0.9
    - 0.8
```

**Step 3: streak_factor — 无需改动**

当前 `lte [2,4] [0.9,0.75]`，用 `>=` 触发时：streak>=2 → 0.9, >=4 → 0.75（惩罚高 streak）。
Spearman 诊断 lte 表示"高 streak 坏"，`>=` + values<1 已正确表达此语义。

**Step 4: Commit**

```
config: migrate lte factor values to penalty form for unified >= scoring
```

---

### Task 5: param_writer.py — values 编码方向

**Files:**
- Modify: `BreakoutStrategy/mining/param_writer.py:17,47-60,72-74,97-98`

**Step 1: 导入 get_factor**

```python
from BreakoutStrategy.mining.factor_registry import FACTOR_REGISTRY, get_factor
```

**Step 2: build_mined_params() 中 values 由 mode 方向决定（第54-60行）**

```python
    for key, threshold in mined_thresholds.items():
        yaml_key = key_to_yaml_key.get(key)
        if yaml_key and yaml_key in qs:
            entry = qs[yaml_key]
            entry['thresholds'] = [round(float(threshold), 4)]
            # values 由 mode 方向决定：gte 奖励，lte 惩罚
            mode = entry.get('mode', 'gte')
            entry['values'] = [0.8] if mode == 'lte' else [1.2]
            applied.append(key)
```

**Step 3: 更新 header 注释（第72-74行）**

```python
    header = (
        "# configs/params/all_factor_mined.yaml\n"
        "# 由 BreakoutStrategy.mining.param_writer 自动生成\n"
        f"# 已优化因子: {', '.join(applied)}\n"
        "# thresholds = 挖掘阈值, values: gte→1.2(奖励) lte→0.8(惩罚)\n\n"
    )
```

**Step 4: Commit**

```
feat: param_writer encodes mining direction as reward/penalty values
```

---

### Task 6: 验证

**Step 1: 检查评分系统无语法错误**

```bash
cd /home/yu/PycharmProjects/Trade_Strategy
uv run python -c "from BreakoutStrategy.analysis.breakout_scorer import BreakoutScorer; print('scorer OK')"
```

**Step 2: 检查挖掘管道无语法错误**

```bash
uv run python -c "from BreakoutStrategy.mining.factor_diagnosis import diagnose_direction; print('diagnosis OK')"
uv run python -c "from BreakoutStrategy.mining.param_writer import build_mined_params; print('param_writer OK')"
```

**Step 3: 验证 mining_mode 覆盖**

```bash
uv run python -c "
from BreakoutStrategy.mining.factor_registry import get_factor
fi = get_factor('overshoot')
assert fi.mining_mode == 'lte', f'Expected lte, got {fi.mining_mode}'
fi2 = get_factor('day_str')
assert fi2.mining_mode is None, f'Expected None, got {fi2.mining_mode}'
print('mining_mode override OK')
"
```

**Step 4: Commit**

```
verify: all modules import successfully after unified-gte refactor
```
