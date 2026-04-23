# K 线图交互行为重构 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 重构图表缩放交互——鼠标锚点为默认、Ctrl 瞬态切到右锚、新增动态 Y 轴自适应。

**Architecture:** 重写 `axes_interaction.py` 的 `apply_constraints`（去 mode）和 `AxesInteractionController`（去持久模式状态机，改为瞬态 Ctrl 判断）。attach 签名加 `n_bars` + `highs/lows` 数组供动态 Y 轴。`canvas_manager.py` 同步改 attach 调用点。测试全部重写。

**Tech Stack:** Python, matplotlib, numpy

---

### Task 1: 重写 `apply_constraints` 纯函数（去掉 mode）

**Files:**
- Modify: `BreakoutStrategy/UI/charts/axes_interaction.py:7-44`
- Modify: `BreakoutStrategy/UI/charts/tests/test_axes_interaction.py:211-345`

- [ ] **Step 1: 重写 `apply_constraints` 函数**

删除 `mode` 参数和模式切换逻辑，返回值从 `((x0,x1), mode)` 改为 `(x0, x1)`：

```python
def apply_constraints(
    x0: float,
    x1: float,
    right_anchor: float,
    data_span_left: float,
    min_width: float,
) -> tuple[float, float]:
    """Constrain (x0, x1): right ceiling, left clip, min width."""
    if x1 >= right_anchor:
        shift = x1 - right_anchor
        x0 -= shift
        x1 = right_anchor

    if x0 < data_span_left:
        x0 = data_span_left

    if x1 - x0 < min_width:
        x0 = x1 - min_width

    return x0, x1
```

- [ ] **Step 2: 重写 `apply_constraints` 测试**

替换全部旧的 apply_constraints 测试（删除 `test_apply_constraints_right_aligned_*`、`test_apply_constraints_free_*` 等 9 个测试），替换为：

```python
# ---------- apply_constraints 纯函数测试 ----------

def test_apply_constraints_clamps_x1_above_ceiling():
    """x1 超过 right_anchor → 整体左移到 x1=ceiling。"""
    from BreakoutStrategy.UI.charts.axes_interaction import apply_constraints

    x0, x1 = apply_constraints(
        x0=80.0, x1=120.0,
        right_anchor=100.0,
        data_span_left=-10.0,
        min_width=3.0,
    )
    assert (x0, x1) == pytest.approx((60.0, 100.0))


def test_apply_constraints_below_ceiling_unchanged():
    """x1 < right_anchor → 不变。"""
    from BreakoutStrategy.UI.charts.axes_interaction import apply_constraints

    x0, x1 = apply_constraints(
        x0=80.0, x1=95.0,
        right_anchor=100.0,
        data_span_left=-10.0,
        min_width=3.0,
    )
    assert (x0, x1) == pytest.approx((80.0, 95.0))


def test_apply_constraints_left_clip():
    """x0 < data_span_left → clip。"""
    from BreakoutStrategy.UI.charts.axes_interaction import apply_constraints

    x0, x1 = apply_constraints(
        x0=-50.0, x1=80.0,
        right_anchor=100.0,
        data_span_left=-1.0,
        min_width=3.0,
    )
    assert (x0, x1) == pytest.approx((-1.0, 80.0))


def test_apply_constraints_min_width():
    """窗口太窄 → x0 让步到 x1 - min_width。"""
    from BreakoutStrategy.UI.charts.axes_interaction import apply_constraints

    x0, x1 = apply_constraints(
        x0=99.0, x1=100.0,
        right_anchor=100.0,
        data_span_left=-10.0,
        min_width=3.0,
    )
    assert (x0, x1) == pytest.approx((97.0, 100.0))


def test_apply_constraints_combined():
    """同时触发右 ceiling + 左 clip。"""
    from BreakoutStrategy.UI.charts.axes_interaction import apply_constraints

    x0, x1 = apply_constraints(
        x0=-50.0, x1=110.0,
        right_anchor=100.0,
        data_span_left=-1.0,
        min_width=3.0,
    )
    assert (x0, x1) == pytest.approx((-1.0, 100.0))
```

- [ ] **Step 3: 运行测试**

Run: `uv run pytest BreakoutStrategy/UI/charts/tests/test_axes_interaction.py -k "apply_constraints" -v`
Expected: 5 PASSED

- [ ] **Step 4: Commit**

```bash
git add BreakoutStrategy/UI/charts/axes_interaction.py BreakoutStrategy/UI/charts/tests/test_axes_interaction.py
git commit -m "refactor: simplify apply_constraints, remove mode parameter"
```

---

### Task 2: 重写 AxesInteractionController 核心（去持久模式 + 瞬态 Ctrl + 动态 Y 轴）

**Files:**
- Modify: `BreakoutStrategy/UI/charts/axes_interaction.py:96-360`

- [ ] **Step 1: 重写 AxesInteractionController 类**

替换整个 class（从 `class AxesInteractionController:` 到文件末尾）为：

```python
class AxesInteractionController:
    """Mouse-wheel zoom + left-drag pan + zoom-level indicator + Reset button + dynamic Y-axis.

    缩放锚点：
    - 默认：鼠标位置（event.xdata）
    - Ctrl 按住：当前 view 最右侧可见 K 线右边缘（瞬态，松开即回鼠标锚点）

    动态 Y 轴：每次 xlim 变化后，按可见 K 线 OHLC 范围重算 ylim（80/10/10 比例）。
    """

    ZOOM_IN_FACTOR = 0.85
    ZOOM_OUT_FACTOR = 1.0 / ZOOM_IN_FACTOR
    MIN_WIDTH = 3.0

    def __init__(
        self,
        ax,
        canvas,
        on_pan_state_change: Optional[Callable[[bool], None]] = None,
        is_ctrl_pressed: Optional[Callable[[], bool]] = None,
    ):
        self._ax = ax
        self._canvas = canvas
        self._on_pan_state_change = on_pan_state_change
        self._is_ctrl_pressed = is_ctrl_pressed or (lambda: False)

        self._zoom_text = None
        self._reset_button = None
        self._cids: list = []

        self._right_anchor: Optional[float] = None
        self._data_span_left: Optional[float] = None
        self._initial_width: Optional[float] = None
        self._initial_x0: Optional[float] = None
        self._n_bars: int = 0
        self._highs: Optional["np.ndarray"] = None
        self._lows: Optional["np.ndarray"] = None

        self.is_panning: bool = False
        self._pan_anchor_px: Optional[float] = None
        self._pan_anchor_xlim: Optional[Tuple[float, float]] = None

    @property
    def zoom_level(self) -> float:
        if self._initial_width is None:
            return 1.0
        x0, x1 = self._ax.get_xlim()
        width = x1 - x0
        if width <= 0:
            return 1.0
        return self._initial_width / width

    @property
    def _needs_reset(self) -> bool:
        """视图偏离默认状态时返回 True（缩放非 1.0 或平移偏移）。"""
        if abs(self.zoom_level - 1.0) > 0.01:
            return True
        if self._initial_x0 is not None:
            x0, _ = self._ax.get_xlim()
            if abs(x0 - self._initial_x0) > 0.5:
                return True
        return False

    def attach(
        self,
        data_span: Tuple[float, float],
        n_bars: int,
        initial_width: float,
        highs: "np.ndarray | None" = None,
        lows: "np.ndarray | None" = None,
    ) -> None:
        """Attach interaction handlers + create zoom_text and Reset button.

        Args:
            data_span: (left_bound, right_bound) — right_bound is xlim ceiling.
            n_bars: number of bars in df (for computing Ctrl-mode anchor).
            initial_width: xlim width restored by reset().
            highs: df["High"].values for dynamic Y-axis (None disables Y rescale).
            lows: df["Low"].values for dynamic Y-axis (None disables Y rescale).
        """
        self._data_span_left = data_span[0]
        self._right_anchor = data_span[1]
        self._initial_width = initial_width
        self._initial_x0 = self._right_anchor - initial_width
        self._n_bars = n_bars
        self._highs = highs
        self._lows = lows

        self._zoom_text = self._ax.text(
            0.02, 0.98, "1.00x",
            transform=self._ax.transAxes,
            fontsize=28, va="top", ha="left", zorder=200,
            bbox=dict(boxstyle="round", fc="white", ec="#888888", alpha=0.9),
        )
        self._reset_button = self._ax.text(
            0.07, 0.98, "[Reset]",
            transform=self._ax.transAxes,
            fontsize=12, va="top", ha="left", zorder=200,
            bbox=dict(boxstyle="round", fc="#F0F0F0", ec="#BBBBBB", alpha=0.6),
            color="#BBBBBB",
        )

        self._cids = [
            self._canvas.mpl_connect("scroll_event", self._on_scroll),
            self._canvas.mpl_connect("button_press_event", self._on_press),
            self._canvas.mpl_connect("motion_notify_event", self._on_motion),
            self._canvas.mpl_connect("button_release_event", self._on_release),
        ]

    def detach(self) -> None:
        for cid in self._cids:
            self._canvas.mpl_disconnect(cid)
        self._cids = []
        self._zoom_text = None
        self._reset_button = None
        self._right_anchor = None
        self._data_span_left = None
        self._initial_width = None
        self._initial_x0 = None
        self._n_bars = 0
        self._highs = None
        self._lows = None
        self.is_panning = False
        self._pan_anchor_px = None
        self._pan_anchor_xlim = None

    def reset(self) -> None:
        """Restore initial xlim + rescale Y + redraw."""
        if self._right_anchor is None or self._initial_width is None:
            return
        self._ax.set_xlim(self._initial_x0, self._right_anchor)
        self._rescale_y()
        self._update_zoom_text()
        self._update_reset_button_style()
        self._canvas.draw_idle()

    # ---------- Event handlers ----------

    def _on_scroll(self, event) -> None:
        if event.inaxes is not self._ax or event.xdata is None:
            return
        factor = self.ZOOM_IN_FACTOR if event.step > 0 else self.ZOOM_OUT_FACTOR

        if self._is_ctrl_pressed() and self._n_bars > 0:
            anchor = min(self._ax.get_xlim()[1], self._n_bars - 0.5)
        else:
            anchor = event.xdata

        new_x0, new_x1 = compute_zoom_xlim(
            xlim=self._ax.get_xlim(),
            mouse_x=anchor,
            factor=factor,
            min_width=self.MIN_WIDTH,
            max_width=float("inf"),
        )
        new_x0, new_x1 = self._apply_constraints(new_x0, new_x1)
        self._ax.set_xlim(new_x0, new_x1)
        self._rescale_y()
        self._update_zoom_text()
        self._update_reset_button_style()
        self._canvas.draw_idle()

    def _on_press(self, event) -> None:
        if event.button == 1 and self._is_in_reset_button(event):
            if self._needs_reset:
                self.reset()
            return

        if event.button != 1 or event.inaxes is not self._ax:
            return

        self.is_panning = True
        self._pan_anchor_px = event.x
        self._pan_anchor_xlim = self._ax.get_xlim()
        if self._on_pan_state_change is not None:
            self._on_pan_state_change(True)

    def _on_motion(self, event) -> None:
        if not self.is_panning or self._pan_anchor_px is None:
            return
        if self._pan_anchor_xlim is None:
            return
        new_x0, new_x1 = compute_pan_xlim(
            anchor_xlim=self._pan_anchor_xlim,
            anchor_px=self._pan_anchor_px,
            current_px=event.x,
            axes_px_width=self._ax.bbox.width,
        )
        new_x0, new_x1 = self._apply_constraints(new_x0, new_x1)
        self._ax.set_xlim(new_x0, new_x1)
        self._rescale_y()
        self._update_zoom_text()
        self._update_reset_button_style()
        self._canvas.draw_idle()

    def _on_release(self, event) -> None:
        if event.button != 1 or not self.is_panning:
            return
        self.is_panning = False
        self._pan_anchor_px = None
        self._pan_anchor_xlim = None
        if self._on_pan_state_change is not None:
            self._on_pan_state_change(False)

    # ---------- Constraint helper ----------

    def _apply_constraints(self, x0: float, x1: float) -> Tuple[float, float]:
        return apply_constraints(
            x0=x0, x1=x1,
            right_anchor=self._right_anchor,
            data_span_left=self._data_span_left,
            min_width=self.MIN_WIDTH,
        )

    # ---------- Dynamic Y-axis ----------

    def _rescale_y(self) -> None:
        """Rescale Y-axis to fit visible OHLC data (80/10/10 ratio)."""
        if self._highs is None or self._lows is None:
            return
        x0, x1 = self._ax.get_xlim()
        i_start = max(0, int(x0 + 0.5))
        i_end = min(len(self._highs), int(x1 + 0.5))
        if i_start >= i_end:
            return
        import numpy as np
        price_max = float(np.max(self._highs[i_start:i_end]))
        price_min = float(np.min(self._lows[i_start:i_end]))
        price_range = price_max - price_min
        if price_range <= 0:
            return
        display_height = price_range / 0.8
        y_bottom = price_min - display_height * 0.1
        self._ax.set_ylim(y_bottom, y_bottom + display_height)

    # ---------- Reset button helpers ----------

    def _update_reset_button_style(self) -> None:
        if self._reset_button is None:
            return
        if self._needs_reset:
            self._reset_button.set_color("black")
            self._reset_button.get_bbox_patch().set_edgecolor("#888888")
            self._reset_button.get_bbox_patch().set_alpha(0.9)
        else:
            self._reset_button.set_color("#BBBBBB")
            self._reset_button.get_bbox_patch().set_edgecolor("#BBBBBB")
            self._reset_button.get_bbox_patch().set_alpha(0.6)

    def _is_in_reset_button(self, event) -> bool:
        if self._reset_button is None:
            return False
        contains, _ = self._reset_button.contains(event)
        return bool(contains)

    # ---------- zoom text ----------

    def _update_zoom_text(self) -> None:
        if self._zoom_text is None:
            return
        self._zoom_text.set_text(f"{self.zoom_level:.2f}x")
```

- [ ] **Step 2: 运行验证（仅 apply_constraints 测试应 PASS，其余暂时 FAIL）**

Run: `uv run pytest BreakoutStrategy/UI/charts/tests/test_axes_interaction.py -k "apply_constraints" -v`
Expected: 5 PASSED

- [ ] **Step 3: Commit**

```bash
git add BreakoutStrategy/UI/charts/axes_interaction.py
git commit -m "refactor: rewrite AxesInteractionController - mouse-anchor default, transient Ctrl, dynamic Y-axis"
```

---

### Task 3: 重写 Controller 测试

**Files:**
- Modify: `BreakoutStrategy/UI/charts/tests/test_axes_interaction.py`

- [ ] **Step 1: 重写 fixture 和 controller 测试**

替换从 `@pytest.fixture def controller_fig` 到文件末尾的全部内容：

```python
@pytest.fixture
def controller_fig():
    """Provide a fresh (fig, ax, canvas, controller) attached instance.

    100 根 K 线，xlim=(0,100)；data_span=(-2, 105)，n_bars=100，initial_width=100。
    highs/lows 为简单斜线数据用于 Y 轴测试。
    """
    import numpy as np
    from BreakoutStrategy.UI.charts.axes_interaction import AxesInteractionController

    fig = plt.figure(figsize=(5, 4))
    ax = fig.add_subplot(111)
    ax.plot(range(100), range(100))
    ax.set_xlim(0, 105)
    fig.canvas.draw()

    highs = np.arange(100, dtype=float) + 10  # [10, 11, ..., 109]
    lows = np.arange(100, dtype=float)         # [0, 1, ..., 99]

    ctrl = AxesInteractionController(ax, fig.canvas)
    ctrl.attach(
        data_span=(-2.0, 105.0),
        n_bars=100,
        initial_width=105.0 - (-2.0),  # full span
        highs=highs,
        lows=lows,
    )
    yield fig, ax, fig.canvas, ctrl
    ctrl.detach()
    plt.close(fig)


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
    import numpy as np
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
    import numpy as np
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
    import numpy as np
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
    # x0 should move toward 30, x1 should also move toward 30
    width_after = x1_mouse - x0_mouse
    width_before = x1_ctrl - x0_ctrl
    assert width_after < width_before  # zoomed in further
    # The 30.0 point should be proportionally closer to center
    frac = (30.0 - x0_mouse) / (x1_mouse - x0_mouse)
    assert 0.1 < frac < 0.9  # mouse anchor is inside visible range

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
    # Shifted left by pixel delta
    expected_shift = -50 * ((105.0 - (-2.0)) / bbox.width)
    assert x0 < 0.0 or x0 == pytest.approx(-2.0, abs=0.5)

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
    import numpy as np
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
    import numpy as np
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
    import numpy as np
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
    import numpy as np
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

    # highs = [10,11,...,109], lows = [0,1,...,99]
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
    import numpy as np
    from BreakoutStrategy.UI.charts.axes_interaction import AxesInteractionController

    fig = plt.figure(figsize=(5, 4))
    ax = fig.add_subplot(111)
    ax.plot(range(100), range(100))
    ax.set_xlim(0, 100)
    ax.set_ylim(0, 100)
    fig.canvas.draw()

    ctrl = AxesInteractionController(ax, fig.canvas)
    ctrl.attach(data_span=(0.0, 105.0), n_bars=100, initial_width=100.0)  # no highs/lows

    ctrl._rescale_y()  # should not crash
    assert ax.get_ylim() == (0.0, 100.0)  # unchanged

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
    import numpy as np
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
```

- [ ] **Step 2: 运行全部测试**

Run: `uv run pytest BreakoutStrategy/UI/charts/tests/test_axes_interaction.py -v`
Expected: ALL PASSED

- [ ] **Step 3: Commit**

```bash
git add BreakoutStrategy/UI/charts/tests/test_axes_interaction.py
git commit -m "test: rewrite interaction tests for new mouse-anchor + Ctrl + Y-axis behavior"
```

---

### Task 4: 更新 canvas_manager.py 的 attach 调用

**Files:**
- Modify: `BreakoutStrategy/UI/charts/canvas_manager.py:288-352`

- [ ] **Step 1: 修改 update_chart 中的 attach 调用**

在 `update_chart` 方法中找到 attach 调用（约第 288-352 行），做以下修改：

1. 在计算 `margin_left` 之前（约第 288 行），提取 highs/lows：

```python
        import numpy as np
        _highs = df["High"].values if "High" in df.columns else None
        _lows = df["Low"].values if "Low" in df.columns else None
```

2. 删除 `bar_anchor = len(df) - 0.5` 这一行（约第 305 行）。

3. 修改 attach 调用（约第 348-352 行），将：

```python
        self.interaction.attach(
            data_span=(data_span_left, right_anchor),
            bar_anchor=bar_anchor,
            initial_width=initial_width,
        )
```

替换为：

```python
        self.interaction.attach(
            data_span=(data_span_left, right_anchor),
            n_bars=len(df),
            initial_width=initial_width,
            highs=_highs,
            lows=_lows,
        )
```

4. 将 `initial_width = right_anchor - (visible_left_idx - 0.5)` 中对 `bar_anchor` 的依赖清理掉。`right_anchor` 的计算改为不依赖 `bar_anchor`：

```python
            right_anchor = len(df) - 0.5 + initial_margin_right
```

- [ ] **Step 2: 运行全部 UI chart 测试**

Run: `uv run pytest BreakoutStrategy/UI/charts/tests/ -v`
Expected: ALL PASSED

- [ ] **Step 3: Commit**

```bash
git add BreakoutStrategy/UI/charts/canvas_manager.py
git commit -m "feat: pass highs/lows + n_bars to interaction controller for dynamic Y-axis"
```

---

### Task 5: 运行完整回归测试

**Files:** None (verification only)

- [ ] **Step 1: 运行全部 UI + live 测试**

Run: `uv run pytest BreakoutStrategy/UI/ BreakoutStrategy/live/ -v`
Expected: ALL PASSED (or SKIPPED for known stubs)

- [ ] **Step 2: 如果有 live 测试引用旧 API（`bar_anchor`），修复之**

检查 `BreakoutStrategy/live/` 下是否有测试直接引用 `AxesInteractionController.attach` 的旧签名。如果有，更新参数。

---

## Verification

```bash
cd /home/yu/PycharmProjects/Trade_Strategy

# 单元测试
uv run pytest BreakoutStrategy/UI/charts/tests/test_axes_interaction.py -v

# 回归
uv run pytest BreakoutStrategy/UI/ BreakoutStrategy/live/ -v
```

手动验证：
1. 启动 Dev UI，滚轮缩放 → 锚点在鼠标位置（K 线图围绕鼠标位置收缩/扩展）
2. 按住 Ctrl + 滚轮 → 锚点在 view 最右 K 线（最右侧保持不动）
3. 松开 Ctrl + 滚轮 → 立刻回到鼠标锚点
4. 缩放/平移后 Y 轴自动适配可见 K 线范围
5. 点击 Reset → 恢复初始视图 + Y 轴
6. Live UI 同样验证以上行为
