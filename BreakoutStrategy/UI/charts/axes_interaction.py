"""Interactive horizontal zoom + right-drag pan for a matplotlib Axes."""
from __future__ import annotations

from typing import Callable, Optional, Tuple


def apply_constraints(
    x0: float,
    x1: float,
    mode: str,
    right_anchor: float,
    data_span_left: float,
    min_width: float,
) -> tuple[tuple[float, float], str]:
    """Constrain (x0, x1) to a right-anchor ceiling, then clip left + min width.

    Right-edge ceiling (both modes): if x1 >= right_anchor, shift the entire
    window left so x1 lands on right_anchor. Only FREE snaps back to
    RIGHT_ALIGNED on this trigger; RIGHT_ALIGNED stays RIGHT_ALIGNED (it never
    pins x1 below the ceiling — that's controlled by the caller's anchor).

    Then clip x0 to data_span_left and enforce min_width with x1 priority.

    Returns ((new_x0, new_x1), new_mode).
    """
    new_mode = mode

    # 1. Right-edge ceiling (applies to both modes; mode-switch only in FREE)
    if x1 >= right_anchor:
        shift = x1 - right_anchor
        x0 -= shift
        x1 = right_anchor
        if mode == "free":
            new_mode = "right_aligned"

    # 2. Left clip
    if x0 < data_span_left:
        x0 = data_span_left

    # 3. Min width (right anchor priority)
    if x1 - x0 < min_width:
        x0 = x1 - min_width

    return (x0, x1), new_mode


def compute_zoom_xlim(
    xlim: Tuple[float, float],
    mouse_x: float,
    factor: float,
    min_width: float = 3.0,
    max_width: float = float("inf"),
) -> Tuple[float, float]:
    """Return new (x0, x1) that keeps mouse_x fixed and scales width by factor.

    factor<1 zooms in (window narrows); factor>1 zooms out (window widens).
    Result is clamped so (x1-x0) stays within [min_width, max_width], with
    mouse_x held fixed at the clamp boundary.
    """
    x0, x1 = xlim
    new_x0 = mouse_x - (mouse_x - x0) * factor
    new_x1 = mouse_x + (x1 - mouse_x) * factor
    width = new_x1 - new_x0

    if width < min_width:
        scale = min_width / width
        new_x0 = mouse_x - (mouse_x - new_x0) * scale
        new_x1 = mouse_x + (new_x1 - mouse_x) * scale
    elif width > max_width:
        scale = max_width / width
        new_x0 = mouse_x - (mouse_x - new_x0) * scale
        new_x1 = mouse_x + (new_x1 - mouse_x) * scale

    return new_x0, new_x1


def compute_pan_xlim(
    anchor_xlim: Tuple[float, float],
    anchor_px: float,
    current_px: float,
    axes_px_width: float,
) -> Tuple[float, float]:
    """Return new (x0, x1) shifted by the data-equivalent of pixel delta.

    Uses the xlim snapshot taken at press time to avoid xdata self-feedback
    loops when updating xlim repeatedly during drag.
    """
    x0, x1 = anchor_xlim
    if axes_px_width <= 0:
        return x0, x1
    data_per_px = (x1 - x0) / axes_px_width
    shift = -(current_px - anchor_px) * data_per_px
    return x0 + shift, x1 + shift


class AxesInteractionController:
    """Mouse-wheel horizontal zoom + left-drag pan + zoom-level indicator + Reset button.

    Two modes:
    - RIGHT_ALIGNED (default): wheel zoom anchored at bar_anchor (the rightmost
      K-line's right edge in data coords) → the rightmost bar's pixel position
      stays fixed during zoom, pixel right margin stays visually constant.
      xlim_right is capped at right_anchor (= data_span right edge).
      Ctrl+wheel switches to FREE.
    - FREE: wheel zoom anchors at mouse position; left-drag pans freely;
      xlim_right cannot exceed right_anchor (snap-back to RIGHT_ALIGNED on
      overshoot).

    Reset button (top-left ax.text artist) returns to RIGHT_ALIGNED with xlim =
    (right_anchor - initial_width, right_anchor).
    """

    MODE_RIGHT_ALIGNED = "right_aligned"
    MODE_FREE = "free"

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

        self.mode: str = self.MODE_RIGHT_ALIGNED
        self._right_anchor: Optional[float] = None
        self._bar_anchor: Optional[float] = None
        self._data_span_left: Optional[float] = None
        self._initial_width: Optional[float] = None

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
        """视图偏离默认状态时返回 True（FREE 模式 或 缩放非 1.0）。"""
        if self.mode == self.MODE_FREE:
            return True
        return abs(self.zoom_level - 1.0) > 0.01

    def attach(
        self,
        data_span: Tuple[float, float],
        bar_anchor: float,
        initial_width: float,
    ) -> None:
        """Attach interaction handlers + create zoom_text and Reset button artists.

        Args:
            data_span: (left_bound, right_bound) data range (incl. left padding).
                data_span[1] doubles as the xlim_right ceiling (right_anchor).
            bar_anchor: data x of the rightmost K-line's right edge. In
                RIGHT_ALIGNED mode wheel zoom anchors here so the rightmost bar
                stays at a fixed pixel position (pixel-constant right margin).
            initial_width: width restored by reset().
        """
        self._data_span_left = data_span[0]
        self._right_anchor = data_span[1]
        self._bar_anchor = bar_anchor
        self._initial_width = initial_width
        self.mode = self.MODE_RIGHT_ALIGNED

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
        self._bar_anchor = None
        self._data_span_left = None
        self._initial_width = None
        self.mode = self.MODE_RIGHT_ALIGNED
        self.is_panning = False
        self._pan_anchor_px = None
        self._pan_anchor_xlim = None

    def reset(self) -> None:
        """Restore RIGHT_ALIGNED mode + initial_width window + redraw."""
        if self._right_anchor is None or self._initial_width is None:
            return
        self.mode = self.MODE_RIGHT_ALIGNED
        self._update_reset_button_style()
        self._ax.set_xlim(
            self._right_anchor - self._initial_width,
            self._right_anchor,
        )
        self._update_zoom_text()
        self._canvas.draw_idle()

    # ---------- Event handlers ----------

    def _on_scroll(self, event) -> None:
        if event.inaxes is not self._ax or event.xdata is None:
            return
        factor = self.ZOOM_IN_FACTOR if event.step > 0 else self.ZOOM_OUT_FACTOR

        if self.mode == self.MODE_RIGHT_ALIGNED and self._is_ctrl_pressed():
            self._switch_to_free()

        anchor = (
            self._bar_anchor
            if self.mode == self.MODE_RIGHT_ALIGNED
            else event.xdata
        )

        new_x0, new_x1 = compute_zoom_xlim(
            xlim=self._ax.get_xlim(),
            mouse_x=anchor,
            factor=factor,
            min_width=self.MIN_WIDTH,
            max_width=float("inf"),
        )
        new_x0, new_x1 = self._apply_constraints(new_x0, new_x1)
        self._ax.set_xlim(new_x0, new_x1)
        self._update_zoom_text()
        self._update_reset_button_style()
        self._canvas.draw_idle()

    def _on_press(self, event) -> None:
        # Reset 按钮区域：视图偏离默认时触发 reset；否则静默拦截
        # （防止默认态按钮被点反而误进 FREE 模式 + pan）
        if event.button == 1 and self._is_in_reset_button(event):
            if self._needs_reset:
                self.reset()
            return

        if event.button != 1 or event.inaxes is not self._ax:
            return

        self._switch_to_free()
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
        self._update_zoom_text()
        self._canvas.draw_idle()

    def _on_release(self, event) -> None:
        if event.button != 1 or not self.is_panning:
            return
        self.is_panning = False
        self._pan_anchor_px = None
        self._pan_anchor_xlim = None
        if self._on_pan_state_change is not None:
            self._on_pan_state_change(False)

    # ---------- Mode helpers ----------

    def _switch_to_free(self) -> None:
        if self.mode == self.MODE_FREE:
            return
        self.mode = self.MODE_FREE
        self._update_reset_button_style()

    def _switch_to_right_aligned(self) -> None:
        if self.mode == self.MODE_RIGHT_ALIGNED:
            return
        self.mode = self.MODE_RIGHT_ALIGNED
        self._update_reset_button_style()

    def _apply_constraints(
        self, x0: float, x1: float
    ) -> Tuple[float, float]:
        (new_x0, new_x1), new_mode = apply_constraints(
            x0=x0, x1=x1,
            mode=self.mode,
            right_anchor=self._right_anchor,
            data_span_left=self._data_span_left,
            min_width=self.MIN_WIDTH,
        )
        if new_mode != self.mode:
            self._switch_to_right_aligned()
        return new_x0, new_x1

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
