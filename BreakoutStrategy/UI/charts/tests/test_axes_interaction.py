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

    初始 xlim=(0,100)；data_span=(0, 100)（右界即 right_anchor），bar_anchor=95
    （模拟最右 K 线右边缘位置），initial_width=100 → "整个数据范围对应一屏视窗"。
    RA 模式缩放锚定在 bar_anchor=95，像素右留白 fraction = 5/100 = 5%。
    """
    from BreakoutStrategy.UI.charts.axes_interaction import AxesInteractionController

    fig = plt.figure(figsize=(5, 4))
    ax = fig.add_subplot(111)
    ax.plot(range(100), range(100))
    ax.set_xlim(0, 100)
    fig.canvas.draw()
    ctrl = AxesInteractionController(ax, fig.canvas)
    ctrl.attach(data_span=(0.0, 100.0), bar_anchor=95.0, initial_width=100.0)
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


def test_scroll_zooms_in_and_updates_zoom_level_text(controller_fig):
    fig, ax, canvas, ctrl = controller_fig

    _scroll(canvas, ax, xdata=50.0, step=1)  # step=+1 => zoom in

    x0, x1 = ax.get_xlim()
    assert (x1 - x0) < 100.0  # window narrowed
    assert ctrl.zoom_level > 1.0
    assert f"{ctrl.zoom_level:.2f}x" in ctrl._zoom_text.get_text()


def test_scroll_outside_axes_is_ignored(controller_fig):
    fig, ax, canvas, ctrl = controller_fig

    event = MouseEvent("scroll_event", canvas, 0, 0, step=1)
    event.inaxes = None  # outside axes
    event.xdata = None
    canvas.callbacks.process("scroll_event", event)

    assert ax.get_xlim() == (0.0, 100.0)
    assert ctrl.zoom_level == 1.0


def test_left_drag_pans_xlim(controller_fig):
    fig, ax, canvas, ctrl = controller_fig

    bbox = ax.bbox
    anchor_px = bbox.x0 + bbox.width * 0.5
    y_px = bbox.y0 + bbox.height * 0.5

    _mouse("button_press_event", canvas, ax, anchor_px, y_px,
           button=1, xdata=50.0, ydata=0)
    assert ctrl.is_panning is True
    # Press switches to FREE mode
    assert ctrl.mode == ctrl.MODE_FREE

    _mouse("motion_notify_event", canvas, ax, anchor_px + 50, y_px,
           button=1, xdata=60.0, ydata=0)

    x0, x1 = ax.get_xlim()
    # Window attempted to shift left by 50 px * (100 data / bbox.width px).
    # In this fixture data_span_left=0, so x0 clamps to 0; x1 decreases by the shift.
    expected_shift = -50 * (100.0 / bbox.width)
    assert x0 == pytest.approx(0.0, abs=0.5)
    assert x1 == pytest.approx(100.0 + expected_shift, abs=0.5)

    _mouse("button_release_event", canvas, ax, anchor_px + 50, y_px,
           button=1, xdata=60.0, ydata=0)
    assert ctrl.is_panning is False


def test_right_drag_does_not_pan(controller_fig):
    fig, ax, canvas, ctrl = controller_fig

    bbox = ax.bbox
    _mouse("button_press_event", canvas, ax, bbox.x0 + 10, bbox.y0 + 10,
           button=3, xdata=10.0, ydata=0)

    assert ctrl.is_panning is False


def test_pan_state_callback_invoked(controller_fig):
    """Controller must call on_pan_state_change with True/False."""
    from BreakoutStrategy.UI.charts.axes_interaction import AxesInteractionController

    fig, ax, canvas, ctrl = controller_fig
    ctrl.detach()

    calls: list[bool] = []
    ctrl2 = AxesInteractionController(ax, canvas, on_pan_state_change=calls.append)
    ctrl2.attach(data_span=(0.0, 100.0), bar_anchor=95.0, initial_width=100.0)

    bbox = ax.bbox
    _mouse("button_press_event", canvas, ax, bbox.x0 + 10, bbox.y0 + 10,
           button=1, xdata=10.0, ydata=0)
    _mouse("button_release_event", canvas, ax, bbox.x0 + 10, bbox.y0 + 10,
           button=1, xdata=10.0, ydata=0)

    assert calls == [True, False]
    ctrl2.detach()


def test_detach_disconnects_callbacks(controller_fig):
    fig, ax, canvas, ctrl = controller_fig

    ctrl.detach()

    _scroll(canvas, ax, xdata=50.0, step=1)
    assert ax.get_xlim() == (0.0, 100.0)  # no zoom after detach


# ---------- apply_constraints 纯函数测试 ----------

def test_apply_constraints_right_aligned_clamps_x1_above_ceiling():
    """RIGHT_ALIGNED：x1 超过 right_anchor 触发 ceiling 左移+裁剪，模式不变。"""
    from BreakoutStrategy.UI.charts.axes_interaction import apply_constraints

    (x0, x1), mode = apply_constraints(
        x0=80.0, x1=120.0,
        mode="right_aligned",
        right_anchor=100.0,
        data_span_left=-10.0,
        min_width=3.0,
    )
    assert (x0, x1) == pytest.approx((60.0, 100.0))
    assert mode == "right_aligned"


def test_apply_constraints_right_aligned_preserves_width():
    """RIGHT_ALIGNED：保宽度，越界时整体左移到 x1=ceiling。"""
    from BreakoutStrategy.UI.charts.axes_interaction import apply_constraints

    (x0, x1), mode = apply_constraints(
        x0=50.0, x1=150.0,
        mode="right_aligned",
        right_anchor=100.0,
        data_span_left=-50.0,
        min_width=3.0,
    )
    assert (x0, x1) == pytest.approx((0.0, 100.0))
    assert mode == "right_aligned"


def test_apply_constraints_right_aligned_below_ceiling_unchanged():
    """RIGHT_ALIGNED：x1 < right_anchor 时 x1 不被钉死（新语义，支持像素锚点）。"""
    from BreakoutStrategy.UI.charts.axes_interaction import apply_constraints

    (x0, x1), mode = apply_constraints(
        x0=80.0, x1=95.0,
        mode="right_aligned",
        right_anchor=100.0,
        data_span_left=-10.0,
        min_width=3.0,
    )
    assert (x0, x1) == pytest.approx((80.0, 95.0))
    assert mode == "right_aligned"


def test_apply_constraints_free_below_anchor_unchanged():
    """FREE：x1 < right_anchor 时不变也不切模式。"""
    from BreakoutStrategy.UI.charts.axes_interaction import apply_constraints

    (x0, x1), mode = apply_constraints(
        x0=80.0, x1=95.0,
        mode="free",
        right_anchor=100.0,
        data_span_left=-10.0,
        min_width=3.0,
    )
    assert (x0, x1) == pytest.approx((80.0, 95.0))
    assert mode == "free"


def test_apply_constraints_free_exceeds_anchor_snaps():
    """FREE：x1 > right_anchor → 整体左移到 x1=anchor，模式切回 RIGHT_ALIGNED。"""
    from BreakoutStrategy.UI.charts.axes_interaction import apply_constraints

    (x0, x1), mode = apply_constraints(
        x0=80.0, x1=105.0,
        mode="free",
        right_anchor=100.0,
        data_span_left=-10.0,
        min_width=3.0,
    )
    assert (x0, x1) == pytest.approx((75.0, 100.0))
    assert mode == "right_aligned"


def test_apply_constraints_free_equals_anchor_also_snaps():
    """FREE：x1 == right_anchor 也算到边界，触发吸附（避免浮点边界漏）。"""
    from BreakoutStrategy.UI.charts.axes_interaction import apply_constraints

    (x0, x1), mode = apply_constraints(
        x0=80.0, x1=100.0,
        mode="free",
        right_anchor=100.0,
        data_span_left=-10.0,
        min_width=3.0,
    )
    assert (x0, x1) == pytest.approx((80.0, 100.0))
    assert mode == "right_aligned"


def test_apply_constraints_left_clip_in_free_mode():
    """左边界裁剪不影响模式。"""
    from BreakoutStrategy.UI.charts.axes_interaction import apply_constraints

    (x0, x1), mode = apply_constraints(
        x0=-50.0, x1=80.0,
        mode="free",
        right_anchor=100.0,
        data_span_left=-1.0,
        min_width=3.0,
    )
    assert (x0, x1) == pytest.approx((-1.0, 80.0))
    assert mode == "free"


def test_apply_constraints_min_width_pins_right():
    """min_width 强制时，保 x1 不动（右锚优先），x0 让步。"""
    from BreakoutStrategy.UI.charts.axes_interaction import apply_constraints

    (x0, x1), mode = apply_constraints(
        x0=99.0, x1=100.0,
        mode="right_aligned",
        right_anchor=100.0,
        data_span_left=-10.0,
        min_width=3.0,
    )
    assert (x0, x1) == pytest.approx((97.0, 100.0))
    assert mode == "right_aligned"


def test_apply_constraints_left_clip_and_right_snap_combined():
    """同时触发左裁 + 右吸附 + 模式切换。"""
    from BreakoutStrategy.UI.charts.axes_interaction import apply_constraints

    (x0, x1), mode = apply_constraints(
        x0=-50.0, x1=110.0,
        mode="free",
        right_anchor=100.0,
        data_span_left=-1.0,
        min_width=3.0,
    )
    assert (x0, x1) == pytest.approx((-1.0, 100.0))
    assert mode == "right_aligned"


# ---------- Controller 双模式集成测试 ----------

def test_controller_attach_initial_mode_is_right_aligned(controller_fig):
    fig, ax, canvas, ctrl = controller_fig
    assert ctrl.mode == ctrl.MODE_RIGHT_ALIGNED


def test_left_press_switches_to_free_mode(controller_fig):
    fig, ax, canvas, ctrl = controller_fig
    bbox = ax.bbox
    _mouse(
        "button_press_event", canvas, ax,
        bbox.x0 + bbox.width * 0.5, bbox.y0 + bbox.height * 0.5,
        button=1, xdata=50.0, ydata=0,
    )
    assert ctrl.mode == ctrl.MODE_FREE
    _mouse(
        "button_release_event", canvas, ax,
        bbox.x0 + bbox.width * 0.5, bbox.y0 + bbox.height * 0.5,
        button=1, xdata=50.0, ydata=0,
    )
    assert ctrl.is_panning is False


def test_ctrl_wheel_switches_to_free_and_anchors_at_mouse():
    """RIGHT_ALIGNED + Ctrl+wheel → 切 FREE，本次缩放锚点 = mouse_x。"""
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
    ctrl.attach(data_span=(0.0, 100.0), bar_anchor=95.0, initial_width=100.0)

    _scroll(fig.canvas, ax, xdata=30.0, step=1)  # zoom in at x=30

    assert ctrl.mode == ctrl.MODE_FREE
    x0, x1 = ax.get_xlim()
    # 锚点在 30，缩放 0.85 → new_x0 = 30 - 30*0.85 = 4.5；new_x1 = 30 + 70*0.85 = 89.5
    assert x0 == pytest.approx(4.5, abs=1e-6)
    assert x1 == pytest.approx(89.5, abs=1e-6)

    ctrl.detach()
    plt.close(fig)


def test_plain_wheel_in_right_aligned_preserves_bar_pixel_position():
    """无 Ctrl + 滚轮 + RIGHT_ALIGNED → 锚点 = bar_anchor；连续缩放中
    (xlim_right - bar_anchor) / width 恒定 → 最右 K 线像素位置恒定、像素留白一致。"""
    from BreakoutStrategy.UI.charts.axes_interaction import AxesInteractionController

    fig = plt.figure(figsize=(5, 4))
    ax = fig.add_subplot(111)
    ax.plot(range(100), range(100))
    ax.set_xlim(0, 100)
    fig.canvas.draw()

    ctrl = AxesInteractionController(ax, fig.canvas)
    # bar_anchor=95, right_anchor=100 → 初始右留白 fraction = (100-95)/100 = 0.05
    ctrl.attach(data_span=(0.0, 100.0), bar_anchor=95.0, initial_width=100.0)

    def right_margin_fraction():
        x0, x1 = ax.get_xlim()
        return (x1 - 95.0) / (x1 - x0)

    initial_fraction = right_margin_fraction()
    assert initial_fraction == pytest.approx(0.05, abs=1e-9)

    # 连续缩放（放大 + 缩小），鼠标位置任意（RA 锚点不随鼠标变化）
    for _ in range(4):
        _scroll(fig.canvas, ax, xdata=30.0, step=1)  # zoom in
    assert right_margin_fraction() == pytest.approx(0.05, abs=1e-9)

    # 放大后的 xlim_right 应严格小于 right_anchor（浮动，不钉死）
    _, x1_after_zoom_in = ax.get_xlim()
    assert x1_after_zoom_in < 100.0

    # 缩小回到默认附近
    for _ in range(4):
        _scroll(fig.canvas, ax, xdata=50.0, step=-1)
    assert right_margin_fraction() == pytest.approx(0.05, abs=1e-9)
    assert ctrl.mode == ctrl.MODE_RIGHT_ALIGNED  # 缩小期间始终 RA

    ctrl.detach()
    plt.close(fig)


def test_free_mode_wheel_overshoots_right_snaps_back():
    """FREE + 缩出 → xlim_right 越过 anchor 触发吸附 + 切回 RIGHT_ALIGNED。"""
    from BreakoutStrategy.UI.charts.axes_interaction import AxesInteractionController

    fig = plt.figure(figsize=(5, 4))
    ax = fig.add_subplot(111)
    ax.plot(range(100), range(100))
    ax.set_xlim(50, 80)  # FREE 起点：宽 30，xlim_right=80 < anchor=100
    fig.canvas.draw()

    ctrl = AxesInteractionController(ax, fig.canvas)
    ctrl.attach(data_span=(0.0, 100.0), bar_anchor=95.0, initial_width=30.0)
    ctrl._switch_to_free()  # 手动进入 FREE
    assert ctrl.mode == ctrl.MODE_FREE

    # 在 mouse_x=70 缩出（factor=ZOOM_OUT_FACTOR≈1.176）
    # new 数学 → x1 = 70 + 10*1.176 = 81.76 < 100，未触发吸附
    # 多次缩出直到越界
    for _ in range(20):
        _scroll(fig.canvas, ax, xdata=70.0, step=-1)

    x0, x1 = ax.get_xlim()
    assert x1 == pytest.approx(100.0, abs=1e-6)
    assert ctrl.mode == ctrl.MODE_RIGHT_ALIGNED  # 吸附后切回

    ctrl.detach()
    plt.close(fig)


def test_reset_method_restores_right_aligned_initial_width():
    """reset() → 模式 RIGHT_ALIGNED + xlim 回到 (anchor - initial_width, anchor)。"""
    from BreakoutStrategy.UI.charts.axes_interaction import AxesInteractionController

    fig = plt.figure(figsize=(5, 4))
    ax = fig.add_subplot(111)
    ax.plot(range(100), range(100))
    ax.set_xlim(0, 100)
    fig.canvas.draw()

    ctrl = AxesInteractionController(ax, fig.canvas)
    ctrl.attach(data_span=(0.0, 100.0), bar_anchor=95.0, initial_width=50.0)

    # 进 FREE + 缩到很小
    ctrl._switch_to_free()
    ax.set_xlim(60, 70)
    assert ctrl.mode == ctrl.MODE_FREE

    ctrl.reset()

    assert ctrl.mode == ctrl.MODE_RIGHT_ALIGNED
    x0, x1 = ax.get_xlim()
    assert (x0, x1) == pytest.approx((50.0, 100.0))

    ctrl.detach()
    plt.close(fig)


def test_reset_button_click_in_right_aligned_is_ignored():
    """RIGHT_ALIGNED 模式下点击 Reset 按钮区域 → 不触发 reset、xlim 不变。"""
    from BreakoutStrategy.UI.charts.axes_interaction import AxesInteractionController

    fig = plt.figure(figsize=(5, 4))
    ax = fig.add_subplot(111)
    ax.plot(range(100), range(100))
    ax.set_xlim(20, 80)  # 非默认 xlim
    fig.canvas.draw()

    ctrl = AxesInteractionController(ax, fig.canvas)
    ctrl.attach(data_span=(0.0, 100.0), bar_anchor=95.0, initial_width=50.0)
    # 此时 mode=RIGHT_ALIGNED；attach 不会动 xlim
    assert ctrl.mode == ctrl.MODE_RIGHT_ALIGNED

    # 触发一次绘制让 transAxes 坐标可计算
    fig.canvas.draw()

    # 取 reset 按钮中心像素并合成 button_press
    bbox_artist = ctrl._reset_button.get_window_extent(renderer=fig.canvas.get_renderer())
    cx = (bbox_artist.x0 + bbox_artist.x1) / 2
    cy = (bbox_artist.y0 + bbox_artist.y1) / 2
    pre_xlim = ax.get_xlim()
    _mouse("button_press_event", fig.canvas, ax, cx, cy, button=1, xdata=50.0, ydata=0)

    assert ax.get_xlim() == pre_xlim  # 没动
    assert not ctrl.is_panning           # 也没进入 pan

    ctrl.detach()
    plt.close(fig)


def test_reset_button_click_in_free_mode_triggers_reset():
    """FREE 模式下点击 Reset 按钮 → 触发 reset() + 切回 RIGHT_ALIGNED + xlim 复位。"""
    from BreakoutStrategy.UI.charts.axes_interaction import AxesInteractionController

    fig = plt.figure(figsize=(5, 4))
    ax = fig.add_subplot(111)
    ax.plot(range(100), range(100))
    ax.set_xlim(60, 70)  # 非默认 xlim，模拟 FREE 后已 zoom 到很小窗口
    fig.canvas.draw()

    ctrl = AxesInteractionController(ax, fig.canvas)
    ctrl.attach(data_span=(0.0, 100.0), bar_anchor=95.0, initial_width=50.0)
    ctrl._switch_to_free()
    assert ctrl.mode == ctrl.MODE_FREE

    # 触发一次绘制让 transAxes 坐标可计算
    fig.canvas.draw()

    # 取 reset 按钮中心像素并合成 button_press
    bbox_artist = ctrl._reset_button.get_window_extent(renderer=fig.canvas.get_renderer())
    cx = (bbox_artist.x0 + bbox_artist.x1) / 2
    cy = (bbox_artist.y0 + bbox_artist.y1) / 2
    _mouse("button_press_event", fig.canvas, ax, cx, cy, button=1, xdata=65.0, ydata=0)

    assert ctrl.mode == ctrl.MODE_RIGHT_ALIGNED
    x0, x1 = ax.get_xlim()
    assert (x0, x1) == pytest.approx((50.0, 100.0))
    assert not ctrl.is_panning  # 没意外进入 pan

    ctrl.detach()
    plt.close(fig)
