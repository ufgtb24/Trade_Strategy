"""try_complex_where — 嵌套复杂 where 的试验田(sandbox)。

拓扑照抄 bottom_burst(bo / burst / tb + 1 条边),但 pattern_id 独立为
"try_complex_where",与主 app 并存互不干扰。**唯一用途是随便改 burst 的 where**,
验证 W.any / W.all / W.not_ / W.child / W.children 的嵌套组合怎么判、UI 怎么显示。

改哪里、有哪些字段可用、组合子怎么写 —— 全在 dag_spec.py 的模块 docstring 里。

公开 API(与主 app 同构;path2_web discovery 要求 PATTERN_DAG + analyze + eval_meta):
  build_pattern(params) -> PatternSpec   # dag 声明工厂
  PATTERN_DAG          : PatternSpec      # 默认参数实例(discovery 发现入口)
  analyze(df, params)  -> AnalysisResult  # 库引擎匹配
  matches(df, params)  -> bool            # 二值判定
  eval_meta(params) -> dict               # end_node + head_buffer(铁律协议)
  Params                                  # schema 层(默认值 = yaml 缺字段时的兜底)
  load_params() -> Params                 # 读【本包自己的】params.yaml(与主 app 独立)
  DEFAULT_YAML_PATH                       # 本包 params.yaml 绝对路径
"""
from .dag_spec import build_pattern, PATTERN_DAG, analyze, matches, eval_meta
from .params import Params, load_params, DEFAULT_YAML_PATH

__all__ = ["build_pattern", "PATTERN_DAG", "analyze", "matches", "eval_meta",
           "Params", "load_params", "DEFAULT_YAML_PATH"]
