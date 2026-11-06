"""new_step — 阶跃后站上新平台(第二版):旧平台 → 一两根放量大阳线的阶跃 → 新平台,新平台上逐日买。

由看图标注里 pattern new_step 的定义与样本翻译而来。识别器 `plateau.PlateauDetector` 只吃 K 线,
在新平台上每天产一个截到当天的复合事件(子段 old / step / new / today),买点是它的 today 段;
零边,够不够格全由 `dag_spec.py` 里 plateau 的 where 判(拓扑与约束归宿表见 dag_spec 模块 docstring)。

公开 API:
  build_pattern(params) -> PatternSpec   # dag 声明工厂
  PATTERN_DAG          : PatternSpec      # 默认参数实例
  analyze(df, params)  -> AnalysisResult  # 库引擎求解
  has_hit(df, params)  -> bool            # 二值判定
  eval_meta(params) -> dict               # 评估元数据(end_node = plateau.today + head_buffer)
  Params / load_params() / DEFAULT_YAML_PATH
"""
from .dag_spec import build_pattern, PATTERN_DAG, analyze, has_hit, eval_meta
from .params import Params, load_params, DEFAULT_YAML_PATH

__all__ = ["build_pattern", "PATTERN_DAG", "analyze", "has_hit", "eval_meta",
           "Params", "load_params", "DEFAULT_YAML_PATH"]
