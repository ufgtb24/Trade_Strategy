"""单样本预处理 — Phase 0 vertical slice 入口。

输入：(ticker, bo_date, df_window, bo_index, pk_index, picked_at, backend)
输出：sample_id（已落盘 chart.png + meta.yaml + nl_description.md）

调用顺序：
1. 生成 sample_id
2. 渲染 chart.png
3. 构建 meta dict + 写 meta.yaml
4. 调 backend.describe_chart → 写 nl_description.md
   （backend 返回空字符串时写 PREPROCESS_FAILED 标记，不抛异常）
"""

from datetime import datetime
from typing import Protocol

import pandas as pd

from BreakoutStrategy.feature_library import paths
from BreakoutStrategy.feature_library.prompts import build_user_message
from BreakoutStrategy.feature_library.sample_id import generate_sample_id
from BreakoutStrategy.feature_library.sample_meta import build_meta, write_meta_yaml
from BreakoutStrategy.feature_library.sample_renderer import render_sample_chart


class _MultimodalBackend(Protocol):
    def describe_chart(self, *, chart_path, user_message: str) -> str: ...


PREPROCESS_FAILED_MARKER = (
    "PREPROCESS_FAILED: backend returned empty response. "
    "请检查 GLM-4V-Flash API key / 网络连接 / 配额，重新运行 preprocess。"
)


def preprocess_sample(
    *,
    ticker: str,
    bo_date: pd.Timestamp,
    df_window: pd.DataFrame,
    bo_index: int,
    pk_index: int,
    picked_at: datetime,
    backend: _MultimodalBackend,
) -> str:
    """完整预处理一个 breakout 样本，返回 sample_id。"""
    sample_id = generate_sample_id(ticker=ticker, bo_date=bo_date)

    # 1. 渲染图（先于 meta，便于 backend 立即可用）
    chart_path = render_sample_chart(
        sample_id=sample_id,
        df_window=df_window,
        bo_index=bo_index,
        left_index=pk_index,   # pk_index 在数据层仍是 consolidation anchor；
                               # sample_renderer 视角是"窗口左端"
    )

    # 2. 构建 meta
    meta = build_meta(
        sample_id=sample_id,
        ticker=ticker.upper(),
        bo_date=bo_date,
        df_window=df_window,
        bo_index=bo_index,
        pk_index=pk_index,
        picked_at=picked_at,
    )
    write_meta_yaml(sample_id, meta)

    # 3. 调 backend 生成 nl_description
    user_msg = build_user_message(meta)
    nl_text = backend.describe_chart(
        chart_path=chart_path, user_message=user_msg,
    )

    # 4. 写 nl_description.md（失败时写 fallback 标记）
    nl_path = paths.nl_description_path(sample_id)
    nl_path.write_text(nl_text if nl_text else PREPROCESS_FAILED_MARKER, encoding="utf-8")

    return sample_id
