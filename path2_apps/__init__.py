"""path2_apps:走势特异应用层(与 path2 平级,仅 import path2.*)。

每条具体走势放 path2_apps/<走势名>/ 子包:
  - detectors.py  走势特异 L2 Detector
  - pattern.py    顶层 matches(df, params) -> bool
  - params.py     frozen @dataclass Params
  - params.yaml   阈值配置
"""
