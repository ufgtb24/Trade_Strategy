# feature-study 关 3 双维去簇 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** feature-study 的关 3 从单一 symbol 去簇扩为「股内 + 时间桶」双维去簇，堵住同期跨股事件聚集（「那星期小盘股集体反弹」= 同一随机源的重复下注）从统计检验漏网。

**Architecture:** `_decluster` 加 `pick` 参数分家两个消费者（关 3 路径去 label 化、`tail_enrichment` 保留 per-symbol 最佳的排行榜语义）；`run_battery` 加 `time_bucket_days` 参数，关 3 拆 3a（symbol 簇）/ 3b（时间簇）两检各自重算 p、两检都过才算过关；判定文案区分死因（个股驱动 / 事件驱动）；另附串联下界读数（先股后时各留一条，仅报告不做闸）；verdicts 结构向后兼容（`gate3 = 3a ∧ 3b`）。

**Tech Stack:** pandas / numpy / scipy.stats（既有依赖，零新增）；pytest（显式路径跑）。

**Spec:** 本文件「设计依据（敲定稿）」节 —— 设计于 2026-08-20 对话中逐条敲定并由用户拍板，无独立 spec 文档。本 plan 中所有项目内路径均相对 repo root。

## Global Constraints

- 项目内路径一律相对 repo root（如 `.claude/skills/feature-study/run_battery.py`）。
- 测试显式路径跑、不进默认 pytest 收集：`uv run pytest .claude/skills/feature-study/test_run_battery.py -q`。
- **`tail_enrichment` 行为不得变**（per-symbol 最佳 = 镜像 UI 排行榜的语义本身）。
- **既有 5 个测试必须零破坏**（它们都不带 `tb_start` 列、不传时间参数，走 3b 降级路径，是向后兼容的回归网）。
- **不动 tune-gates**（时间桶分解列 / se 两维 bootstrap / 功效线聚集读数，按 2026-08-20 讨论延后到首轮实战 `reference.md` 一起进）。
- 注释 / 文档中文；commit message 沿用项目风格（`feat(skill): …` / `docs(skill): …`）。

## 设计依据（敲定稿，2026-08-20 对话）

1. **保留双维、不删 symbol 键**：label 的共同成分有两个来源——同股不同期（个股成分：波动率水平、筹码结构、回踩特征）与同期不同股（时段成分：集体反弹事件）。symbol 去簇守股票轴泛化，时间去簇守时间轴泛化，缺一留盲区。双检分开还能区分死因：3a 死 = 个股驱动、3b 死 = 事件驱动。
2. **簇代表选择去 label 化（仅关 3 路径）**：现实现「每 symbol 留 label 最高一条」被 label 选择污染——集体反弹周的 label 系统性最高，留下的恰恰是吃到反弹的样本，对时间聚集是反向选择。关 3 改为留数据原序首条（固定规则、与 label 无关）。`tail_enrichment` 的 per-symbol 最佳是排行榜语义，保留。
3. **时间桶键 = `tb_start // time_bucket_days`**：`extract_skeleton` 各股 `win` 用同一个 scan 切窗 `(win_start, win_end)`，日期轴完全一致，故 `tb_start`（窗内 bar 序号）跨股直接可比，不需要日期对齐。桶宽由调用方从 scan 的 `label_horizon` 取整传入（桶宽 ≥ label_horizon 才保证 forward window 重叠的 match 归同簇；推荐取整到 5 的倍数）。
4. **两检各自过、不做复合簇键**：簇 = symbol×时间桶 是错的（「同股同桶」漏掉跨股同桶）。对应计量里的双向聚类思想：3a、3b 各自去簇重算、各自 p<0.05 且同号，两检都过才算关 3 过。
5. **串联下界仅报告不做闸**：先 symbol 后 time 各留首条再重算，作为「最保守视角还剩什么」的报告行。
6. **降级路径对齐「无 controls」模式**：`time_bucket_days=None` 或 CSV 缺 `tb_start` 列时 3b 跳过，打印警告、verdict 标注降级、`gate3 = gate3_sym`；不 raise。
7. **`extract_skeleton` 补 `tb_date` 列**（`win["date"].iat[t0]`）：纯报告可读性——诊断「死在哪个事件」时能说出日期桶，`run_battery` 消费的是 `tb_start` 序号。

---

### Task 1: `_decluster` 分家（pick 参数）

**Files:**
- Modify: `.claude/skills/feature-study/run_battery.py:84-86`（`_decluster`）及 `:92`（`tail_enrichment` 内调用点）
- Test: `.claude/skills/feature-study/test_run_battery.py`（追加）

**Interfaces:**
- Consumes: 现有 `_decluster(d: pd.DataFrame, label: str) -> pd.DataFrame`。
- Produces: `_decluster(d: pd.DataFrame, label: str, pick: str = "best") -> pd.DataFrame`——`pick="best"` 行为与现实现逐字节等价（每 symbol 留 label 最高一条）；`pick="first"` 每簇留数据原序首条（与 label 无关）。Task 2 的关 3 将消费 `pick="first"`。

- [ ] **Step 1: Write the failing test**

追加到 `test_run_battery.py`（同时把 import 行改为 `from run_battery import _bh_fdr, _decluster, run_battery`）：

```python
def test_decluster_pick_modes():
    """pick 分家:first=数据原序首条(与 label 无关);best=每簇 label 最高(旧行为)。"""
    d = pd.DataFrame({"symbol": ["A", "A", "B"],
                      "label": [1.0, 5.0, 2.0]})
    first = _decluster(d, "label", pick="first")
    best = _decluster(d, "label", pick="best")
    # A 股两行:原序首条 label=1.0;label 最高 label=5.0。B 股一条两边都在。
    assert set(first["label"]) == {1.0, 2.0}
    assert set(best["label"]) == {5.0, 2.0}


def test_tail_enrichment_keeps_best_semantics():
    """tail_enrichment 保留 per-symbol 最佳(镜像 UI 排行榜的语义,不随关 3 改)。"""
    from run_battery import tail_enrichment
    d = pd.DataFrame({"symbol": ["A", "A", "B"],
                      "label": [5.0, 1.0, 2.0],
                      "flag": [0, 1, 1]})
    # per-symbol 最佳行:A(label=5, flag=0)、B(label=2, flag=1) → 基率 1/2
    lines = tail_enrichment(d, "flag", "label", ks=(2,))
    assert "50.0%" in lines[0]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest .claude/skills/feature-study/test_run_battery.py -q`
Expected: 新增 2 测试 FAIL（`_decluster() got an unexpected keyword argument 'pick'`；`tail_enrichment` 用例可能 PASS——它锁的是旧行为，作为分家不回归的哨兵，PASS 也可接受），既有 5 测试 PASS。

- [ ] **Step 3: Write minimal implementation**

改 `run_battery.py` 的 `_decluster`：

```python
def _decluster(d: pd.DataFrame, label: str, pick: str = "best") -> pd.DataFrame:
    """去簇(观测非独立的稳健性检查)。

    pick="best":每 symbol 留 label 最高一条 —— tail_enrichment 消费
        (镜像 UI 排行榜,排行榜展示的就是每只股票的最佳,语义本身)。
    pick="first":每 symbol 留数据原序首条 —— 关 3 消费。稳健性检查的簇代表
        不能由 label 挑选,否则检验被选择污染,还会反向保留事件聚集样本
        (集体反弹周 label 系统性偏高,留最高恰好吃到反弹的那条)。
    """
    if pick == "best":
        return d.sort_values(label, ascending=False).groupby("symbol").head(1)
    return d.groupby("symbol", sort=False).head(1)
```

同时把 `tail_enrichment` 内 `:92` 的 `best = _decluster(d, label)` 改为 `best = _decluster(d, label, pick="best")`（语义显式化，行为不变）。本 task **不动** 关 3 的 `:184` 调用点（默认 `pick="best"` 保持旧行为，Task 2 再改）。

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest .claude/skills/feature-study/test_run_battery.py -q`
Expected: 7 passed。

- [ ] **Step 5: Commit**

```bash
git add .claude/skills/feature-study/run_battery.py .claude/skills/feature-study/test_run_battery.py
git commit -m "feat(skill): _decluster 加 pick 分家——关3 将去 label 化,tail_enrichment 显式保留排行榜语义"
```

---

### Task 2: 时间簇 + 关 3 双检 + 死因文案 + 串联下界

**Files:**
- Modify: `.claude/skills/feature-study/run_battery.py`（签名 / docstring 三关描述 / 关 3 段 `:183-199` / 判定段 `:201-227`）
- Test: `.claude/skills/feature-study/test_run_battery.py`（追加）

**Interfaces:**
- Consumes: Task 1 的 `_decluster(d, label, pick="first")`。
- Produces:
  - 模块级 `_decluster_time(d: pd.DataFrame, label: str, bucket_days: int, time_col: str = "tb_start") -> pd.DataFrame`——同时间桶（`tb_start // bucket_days`）只留数据原序首条。
  - 模块级 `_retest(dset: pd.DataFrame, m: str, label: str, kind: str) -> tuple[float, float]`——在给定集合上重算特征-label 关联（`kind="cont"` 用 Spearman；`kind="bin"` 用 Mann-Whitney，保留既有 `len(g1)>=5 and len(g0)>=5` 守护，不足返回 `(nan, 1.0)`）。
  - `run_battery(csv_path, features, label="label", binaries=None, controls=None, win_thresholds=(0.10, 0.30), time_bucket_days=None) -> dict`。
  - verdicts dict 每项新增 `gate3_sym: bool`、`gate3_time: bool | None`（None = 时间维未跑）、`declust_time_p: float | None`；既有 `gate3` 语义升级为 `3a ∧ 3b`（时间维未跑时 = `gate3_sym`）、既有 `declust_p` 保留为股内维读数。Task 3 的 SKILL.md 按此口径写文档。

- [ ] **Step 1: Write the failing tests**

追加到 `test_run_battery.py`：

```python
def _csv(d: pd.DataFrame, name: str) -> str:
    p = Path(f"/tmp/fs_{name}.csv")
    d.to_csv(p, index=False)
    return str(p)


def test_gate3a_symbol_cluster_kills(capsys):
    """股簇杀:相关由 3 只妖股各 15 条重复观测刷出 → 股内去簇(留首条)后死。"""
    rng = np.random.default_rng(5)
    rows = []
    for i in range(3):  # 3 只妖股 × 15 条,股内 x/label 双高
        x = rng.normal(2, 0.4, 15); lab = rng.normal(2, 0.5, 15)
        rows += [(f"M{i}", j * 3, xx, ll) for j, (xx, ll) in enumerate(zip(x, lab))]
    for i in range(40):  # 40 只正常股各 1 条,无关联
        rows.append((f"S{i}", 100 + i * 5, rng.normal(0, 1), rng.normal(0, 1)))
    d = pd.DataFrame(rows, columns=["symbol", "tb_start", "x_m", "label"])
    v = run_battery(_csv(d, "symclus"), features=["x_m"], binaries=[],
                    controls=[], time_bucket_days=5)["x_m"]
    assert v["gate1"] and v["gate3_sym"] is False
    assert "个股驱动" in v["verdict"] and v["gate3"] is False


def test_gate3b_time_cluster_kills(capsys):
    """时簇杀:每股一条(3a 无压缩)、但 20 股挤同一时间桶 → 时间去簇后死。"""
    rng = np.random.default_rng(11)
    n0 = 40  # 分散桶,每股一条,无关联
    x0 = rng.normal(0, 1, n0); lab0 = rng.normal(0, 1, n0)
    tb0 = np.arange(n0) * 5           # 桶 0..39,每桶一条
    n1 = 20   # 事件簇:同一桶,x/label 双高
    x1 = rng.normal(3, 0.3, n1); lab1 = rng.normal(3, 0.5, n1)
    tb1 = np.full(n1, 400)            # 全在桶 80
    d = pd.DataFrame({"symbol": [f"S{i}" for i in range(n0 + n1)],
                      "tb_start": np.concatenate([tb0, tb1]),
                      "x_ev": np.concatenate([x0, x1]),
                      "label": np.concatenate([lab0, lab1])})
    v = run_battery(_csv(d, "timeclus"), features=["x_ev"], binaries=[],
                    controls=[], time_bucket_days=5)["x_ev"]
    assert v["gate1"] and v["gate3_sym"] is True   # 每股一条,股内去簇活着
    assert v["gate3_time"] is False                # 时间去簇杀死
    assert "事件驱动" in v["verdict"] and v["gate3"] is False


def test_gate3_both_pass(capsys):
    """两检都过:每股一条、每桶一条的普通强相关 → gate3 True。"""
    rng = np.random.default_rng(3)
    n = 60
    x = rng.normal(0, 1, n)
    d = pd.DataFrame({"symbol": [f"S{i}" for i in range(n)],
                      "tb_start": np.arange(n) * 5,
                      "x_ok": x, "label": x + 0.5 * rng.normal(0, 1, n)})
    v = run_battery(_csv(d, "bothpass"), features=["x_ok"], binaries=[],
                    controls=[], time_bucket_days=5)["x_ok"]
    assert v["gate3_sym"] is True and v["gate3_time"] is True
    assert v["gate3"] is True and "有信号" in v["verdict"]


def test_time_dim_missing_degrades(capsys):
    """缺 tb_start 列或未传 time_bucket_days → 3b 跳过,verdict 标注降级。"""
    rng = np.random.default_rng(3)
    n = 60
    x = rng.normal(0, 1, n)
    d = pd.DataFrame({"symbol": [f"S{i}" for i in range(n)],
                      "x_ok": x, "label": x + 0.5 * rng.normal(0, 1, n)})
    out = capsys.readouterr().out
    v1 = run_battery(_csv(d, "nocol"), features=["x_ok"], binaries=[],
                     controls=[], time_bucket_days=5)["x_ok"]      # 有参数、缺列
    v2 = run_battery(_csv(d, "nocol"), features=["x_ok"], binaries=[],
                     controls=[])["x_ok"]                          # 无参数(默认)
    for v in (v1, v2):
        assert v["gate3_time"] is None and v["declust_time_p"] is None
        assert v["gate3"] == v["gate3_sym"] is True
        assert "时间维未检" in v["verdict"]
    assert "tb_start" in capsys.readouterr().out  # 警告打印提到缺列原因
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest .claude/skills/feature-study/test_run_battery.py -q`
Expected: 新增 4 测试 FAIL（`gate3_sym` 等 key 不存在 / 文案不匹配），既有 7 测试 PASS。

- [ ] **Step 3: Write the implementation**

对 `run_battery.py` 做以下修改（一次成形，代码如下）：

**(a) 模块级新增两个函数**（放 `_decluster` 之后）：

```python
def _decluster_time(d: pd.DataFrame, label: str, bucket_days: int,
                    time_col: str = "tb_start") -> pd.DataFrame:
    """同时间桶只留数据原序首条(同期跨股共同事件的去簇)。

    桶键 = time_col // bucket_days。time_col 是同一 scan 切窗内的 bar 序号,
    各股日期轴一致,跨股直接可比。簇代表不按 label 挑选(理由同 pick="first")。
    桶宽机制:两笔 match 的 forward window 重叠 ⟺ label 随机源共享,故桶宽
    下界 = label_horizon 的交易日数,调用方从 scan 取整后传入。
    """
    return (d.assign(_bucket=d[time_col] // bucket_days)
             .groupby("_bucket", sort=False).head(1)
             .drop(columns="_bucket"))


def _retest(dset: pd.DataFrame, m: str, label: str, kind: str) -> tuple[float, float]:
    """在给定集合上重算特征-label 关联(股内/时间/串联三处共用)。"""
    if kind == "cont":
        ok = dset[m].notna() & dset[label].notna()
        rs, ps = stats.spearmanr(dset.loc[ok, m], dset.loc[ok, label])
        return float(rs), float(ps)
    g1, g0 = dset.loc[dset[m] == 1, label], dset.loc[dset[m] == 0, label]
    if len(g1) >= 5 and len(g0) >= 5:
        _, ps = stats.mannwhitneyu(g1, g0, alternative="two-sided")
        return float(g1.median() - g0.median()), float(ps)
    return np.nan, 1.0
```

**(b) `run_battery` 签名**追加 `time_bucket_days: int | None = None`（放 `win_thresholds` 之后）。

**(c) 关 3 段**（原 `:183-199`）整段替换为：

```python
    # 关3:双维去簇(股内簇 + 时间簇,两检各自过;代表选择与 label 无关)
    sym_first = _decluster(d, label, pick="first")
    run_time = time_bucket_days is not None and "tb_start" in d.columns
    if time_bucket_days is not None and "tb_start" not in d.columns:
        print("⚠ 已传 time_bucket_days 但 CSV 缺 tb_start 列:关3 时间维跳过,判定降级")
    if time_bucket_days is None:
        print("⚠ 未传 time_bucket_days:关3 时间维跳过(桶宽应从 scan 的 label_horizon 取整),判定降级")
    time_first = _decluster_time(sym_first if run_time else d, label,
                                 time_bucket_days) if run_time else None
    print(f"\n== 关3a 股内去簇(每 symbol 首条,n={len(sym_first)}) ==")
    declust_sym = {m: _retest(sym_first, m, label, raw[m]["kind"])
                   for m in features + binaries}
    for m, (ds, dp) in declust_sym.items():
        print(f"{m:24s} stat={ds:+.3f} p={dp:.2g}")
    if time_first is not None:
        print(f"== 关3b 时间去簇(每时间桶首条,桶宽={time_bucket_days},n={len(time_first)}) ==")
        declust_time = {m: _retest(time_first, m, label, raw[m]["kind"])
                        for m in features + binaries}
        for m, (ds, dp) in declust_time.items():
            print(f"{m:24s} stat={ds:+.3f} p={dp:.2g}")
        ser = _decluster_time(d, label, time_bucket_days)   # 串联下界:先股后时
        print(f"== 关3 串联下界(先股内后时间各留首条,n={len(ser)};最保守读数,不做闸) ==")
        for m in features + binaries:
            ds, dp = _retest(ser, m, label, raw[m]["kind"])
            print(f"{m:24s} stat={ds:+.3f} p={dp:.2g}")
    else:
        declust_time = {}
```

注意串联下界在**原始 d** 上先按 symbol 再按时间各留首条（不是在 `sym_first` 上再做时间——`time_first` 是对 `sym_first` 做的 3b，两者口径不同：3b 单独检时间维时先过一道 symbol 去簇可避免股簇干扰时簇读数；串联下界则是双维同时压缩的最保守集合）。

**(d) 判定段**（原 `:201-227`）中关 3 相关部分替换为：

```python
    for m in features + binaries:
        v = raw[m]
        gate1 = v["q_fdr"] < 0.05
        sign_ok = (np.sign(t_ctrl[m]) == np.sign(v["stat"])) if controls else True
        gate2 = (abs(t_ctrl[m]) >= 2 and sign_ok) if controls else None
        ds_sym, dp_sym = declust_sym[m]
        gate3_sym = dp_sym < 0.05 and np.sign(ds_sym) == np.sign(v["stat"])
        if m in declust_time:
            ds_time, dp_time = declust_time[m]
            gate3_time = (dp_time < 0.05
                          and np.sign(ds_time) == np.sign(v["stat"]))
        else:
            ds_time, dp_time, gate3_time = np.nan, None, None
        gate3 = gate3_sym if gate3_time is None else (gate3_sym and gate3_time)
        time_note = "" if gate3_time is not None else ";时间维未检(缺 tb_start 列或未传 time_bucket_days),关3 降级"
        if not gate1:
            verdict = "无信号"
        elif controls and abs(t_ctrl[m]) >= 2 and not sign_ok:
            verdict = ("反转(suppression):原始方向由控制集承载,"
                       f"控制后残余反向 t={t_ctrl[m]:+.2f}")
        elif gate2 is False:
            verdict = "代理(被控制集吸收)"
        elif not gate3_sym and gate3_time is False:
            verdict = "不稳(双维去簇均不显著,个股+事件混合驱动)"
        elif not gate3_sym:
            verdict = "不稳(股内去簇后不显著,疑似个股驱动——少数股票反复观测刷出)"
        elif gate3_time is False:
            verdict = "不稳(时间去簇后不显著,疑似事件驱动——同期跨股共同行情)"
        elif not gate3:
            verdict = "不稳(去簇后不显著)"
        else:
            verdict = ("有信号" if controls else "疑似有信号(无控制,降级)")
            verdict += f",方向{'+' if v['stat'] > 0 else '−'}"
            if m in shapes:
                verdict += f",形状:{shapes[m]}"
        verdict += time_note
        verdicts[m] = dict(verdict=verdict, gate1=gate1, gate2=gate2, gate3=bool(gate3),
                           gate3_sym=bool(gate3_sym), gate3_time=gate3_time,
                           q_fdr=v["q_fdr"], t_ctrl=t_ctrl.get(m),
                           declust_p=dp_sym, declust_time_p=dp_time)
        print(f"{m:24s} → {verdict}")
    return verdicts
```

**(e) docstring 三关描述**更新（`"""` 块内）：

```
    关3 去簇存活(双维,两检各自过):
        3a 股内:每 symbol 留数据原序首条(不按 label 挑)后重算,p<0.05 且同号
            → 防「特征效应其实是少数个股反复观测刷出」(股票轴泛化检查)
        3b 时间:每时间桶(tb_start//time_bucket_days)留首条后重算,同款判据
            → 防「同期跨股共同事件(如某周小盘集体反弹)是同一随机源的
               重复下注」(时间轴泛化检查;桶宽从 scan 的 label_horizon 取整,
               ≥horizon 才保证 forward window 重叠的 match 归同簇)
        time_bucket_days=None 或 CSV 缺 tb_start 列 → 3b 跳过,verdict 标注降级
        死因可区分:3a 死=个股驱动 / 3b 死=事件驱动;另打印串联下界
        (先股内后时间各留首条,最保守读数)仅报告不做闸
    三关全过 = 有信号;过1而关2 |t|<2 = 代理(被控制集吸收);关1不过 = 无信号。
    controls 为空时关2 跳过,结论必须标注"无已知信号可控,判定降级"。

CSV 约定:必含 symbol、label 列;features/binaries/controls 为其列名子集;
        做时间维去簇另需 tb_start 列(同一 scan 窗内 bar 序号,跨股可比)。
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest .claude/skills/feature-study/test_run_battery.py -q`
Expected: 11 passed（新 4 + 旧 7）。旧 5 个 battery 测试走 `gate3_time=None` 降级路径零破坏；`test_decluster_pick_modes` / `test_tail_enrichment_keeps_best_semantics` 不受影响。

- [ ] **Step 5: Commit**

```bash
git add .claude/skills/feature-study/run_battery.py .claude/skills/feature-study/test_run_battery.py
git commit -m "feat(skill): 关3 扩双维去簇——股内簇+时间桶两检各自过,死因区分个股/事件驱动,串联下界仅报告"
```

---

### Task 3: `extract_skeleton` 补 `tb_date` + SKILL.md 同步

**Files:**
- Modify: `.claude/skills/feature-study/extract_skeleton.py:144-150`（`o` dict）及 docstring 产出说明
- Modify: `.claude/skills/feature-study/SKILL.md`（第 3 步示例 / 第 4 步判定 / 第 5 步结论纪律 / 常见坑表 / 沿革）

**Interfaces:**
- Consumes: Task 2 的 `run_battery(..., time_bucket_days=...)` 签名与 verdicts 口径（`gate3_sym` / `gate3_time` / 死因文案）。
- Produces: dataset.csv 多一列 `tb_date`（报告可读用；`run_battery` 消费的是 `tb_start` 序号，`tb_date` 不进电池）。

- [ ] **Step 1: Modify `extract_skeleton.py`**

`o` dict 内（`tb_start=t0, tb_end=t1,` 一行之后）加一行：

```python
            o = dict(symbol=sym, tb_id=tb.instance_id, bo_id=tb.anchor_bo_id,
                     bo_idx=b, tb_start=t0, tb_end=t1,
                     tb_date=str(win["date"].iat[t0]),   # 时间桶诊断可读用(电池用 tb_start 序号)
```

并在 docstring 产出清单（`产出 CSV:每行 = …` 段）的列说明里补一句：`tb_date(tb_start 对应日期,双维去簇的事件诊断可读用;各股 win 同一切窗,tb_start 序号跨股可比)`。

- [ ] **Step 2: Import smoke check**

Run: `uv run python -c "import sys; sys.path.insert(0, '.claude/skills/feature-study'); import extract_skeleton; print('import ok')"`
Expected: `import ok`（skeleton 的重活全在 `main()`，import 不触发数据读取）。

- [ ] **Step 3: Update SKILL.md（四处 + 沿革）**

1. 第 3 步统计电池的调用示例改为：

```python
verdicts = run_battery("dataset.csv", features=[连续口径列], binaries=[0/1列],
                       controls=["m1_burst_runup", "m2_depth_rel"],
                       time_bucket_days=10)  # 从 scan 的 label_horizon 取整到 5 的倍数
```

并紧跟一行说明：`桶宽 ≥ label_horizon 才保证 forward window 重叠的 match 归同簇(两笔 match 的 label 随机源共享 ⟺ 窗口重叠)`。

2. 第 4 步判定的三关描述改为：`三关 = FDR q<0.05 → 控制后 |t|≥2 且同号 → 双维去簇(股内簇/时间桶)各自 p<0.05 且同号。`，其下补一行：`关 3 死因可区分:个股驱动(少数股票反复观测刷出)/事件驱动(同期跨股共同行情=同一随机源的重复下注);串联下界为最保守读数仅报告。`

3. 第 5 步结论纪律的「观测非独立(去簇已检)」改为「观测非独立(双维去簇已检:股内防个股复读、时间桶防事件复读)」。

4. 常见坑表追加一行：

```markdown
| 同期跨股 match 当独立样本 | 「那星期小盘股集体反弹」=同一随机源的重复下注,名义 n 虚高;时间桶去簇把关(桶宽锚 label_horizon) |
```

5. 沿革段末尾补：`2026-08-20 关3 扩双维去簇(股内簇+时间桶;簇代表去 label 化,tail_enrichment 的 per-symbol 最佳为排行榜语义保留)——同期跨股事件聚集是 symbol 单维去簇的盲区。`

- [ ] **Step 4: Full regression**

Run: `uv run pytest .claude/skills/feature-study/test_run_battery.py .claude/skills/tune-gates/test_plateau.py -q`
Expected: 11 + 8 = 19 passed（tune-gates 未动，应全绿）。

- [ ] **Step 5: Commit**

```bash
git add .claude/skills/feature-study/extract_skeleton.py .claude/skills/feature-study/SKILL.md
git commit -m "docs(skill): feature-study 同步双维去簇——骨架补 tb_date 列,SKILL.md 判定/坑表/沿革跟上"
```

---

## Self-Review 结论

- **Spec 覆盖**：设计依据 7 条 → Task 1 覆盖条 2（pick 分家 + tail 保留）、Task 2 覆盖条 1/3/4/5/6、Task 3 覆盖条 7 及文档同步；「不动 tune-gates」写入 Global Constraints。无缺口。
- **占位符扫描**：所有代码步骤均给出完整代码，无 TBD/「类似 Task N」。
- **类型一致性**：`gate3_sym`/`gate3_time`/`declust_time_p`/`_decluster_time`/`_retest`/`time_bucket_days` 在 Task 2 接口块、实现、测试断言与 Task 3 文档口径中一致。
