# path2_web debug 后端 · 精准断点设计(env var 联动框选 idx)

## Context

**问题**:PyCharm Debug 直接启动 `path2_web/main.py` 已跑通(DEBUG_MODE=1 → 8009 debug 后端 + reload=False,与 8000 主实例并存)。用户在 `path2/atoms/throwback.py` 关键 emit 位置手动打断点,但**每次前端 `/diagnose` 到达都跑整段 detector**,断点被反复命中——包括打开股票的 overall 诊断、切 pattern、hover 侧栏等场景,大部分与用户当前关注的 bar 无关,严重打扰调试流。

**目标**:让断点**只在用户框选窗内**命中,其他时候静默,支持"反复框同一段调同一 bar"的迭代调试节奏。

**手段**:抽一个 path2 顶层公用模块 `debug_ctx.py`,靠环境变量 `DEBUG_MODE` + `DEBUG_BAR_RANGE` 双闸控制;detector 埋一行 `debug_break(i)`,`/diagnose` handler 按 `start_bar/end_bar` 动态覆盖 range。

**前置(已落 working tree · 未 commit · 本 spec 不覆盖,但作为设计假设)**:

1. `configs/path2_web.yaml`:加 `backend_port_dbg`(用户已改为 8009)
2. `path2_web/config.py::DEFAULT_CONFIG`:同名 default
3. `path2_web/main.py::main()`:
   ```python
   DEBUG_MODE = os.environ.get("DEBUG_MODE") == "1"
   PORT = int(cfg["backend_port_dbg"] if DEBUG_MODE else cfg["backend_port"])
   RELOAD = not DEBUG_MODE
   ```
4. 前端 debug 侧手动跑(与主实例前端并存):
   ```bash
   cd path2_web_ui && VITE_API_BASE=http://localhost:8009 npm run dev -- --port 5179 --strictPort
   ```
5. PyCharm Debug config Env:`DEBUG_MODE=1`

以上 5 条已在 working tree 就绪(未 commit)。本 spec 只增量落实"精准断点"三个改动(§ B/C/D)。

**非目标**:见 § F。

---

## § A · 架构骨架

**新模块**:`path2/debug_ctx.py`。放 `path2/` 顶层(与 detector 平级,非 atoms 内部),使 atoms 及后续任何 detector 都可 import;detector 主逻辑保持纯净,debug 关注点物理隔离到一个文件。

**API 表面**:只暴露一个函数 `debug_break(i: int) -> None`。atom 一行调用即完成埋点。内部读 `_DEBUG_MODE`(模块顶部一次性算)和 `DEBUG_BAR_RANGE`(每次调用现读)。**不暴露** `is_debug_mode()`——按 YAGNI 精神只留一个入口,atom 内不做二次判断。

**性能**:`DEBUG_MODE=0` 时 `_DEBUG_MODE = False` 是模块级常量,`debug_break()` 第一行 `if not _DEBUG_MODE: return`——**dead code path,零成本**(一次比较即返)。

---

## § B · `path2/debug_ctx.py` 完整实现

```python
"""debug 断点辅助 · env var 驱动 · DEBUG_MODE=0 时全部 dead code。

- DEBUG_MODE=1(main.py 已消费,启 debug 后端 8009):启用 debug_break()
- DEBUG_BAR_RANGE="lo,hi"(handler 按 start_bar/end_bar 设):限定命中 bar 范围
- DEBUG_BAR_RANGE 未设:debug_break() 不停(避免打开股票就吵)
"""
import os
from typing import Optional

_DEBUG_MODE = os.environ.get("DEBUG_MODE") == "1"


def _read_range() -> Optional[tuple[int, int]]:
    """每次现读 env(handler 会动态覆盖);解析失败静默返 None,不干扰 detector。"""
    raw = os.environ.get("DEBUG_BAR_RANGE")
    if not raw:
        return None
    try:
        lo, hi = (int(x) for x in raw.split(","))
        return lo, hi
    except (ValueError, TypeError):
        return None


def debug_break(i: int) -> None:
    """在 detector 埋点处调用:DEBUG_MODE=1 且 i 落在 DEBUG_BAR_RANGE 内 → 触发 breakpoint()。

    未设 DEBUG_BAR_RANGE = 不停(需框选一次 time diag 才激活)。
    breakpoint() 走 sys.breakpointhook,PyCharm pydevd 会 hook,等同该行手动打点。
    PYTHONBREAKPOINT=0 可完全短路。
    """
    if not _DEBUG_MODE:
        return
    r = _read_range()
    if r is None:
        return
    if r[0] <= i <= r[1]:
        breakpoint()
```

**要点**:
- `_DEBUG_MODE` 模块级常量(进程启动时一次性算)→ 关闭态是 dead code
- `_read_range()` 每次现读 env(handler 会覆盖)→ 无缓存,直接反映最新框选
- 解析异常静默 return None(detector 是热路径,不因 env 格式错误 crash)
- `DEBUG_BAR_RANGE` 未设 → 不停("打开股票不吵,框选一次才激活")

---

## § C · `path2/atoms/throwback.py` 埋点具体形态

改动只在 `path2/atoms/throwback.py:85-112` 的 `_emit_tb_gate`——**一行 import + 一行调用**。

**顶部 import**(现有 import 段末尾):

```python
from path2.debug_ctx import debug_break
```

**`_emit_tb_gate` 内部**(在 `if on_gate is None: return` 之后 · 方案 B):

```python
def _emit_tb_gate(bo_idx: int, gate_idx: int, gate_name: str,
                  measured: MeasuredKindAware, threshold,
                  atr_window: int,
                  on_gate: Optional[Callable[[GateFailure], None]],
                  *, op: Optional[str] = None,
                  threshold_param: Optional[str] = None) -> None:
    """辅助 · 组装 GateFailure 并 emit(避免 4 处埋点重复 boilerplate)。..."""
    if on_gate is None:
        return                          # ← 现有 · scan 路径静默早退
    debug_break(gate_idx)               # ← 新增 · 只在 diagnose 路径生效(方案 B)
    on_gate(GateFailure(
        failure_event_window=(bo_idx + 1, gate_idx),
        ...
    ))
```

**关键决定**:

- **埋在 `if on_gate is None: return` 之后(方案 B)**:位置放在这个早退分支之后,让「压根没挂 gate-failure 消费者」的调用方式(local invariant)也不会触发 `debug_break`。⚠**勘误(见本节末尾)**:这不等于「scan 路径完全绕过」——真实 scan 会 attach 非 None 的 `on_gate`,`debug_break(gate_idx)` 在 scan 上同样执行,真正挡住它的是 `_DEBUG_MODE=False`
- **传 `gate_idx` 而非 `bo_idx`**:`gate_idx` 是失败**实际发生**的 bar,与前端框选 (start_bar/end_bar) 天然对齐;`bo_idx` 是 BO 起点,一次 `evaluate_throwback` 内多个失败共用同一 bo_idx,过滤粒度太粗
- **4 处 call site(139/161/171/201)不需要任何改动**:单点埋、覆盖 4 种 gate failure(phase1_break / pullback_shortage / no_trough_timeout / phase2_break),DRY

**bo/trend/burst 等其他 atoms**:本 spec **不预先埋点**;后续想 debug 时按需调 `debug_break(<bar_idx>)`,加一行 import + 一行调用即可。`debug_ctx` 已作为公用基础设施准备好。

### 勘误(final holistic review,post-implementation)

上面「scan 路径完全绕过」的表述**不准确**,在此更正:

- 真实 scan 路径是 `path2_web/scan.py:68`(`collector = attach_and_collect(spec)`)→ `path2_web/gate_collector.py:41`(`node.detector.on_gate = collector.add`)。也就是说 **`on_gate` 在真实 scan 中并非 None**,`_emit_tb_gate` 不会在 `if on_gate is None: return` 处早退,`debug_break(gate_idx)` 在 scan 路径上同样会被调用。
- `on_gate is None` 这个早退分支只是一个 **local invariant**——防御「压根没挂任何 gate-failure 消费者」的调用方式(比如某些直接单测调用 `_emit_tb_gate` 但不传 `on_gate`)。它不是 scan 与 diagnose 的分野。
- 真正让 8000 主进程的 scan 免受断点侵入的机制是 `path2/debug_ctx.py` 里的 **`_DEBUG_MODE` 模块级常量**:8000 主进程没有设 `DEBUG_MODE=1`,所以 `debug_break()` 内部第一行 `if not _DEBUG_MODE: return` 就早退了——bypass 发生在 `debug_ctx.py` 内部,不在 `_emit_tb_gate` 的 `on_gate` 判断里。

### Known Limitation:8009 debug 后端上跑 `/scan` 可能静默 hang

若在 8009 debug 后端(`DEBUG_MODE=1`)上发起 `/scan`(而非 `/diagnose`):`scan.py` 用 `ProcessPoolExecutor` fork worker 子进程,worker 会继承父进程 env——即 `DEBUG_MODE=1` 与当前 `DEBUG_BAR_RANGE`。若某只股票的 detector 在该 bar range 内恰好命中 gate failure,`debug_break()` 会在 worker 子进程里触发 `breakpoint()`;但 worker 子进程没有可交互的 stdin(pdb 拿不到终端),会**静默 hang**——不报错、不返回,扫描任务卡死不动、界面无任何提示。

**已知限制,用户选择接受、不加代码 gate 防护**。建议用法:

- 8009 debug 后端只用来跑 `/diagnose`(单股即时诊断,单进程同步执行,断点行为符合预期);
- `/scan`(批量、多进程)只在 8000 主实例上跑(`DEBUG_MODE` 未设 → `_DEBUG_MODE=False` → `debug_break` 早退,零风险);
- 若确实要在 8009 上跑 `/scan`,建议跑之前先 `unset DEBUG_BAR_RANGE`(更稳妥的做法还是把 `/scan` 留给 8000)。

---

## § D · `path2_web/api.py::/diagnose` handler env 注入

改动在 `path2_web/api.py:197` `/diagnose` handler 顶部。**只 set 不 clear**——用户已选"overall diag 不清 env",保留上次框选 range 支持"反复调同一段"。

```python
@router.get("/diagnose")
def get_diagnose(pattern_id: str, symbol: str, start: str, end: str,
                 scope: Optional[str] = None,
                 ...
                 start_bar: Optional[int] = None, end_bar: Optional[int] = None):
    # ← 新增 2 行:仅 time diag(start_bar/end_bar 齐全)写 DEBUG_BAR_RANGE;
    # overall diag(无 bar)不动 env,保留上次框选的 range,支持"反复调同一段"。
    if start_bar is not None and end_bar is not None:
        os.environ["DEBUG_BAR_RANGE"] = f"{start_bar},{end_bar}"
    # ↓ 现有代码不变
    mod = registry.get(pattern_id)
    ...
```

**顶部 `import os`**:落地时确认 `api.py` 是否已 import(大概率已有)。

**行为矩阵**:

| 前端动作 | request | handler 写 env? | detector 内 `debug_break` 行为 |
|---|---|---|---|
| 打开股票 | `getDiagnose` overall(无 bar) | ✗ 不动 | 首次 → env 未设 → 不停;有上次 range → 沿用 |
| 框选 245-260 | `getTimeDiagnose(scope=time, start_bar=245, end_bar=260)` | ✓ set `"245,260"` | 停在 `i∈[245,260]` |
| 再打开另一只股 | overall(无 bar) | ✗ 不动 | 上次 range 仍在 → 停 245-260(新股上下文里的 bar 索引) |
| 再框选 300-320 | `getTimeDiagnose(..., 300, 320)` | ✓ set `"300,320"` | 覆盖上次,停 300-320 |
| 想解除 range | — | — | 重启 8009 debug 后端 |

**注意点**:

- **DEBUG_MODE=0**(生产/主实例)时,handler 照样 set env——但 `debug_break` 里 `if not _DEBUG_MODE: return` 早退,**env 写了也白写**,零副作用
- **8000 主实例也会执行这段 handler 代码**:不影响它自己(`_DEBUG_MODE=False`),但会污染 process env——不是问题,因为 8000 主实例不 debug、不读这个 env
- **不 unset**:意味着 `DEBUG_BAR_RANGE` 可能持续到进程退出。可接受(8009 debug 后端是短生命周期开发工具进程)

---

## § E · Verification

### 单元测试(`tests/path2/test_debug_ctx.py`)

覆盖纯函数解析 + 断点触发条件:

- **`_read_range` 解析**:
  - 未设 env / `""` → None
  - `"245,260"` → `(245, 260)`
  - `"bogus"` / `"1,2,3"` / `"abc,def"` → None(异常安全)
- **`debug_break` 触发**(mock breakpoint 姿势:`monkeypatch.setattr("builtins.breakpoint", mock)` 或 `monkeypatch.setattr(sys, "breakpointhook", mock)`,择一;`_DEBUG_MODE` 是模块级常量,测试里改 env 不生效,需 `monkeypatch.setattr(debug_ctx, "_DEBUG_MODE", True/False)` 直接注入):
  - `_DEBUG_MODE=False` → 从不调
  - `_DEBUG_MODE=True` + range 未设 → 不调
  - `_DEBUG_MODE=True` + range=(245,260) + i=250 → 调 1 次
  - `_DEBUG_MODE=True` + range=(245,260) + i=270 → 不调

### 手动端到端验证

| # | 前置 | 操作 | 预期 |
|---|---|---|---|
| 1 | 只启 8000 主实例(`run_path2_web.py`),`DEBUG_MODE` 未设 | 前端 5170 打开股票、框选任意段 | 无断点触发(PyCharm 未 attach,`debug_break` 里 `_DEBUG_MODE=False` 早退) |
| 2 | 加启 8009 debug 后端(PyCharm Debug + `DEBUG_MODE=1`),单独前端 5179 指向 8009 | 5179 打开股票,**不框选** | `debug_break` 里 `_read_range` 返 None → 不停 |
| 3 | 同 #2 | 5179 主图 brush 框选 245-260 | `/diagnose?scope=time&start_bar=245&end_bar=260` 到达 → env set;detector 跑到 gate failure 且 `gate_idx∈[245,260]` → PyCharm 停在 `debug_ctx.py::debug_break` 的 `breakpoint()`;Frames 里能看到 `throwback._emit_tb_gate` 与 `gate_name` 局部 |
| 4 | 同 #3 continue 后 | 换另一只股再框选 300-320 | env 更新到 `"300,320"`;新股 detector 停在 `i∈[300,320]`;245-260 不再触发 |

### 回归验证

- `pytest tests/path2/` 全绿(含新增 `test_debug_ctx` + 现有 detector 测试不受影响:`on_gate=None` 分支照旧提前 return,detector 计算量、输出格式零变化)
- `uv run python scripts/path2_filter_bottom_burst.py` 或已有全集扫描脚本跑一遍 → 结果与 `DEBUG_MODE` 引入前**逐行等价**(scan 路径 `on_gate=None`,`debug_break` 从未被调用)

---

## § F · 非目标 / 兜底约定

**非目标(明确排除)**:

- **不改前端**:前端触发 debug 后端由用户按 memo §1.3 命令另开 vite dev server(`VITE_API_BASE=http://localhost:8009 npm run dev -- --port 5179 --strictPort`),不做任何 UI 侵入
- **不做 contextvars 版**:用户已裁 env var 单人 debug 场景够用;若未来要 debug 多用户并发场景再单独 spec
- **不改 bo/trend/burst atoms**:本 spec 只落 throwback 一处埋点 + `debug_ctx` 公用基础设施;其他 atoms 后续想 debug 时自行加一行 import + 一行 `debug_break(<bar_idx>)`
- **不做 range 清除的显式 UI / API**:想解除 range 就重启 8009 debug 后端;`DEBUG_BAR_RANGE` 不持久化到 yaml/文件、只活在 process env
- **不埋成功链路断点**:用户当前只需"失败 gate 前停";后续想在 `_find_start_idx` 成功 return trough_idx 前停,追加一行 `debug_break(trough_idx)` 即可,不在本 spec 承诺
- **不合并 `DEBUG_MODE` 与 `DEBUG_BAR_RANGE` 到单 env**:两个语义正交(前者= debug 后端启用、后者= 范围过滤),分离让 range 可独立动态覆盖
- **不改 `scan.py` subprocess pool**:workers 走独立 process,env 天然不共享;`DEBUG_MODE=1` 也不影响 scan 结果(scan 是 8000 主实例,8009 debug 后端根本不跑 scan)

**兜底 · 边缘行为约定**:

- **`DEBUG_BAR_RANGE` 解析异常**(`"bogus"` / `"1,2,3"`)→ `_read_range` 静默返 None(等同未设)→ `debug_break` 不停。detector 是热路径,绝不因 env 格式错误 crash
- **PyCharm 没 attach 但 `DEBUG_MODE=1`**(用户在 shell 直接跑 debug 后端)→ 命中 `breakpoint()` 会进入命令行 pdb(Python 默认行为)。设计上是正确后果,不特别处理;嫌吵就 `PYTHONBREAKPOINT=0` 总闸关掉
- **`debug_break(i)` 中 i 参数语义** = 与前端 `start_bar/end_bar` 对齐的 bar 索引(同一 win 内 0-based)。后续 detector 埋点时用最贴切的 bar 索引(如 `_find_start_idx` 内的循环变量 `i`)

---

## Design 总览

```
┌─ path2/debug_ctx.py (新增,10 行)
│    _DEBUG_MODE = env["DEBUG_MODE"] == "1"           ← 模块级常量,关闭态 dead code
│    debug_break(i):
│      if not _DEBUG_MODE: return                     ← 早退
│      r = _read_range()                              ← 每次现读 env
│      if r and r[0] <= i <= r[1]: breakpoint()       ← 编程式断点
│
├─ path2/atoms/throwback.py (改动 2 行)
│    from path2.debug_ctx import debug_break          ← 新 import
│    def _emit_tb_gate(...):
│        if on_gate is None: return                   ← 现有 · local invariant 早退(见 § 勘误)
│        debug_break(gate_idx)                        ← 新增(dead-code when DEBUG_MODE=0)
│        on_gate(GateFailure(...))                    ← 现有
│
└─ path2_web/api.py::/diagnose (改动 2 行)
     if start_bar is not None and end_bar is not None:
         os.environ["DEBUG_BAR_RANGE"] = f"{start_bar},{end_bar}"   ← 新增(仅 time diag set)
```

**净改动**:+10 行新模块 + 2 行 throwback + 2 行 api handler = **14 行**(不含注释/docstring)。
