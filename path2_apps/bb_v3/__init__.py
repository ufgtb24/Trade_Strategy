# path2_apps/bb_v3
"""bb_v3:V3 throwback(re-entry 多段)承载 app。

结构与 bb_v1 完全相同,唯一区别:tb node 用 V3 ThrowbackDetectorV3
(throwback_v3.py,一 bo 多段 re-entry),默认参数 = bb_v1
调参版 + max_start_gap=15(re-entry 预算空间)。

公开 API:
  build_pattern(params) -> PatternSpec   # dag 声明工厂
  PATTERN_DAG          : PatternSpec      # 默认参数实例(to_topology / 发现入口;= build_pattern(Params.default()))
  analyze(df, params)  -> AnalysisResult  # 库引擎匹配
  matches(df, params)  -> bool            # 二值判定
  eval_meta(params) -> dict               # 评估元数据(end_node + head_buffer,path2_web 可选协议)
  Params                                  # schema 层 (字段名/类型,默认值是 yaml 兜底 + CLI fixture 默认)
  load_params() -> Params                 # web 入口统一加载点(读 params.yaml,SSoT,热加载)
  DEFAULT_YAML_PATH                       # params.yaml 绝对路径
"""
from .dag_spec import build_pattern, PATTERN_DAG, analyze, matches, eval_meta
from .params import Params, load_params, DEFAULT_YAML_PATH

__all__ = ["build_pattern", "PATTERN_DAG", "analyze", "matches", "eval_meta",
           "Params", "load_params", "DEFAULT_YAML_PATH"]
