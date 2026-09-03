"""bb_v1 — V1 throwback 完整备份 app。

结构与 bottom_burst 完全相同,唯一区别:tb node 用 V1 ThrowbackDetectorV1
(throwback_v1.py),tb 参数 = 2026-08-25 首段状态机重写默认值。
用途:V1 时代可运行的完整 app 备份——可扫描、可与 V2 容器版(bottom_burst)对比。

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
