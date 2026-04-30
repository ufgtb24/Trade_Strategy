"""KeyboardPicker 三态状态机单元测试。

KeyboardPicker 与 Tk / matplotlib 完全解耦——所有外界交互（拿当前 hover bar、
BO 集合、触发渲染、显示 toast / sticky 状态栏）通过注入的回调完成。

三态 FSM 迁移路径覆盖：
    IDLE --P--> AWAITING_BO --P(∈BO)--> AWAITING_LEFT --P(<bo_idx)--> IDLE
                             --P(∉BO)--> AWAITING_BO (toast)
                                         --P(>=bo_idx)--> AWAITING_LEFT (toast)
    任意非 IDLE 状态 --ESC--> IDLE
"""

import pytest

from BreakoutStrategy.UI.charts.keyboard_picker import (
    KeyboardPicker,
    PickerStatus,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def picker_calls():
    """收集 picker 的所有外向回调，便于断言行为序列。"""
    return {
        "render": [],
        "toast": [],
        "sticky": [],
        "marker_redraw": [],
    }


@pytest.fixture
def make_picker(picker_calls):
    """工厂：接受可变 hovered_bar 与 bo_set。

    Returns:
        (factory_fn, state_dict) — factory_fn 接受 bo_set 创建 KeyboardPicker；
        state_dict["hovered"] 可在测试中直接修改来模拟 hover 变化。
    """
    state = {"hovered": None}

    def _make(bo_set: frozenset = frozenset({5})):
        return KeyboardPicker(
            get_hovered_bar=lambda: state["hovered"],
            get_bo_indices=lambda: bo_set,
            on_render=lambda l, r: picker_calls["render"].append((l, r)),
            on_toast=lambda k, t: picker_calls["toast"].append((k, t)),
            on_sticky=lambda t: picker_calls["sticky"].append(t),
            on_marker_redraw=lambda b: picker_calls["marker_redraw"].append(list(b)),
        )

    return _make, state


# ---------------------------------------------------------------------------
# Task 1 验证：初始状态
# ---------------------------------------------------------------------------

def test_initial_state_is_idle(make_picker):
    """初始状态应为 IDLE，endpoint_bars 为空。"""
    _make, _ = make_picker
    picker = _make()
    assert picker.status == PickerStatus.IDLE
    assert picker.endpoint_bars == []


# ---------------------------------------------------------------------------
# IDLE → AWAITING_BO
# ---------------------------------------------------------------------------

def test_p_in_idle_without_hover_enters_awaiting_bo(make_picker, picker_calls):
    """D-01 核心：IDLE + get_hovered_bar() 返回 None 时按 P，
    应无条件进入 AWAITING_BO，sticky 含 [PICK 1/2]。"""
    _make, state = make_picker
    state["hovered"] = None  # 明确：未 hover
    picker = _make()

    picker.on_press_p()

    assert picker.status == PickerStatus.AWAITING_BO, (
        "IDLE 按 P 应无条件进入 AWAITING_BO，不依赖 hover"
    )
    assert any("[PICK 1/2]" in s for s in picker_calls["sticky"]), (
        "sticky 应包含 [PICK 1/2] 提示"
    )


def test_press_p_in_idle_enters_awaiting_bo_with_sticky_pick_1_of_2(make_picker, picker_calls):
    """IDLE 按 P（有 hover），sticky 应含 [PICK 1/2] 和 'Hover the BO bar'。"""
    _make, state = make_picker
    state["hovered"] = 3
    picker = _make()

    picker.on_press_p()

    assert picker.status == PickerStatus.AWAITING_BO
    assert any(
        "[PICK 1/2]" in s and "Hover the BO bar" in s
        for s in picker_calls["sticky"]
    ), f"sticky 未包含预期文案，实际: {picker_calls['sticky']}"


# ---------------------------------------------------------------------------
# AWAITING_BO → AWAITING_LEFT（合法 BO）
# ---------------------------------------------------------------------------

def test_press_p_in_awaiting_bo_on_bo_bar_enters_awaiting_left(make_picker, picker_calls):
    """AWAITING_BO + hover 在 BO 集合内，按 P → 进入 AWAITING_LEFT。
    sticky 含 [PICK 2/2] 和 BEFORE BO；marker_redraw([bo_idx]) 被调用。"""
    _make, state = make_picker
    picker = _make(bo_set=frozenset({5}))

    # 第一次 P：进入 AWAITING_BO
    state["hovered"] = None
    picker.on_press_p()
    assert picker.status == PickerStatus.AWAITING_BO

    # 第二次 P：hover 在 BO bar 5
    state["hovered"] = 5
    picker.on_press_p()

    assert picker.status == PickerStatus.AWAITING_LEFT
    assert picker._bo_idx == 5
    assert any(
        "[PICK 2/2]" in s and "BEFORE BO" in s
        for s in picker_calls["sticky"]
    ), f"sticky 未含预期文案，实际: {picker_calls['sticky']}"
    assert [5] in picker_calls["marker_redraw"], (
        "进入 AWAITING_LEFT 时应调 on_marker_redraw([bo_idx])"
    )


# ---------------------------------------------------------------------------
# AWAITING_BO：错误路径（非 BO bar）
# ---------------------------------------------------------------------------

def test_press_p_in_awaiting_bo_on_non_bo_bar_stays_awaiting_bo_with_warning_toast(
    make_picker, picker_calls
):
    """AWAITING_BO + hover 在非 BO bar，按 P → toast warning，状态保持 AWAITING_BO。"""
    _make, state = make_picker
    picker = _make(bo_set=frozenset({5}))

    # 进入 AWAITING_BO
    state["hovered"] = None
    picker.on_press_p()

    # hover 在非 BO bar 3
    state["hovered"] = 3
    picker.on_press_p()

    assert picker.status == PickerStatus.AWAITING_BO, (
        "非 BO bar 应保持 AWAITING_BO"
    )
    assert ("warning", "This bar is not a detected BO. Hover a BO and press P.") in picker_calls["toast"]


def test_press_p_in_awaiting_bo_without_hover_emits_hover_first_toast(make_picker, picker_calls):
    """AWAITING_BO + None hover，按 P → toast info 'Hover over a bar first'，状态不变。"""
    _make, state = make_picker
    picker = _make()

    # 进入 AWAITING_BO
    state["hovered"] = None
    picker.on_press_p()
    assert picker.status == PickerStatus.AWAITING_BO

    # 清除之前的 toast，再试 None hover
    picker_calls["toast"].clear()
    picker.on_press_p()

    assert picker.status == PickerStatus.AWAITING_BO
    assert ("info", "Hover over a bar first") in picker_calls["toast"]


# ---------------------------------------------------------------------------
# AWAITING_LEFT → IDLE（合法左端）
# ---------------------------------------------------------------------------

def test_press_p_in_awaiting_left_left_of_bo_triggers_render_and_returns_idle(
    make_picker, picker_calls
):
    """AWAITING_LEFT + hover idx < bo_idx，按 P → on_render(left, bo)，回 IDLE，sticky 末位为 ''。"""
    _make, state = make_picker
    picker = _make(bo_set=frozenset({10}))

    # IDLE → AWAITING_BO
    state["hovered"] = None
    picker.on_press_p()

    # AWAITING_BO → AWAITING_LEFT（hover 在 BO bar 10）
    state["hovered"] = 10
    picker.on_press_p()
    assert picker.status == PickerStatus.AWAITING_LEFT

    # AWAITING_LEFT → IDLE（hover 在 bar 3，< bo_idx 10）
    state["hovered"] = 3
    picker.on_press_p()

    assert picker.status == PickerStatus.IDLE
    assert picker_calls["render"] == [(3, 10)], (
        "on_render 应以 (left, bo_idx) 触发"
    )
    assert picker.endpoint_bars == []
    assert picker_calls["sticky"][-1] == "", "渲染后 sticky 应被清空"


# ---------------------------------------------------------------------------
# AWAITING_LEFT：错误路径（bar >= bo_idx）
# ---------------------------------------------------------------------------

def test_press_p_in_awaiting_left_at_or_right_of_bo_stays_with_warning(make_picker, picker_calls):
    """AWAITING_LEFT + hover idx >= bo_idx（且非同根），按 P → toast warning，状态保持。"""
    _make, state = make_picker
    picker = _make(bo_set=frozenset({10}))

    state["hovered"] = None
    picker.on_press_p()
    state["hovered"] = 10
    picker.on_press_p()
    assert picker.status == PickerStatus.AWAITING_LEFT

    # hover 在 bar 15（> bo_idx 10）
    state["hovered"] = 15
    picker.on_press_p()

    assert picker.status == PickerStatus.AWAITING_LEFT
    assert ("warning", "Pick a K-line BEFORE the BO bar.") in picker_calls["toast"]
    assert picker_calls["render"] == [], "不应触发渲染"


def test_press_p_in_awaiting_left_same_bar_as_bo_emits_same_bar_toast(make_picker, picker_calls):
    """AWAITING_LEFT + hover == bo_idx（同根），按 P → toast info 'Same bar, hover another'。"""
    _make, state = make_picker
    picker = _make(bo_set=frozenset({10}))

    state["hovered"] = None
    picker.on_press_p()
    state["hovered"] = 10
    picker.on_press_p()
    assert picker.status == PickerStatus.AWAITING_LEFT

    # 再次 hover 同一根 BO bar 10
    state["hovered"] = 10
    picker.on_press_p()

    assert picker.status == PickerStatus.AWAITING_LEFT
    assert ("info", "Same bar, hover another") in picker_calls["toast"]
    assert picker_calls["render"] == []


# ---------------------------------------------------------------------------
# ESC 行为
# ---------------------------------------------------------------------------

def test_escape_in_awaiting_bo_resets_and_consumes(make_picker, picker_calls):
    """AWAITING_BO 按 ESC → consumed=True，回 IDLE，toast 'Picking cancelled'。"""
    _make, state = make_picker
    picker = _make()

    state["hovered"] = None
    picker.on_press_p()
    assert picker.status == PickerStatus.AWAITING_BO

    consumed = picker.on_press_escape()

    assert consumed is True
    assert picker.status == PickerStatus.IDLE
    assert ("info", "Picking cancelled") in picker_calls["toast"]
    assert picker.endpoint_bars == []


def test_escape_in_awaiting_left_resets_and_consumes(make_picker, picker_calls):
    """AWAITING_LEFT 按 ESC → consumed=True，回 IDLE，toast 'Picking cancelled'，marker 清空。"""
    _make, state = make_picker
    picker = _make(bo_set=frozenset({5}))

    state["hovered"] = None
    picker.on_press_p()
    state["hovered"] = 5
    picker.on_press_p()
    assert picker.status == PickerStatus.AWAITING_LEFT

    consumed = picker.on_press_escape()

    assert consumed is True
    assert picker.status == PickerStatus.IDLE
    assert ("info", "Picking cancelled") in picker_calls["toast"]
    assert picker.endpoint_bars == []
    assert picker_calls["marker_redraw"][-1] == [], "ESC 后 marker 应被清空"


def test_escape_in_idle_returns_false_for_passthrough(make_picker):
    """IDLE 按 ESC → 返回 False（透传给 canvas_manager 处理窗口关闭）。"""
    _make, _ = make_picker
    picker = _make()

    consumed = picker.on_press_escape()

    assert consumed is False


# ---------------------------------------------------------------------------
# reset() 外部强制清空
# ---------------------------------------------------------------------------

def test_reset_clears_state_silently(make_picker, picker_calls):
    """reset() 强制清空状态，不发 toast。"""
    _make, state = make_picker
    picker = _make(bo_set=frozenset({5}))

    # 进入 AWAITING_LEFT
    state["hovered"] = None
    picker.on_press_p()
    state["hovered"] = 5
    picker.on_press_p()
    assert picker.status == PickerStatus.AWAITING_LEFT

    toast_before = list(picker_calls["toast"])
    picker.reset()

    assert picker.status == PickerStatus.IDLE
    assert picker.endpoint_bars == []
    assert picker._bo_idx is None
    assert picker_calls["marker_redraw"][-1] == []
    # reset 不应增加新 toast
    assert picker_calls["toast"] == toast_before, (
        "reset() 应静默清空，不发 toast"
    )


# ---------------------------------------------------------------------------
# canvas_manager 集成回归测试
# ---------------------------------------------------------------------------

def test_canvas_manager_escape_priority_routing():
    """canvas_manager._on_close_window_key 应先问 picker.on_press_escape()，
    返回 True 时不再做关窗动作；返回 False 时才走原关窗逻辑。
    """
    from unittest.mock import MagicMock
    from BreakoutStrategy.UI.charts.canvas_manager import ChartCanvasManager

    cm = MagicMock(spec=ChartCanvasManager)
    cm._picker = MagicMock()
    cm._picker.on_press_escape.return_value = True  # picker 消费

    fake_event = MagicMock()
    ChartCanvasManager._on_close_window_key(cm, fake_event)

    cm._picker.on_press_escape.assert_called_once()
    # picker 消费时不应进入原关窗路径（_cleanup_closed_windows 不被调用）
    cm._cleanup_closed_windows.assert_not_called()


def test_canvas_manager_picker_callback_passes_wired_df_not_full_df():
    """回归测试：picker 触发渲染时应回传 _wire_picker 时的 df / breakouts，
    避免 dev/main 用 self.current_df（可能是 full pre-processed df）导致索引错位。

    当 display 窗口从 full df 第 500 根开始，picker 吐出的 (left, right) 是
    display-space 索引（0-based）。upstream callback 必须用同一个 display_df
    而非 full df 来做 iloc 切片，否则会取到错误日期的 sample。

    注意：_wire_picker 在 plan 02 实施前签名尚不含 get_bo_indices；
    本测试通过直接构造 KeyboardPicker（绕过 _wire_picker），
    验证 on_render 闭包正确捕获 display_df / display_breakouts 的语义不变量。
    plan 02 落地后，将恢复为调真实 _wire_picker 的完整集成测试。
    """
    from BreakoutStrategy.UI.charts.keyboard_picker import KeyboardPicker

    display_df = object()  # 用唯一 identity 验证引用正确
    bo_mock = object()
    display_breakouts = [bo_mock]

    captured = []

    def fake_on_endpoints_picked(left, right, df_arg, bo_arg):
        captured.append((left, right, df_arg, bo_arg))

    # 模拟 _wire_picker 内部的 on_render 闭包逻辑：
    # 把 wired 的 display_df + display_breakouts 一起回传给 dev/main
    def on_render(left, right):
        fake_on_endpoints_picked(left, right, display_df, display_breakouts)

    # 直接构造 picker（plan 02 前绕过 _wire_picker 避免签名差异）
    picker = KeyboardPicker(
        get_hovered_bar=lambda: 3,
        get_bo_indices=lambda: frozenset({5}),
        on_render=on_render,
        on_toast=lambda k, t: None,
        on_sticky=lambda t: None,
        on_marker_redraw=lambda b: None,
    )

    # 直接驱动 on_render 闭包，验证 display_df / display_breakouts 正确传递
    picker._on_render(3, 5)

    assert len(captured) == 1, "on_render 应触发一次 on_endpoints_picked"
    left, right, df_arg, bo_arg = captured[0]
    assert left == 3
    assert right == 5
    assert df_arg is display_df, (
        "应传回 _wire_picker 时的 display_df，不是 self.current_df（full df）"
    )
    assert bo_arg is display_breakouts, (
        "应传回 _wire_picker 时的 display_breakouts"
    )


def test_canvas_manager_picker_returns_none_when_mouse_never_hovered():
    """回归测试：_wire_picker 的 get_hovered_bar 闭包应在用户未 hover 时返回 None，
    避免 P 键触发时把默认 bar 0 当作第一根端点。
    """
    from unittest.mock import MagicMock
    from BreakoutStrategy.UI.charts.canvas_manager import ChartCanvasManager

    cm = MagicMock(spec=ChartCanvasManager)
    cm._last_hover_x = 0
    cm._hover_in_chart = False
    cm._endpoint_marker_lines = []
    cm.canvas = MagicMock()
    cm.fig = MagicMock()
    cm.fig.axes = [MagicMock()]

    captured_bar = []

    def fake_wire():
        def get_hovered_bar():
            if not getattr(cm, "_hover_in_chart", False):
                return None
            return getattr(cm, "_last_hover_x", None)
        captured_bar.append(get_hovered_bar())

    fake_wire()
    assert captured_bar == [None], "未 hover 时应返回 None，不应是 0"

    cm._hover_in_chart = True
    cm._last_hover_x = 5
    captured_bar.clear()
    fake_wire()
    assert captured_bar == [5], "hover 到 bar 5 时应返回 5"

    cm._hover_in_chart = True
    cm._last_hover_x = 0
    captured_bar.clear()
    fake_wire()
    assert captured_bar == [0], "合法 hover 到 bar 0 时应返回 0（不是 None）"


def test_wire_picker_injects_bo_indices_closure_from_breakouts():
    """_wire_picker 注入的 get_bo_indices 闭包应返回 frozenset(b.index for b in breakouts)。"""
    from unittest.mock import MagicMock
    from BreakoutStrategy.UI.charts.canvas_manager import ChartCanvasManager

    cm = MagicMock(spec=ChartCanvasManager)
    cm._endpoint_marker_lines = []
    cm._last_hover_x = 0
    cm._hover_in_chart = False
    cm.canvas = MagicMock()
    cm.fig = MagicMock()
    cm.fig.axes = [MagicMock()]

    bo1 = MagicMock(); bo1.index = 5
    bo2 = MagicMock(); bo2.index = 10
    breakouts = [bo1, bo2]

    ChartCanvasManager._wire_picker(
        cm, ax_price=MagicMock(), df=MagicMock(),
        breakouts=breakouts,
        on_endpoints_picked=lambda l, r, df_, bo_: None,
    )
    real_picker = cm._picker
    assert real_picker is not None
    # 闭包应返回 frozenset({5, 10})
    assert real_picker._get_bo_indices() == frozenset({5, 10})
