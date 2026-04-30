"""Phase 1 vertical slice 入口脚本(批量自动化烟测)。

运行方式：
    uv run python scripts/feature_mining_phase1.py

参数全部在 main() 起始位置声明（CLAUDE.md 要求，不用 argparse）。
默认从 datasets/pkls/ 加载指定 ticker，调用 BreakoutDetector 找前 N 个 breakouts，
对每个跑 Phase 0 preprocess（如未跑过），然后用 Inducer 多图 batch 归纳，
Librarian 累积入 features 库。

定位:本脚本是 Phase 1 批量自动化烟测/验证入口,不是正式 feature mining 流程 ——
正式流程是 dev UI(scripts/visualization/interactive_viewer.py) 下用户按 P 灵活
挑选样本左端点。本脚本用 `min_bars_before_bo` 强制最小窗口,确保 GLM-4V 拿到
足够视觉上下文,避免 broken_peak 紧挨 BO 时窗口仅几根 K 线。

依赖 GLM-4V-Flash 真实 API 调用（zhipuai key from configs/api_keys.yaml）。
"""

from datetime import datetime
from pathlib import Path

import pandas as pd
import yaml

from BreakoutStrategy.analysis.breakout_detector import BreakoutDetector
from BreakoutStrategy.feature_library import paths
from BreakoutStrategy.feature_library.feature_models import derive_status_band
from BreakoutStrategy.feature_library.feature_store import FeatureStore
from BreakoutStrategy.feature_library.glm4v_backend import (
    GLM4V_MAX_IMAGES, GLM4VBackend,
)
from BreakoutStrategy.feature_library.inducer import batch_induce
from BreakoutStrategy.feature_library.librarian import Librarian
from BreakoutStrategy.feature_library.preprocess import preprocess_sample
from BreakoutStrategy.feature_library.sample_id import generate_sample_id
from BreakoutStrategy.dev.sample_picker_handler import WINDOW_BARS_BEFORE_BO

REPO_ROOT = Path(__file__).resolve().parents[1]


def _load_zhipuai_key() -> str:
    cfg_path = REPO_ROOT / "configs" / "api_keys.yaml"
    keys = yaml.safe_load(cfg_path.read_text())
    api_key = keys.get("zhipuai", "")
    if not api_key:
        raise RuntimeError("configs/api_keys.yaml 中 zhipuai key 为空")
    return api_key


def _load_pkl(ticker: str) -> pd.DataFrame:
    pkl_path = REPO_ROOT / "datasets" / "pkls" / f"{ticker}.pkl"
    if not pkl_path.exists():
        raise FileNotFoundError(f"未找到 {pkl_path}")
    return pd.read_pickle(pkl_path)


def _ensure_samples(
    ticker: str, count: int, backend: GLM4VBackend,
    *, min_bars_before_bo: int,
) -> list[str]:
    """获取 N 个 sample_id；缺失的调 preprocess_sample 补齐。

    min_bars_before_bo: 强制 BO 之前至少 N 根 K 线进入 sample window
    (broken_peak 紧挨 BO 时,自动 pk_index 仅 7 根 → GLM-4V 视觉 context 不足)。
    """
    df = _load_pkl(ticker)
    print(f"[Phase 1] {ticker} 数据范围 {df.index[0].date()} ~ {df.index[-1].date()}, {len(df)} bars")

    detector = BreakoutDetector(symbol=ticker)
    breakouts = detector.batch_add_bars(df)
    print(f"[Phase 1] 检测到 {len(breakouts)} 个 breakouts，取前 {count} 个")

    if len(breakouts) < count:
        raise RuntimeError(
            f"breakouts 数 {len(breakouts)} < 请求 {count}，换 ticker 或减小 count"
        )

    targets = breakouts[:count]
    sample_ids: list[str] = []

    for i, bo in enumerate(targets, start=1):
        bo_index = bo.current_index
        # pk_index 取最近被突破的 peak（与 Phase 0 entry script 一致语义）
        # broken_peaks 包含突破事件同时跨越的所有 peaks；取 index 最大者作为
        # consolidation 起点（聚焦最直接的盘整窗口，避免长 base 稀释信号）
        pk_index = (
            max(p.index for p in bo.broken_peaks)
            if bo.broken_peaks else bo_index - 1
        )
        # Smoke-test clamp:确保 GLM-4V 至少看到 min_bars_before_bo 根 K 线;
        # broken_peak 离 BO 远时自动选保留原值。
        pk_index = min(pk_index, max(0, bo_index - min_bars_before_bo))
        bo_date = df.index[bo_index]
        sid = generate_sample_id(ticker=ticker, bo_date=bo_date)

        if (
            paths.chart_png_path(sid).exists()
            and paths.meta_yaml_path(sid).exists()
            and paths.nl_description_path(sid).exists()
        ):
            print(f"[Phase 1] [{i}/{count}] sample {sid} 已存在，跳过 preprocess")
        else:
            print(f"[Phase 1] [{i}/{count}] preprocess sample {sid} ...")
            window_start = max(0, bo_index - WINDOW_BARS_BEFORE_BO)
            df_window = df.iloc[window_start: bo_index + 1]
            local_bo = bo_index - window_start
            local_pk = max(0, pk_index - window_start)
            preprocess_sample(
                ticker=ticker,
                bo_date=bo_date,
                df_window=df_window,
                bo_index=local_bo,
                pk_index=local_pk,
                picked_at=datetime.now(),
                backend=backend,
            )
        sample_ids.append(sid)

    return sample_ids


def _print_library_summary(store: FeatureStore, recently_affected: list) -> None:
    all_features = store.list_all()
    print(f"\n[Phase 1] features 库当前状态：{len(all_features)} features")
    for f in sorted(all_features, key=lambda x: x.id):
        signal = f.observations[-1].signal_after if f.observations else 0.0
        band = derive_status_band(signal, f.provenance)
        text_preview = f.text[:40] + ("..." if len(f.text) > 40 else "")
        print(
            f"  {f.id} [{band.value:13s}] α={f.alpha:.2f} β={f.beta:.2f} "
            f"P5={signal:.3f} obs={len(f.observations)} text=\"{text_preview}\""
        )

    if recently_affected:
        affected_ids = sorted({f.id for f in recently_affected})
        print(
            f"[Phase 1] 本轮新增 / 强化 features：{', '.join(affected_ids)}"
            f"（共 {len(affected_ids)} 条）"
        )
    print(f"[Phase 1] features 文件位置：{paths.FEATURES_DIR}")


def main() -> None:
    # ---------------- 参数声明区 ----------------
    ticker: str = "AAPL"                          # 目标股票
    sample_count: int = 5                         # 处理几个 breakout（≤ GLM4V_MAX_IMAGES）
    skip_preprocess: bool = False                 # True 时跳过 Phase 0 preprocess（假定 samples 已存在）
    inducer_max_batch: int = GLM4V_MAX_IMAGES     # GLM-4V-Flash 单次上限 5
    min_bars_before_bo: int = 30                  # 自动化 smoke 强制 BO 前最小 K 线数(dev UI 下不生效)
    # -------------------------------------------

    if sample_count > inducer_max_batch:
        raise ValueError(
            f"sample_count={sample_count} > inducer_max_batch={inducer_max_batch}"
        )

    print(f"[Phase 1] 加载 zhipuai API key...")
    api_key = _load_zhipuai_key()
    backend = GLM4VBackend(api_key=api_key)

    print(f"[Phase 1] 准备 {sample_count} 个 samples...")
    if skip_preprocess:
        # 复用现有 samples（不重新 preprocess）
        sample_ids = sorted(
            d.name for d in paths.SAMPLES_DIR.iterdir()
            if d.is_dir() and d.name.startswith(f"BO_{ticker.upper()}_")
        )[:sample_count]
        if len(sample_ids) < sample_count:
            raise RuntimeError(
                f"现有 samples 数 {len(sample_ids)} < 请求 {sample_count}，"
                f"取消 skip_preprocess 重跑"
            )
        print(f"[Phase 1] 复用现有 samples: {sample_ids}")
    else:
        sample_ids = _ensure_samples(
            ticker=ticker, count=sample_count, backend=backend,
            min_bars_before_bo=min_bars_before_bo,
        )

    print(f"\n[Phase 1] Inducer batch 归纳 {len(sample_ids)} 张样本...")
    candidates = batch_induce(
        sample_ids=sample_ids[:inducer_max_batch],
        backend=backend,
    )
    print(f"[Phase 1] Inducer 产出 {len(candidates)} 个 candidate features")
    for i, c in enumerate(candidates, start=1):
        text_preview = c.text[:60] + ('...' if len(c.text) > 60 else '')
        print(f"  [{i}] K={c.K}/N={c.N} text=\"{text_preview}\"")

    if not candidates:
        print("[Phase 1] 无 candidate，退出（features 库不变）")
        _print_library_summary(FeatureStore(), recently_affected=[])
        return

    print(f"\n[Phase 1] Librarian 累积 candidates 入库...")
    store = FeatureStore()
    librarian = Librarian(store=store)
    affected = []
    for c in candidates:
        feature = librarian.upsert_candidate(
            candidate=c,
            batch_sample_ids=sample_ids[:inducer_max_batch],
            source="ai_induction",
        )
        affected.append(feature)

    _print_library_summary(store, recently_affected=affected)


if __name__ == "__main__":
    main()
