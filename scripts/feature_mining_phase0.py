"""Phase 0 vertical slice 入口脚本。

运行方式：
    uv run python scripts/feature_mining_phase0.py

参数全部在 main() 起始位置声明（CLAUDE.md 要求，不用 argparse）。
默认从 datasets/pkls/ 加载指定 ticker，调用 BreakoutDetector.batch_add_bars
找到第一个满足条件的 breakout，做单样本 preprocess。

依赖 GLM-4V-Flash 真实 API 调用（zhipuai key from configs/api_keys.yaml）。
"""

from datetime import datetime
from pathlib import Path

import pandas as pd
import yaml

from BreakoutStrategy.analysis.breakout_detector import BreakoutDetector
from BreakoutStrategy.feature_library import paths
from BreakoutStrategy.feature_library.glm4v_backend import GLM4VBackend
from BreakoutStrategy.feature_library.preprocess import preprocess_sample


REPO_ROOT = Path(__file__).resolve().parents[1]


def _load_zhipuai_key() -> str:
    cfg_path = REPO_ROOT / "configs" / "api_keys.yaml"
    keys = yaml.safe_load(cfg_path.read_text())
    api_key = keys.get("zhipuai", "")
    if not api_key:
        raise RuntimeError(
            "configs/api_keys.yaml 中 zhipuai key 为空，请填写后重试"
        )
    return api_key


def _load_pkl(ticker: str) -> pd.DataFrame:
    pkl_path = REPO_ROOT / "datasets" / "pkls" / f"{ticker}.pkl"
    if not pkl_path.exists():
        raise FileNotFoundError(f"未找到 {pkl_path}")
    return pd.read_pickle(pkl_path)


def main() -> None:
    # ---------------- 参数声明区 ----------------
    ticker: str = "AAPL"    # 目标股票
    sample_count: int = 1   # 处理几个 breakout
    # BreakoutDetector 额外参数（全用默认值，symbol 由脚本自动传入）
    total_window: int = 10
    min_side_bars: int = 2
    # -------------------------------------------

    print(f"[Phase 0] 加载 {ticker} 历史数据...")
    df = _load_pkl(ticker)
    print(f"[Phase 0] 数据范围 {df.index[0].date()} ~ {df.index[-1].date()}, {len(df)} bars")

    print(f"[Phase 0] 检测 breakouts...")
    # BreakoutDetector 需要 symbol 作为第一参数；批量检测用 batch_add_bars
    detector = BreakoutDetector(
        symbol=ticker,
        total_window=total_window,
        min_side_bars=min_side_bars,
    )
    breakout_infos = detector.batch_add_bars(df)
    print(f"[Phase 0] 检测到 {len(breakout_infos)} 个 breakouts，取前 {sample_count} 个")

    if not breakout_infos:
        print("[Phase 0] 无 breakout，退出")
        return

    print(f"[Phase 0] 加载 zhipuai API key...")
    api_key = _load_zhipuai_key()
    backend = GLM4VBackend(api_key=api_key)

    targets = breakout_infos[:sample_count]
    for i, bo in enumerate(targets, start=1):
        # bo 是 BreakoutInfo，字段：current_index, broken_peaks（列表）
        bo_index = bo.current_index
        # pk_index 选择策略：取"最近"被突破的 peak（按 index 最大）作为 consolidation 起点。
        # broken_peaks 包含突破事件同时跨越的所有 peaks（可能横跨多个高点）。
        # 选"最近"而非"最远"的语义：聚焦于突破事件最直接前置的盘整窗口，
        # 避免把整个长期 base 当成一段"盘整"——那会让 consolidation_length_bars 过大、
        # 稀释特征信号（短期紧凑盘整 vs. 多月宽松底部 的区分失效）。
        # Phase 1 若 Inducer 需要"完整 base"语义（关注整个宽底），
        # 可改用 min(p.index for p in bo.broken_peaks) 作为替代。
        pk_index = max(p.index for p in bo.broken_peaks) if bo.broken_peaks else bo_index

        # df_window：取 bo 点前 200 根 K 线（含 bo 本身）
        win_start = max(0, bo_index - 200)
        df_window = df.iloc[win_start: bo_index + 1]
        # 将全局索引换算为窗口内的局部索引
        local_bo_index = bo_index - win_start
        local_pk_index = max(0, pk_index - win_start)

        print(f"\n[Phase 0] [{i}/{len(targets)}] 处理 BO "
              f"bo_index={bo_index} date={bo.current_date} price={bo.current_price:.2f} ...")
        sample_id = preprocess_sample(
            ticker=ticker,
            bo_date=df.index[bo_index],
            df_window=df_window,
            bo_index=local_bo_index,
            pk_index=local_pk_index,
            picked_at=datetime.now(),
            backend=backend,
        )
        print(f"[Phase 0] 完成 sample_id={sample_id}")
        print(f"[Phase 0]   chart.png: {paths.chart_png_path(sample_id)}")
        print(f"[Phase 0]   meta.yaml: {paths.meta_yaml_path(sample_id)}")
        print(f"[Phase 0]   nl_description.md: {paths.nl_description_path(sample_id)}")
        nl_text = paths.nl_description_path(sample_id).read_text(encoding="utf-8")
        print(f"[Phase 0]   nl_description 摘录: {nl_text[:200]}...")


if __name__ == "__main__":
    main()
