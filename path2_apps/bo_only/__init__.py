"""bo_only — 单 BODetector 节点的 dag 走势包(锚 pattern,服务多 pattern UI 找漏检场景)。

公开 API:
  build_pattern(params) -> PatternSpec
  PATTERN_DAG          : PatternSpec
  analyze(df, params)  -> AnalysisResult
  matches(df, params)  -> bool
  eval_meta(params) -> dict   # end_role=bo, head_buffer=max(vol_baseline_period, total_window)
  Params
  load_params() -> Params
  DEFAULT_YAML_PATH
"""
from .dag_spec import build_pattern, PATTERN_DAG, analyze, matches, eval_meta
from .params import Params, load_params, DEFAULT_YAML_PATH

__all__ = ["build_pattern", "PATTERN_DAG", "analyze", "matches", "eval_meta",
           "Params", "load_params", "DEFAULT_YAML_PATH"]
