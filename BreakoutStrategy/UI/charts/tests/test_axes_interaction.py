"""Unit tests for AxesInteractionController math + event behavior."""
import math

import pytest
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.backend_bases import MouseEvent


def test_compute_zoom_xlim_anchors_mouse_position():
    """放大时鼠标所在数据 x 不动，新窗口以 factor 收缩。"""
    from BreakoutStrategy.UI.charts.axes_interaction import compute_zoom_xlim

    # 当前 xlim = (0, 100), 鼠标在 x=30
    new_x0, new_x1 = compute_zoom_xlim(
        xlim=(0.0, 100.0), mouse_x=30.0, factor=0.5
    )
    # 期望：mouse_x=30 不动；新宽度 = 50
    # new_x0 = 30 - (30-0)*0.5 = 15
    # new_x1 = 30 + (100-30)*0.5 = 65
    assert math.isclose(new_x0, 15.0)
    assert math.isclose(new_x1, 65.0)


def test_compute_zoom_xlim_enforces_min_width():
    """连续放大到最小宽度后不再缩小窗口。"""
    from BreakoutStrategy.UI.charts.axes_interaction import compute_zoom_xlim

    # 当前窗口宽度=4, 再放大(factor=0.5)会给出 2 < min_width=3
    new_x0, new_x1 = compute_zoom_xlim(
        xlim=(10.0, 14.0), mouse_x=12.0, factor=0.5, min_width=3.0, max_width=1000.0
    )
    assert math.isclose(new_x1 - new_x0, 3.0, abs_tol=1e-6)


def test_compute_zoom_xlim_enforces_max_width():
    """连续缩小到最大宽度后不再扩张窗口。"""
    from BreakoutStrategy.UI.charts.axes_interaction import compute_zoom_xlim

    new_x0, new_x1 = compute_zoom_xlim(
        xlim=(0.0, 100.0), mouse_x=50.0, factor=2.0, min_width=3.0, max_width=150.0
    )
    assert math.isclose(new_x1 - new_x0, 150.0, abs_tol=1e-6)


def test_compute_pan_xlim_shifts_by_pixel_delta():
    """鼠标向右拖 100px 时，视窗向左移（内容跟手右移）。"""
    from BreakoutStrategy.UI.charts.axes_interaction import compute_pan_xlim

    # axes 像素宽度 500，当前 xlim 宽度 100 → 1 像素 = 0.2 数据单位
    # 鼠标右移 100px → shift = -100 * 0.2 = -20 → xlim 左移 20
    new_x0, new_x1 = compute_pan_xlim(
        anchor_xlim=(0.0, 100.0),
        anchor_px=200.0,
        current_px=300.0,
        axes_px_width=500.0,
    )
    assert new_x0 == pytest.approx(-20.0)
    assert new_x1 == pytest.approx(80.0)


def test_compute_pan_xlim_shifts_right_when_mouse_moves_left():
    """鼠标向左拖 → 视窗右移（内容跟手左移）。"""
    from BreakoutStrategy.UI.charts.axes_interaction import compute_pan_xlim

    new_x0, new_x1 = compute_pan_xlim(
        anchor_xlim=(0.0, 100.0),
        anchor_px=300.0,
        current_px=200.0,
        axes_px_width=500.0,
    )
    assert new_x0 == pytest.approx(20.0)
    assert new_x1 == pytest.approx(120.0)


@pytest.fixture
def controller_fig():
    """Provide a fresh (fig, ax, canvas, controller) attached instance.

    100 根 K 线，xlim=(0,105)；data_span=(-2, 105)，n_bars=100，initial_width=107。
    highs/lows 为简单斜线数据用于 Y 轴测试。
    """
    import numpy as np
    from BreakoutStrategy.UI.charts.axes_interaction import AxesInteractionController

    fig = plt.figure(figsize=(5, 4))
    ax = fig.add_subplot(111)
    ax.plot(range(100), range(100))
    ax.set_xlim(-2, 105)
    fig.canvas.draw()

    highs = np.arange(100, dtype=float) + 10  # [10, 11, ..., 109]
    lows = np.arange(100, dtype=float)         # [0, 1, ..., 99]

    ctrl = AxesInteractionController(ax, fig.canvas)
    ctrl.attach(
        data_span=(-2.0, 105.0),
        n_bars=100,
        initial_width=107.0,
        highs=highs,
        lows=lows,
    )
    yield fig, ax, fig.canvas, ctrl
    ctrl.detach()
    plt.close(fig)


def _scroll(canvas, ax, xdata, step):
    """Synthesize a matplotlib scroll_event at data x=xdata."""
    x_px, y_px = ax.transData.transform((xdata, 0))
    event = MouseEvent(
        "scroll_event", canvas, x_px, y_px, step=step,
    )
    event.inaxes = ax
    event.xdata = xdata
    event.ydata = 0
    canvas.callbacks.process("scroll_event", event)


def _mouse(name, canvas, ax, x_px, y_px, button=None, xdata=None, ydata=None):
    """Synthesize a matplotlib mouse event."""
    event = MouseEvent(name, canvas, x_px, y_px, button=button)
    event.inaxes = ax
    event.xdata = xdata
    event.ydata = ydata
    canvas.callbacks.process(name, event)


# ---------- 基础缩放测试 ----------

def test_scroll_zooms_in_and_updates_zoom_level_text(controller_fig):
    fig, ax, canvas, ctrl = controller_fig

    _scroll(canvas, ax, xdata=50.0, step=1)  # zoom in

    x0, x1 = ax.get_xlim()
    assert (x1 - x0) < 107.0  # window narrowed
    assert ctrl.zoom_level > 1.0
    assert f"{ctrl.zoom_level:.2f}x" in ctrl._zoom_text.get_text()


def test_scroll_outside_axes_is_ignored(controller_fig):
    fig, ax, canvas, ctrl = controller_fig

    event = MouseEvent("scroll_event", canvas, 0, 0, step=1)
    event.inaxes = None
    event.xdata = None
    canvas.callbacks.process("scroll_event", event)

    assert ctrl.zoom_level == pytest.approx(1.0, abs=0.01)


def test_default_scroll_anchors_at_mouse_position():
    """默认（无 Ctrl）缩放锚点 = 鼠标位置。"""
    from BreakoutStrategy.UI.charts.axes_interaction import AxesInteractionController

    fig = plt.figure(figsize=(5, 4))
    ax = fig.add_subplot(111)
    ax.plot(range(100), range(100))
    ax.set_xlim(0, 100)
    fig.canvas.draw()

    ctrl = AxesInteractionController(ax, fig.canvas)
    ctrl.attach(data_span=(0.0, 100.0), n_bars=100, initial_width=100.0)

    _scroll(fig.canvas, ax, xdata=30.0, step=1)  # zoom in at x=30

    x0, x1 = ax.get_xlim()
    # anchor=30, factor=0.85 → x0 = 30 - 30*0.85 = 4.5; x1 = 30 + 70*0.85 = 89.5
    assert x0 == pytest.approx(4.5, abs=1e-6)
    assert x1 == pytest.approx(89.5, abs=1e-6)

    ctrl.detach()
    plt.close(fig)


def test_ctrl_scroll_anchors_at_rightmost_visible_bar():
    """Ctrl+缩放 → 锚点 = 当前 view 最右可见 K 线右边缘。"""
    from BreakoutStrategy.UI.charts.axes_interaction import AxesInteractionController

    fig = plt.figure(figsize=(5, 4))
    ax = fig.add_subplot(111)
    ax.plot(range(100), range(100))
    ax.set_xlim(0, 100)
    fig.canvas.draw()

    ctrl = AxesInteractionController(
        ax, fig.canvas,
        is_ctrl_pressed=lambda: True,
    )
    ctrl.attach(data_span=(0.0, 105.0), n_bars=100, initial_width=100.0)

    # Ctrl+zoom in: anchor = min(xlim[1]=100, n_bars-0.5=99.5) = 99.5
    _scroll(fig.canvas, ax, xdata=30.0, step=1)  # mouse at 30 but anchor at 99.5

    x0, x1 = ax.get_xlim()
    # anchor=99.5, factor=0.85
    # x0 = 99.5 - (99.5-0)*0.85 = 99.5 - 84.575 = 14.925
    # x1 = 99.5 + (100-99.5)*0.85 = 99.5 + 0.425 = 99.925
    assert x0 == pytest.approx(14.925, abs=0.01)
    assert x1 == pytest.approx(99.925, abs=0.01)

    ctrl.detach()
    plt.close(fig)


def test_ctrl_release_returns_to_mouse_anchor():
    """Ctrl 松开后缩放回到鼠标锚点。"""
    from BreakoutStrategy.UI.charts.axes_interaction import AxesInteractionController

    fig = plt.figure(figsize=(5, 4))
    ax = fig.add_subplot(111)
    ax.plot(range(100), range(100))
    ax.set_xlim(0, 100)
    fig.canvas.draw()

    ctrl_held = [True]
    ctrl = AxesInteractionController(
        ax, fig.canvas,
        is_ctrl_pressed=lambda: ctrl_held[0],
    )
    ctrl.attach(data_span=(0.0, 105.0), n_bars=100, initial_width=100.0)

    # Ctrl+zoom in
    _scroll(fig.canvas, ax, xdata=30.0, step=1)
    x0_ctrl, x1_ctrl = ax.get_xlim()

    # Release Ctrl, zoom again at same mouse position
    ctrl_held[0] = False
    _scroll(fig.canvas, ax, xdata=30.0, step=1)
    x0_mouse, x1_mouse = ax.get_xlim()

    # With mouse anchor at 30, the zoom should shrink symmetrically around 30
    width_after = x1_mouse - x0_mouse
    width_before = x1_ctrl - x0_ctrl
    assert width_after < width_before  # zoomed in further
    # The 30.0 point should be proportionally inside visible range
    frac = (30.0 - x0_mouse) / (x1_mouse - x0_mouse)
    assert 0.1 < frac < 0.9

    ctrl.detach()
    plt.close(fig)


# ---------- 平移测试 ----------

def test_left_drag_pans_xlim(controller_fig):
    fig, ax, canvas, ctrl = controller_fig

    bbox = ax.bbox
    anchor_px = bbox.x0 + bbox.width * 0.5
    y_px = bbox.y0 + bbox.height * 0.5

    _mouse("button_press_event", canvas, ax, anchor_px, y_px,
           button=1, xdata=50.0, ydata=0)
    assert ctrl.is_panning is True

    _mouse("motion_notify_event", canvas, ax, anchor_px + 50, y_px,
           button=1, xdata=60.0, ydata=0)

    x0, x1 = ax.get_xlim()
    assert x0 >= -2.0 - 0.5  # left clamp

    _mouse("button_release_event", canvas, ax, anchor_px + 50, y_px,
           button=1, xdata=60.0, ydata=0)
    assert ctrl.is_panning is False


def test_right_drag_does_not_pan(controller_fig):
    fig, ax, canvas, ctrl = controller_fig

    bbox = ax.bbox
    _mouse("button_press_event", canvas, ax, bbox.x0 + 10, bbox.y0 + 10,
           button=3, xdata=10.0, ydata=0)
    assert ctrl.is_panning is False


def test_pan_state_callback_invoked():
    """Controller must call on_pan_state_change with True/False."""
    from BreakoutStrategy.UI.charts.axes_interaction import AxesInteractionController

    fig = plt.figure(figsize=(5, 4))
    ax = fig.add_subplot(111)
    ax.plot(range(100), range(100))
    ax.set_xlim(0, 100)
    fig.canvas.draw()

    calls: list[bool] = []
    ctrl = AxesInteractionController(ax, fig.canvas, on_pan_state_change=calls.append)
    ctrl.attach(data_span=(0.0, 100.0), n_bars=100, initial_width=100.0)

    bbox = ax.bbox
    _mouse("button_press_event", fig.canvas, ax, bbox.x0 + 10, bbox.y0 + 10,
           button=1, xdata=10.0, ydata=0)
    _mouse("button_release_event", fig.canvas, ax, bbox.x0 + 10, bbox.y0 + 10,
           button=1, xdata=10.0, ydata=0)

    assert calls == [True, False]
    ctrl.detach()
    plt.close(fig)


def test_detach_disconnects_callbacks(controller_fig):
    fig, ax, canvas, ctrl = controller_fig
    ctrl.detach()
    pre_xlim = ax.get_xlim()
    _scroll(canvas, ax, xdata=50.0, step=1)
    assert ax.get_xlim() == pre_xlim


# ---------- Reset 测试 ----------

def test_reset_restores_initial_xlim():
    """reset() → xlim 回到初始值。"""
    from BreakoutStrategy.UI.charts.axes_interaction import AxesInteractionController

    fig = plt.figure(figsize=(5, 4))
    ax = fig.add_subplot(111)
    ax.plot(range(100), range(100))
    ax.set_xlim(0, 100)
    fig.canvas.draw()

    ctrl = AxesInteractionController(ax, fig.canvas)
    ctrl.attach(data_span=(0.0, 100.0), n_bars=100, initial_width=50.0)

    ax.set_xlim(60, 70)  # simulate zoom
    ctrl.reset()

    x0, x1 = ax.get_xlim()
    assert (x0, x1) == pytest.approx((50.0, 100.0))

    ctrl.detach()
    plt.close(fig)


def test_reset_button_disabled_at_initial_view(controller_fig):
    """初始视图 → Reset 按钮灰色。"""
    fig, ax, canvas, ctrl = controller_fig
    assert ctrl._reset_button.get_color() == "#BBBBBB"


def test_scroll_zoom_enables_reset_button(controller_fig):
    """缩放后 → Reset 按钮变黑。"""
    fig, ax, canvas, ctrl = controller_fig
    _scroll(canvas, ax, xdata=50.0, step=1)
    assert ctrl._reset_button.get_color() == "black"


def test_pan_enables_reset_button(controller_fig):
    """平移后 → Reset 按钮变黑。"""
    fig, ax, canvas, ctrl = controller_fig
    bbox = ax.bbox
    _mouse("button_press_event", canvas, ax, bbox.x0 + bbox.width * 0.5,
           bbox.y0 + bbox.height * 0.5, button=1, xdata=50.0, ydata=0)
    _mouse("motion_notify_event", canvas, ax, bbox.x0 + bbox.width * 0.5 + 100,
           bbox.y0 + bbox.height * 0.5, button=1, xdata=60.0, ydata=0)
    _mouse("button_release_event", canvas, ax, bbox.x0 + bbox.width * 0.5 + 100,
           bbox.y0 + bbox.height * 0.5, button=1, xdata=60.0, ydata=0)
    assert ctrl._needs_reset is True
    assert ctrl._reset_button.get_color() == "black"


def test_zoom_in_then_reset_click():
    """缩放 → 点击 Reset → xlim 恢复。"""
    from BreakoutStrategy.UI.charts.axes_interaction import AxesInteractionController

    fig = plt.figure(figsize=(5, 4))
    ax = fig.add_subplot(111)
    ax.plot(range(100), range(100))
    ax.set_xlim(50, 100)
    fig.canvas.draw()

    ctrl = AxesInteractionController(ax, fig.canvas)
    ctrl.attach(data_span=(0.0, 100.0), n_bars=100, initial_width=50.0)

    _scroll(fig.canvas, ax, xdata=70.0, step=1)
    _scroll(fig.canvas, ax, xdata=70.0, step=1)
    assert ctrl.zoom_level > 1.0

    fig.canvas.draw()
    bbox_artist = ctrl._reset_button.get_window_extent(renderer=fig.canvas.get_renderer())
    cx = (bbox_artist.x0 + bbox_artist.x1) / 2
    cy = (bbox_artist.y0 + bbox_artist.y1) / 2
    _mouse("button_press_event", fig.canvas, ax, cx, cy, button=1, xdata=75.0, ydata=0)

    assert ctrl.zoom_level == pytest.approx(1.0)
    x0, x1 = ax.get_xlim()
    assert (x0, x1) == pytest.approx((50.0, 100.0))
    assert not ctrl.is_panning

    ctrl.detach()
    plt.close(fig)


def test_reset_click_at_initial_view_ignored():
    """初始视图点击 Reset → 不触发、不进入 pan。"""
    from BreakoutStrategy.UI.charts.axes_interaction import AxesInteractionController

    fig = plt.figure(figsize=(5, 4))
    ax = fig.add_subplot(111)
    ax.plot(range(100), range(100))
    ax.set_xlim(50, 100)
    fig.canvas.draw()

    ctrl = AxesInteractionController(ax, fig.canvas)
    ctrl.attach(data_span=(0.0, 100.0), n_bars=100, initial_width=50.0)
    fig.canvas.draw()

    bbox_artist = ctrl._reset_button.get_window_extent(renderer=fig.canvas.get_renderer())
    cx = (bbox_artist.x0 + bbox_artist.x1) / 2
    cy = (bbox_artist.y0 + bbox_artist.y1) / 2
    pre_xlim = ax.get_xlim()
    _mouse("button_press_event", fig.canvas, ax, cx, cy, button=1, xdata=75.0, ydata=0)

    assert ax.get_xlim() == pre_xlim
    assert not ctrl.is_panning

    ctrl.detach()
    plt.close(fig)


# ---------- 动态 Y 轴测试 ----------

def test_rescale_y_adjusts_to_visible_range():
    """缩放后 Y 轴范围应匹配可见 K 线的 high/low。"""
    import numpy as np
    from BreakoutStrategy.UI.charts.axes_interaction import AxesInteractionController

    fig = plt.figure(figsize=(5, 4))
    ax = fig.add_subplot(111)
    ax.plot(range(100), range(100))
    ax.set_xlim(0, 100)
    fig.canvas.draw()

    highs = np.arange(100, dtype=float) + 10
    lows = np.arange(100, dtype=float)

    ctrl = AxesInteractionController(ax, fig.canvas)
    ctrl.attach(
        data_span=(0.0, 105.0), n_bars=100, initial_width=100.0,
        highs=highs, lows=lows,
    )

    # Zoom to bars 40-60 (xlim ~39.5 to 60.5)
    ax.set_xlim(39.5, 60.5)
    ctrl._rescale_y()

    y_bottom, y_top = ax.get_ylim()
    # visible bars 40-60: lows[40]=40, highs[60]=70
    # price_range = 70-40 = 30; display_height = 30/0.8 = 37.5
    # y_bottom = 40 - 37.5*0.1 = 36.25; y_top = 36.25 + 37.5 = 73.75
    assert y_bottom == pytest.approx(36.25, abs=0.5)
    assert y_top == pytest.approx(73.75, abs=0.5)

    ctrl.detach()
    plt.close(fig)


def test_rescale_y_skipped_when_no_data():
    """highs/lows 为 None 时不崩溃。"""
    from BreakoutStrategy.UI.charts.axes_interaction import AxesInteractionController

    fig = plt.figure(figsize=(5, 4))
    ax = fig.add_subplot(111)
    ax.plot(range(100), range(100))
    ax.set_xlim(0, 100)
    ax.set_ylim(0, 100)
    fig.canvas.draw()

    ctrl = AxesInteractionController(ax, fig.canvas)
    ctrl.attach(data_span=(0.0, 105.0), n_bars=100, initial_width=100.0)

    ctrl._rescale_y()  # should not crash
    assert ax.get_ylim() == (0.0, 100.0)

    ctrl.detach()
    plt.close(fig)


def test_scroll_triggers_y_rescale():
    """缩放操作自动触发 Y 轴重算。"""
    import numpy as np
    from BreakoutStrategy.UI.charts.axes_interaction import AxesInteractionController

    fig = plt.figure(figsize=(5, 4))
    ax = fig.add_subplot(111)
    ax.plot(range(100), range(100))
    ax.set_xlim(0, 100)
    ax.set_ylim(0, 200)  # deliberately wrong
    fig.canvas.draw()

    highs = np.full(100, 50.0)
    lows = np.full(100, 10.0)

    ctrl = AxesInteractionController(ax, fig.canvas)
    ctrl.attach(
        data_span=(0.0, 105.0), n_bars=100, initial_width=100.0,
        highs=highs, lows=lows,
    )

    _scroll(fig.canvas, ax, xdata=50.0, step=1)  # triggers rescale

    y_bottom, y_top = ax.get_ylim()
    # All bars have high=50, low=10, range=40, display_height=50
    # y_bottom = 10 - 5 = 5; y_top = 5 + 50 = 55
    assert y_bottom == pytest.approx(5.0, abs=1.0)
    assert y_top == pytest.approx(55.0, abs=1.0)

    ctrl.detach()
    plt.close(fig)


# ---------- 约束测试 ----------

def test_zoom_out_caps_at_right_anchor():
    """连续缩小不超过 right_anchor。"""
    from BreakoutStrategy.UI.charts.axes_interaction import AxesInteractionController

    fig = plt.figure(figsize=(5, 4))
    ax = fig.add_subplot(111)
    ax.plot(range(100), range(100))
    ax.set_xlim(50, 80)
    fig.canvas.draw()

    ctrl = AxesInteractionController(ax, fig.canvas)
    ctrl.attach(data_span=(0.0, 100.0), n_bars=100, initial_width=30.0)

    for _ in range(30):
        _scroll(fig.canvas, ax, xdata=70.0, step=-1)

    _, x1 = ax.get_xlim()
    assert x1 <= 100.0 + 0.01

    ctrl.detach()
    plt.close(fig)
