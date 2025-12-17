# Scoring Fix + Pattern Label Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Fix 3 high-priority scoring issues and add lightweight pattern classification labels to breakout scoring.

**Architecture:** Keep the multiplicative scoring model intact. Fix gap_vol/idr_vol double-counting by merging into one bonus, relax overshoot penalty, expand streak bonus levels. Add post-scoring pattern classification that labels each breakout with its dominant pattern type (momentum, historical, volume_surge, etc.).

**Tech Stack:** Python, dataclasses, existing BreakoutScorer framework

---

### Task 1: Merge gap_vol + idr_vol into breakout_day_strength bonus (breakout_scorer.py)

**Files:**
- Modify: `BreakoutStrategy/analysis/breakout_scorer.py:166-178` (config init)
- Modify: `BreakoutStrategy/analysis/breakout_scorer.py:551-659` (two methods -> one)
- Modify: `BreakoutStrategy/analysis/breakout_scorer.py:880-892` (assembly)

**Step 1: Replace config init for gap_vol and idr_vol with unified breakout_day_strength**

In `__init__`, replace the two separate config blocks (lines 166-178) with:

```python
        # Breakout Day Strength bonus（突破日强度，取 IDR-Vol 和 Gap-Vol 中较大者）
        # 合并原 intraday_return_vol_bonus 和 gap_vol_bonus，消除双重计分
        bds = config.get('breakout_day_strength_bonus', {})
        self.bds_bonus_enabled = bds.get('enabled', True)
        self.bds_bonus_thresholds = bds.get('thresholds', [1.5, 2.5])
        self.bds_bonus_values = bds.get('values', [1.10, 1.20])
```

**Step 2: Replace `_get_intraday_return_vol_bonus` and `_get_gap_vol_bonus` with `_get_breakout_day_strength_bonus`**

Delete both old methods (lines 551-659). Add new method:

```python
    def _get_breakout_day_strength_bonus(
        self,
        intraday_change_pct: float,
        gap_up_pct: float,
        annual_volatility: float
    ) -> BonusDetail:
        """
        计算突破日强度 bonus（合并 IDR-Vol 和 Gap-Vol）

        取日内涨幅和跳空幅度的波动率标准化值中的较大者，避免双重计分。

        公式：ratio = max(intraday_return / daily_vol, gap_up_pct / daily_vol)
        单位：sigma

        Args:
            intraday_change_pct: 日内涨幅（收盘价相对开盘价）
            gap_up_pct: 跳空幅度（开盘价相对前收）
            annual_volatility: 年化波动率

        Returns:
            BonusDetail
        """
        import math

        if not self.bds_bonus_enabled or annual_volatility <= 0:
            return BonusDetail(
                name="DayStr",
                raw_value=0.0,
                unit="sigma",
                bonus=1.0,
                triggered=False,
                level=0
            )

        daily_vol = annual_volatility / math.sqrt(252)
        idr_ratio = intraday_change_pct / daily_vol if intraday_change_pct > 0 else 0.0
        gap_ratio = gap_up_pct / daily_vol if gap_up_pct > 0 else 0.0
        ratio = max(idr_ratio, gap_ratio)

        bonus, level = self._get_bonus_value(
            ratio,
            self.bds_bonus_thresholds,
            self.bds_bonus_values
        )

        return BonusDetail(
            name="DayStr",
            raw_value=round(ratio, 1),
            unit="sigma",
            bonus=bonus,
            triggered=(bonus > 1.0),
            level=level
        )
```

**Step 3: Update `get_breakout_score_breakdown_bonus` assembly**

Replace the two bonus append blocks (lines 880-892):

```python
        # Before (remove):
        # idr_vol_bonus = self._get_intraday_return_vol_bonus(...)
        # bonuses.append(idr_vol_bonus)
        # gap_vol_bonus = self._get_gap_vol_bonus(...)
        # bonuses.append(gap_vol_bonus)

        # After:
        bds_bonus = self._get_breakout_day_strength_bonus(
            breakout.intraday_change_pct,
            breakout.gap_up_pct,
            breakout.annual_volatility
        )
        bonuses.append(bds_bonus)
```

**Step 4: Verify no import errors**

Run: `cd /home/yu/PycharmProjects/Trade_Strategy && python -c "from BreakoutStrategy.analysis.breakout_scorer import BreakoutScorer; print('OK')"`
Expected: `OK`

**Step 5: Commit**

```
feat: merge gap_vol + idr_vol into breakout_day_strength bonus
```

---

### Task 2: Relax overshoot penalty (breakout_scorer.py + scan_params.yaml)

**Files:**
- Modify: `BreakoutStrategy/analysis/breakout_scorer.py:163-164` (default values)
- Modify: `BreakoutStrategy/analysis/breakout_scorer.py:506-508` (docstring)
- Modify: `configs/params/scan_params.yaml:63-65` (production config)

**Step 1: Update default values in breakout_scorer.py**

Line 163-164, change:
```python
        self.overshoot_penalty_thresholds = overshoot.get('thresholds', [3.0, 4.0])
        self.overshoot_penalty_values = overshoot.get('values', [0.7, 0.4])
```
to:
```python
        self.overshoot_penalty_thresholds = overshoot.get('thresholds', [3.0, 4.0])
        self.overshoot_penalty_values = overshoot.get('values', [0.80, 0.60])
```

**Step 2: Update docstring**

In `_get_overshoot_penalty` docstring (lines 506-508), change:
```
        - >= 3sigma -> 0.7x (mild)
        - >= 4sigma -> 0.4x (severe)
```
to:
```
        - >= 3sigma -> 0.80x (mild)
        - >= 4sigma -> 0.60x (moderate)
```

**Step 3: Update scan_params.yaml**

Lines 63-65, change:
```yaml
    values:
    - 0.8
    - 0.4
```
to:
```yaml
    values:
    - 0.80
    - 0.60
```

**Step 4: Verify**

Run: `cd /home/yu/PycharmProjects/Trade_Strategy && python -c "from BreakoutStrategy.analysis.breakout_scorer import BreakoutScorer; s = BreakoutScorer(); print(s.overshoot_penalty_values)"`
Expected: `[0.8, 0.6]`

**Step 5: Commit**

```
fix: relax overshoot penalty from [0.7, 0.4] to [0.80, 0.60]
```

---

### Task 3: Expand streak bonus levels (breakout_scorer.py + scan_params.yaml)

**Files:**
- Modify: `BreakoutStrategy/analysis/breakout_scorer.py:143-144` (default values)
- Modify: `configs/params/scan_params.yaml:90-95` (production config)

**Step 1: Update default values in breakout_scorer.py**

Lines 143-144, change:
```python
        self.streak_bonus_thresholds = streak_bonus.get('thresholds', [2])
        self.streak_bonus_values = streak_bonus.get('values', [1.20])
```
to:
```python
        self.streak_bonus_thresholds = streak_bonus.get('thresholds', [2, 4])
        self.streak_bonus_values = streak_bonus.get('values', [1.20, 1.40])
```

**Step 2: Update scan_params.yaml**

Lines 90-95, change:
```yaml
  streak_bonus:
    enabled: true
    thresholds:
    - 2
    values:
    - 1.1
```
to:
```yaml
  streak_bonus:
    enabled: true
    thresholds:
    - 2
    - 4
    values:
    - 1.20
    - 1.40
```

**Step 3: Verify**

Run: `cd /home/yu/PycharmProjects/Trade_Strategy && python -c "from BreakoutStrategy.analysis.breakout_scorer import BreakoutScorer; s = BreakoutScorer(); print(s.streak_bonus_thresholds, s.streak_bonus_values)"`
Expected: `[2, 4] [1.2, 1.4]`

**Step 4: Commit**

```
feat: expand streak bonus to 2 levels (2x->1.20, 4x->1.40)
```

---

### Task 4: Update UI config schema (param_editor_schema.py)

**Files:**
- Modify: `BreakoutStrategy/UI/config/param_editor_schema.py:294-322` (streak schema)
- Modify: `BreakoutStrategy/UI/config/param_editor_schema.py:352-408` (remove idr_vol and gap_vol, add breakout_day_strength)

**Step 1: Update streak_bonus schema defaults**

In lines 294-322, update defaults to match new 2-level config:
```python
        "streak_bonus": {
            "type": dict,
            "is_bonus_group": True,
            "default": {
                "enabled": True,
                "thresholds": [2, 4],
                "values": [1.20, 1.40],
            },
            "description": "Streak bonus (连续突破): thresholds are breakout counts",
            "sub_params": {
                "enabled": {
                    "type": bool,
                    "default": True,
                    "description": "Enable streak bonus",
                },
                "thresholds": {
                    "type": list,
                    "element_type": int,
                    "default": [2, 4],
                    "description": "Threshold levels (2+ breakouts, 4+ strong trend)",
                },
                "values": {
                    "type": list,
                    "element_type": float,
                    "default": [1.20, 1.40],
                    "description": "Bonus multipliers for each level",
                },
            },
        },
```

**Step 2: Replace idr_vol_bonus and gap_vol_bonus with breakout_day_strength_bonus**

Remove the two schema entries (lines 352-408) and replace with:
```python
        "breakout_day_strength_bonus": {
            "type": dict,
            "is_bonus_group": True,
            "default": {
                "enabled": True,
                "thresholds": [1.5, 2.5],
                "values": [1.10, 1.20],
            },
            "description": "Breakout Day Strength bonus (突破日强度): max(IDR-Vol, Gap-Vol) in sigma",
            "sub_params": {
                "enabled": {
                    "type": bool,
                    "default": True,
                    "description": "Enable breakout day strength bonus",
                },
                "thresholds": {
                    "type": list,
                    "element_type": float,
                    "default": [1.5, 2.5],
                    "description": "Threshold levels (1.5sigma, 2.5sigma)",
                },
                "values": {
                    "type": list,
                    "element_type": float,
                    "default": [1.10, 1.20],
                    "description": "Bonus multipliers for each level",
                },
            },
        },
```

**Step 3: Update overshoot_penalty schema defaults**

In lines 323-350, update the default values:
```python
            "default": {
                "enabled": True,
                "thresholds": [3.0, 4.0],
                "values": [0.80, 0.60],
            },
```
and sub_params values default:
```python
                    "default": [0.80, 0.60],
```

**Step 4: Verify**

Run: `cd /home/yu/PycharmProjects/Trade_Strategy && python -c "from BreakoutStrategy.UI.config.param_editor_schema import PARAM_CONFIGS; print(list(PARAM_CONFIGS['quality_scorer'].keys()))"`
Expected: should contain `breakout_day_strength_bonus` and NOT contain `intraday_return_vol_bonus` or `gap_vol_bonus`

**Step 5: Commit**

```
chore: update UI param schema for scoring fixes
```

---

### Task 5: Update UI config loader (param_loader.py)

**Files:**
- Modify: `BreakoutStrategy/UI/config/param_loader.py` (adapt to new config keys)

**Step 1: Check current loader references**

Search for `intraday_return_vol_bonus` and `gap_vol_bonus` in param_loader.py and replace with `breakout_day_strength_bonus` handling. Also update streak_bonus loading if needed.

Note: param_loader.py reads from YAML and feeds to BreakoutScorer. Since BreakoutScorer now reads `breakout_day_strength_bonus` from config dict, the loader should pass through the YAML key as-is. Check if any explicit key references need updating.

**Step 2: Verify full config load**

Run: `cd /home/yu/PycharmProjects/Trade_Strategy && python -c "
from BreakoutStrategy.UI.config.param_loader import ParamLoader
loader = ParamLoader()
params = loader.load_from_yaml('configs/params/scan_params.yaml')
print('Loaded OK, scorer keys:', list(params.get('quality_scorer', {}).keys()))
"`

**Step 3: Commit**

```
chore: update param_loader for breakout_day_strength_bonus
```

---

### Task 6: Update scan_params.yaml config (replace gap_vol/idr_vol)

**Files:**
- Modify: `configs/params/scan_params.yaml` (replace two config sections with one)

**Step 1: Replace config sections**

Remove `gap_vol_bonus` and `intraday_return_vol_bonus` sections, add `breakout_day_strength_bonus`:

```yaml
  breakout_day_strength_bonus:
    enabled: true
    thresholds:
    - 1.5
    - 2.5
    values:
    - 1.10
    - 1.20
```

**Step 2: Verify YAML parses correctly**

Run: `cd /home/yu/PycharmProjects/Trade_Strategy && python -c "
import yaml
with open('configs/params/scan_params.yaml') as f:
    cfg = yaml.safe_load(f)
print('quality_scorer keys:', list(cfg.get('quality_scorer', {}).keys()))
"`

**Step 3: Commit**

```
chore: update scan_params.yaml for scoring fixes
```

---

### Task 7: Update scan_manager.py references

**Files:**
- Modify: `BreakoutStrategy/UI/managers/scan_manager.py` (update buffer constant comment)

**Step 1: Update ANNUAL_VOL_LOOKBACK_BUFFER comment**

The comment on line 30 references "IDR-Vol Bonus, Gap-Vol Bonus". Update to reference "Breakout Day Strength Bonus".

**Step 2: Commit**

```
chore: update scan_manager comment for new bonus name
```

---

### Task 8: Add pattern_label to ScoreBreakdown (breakout_scorer.py)

**Files:**
- Modify: `BreakoutStrategy/analysis/breakout_scorer.py:46-55` (ScoreBreakdown dataclass)

**Step 1: Add pattern_label field**

Add to `ScoreBreakdown` dataclass after `bonuses` field:

```python
    pattern_label: Optional[str] = None  # 模式标签 (momentum, historical, volume_surge, etc.)
```

**Step 2: Verify**

Run: `cd /home/yu/PycharmProjects/Trade_Strategy && python -c "from BreakoutStrategy.analysis.breakout_scorer import ScoreBreakdown; print(ScoreBreakdown.__dataclass_fields__['pattern_label'])"`

**Step 3: Commit**

```
feat: add pattern_label field to ScoreBreakdown
```

---

### Task 9: Implement _classify_pattern method (breakout_scorer.py)

**Files:**
- Modify: `BreakoutStrategy/analysis/breakout_scorer.py` (add method before `get_breakout_score_breakdown_bonus`)

**Step 1: Add _classify_pattern method to BreakoutScorer**

```python
    def _classify_pattern(self, bonuses: List[BonusDetail]) -> str:
        """
        根据主导 bonus 对突破进行模式分类

        模式定义（按优先级）：
        - 混合模式优先：A+B 深蹲远射, B+C 放量历史, B+D 磨穿防线
        - 单一模式：A 势能, B 历史阻力, C 放量爆发, D 密集测试, E 趋势延续
        - 兜底：basic

        Args:
            bonuses: bonus 列表

        Returns:
            模式标签字符串
        """
        b = {bonus.name: bonus for bonus in bonuses}

        pk_mom = b.get("PK-Mom")
        age = b.get("Age")
        tests = b.get("Tests")
        vol = b.get("Volume")
        streak = b.get("Streak")

        pk_mom_level = pk_mom.level if pk_mom else 0
        age_level = age.level if age else 0
        tests_level = tests.level if tests else 0
        vol_level = vol.level if vol else 0
        streak_level = streak.level if streak else 0

        # 混合模式优先判定
        if pk_mom_level >= 1 and age_level >= 2:
            return "deep_rebound"       # A+B 深蹲远射
        if vol_level >= 1 and age_level >= 2:
            return "power_historical"   # B+C 放量历史突破
        if age_level >= 2 and tests_level >= 1:
            return "grind_through"      # B+D 磨穿防线

        # 单一模式判定
        if pk_mom_level >= 1:
            return "momentum"           # A 势能突破
        if age_level >= 2:
            return "historical"         # B 历史阻力突破
        if vol_level >= 1:
            return "volume_surge"       # C 放量爆发
        if tests_level >= 2:
            return "dense_test"         # D 密集测试
        if streak_level >= 1:
            return "trend_continuation" # E 趋势延续

        return "basic"                  # F 基础突破
```

**Step 2: Wire up in get_breakout_score_breakdown_bonus**

After computing `total_score` (around line 914), add:

```python
        # 5. 分类模式标签
        pattern_label = self._classify_pattern(bonuses)
```

Update the return statement to include `pattern_label`:
```python
        return ScoreBreakdown(
            entity_type='breakout',
            entity_id=None,
            total_score=total_score,
            broken_peak_ids=broken_peak_ids,
            base_score=base_score,
            bonuses=bonuses,
            pattern_label=pattern_label
        )
```

**Step 3: Verify**

Run: `cd /home/yu/PycharmProjects/Trade_Strategy && python -c "
from BreakoutStrategy.analysis.breakout_scorer import BreakoutScorer, BonusDetail
scorer = BreakoutScorer()
# Test classify with mock bonuses
bonuses = [
    BonusDetail('Age', 300, 'd', 1.50, True, 3),
    BonusDetail('Tests', 3, 'x', 1.25, True, 2),
    BonusDetail('PK-Mom', 0, '', 1.0, False, 0),
    BonusDetail('Volume', 1.0, 'x', 1.0, False, 0),
    BonusDetail('Streak', 1, 'bo', 1.0, False, 0),
]
label = scorer._classify_pattern(bonuses)
print(f'Pattern: {label}')  # Should be 'grind_through'
"`
Expected: `Pattern: grind_through`

**Step 4: Commit**

```
feat: implement pattern classification for breakout scoring
```

---

### Task 10: Add pattern_label to PoolEntry (simple_pool)

**Files:**
- Modify: `BreakoutStrategy/simple_pool/models.py:32` (add field)
- Modify: `BreakoutStrategy/simple_pool/models.py:96-133` (serialization)
- Modify: `BreakoutStrategy/simple_pool/manager.py:46,74,104` (pass through)

**Step 1: Add pattern_label field to PoolEntry**

After `quality_score` field (line 32), add:
```python
    pattern_label: str = "basic"  # 突破模式标签
```

**Step 2: Update to_dict**

Add to `to_dict` (after quality_score line):
```python
            'pattern_label': self.pattern_label,
```

**Step 3: Update from_dict**

Add to `from_dict` constructor call:
```python
            pattern_label=data.get('pattern_label', 'basic'),
```

**Step 4: Update manager.add_entry**

In `manager.py:46`, add `pattern_label: str = "basic"` parameter.
In `manager.py:74`, add `pattern_label=pattern_label` to PoolEntry constructor.

**Step 5: Update manager.add_breakout**

In `manager.py:104`, add:
```python
            pattern_label=getattr(breakout, 'pattern_label', 'basic')
```

Note: Breakout object doesn't have pattern_label directly. It comes from ScoreBreakdown. For simplicity, we need to store it on the Breakout object during scoring, or pass it separately. The simplest approach: after `score_breakout()` sets `breakout.quality_score`, we can also store the pattern_label. But Breakout is defined in breakout_detector.py and may not have this field.

Alternative: store pattern_label on Breakout via a simple attribute assignment (Python allows dynamic attrs), or read it from the scorer at add_breakout time.

**Simplest approach**: In `BreakoutScorer.score_breakout()`, also set `breakout.pattern_label`:

In `breakout_scorer.py:score_breakout()`:
```python
    def score_breakout(self, breakout: Breakout) -> float:
        breakdown = self.get_breakout_score_breakdown_bonus(breakout)
        breakout.quality_score = breakdown.total_score
        breakout.pattern_label = breakdown.pattern_label  # Store pattern label
        return breakdown.total_score
```

Then `manager.add_breakout` can use `getattr(breakout, 'pattern_label', 'basic')`.

**Step 6: Verify**

Run: `cd /home/yu/PycharmProjects/Trade_Strategy && python -c "
from BreakoutStrategy.simple_pool.models import PoolEntry
from datetime import date
entry = PoolEntry(
    symbol='TEST', entry_id='TEST_2024-01-01',
    breakout_date=date(2024,1,1), breakout_price=100.0,
    peak_price=95.0, initial_atr=2.0, quality_score=80.0,
    pattern_label='momentum'
)
d = entry.to_dict()
print(d['pattern_label'])
entry2 = PoolEntry.from_dict(d)
print(entry2.pattern_label)
"`
Expected: `momentum` (twice)

**Step 7: Commit**

```
feat: add pattern_label to PoolEntry for downstream use
```

---

### Task 11: Display pattern_label in score tooltip (UI)

**Files:**
- Modify: `BreakoutStrategy/UI/charts/components/score_tooltip.py:97-155` (add pattern label display)

**Step 1: Add pattern label display in _build_breakout_card**

After the header section (around line 127, after score_label), add a pattern label:

```python
        # Pattern label
        if breakdown.pattern_label and breakdown.pattern_label != "basic":
            pattern_label = tk.Label(
                header,
                text=f"[{breakdown.pattern_label}]",
                font=self.FONTS["header_small"],
                bg=self.COLORS["bo_header_bg"],
                fg=self.COLORS["score_medium_light"],
                padx=4,
                pady=6
            )
            pattern_label.pack(side=tk.RIGHT)
```

**Step 2: Verify visually** (manual - launch UI and check tooltip)

**Step 3: Commit**

```
feat: display pattern label in score tooltip
```

---

### Task 12: Update module docstring (breakout_scorer.py)

**Files:**
- Modify: `BreakoutStrategy/analysis/breakout_scorer.py:1-24` (module docstring)

**Step 1: Update docstring to reflect new architecture**

```python
"""
突破评分模块（Bonus 乘法模型 + 模式标签）

突破评分公式：
    总分 = BASE x age_bonus x test_bonus x height_bonus x peak_volume_bonus x
           volume_bonus x breakout_day_strength_bonus x pbm_bonus x
           streak_bonus x pk_momentum_bonus x overshoot_penalty

模式标签（后处理）：
    基于主导 bonus 自动分类：momentum, historical, volume_surge,
    dense_test, trend_continuation, deep_rebound, power_historical,
    grind_through, basic

设计理念：
1. 所有因素统一为乘数形式，避免权重归一化
2. 满足条件时获得对应 bonus 乘数（>1.0），否则为 1.0（无加成）
3. 总分可超过 100，只要同一基准下可比即可
4. 模式标签不影响评分，仅为下游策略提供维度信息

阻力属性 Bonus：
- age_bonus: 最老峰值年龄（远期 > 近期）
- test_bonus: 测试次数（最大簇的峰值数）
- height_bonus: 最大相对高度
- peak_volume_bonus: 峰值放量

突破行为 Bonus：
- volume_bonus: 成交量放大
- breakout_day_strength_bonus: 突破日强度（合并 IDR-Vol 和 Gap-Vol）
- pbm_bonus: 突破前涨势强度 (Pre-Breakout Momentum)
- streak_bonus: 连续突破
- pk_momentum_bonus: 近期 peak 凹陷深度
- overshoot_penalty: 超涨惩罚
"""
```

**Step 2: Commit**

```
docs: update breakout_scorer module docstring
```

---

### Task 13: End-to-end verification

**Step 1: Import chain test**

Run: `cd /home/yu/PycharmProjects/Trade_Strategy && python -c "
from BreakoutStrategy.analysis import BreakoutScorer, ScoreBreakdown
scorer = BreakoutScorer()
print('ScoreBreakdown has pattern_label:', hasattr(ScoreBreakdown, '__dataclass_fields__') and 'pattern_label' in ScoreBreakdown.__dataclass_fields__)
print('Scorer has _classify_pattern:', hasattr(scorer, '_classify_pattern'))
print('Scorer has _get_breakout_day_strength_bonus:', hasattr(scorer, '_get_breakout_day_strength_bonus'))
print('Scorer does NOT have _get_gap_vol_bonus:', not hasattr(scorer, '_get_gap_vol_bonus'))
print('Scorer does NOT have _get_intraday_return_vol_bonus:', not hasattr(scorer, '_get_intraday_return_vol_bonus'))
"`
Expected: all True

**Step 2: Full config load test**

Run: `cd /home/yu/PycharmProjects/Trade_Strategy && python -c "
import yaml
from BreakoutStrategy.analysis import BreakoutScorer
with open('configs/params/scan_params.yaml') as f:
    cfg = yaml.safe_load(f)
scorer = BreakoutScorer(cfg.get('quality_scorer', {}))
print('overshoot values:', scorer.overshoot_penalty_values)
print('streak thresholds:', scorer.streak_bonus_thresholds)
print('bds enabled:', scorer.bds_bonus_enabled)
"`
Expected:
```
overshoot values: [0.8, 0.6]
streak thresholds: [2, 4]
bds enabled: True
```

**Step 3: Commit all**

```
feat: scoring system C+ — merge gap/idr, relax overshoot, add pattern labels

Implements the recommended C+ architecture from scoring pattern analysis:
- Merge gap_vol + idr_vol into breakout_day_strength bonus (fix double-counting)
- Relax overshoot penalty from [0.7, 0.4] to [0.80, 0.60]
- Expand streak bonus to 2 levels (2x->1.20, 4x->1.40)
- Add pattern classification labels (9 types)
- Display pattern label in score tooltip UI
```
