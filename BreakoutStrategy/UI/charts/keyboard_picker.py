"""KeyboardPicker — dev UI 中用户挑选样本端点的状态机。

三态 FSM：IDLE → AWAITING_BO → AWAITING_LEFT → IDLE。
第一次 P 强制 hover 在 detected BO 集合内；第二次 P 强制 hover idx < bo_idx。
错点保持当前态 + toast 警告，不重置。

状态转移说明：
- IDLE：无 sticky 提示；按 P 无条件进入 AWAITING_BO（不依赖 hover 是否存在）。
- AWAITING_BO：按 P 时若 hover bar ∈ get_bo_indices() → 进入 AWAITING_LEFT，
  sticky 切换为第二步提示；否则 toast 警告保持 AWAITING_BO。
- AWAITING_LEFT：按 P 时若 hover idx < bo_idx → 触发 on_render + 回 IDLE；
  否则 toast 警告保持 AWAITING_LEFT。

与 Tk / matplotlib 完全解耦：所有外界交互（hover 状态、触发渲染、toast、
sticky 状态栏、marker 重绘、BO 集合）通过构造函数注入的回调完成。

Esc 键：picking 状态时消费（清空 + 返回 True），idle 状态时透传
（返回 False，让上层把 Esc 交给 canvas_manager 原有的窗口关闭处理）。

使用例（canvas_manager 内）：
    picker = KeyboardPicker(
        get_hovered_bar=lambda: self._last_hover_x,
        get_bo_indices=lambda: frozenset(b.idx for b in breakouts),
        on_render=self._trigger_sample_render,
        on_toast=self._show_toast,
        on_sticky=self._set_status_sticky,
        on_marker_redraw=self._redraw_endpoint_markers,
    )
    canvas_widget.bind("<p>", lambda e: picker.on_press_p())
    canvas_widget.bind("<P>", lambda e: picker.on_press_p())
"""

from enum import Enum
from typing import Callable, Iterable, Optional


class PickerStatus(str, Enum):
    IDLE = "idle"
    AWAITING_BO = "awaiting_bo"
    AWAITING_LEFT = "awaiting_left"


class KeyboardPicker:
    """三态端点挑选状态机。

    规则：
    - 第一次 P 必须 hover 在 detected BO 集合内（AWAITING_BO 校验）。
    - 第二次 P 必须 hover 在 idx < bo_idx 的 K 线上（AWAITING_LEFT 校验）。
    - 错点统一为 stay + toast 警告，不重置、不前进。
    """

    def __init__(
        self,
        *,
        get_hovered_bar: Callable[[], Optional[int]],
        get_bo_indices: Callable[[], frozenset],  # D-02 注入 BO 集合
        on_render: Callable[[int, int], None],
        on_toast: Callable[[str, str], None],
        on_sticky: Callable[[str], None],
        on_marker_redraw: Callable[[Iterable[int]], None],
    ) -> None:
        # 注入依赖（便于单元测试）
        self._get_hovered_bar = get_hovered_bar
        self._get_bo_indices = get_bo_indices
        self._on_render = on_render
        self._on_toast = on_toast
        self._on_sticky = on_sticky
        self._on_marker_redraw = on_marker_redraw

        # 状态
        self.status: PickerStatus = PickerStatus.IDLE
        self.endpoint_bars: list[int] = []
        self._bo_idx: Optional[int] = None  # AWAITING_LEFT 阶段记录已选定的 BO bar

    # ---------- 公开 API ----------

    def on_press_p(self) -> None:
        """处理 P 键按下事件。

        IDLE 分支优先处理（D-01 要求 IDLE 按 P 无条件进入 AWAITING_BO，
        不依赖 hover bar 是否存在）；已激活拾取的状态才检查 hover。
        """
        # IDLE 分支优先：D-01 要求 IDLE 按 P 无条件进入 AWAITING_BO，
        # 不依赖 hover bar（用户尚未开始挑选，提示其去 hover BO 即可）
        if self.status == PickerStatus.IDLE:
            self.status = PickerStatus.AWAITING_BO
            self._on_sticky("[PICK 1/2] Hover the BO bar, press P")
            # 不调用 on_marker_redraw([]) — marker 已为空（由 _reset_silent 在上一轮 ESC/完成后保证）
            # D-11 要求 IDLE 时 marker 为空，这里依赖上次状态退出时的 _reset_silent 保证不变量
            return

        # 已激活拾取的状态（AWAITING_BO / AWAITING_LEFT）才检查 hover
        bar = self._get_hovered_bar()
        if bar is None:
            self._on_toast("info", "Hover over a bar first")
            return

        if self.status == PickerStatus.AWAITING_BO:
            self._handle_p_in_awaiting_bo(bar)
            return
        if self.status == PickerStatus.AWAITING_LEFT:
            self._handle_p_in_awaiting_left(bar)
            return

    def on_press_escape(self) -> bool:
        """处理 Esc 键按下事件。

        Returns:
            True 表示 picker 消费了事件（picking 状态被清空）；
            False 表示 idle 状态下 picker 不感兴趣，调用方应透传给其他 handler。
        """
        if self.status == PickerStatus.IDLE:
            return False
        self._reset_silent()
        self._on_toast("info", "Picking cancelled")
        return True

    def reset(self) -> None:
        """外部强制重置（如切换 ticker 时调用）；不发 toast。"""
        self._reset_silent()

    # ---------- 内部分支处理 ----------

    def _handle_p_in_awaiting_bo(self, bar: int) -> None:
        """处理 AWAITING_BO 状态下的 P 键（bar 已确认非 None）。

        若 bar ∈ BO 集合：进入 AWAITING_LEFT，记录 bo_idx，更新 sticky 与 marker。
        若 bar ∉ BO 集合：toast 警告，保持 AWAITING_BO，不动 marker/sticky。
        """
        bo_set = self._get_bo_indices()
        if bar in bo_set:
            self.status = PickerStatus.AWAITING_LEFT
            self._bo_idx = bar
            self.endpoint_bars = [bar]
            self._on_sticky(
                "[PICK 2/2] Hover any K-line BEFORE BO, press P. ESC to cancel"
            )
            self._on_marker_redraw([bar])
        else:
            self._on_toast(
                "warning",
                "This bar is not a detected BO. Hover a BO and press P.",
            )
            # 保持 AWAITING_BO，不动 status / marker / sticky

    def _handle_p_in_awaiting_left(self, bar: int) -> None:
        """处理 AWAITING_LEFT 状态下的 P 键（bar 已确认非 None）。

        若 bar == bo_idx：toast 同根警告，保持 AWAITING_LEFT。
        若 bar >= bo_idx：toast 位置警告，保持 AWAITING_LEFT。
        若 bar < bo_idx：触发 on_render(bar, bo_idx) 后回 IDLE。
        """
        bo_idx = self._bo_idx  # 此时必非 None（进入 AWAITING_LEFT 时已赋值）
        assert bo_idx is not None, "AWAITING_LEFT 状态下 _bo_idx 不应为 None"

        if bar == bo_idx:
            # 同根：D-01 规定 toast + 保持当前态
            self._on_toast("info", "Same bar, hover another")
            return
        if bar >= bo_idx:
            # hover 在 BO 右侧或 BO 本身（>= 覆盖 == 之外的右侧情况，== 已上面处理）
            self._on_toast("warning", "Pick a K-line BEFORE the BO bar.")
            return
        # bar < bo_idx：合法，触发渲染
        self._on_render(bar, bo_idx)
        self._reset_silent()

    # ---------- 内部工具 ----------

    def _reset_silent(self) -> None:
        """清状态 + 重绘空 marker + 清 sticky；不发 toast。"""
        self.status = PickerStatus.IDLE
        self.endpoint_bars = []
        self._bo_idx = None
        self._on_marker_redraw([])
        self._on_sticky("")
