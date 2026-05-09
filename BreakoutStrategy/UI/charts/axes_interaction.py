"""Interactive horizontal zoom + right-drag pan for a matplotlib Axes."""
from __future__ import annotations

from typing import Callable, Optional, Tuple


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
        self._volumes: Optional["np.ndarray"] = None
        self._vol_bars: Optional[list] = None
        self._volume_scale_ratio: float = 0.2

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
        volumes: "np.ndarray | None" = None,
        vol_bars: "list | None" = None,
        volume_scale_ratio: float = 0.2,
    ) -> None:
        """Attach interaction handlers + create zoom_text and Reset button.

        Args:
            data_span: (left_bound, right_bound) — right_bound is xlim ceiling.
            n_bars: number of bars in df (for computing Ctrl-mode anchor).
            initial_width: xlim width restored by reset().
            highs: df["High"].values for dynamic Y-axis (None disables Y rescale).
            lows: df["Low"].values for dynamic Y-axis (None disables Y rescale).
            volumes: df["Volume"].values for dynamic volume bar rescaling.
            vol_bars: list of Rectangle artists from draw_volume_background.
            volume_scale_ratio: volume height as fraction of display_height (default 0.2).
        """
        self._data_span_left = data_span[0]
        self._right_anchor = data_span[1]
        self._initial_width = initial_width
        self._initial_x0 = self._right_anchor - initial_width
        self._n_bars = n_bars
        self._highs = highs
        self._lows = lows
        self._volumes = volumes
        self._vol_bars = vol_bars
        self._volume_scale_ratio = volume_scale_ratio

        self._zoom_text = self._ax.text(
            0.02, 0.98, "1.00x",
            transform=self._ax.transAxes,
            fontsize=28, va="top", ha="left", zorder=200,
            bbox=dict(boxstyle="round", fc="white", ec="#888888", alpha=0.9),
        )
        self._reset_button = self._ax.text(
            0.10, 0.98, "[Reset]",
            transform=self._ax.transAxes,
            fontsize=28, va="top", ha="left", zorder=200,
            bbox=dict(boxstyle="round", fc="#F0F0F0", ec="#BBBBBB", alpha=0.6),
            color="#BBBBBB",
        )

        self._cids = [
            self._canvas.mpl_connect("scroll_event", self._on_scroll),
            self._canvas.mpl_connect("button_press_event", self._on_press),
            self._canvas.mpl_connect("motion_notify_event", self._on_motion),
            self._canvas.mpl_connect("button_release_event", self._on_release),
        ]

        # 把 ylim 拟合到当前可见 xlim 切片：candlestick.draw_volume_background
        # 用全 df min/max 设的初始 ylim，对长历史 + 拆股股票会把可见窗口压到底部。
        self._rescale_y()

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
        self._volumes = None
        self._vol_bars = None
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

    def restore_xlim(self, xlim: Tuple[float, float]) -> None:
        """Restore a previously captured xlim (clamped to current data span) + rescale Y."""
        if self._right_anchor is None:
            return
        x0, x1 = self._apply_constraints(xlim[0], xlim[1])
        self._ax.set_xlim(x0, x1)
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
        """Rescale Y-axis to fit visible OHLC data (80/10/10 ratio) + update volume bars."""
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

        # 动态更新 volume bar artists：底边贴合 y_bottom，高度按可见 volume max 缩放
        if self._volumes is not None and self._vol_bars is not None:
            vis_vol = self._volumes[i_start:i_end]
            vis_vol_max = float(np.max(vis_vol)) if len(vis_vol) > 0 else 0
            vol_scale = (
                (display_height * self._volume_scale_ratio) / vis_vol_max
                if vis_vol_max > 0 else 0
            )
            for i, bar in enumerate(self._vol_bars):
                bar.set_y(y_bottom)
                bar.set_height(self._volumes[i] * vol_scale if vol_scale > 0 else 0)

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
