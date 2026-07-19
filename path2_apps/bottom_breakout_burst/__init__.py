"""bottom_breakout_burst — dag 纯声明走势包(理想架构)。

7 业务约束 -> 4 节点(down/side/bo+/tb) + 3 类型化边,全部在 dag_spec.build_pattern 中声明,
匹配交库引擎 path2.dag.engine.analyze。详见 dag_spec.py 与 docs/path2/example-bottom-breakout-burst.md。

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
