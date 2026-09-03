"""debug 断点辅助 · env var 驱动 · DEBUG_MODE=0 时零成本短路(一次 bool 比较即返)。

- DEBUG_MODE=1(main.py 已消费,启 debug 后端 8010):启用 debug_break()
- DEBUG_BAR_RANGE="lo,hi"(handler 按 start_bar/end_bar 设):限定命中 bar 范围
- DEBUG_ANCHOR_KIND="anchor_kind"(v3 · handler 按 anchor_kind query 设):限定命中锚点;未设或空串 = 全 anchor_kind fire
- DEBUG_BAR_RANGE 未设:debug_break() 不停(避免打开股票就吵)
"""
import os
from typing import Any, Optional

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


def _read_anchor_kind() -> Optional[str]:
    """读 DEBUG_ANCHOR_KIND env · 未设或空串返 None(v1 兼容 fallback:不做 anchor_kind 匹配)。"""
    r = os.environ.get("DEBUG_ANCHOR_KIND")
    return r if r else None


def debug_break(i: int, *, anchor_kind: str,
                stop_at_frame: Optional[Any] = None) -> None:
    """在 detector 埋点处调用:三门合取通过时触发 pause。

    required keyword-only 参数:
    - anchor_kind:5 元 enum(gate/trough/end/entry/confirm)· detector 内部锚点位置
    - 缺该 kwarg → Python 抛 TypeError(required · 无 default)

    判据(短路顺序):
      _DEBUG_MODE ∧ bar in range
        ∧ (DEBUG_ANCHOR_KIND 未设 or 匹配 anchor_kind)

    优先 pydevd.settrace(suspend=True)——PyCharm 显式 pause API · 每次都 fire;
    breakpoint() 在 pydevd 下同一源码位置只报告一次 · 二次触发会静默 fall through
    (实测 2026-07-16 sync+async 皆然)· 故仅在无 pydevd(非 PyCharm 启动)时兜底。
    _DEBUG_MODE=False 时函数第一行 return · pydevd 不 import · 生产零成本。

    ⚠ pydevd stop_at_frame 首次 miss(2026-07-18 实测 · 2026-08-14 定性为环境性 ·
    已接受):受影响环境下 · 每次进程重启后首次 `settrace(suspend=True, stop_at_frame=X)`
    立即 return 不 suspend · 同 code site 的下一次调用才真 pause(用户可感 = 重启后首次
    右键 debug/brush 不命中 · 第二次起正常);不受影响的项目窗口下首枪即 pause(无此
    现象)。2026-08-14 双目录对照实证:同一分支代码 · 主目录项目窗口首次即命中 ·
    worktree 项目窗口首枪必 miss——代码侧无可修根因(fire 序列/前端请求参数/api
    handler 两环境逐条一致 · 解释器同为 3.12.12)· 差异在打开目录的 IDE/pydevd 版本
    组合。代码侧对策均已实测否决:运行期紧邻补第二枪仍 miss;启动期牺牲首枪 warmup
    在受影响环境自身也 miss。规避 = 在不受影响的项目窗口(主目录)下调试。
    """
    if not _DEBUG_MODE:
        return
    r = _read_range()
    if r is None:
        return
    if not (r[0] <= i <= r[1]):
        return
    required_ak = _read_anchor_kind()
    if required_ak is not None and required_ak != anchor_kind:
        return
    try:
        import pydevd
        import sys
        pydevd.settrace(suspend=True,
                        stop_at_frame=stop_at_frame or sys._getframe(1))
    except ImportError:
        breakpoint()
