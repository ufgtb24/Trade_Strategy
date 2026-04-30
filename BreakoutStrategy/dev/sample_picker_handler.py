"""dev UI sample picker 集成 handler。

把 KeyboardPicker 挑出的两个端点 (left_idx, right_idx) 转成
feature_library.preprocess.preprocess_sample 的调用，处理：
- 全局 index → df_window 局部 index 转换（200 bar 切片）
- bo_date 推算
- preprocess 异常捕获（不让异常逃逸阻塞 Tk 主循环）
- on_done 回调（sample_id 或 None）

与 dev/main.py 解耦——便于单元测试 + 未来其他入口（如 web UI）复用。
"""

from datetime import datetime
from pathlib import Path
from typing import Callable, Optional

import pandas as pd
import yaml

from BreakoutStrategy.feature_library.glm4v_backend import GLM4VBackend
from BreakoutStrategy.feature_library.preprocess import preprocess_sample

_REPO_ROOT = Path(__file__).resolve().parents[2]
_API_KEYS_PATH = _REPO_ROOT / "configs" / "api_keys.yaml"
_GLM4V_SINGLETON: Optional[GLM4VBackend] = None

WINDOW_BARS_BEFORE_BO = 200


def handle_endpoints_picked(
    *,
    left_idx: int,
    right_idx: int,
    ticker: str,
    df: pd.DataFrame,
    picked_at: datetime,
    backend,
    on_done: Callable[[Optional[str]], None],
) -> None:
    """把两个全局 bar index 转成 preprocess_sample 调用。

    Args:
        left_idx: 较小的全局 bar index（pk_index 候选）
        right_idx: 较大的全局 bar index（bo_index 候选；调用方已保证 ∈ BO 集合）
        ticker: 股票代码
        df: 完整 OHLCV DataFrame（dev UI 的 current_df）
        picked_at: 用户挑选时刻
        backend: 多模态 backend（如 GLM4VBackend），需有 describe_chart 方法
        on_done: 完成回调，接收 sample_id 或 None（失败时）
    """
    window_start = max(0, right_idx - WINDOW_BARS_BEFORE_BO)
    df_window = df.iloc[window_start: right_idx + 1]
    local_bo = right_idx - window_start
    local_pk = left_idx - window_start
    bo_date = df.index[right_idx]

    try:
        sample_id = preprocess_sample(
            ticker=ticker,
            bo_date=bo_date,
            df_window=df_window,
            bo_index=local_bo,
            pk_index=local_pk,
            picked_at=picked_at,
            backend=backend,
        )
    except Exception as exc:
        # 捕获以避免 Tk 主循环被异常挂掉；调用方通过 on_done(None) 感知失败
        print(f"[sample_picker_handler] preprocess_sample 失败：{exc!r}")
        on_done(None)
        return

    on_done(sample_id)


def get_glm4v_backend_lazy() -> Optional[GLM4VBackend]:
    """lazy 实例化 GLM4VBackend 单例。

    Returns:
        GLM4VBackend 实例；若 api_keys.yaml 缺失或 zhipuai key 为空则 None
        （调用方应据此禁用 picker 或显示错误提示）。
    """
    global _GLM4V_SINGLETON
    if _GLM4V_SINGLETON is not None:
        return _GLM4V_SINGLETON
    if not _API_KEYS_PATH.exists():
        return None
    try:
        keys = yaml.safe_load(_API_KEYS_PATH.read_text(encoding="utf-8")) or {}
    except Exception as exc:
        print(f"[sample_picker_handler] api_keys.yaml 解析失败：{exc!r}")
        return None
    api_key = keys.get("zhipuai", "").strip()
    if not api_key:
        return None
    _GLM4V_SINGLETON = GLM4VBackend(api_key=api_key)
    return _GLM4V_SINGLETON
