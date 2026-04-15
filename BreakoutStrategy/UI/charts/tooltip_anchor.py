"""Hover tooltip edge-aware anchor computation.

Pure function — no matplotlib / canvas dependency; trivially unit-testable.
"""
from __future__ import annotations


def compute_tooltip_anchor(
    cursor_px: tuple[float, float],
    fig_size: tuple[float, float],
    est_tooltip_size: tuple[float, float],
    arrow_offset: float = 40,
    edge_margin: float = 10,
) -> tuple[float, float, str, str]:
    """Return (offset_x, offset_y, ha, va) for an mpl Annotation at cursor.

    Args:
        cursor_px: (event.x, event.y) — mpl MouseEvent pixel coords, origin lower-left.
        fig_size: (fig_w_px, fig_h_px).
        est_tooltip_size: conservative (w, h) estimate of tooltip bbox in px.
        arrow_offset: distance from cursor to tooltip's near corner, in points.
        edge_margin: extra safety gap from canvas edge before triggering flip.

    Tooltip's near corner is placed at cursor + (offset_x, offset_y) when
    annotate is configured with the returned ha/va.
    """
    cx, cy = cursor_px
    fw, fh = fig_size
    tw, th = est_tooltip_size

    flip_x = cx + tw + edge_margin > fw
    flip_y = cy + th + edge_margin > fh

    offset_x = -arrow_offset if flip_x else arrow_offset
    ha = "right" if flip_x else "left"
    offset_y = -arrow_offset if flip_y else arrow_offset
    va = "top" if flip_y else "bottom"

    return offset_x, offset_y, ha, va
