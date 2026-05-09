"""Tests for FactorGroupFrame.

These run headless via Tk's ability to create a hidden root.
Skipped automatically when no display is available.
"""

import os
import tkinter as tk
import pytest

from BreakoutStrategy.dev.editors.factor_group_frame import FactorGroupFrame


@pytest.fixture
def root():
    """Hidden Tk root, withdrawn so no window appears."""
    if not os.environ.get('DISPLAY') and os.name != 'nt':
        pytest.skip('No display available for Tk tests')
    r = tk.Tk()
    r.withdraw()
    yield r
    r.destroy()


def test_factor_group_frame_is_a_ttk_frame(root):
    """FactorGroupFrame must be parent-able like ttk.Frame."""
    from tkinter import ttk
    fgf = FactorGroupFrame(root, title='age_factor', tooltip_text='hello')
    assert isinstance(fgf, ttk.Frame)


def test_factor_group_frame_displays_title(root):
    """The title text must be rendered as a Label inside the frame."""
    fgf = FactorGroupFrame(root, title='age_factor', tooltip_text='hello')
    assert fgf.title_label.cget('text') == 'age_factor'


def test_factor_group_frame_binds_tooltip_when_text_present(root):
    """When tooltip_text is non-empty, hovering the title shows ToolTip."""
    fgf = FactorGroupFrame(root, title='age_factor', tooltip_text='hello')
    # ToolTip stores itself on the widget via _tooltip attr (see Step 3)
    assert fgf.title_label._tooltip is not None
    assert fgf.title_label._tooltip.text == 'hello'


def test_factor_group_frame_no_tooltip_when_text_empty(root):
    """Empty tooltip_text → no ToolTip bound (attribute exists as None)."""
    fgf = FactorGroupFrame(root, title='age_factor', tooltip_text='')
    assert hasattr(fgf.title_label, '_tooltip')
    assert fgf.title_label._tooltip is None


def test_factor_group_frame_no_tooltip_when_text_none(root):
    """None tooltip_text → no ToolTip bound (attribute exists as None)."""
    fgf = FactorGroupFrame(root, title='age_factor', tooltip_text=None)
    assert hasattr(fgf.title_label, '_tooltip')
    assert fgf.title_label._tooltip is None


def test_factor_group_frame_accepts_children(root):
    """Can pack child widgets into FactorGroupFrame just like ttk.Frame."""
    from tkinter import ttk
    fgf = FactorGroupFrame(root, title='age_factor', tooltip_text='hello')
    child = ttk.Label(fgf, text='child')
    child.pack()
    assert child in fgf.winfo_children()


