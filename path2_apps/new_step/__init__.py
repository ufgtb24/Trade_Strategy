"""new_step — 阶跃后站上新平台、逐日判断企稳买(由第一批看图标注翻译而来,见 dag_spec.py)。

公开 API:
  build_pattern(params) -> PatternSpec   # dag 声明工厂
  PATTERN_DAG          : PatternSpec      # 默认参数实例
  analyze(df, params)  -> AnalysisResult  # 库引擎匹配
  matches(df, params)  -> bool            # 二值判定
  eval_meta(params) -> dict               # 评估元数据(end_node + head_buffer)
  Params / load_params() / DEFAULT_YAML_PATH
"""
from .dag_spec import build_pattern, PATTERN_DAG, analyze, matches, eval_meta
from .params import Params, load_params, DEFAULT_YAML_PATH

__all__ = ["build_pattern", "PATTERN_DAG", "analyze", "matches", "eval_meta",
           "Params", "load_params", "DEFAULT_YAML_PATH"]
