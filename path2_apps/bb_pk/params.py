# bb_pk 参数 — 完全复用 bb_v1 的 Params schema(含 BoParams.bear 字段,Task 3 已加)。
# bb_pk 拓扑与 bb_v1 同构,仅 bo 多产一条 pk 显示流;参数零改动。
from pathlib import Path
from path2_apps.bb_v1.params import Params

DEFAULT_YAML_PATH = Path(__file__).parent / "params.yaml"


def load_params() -> Params:
    """web 统一加载点:读本包 yaml 作 Params(参照 bb_v1.load_params 签名)。
    每次调用重新读 yaml 文件,热加载。"""
    return Params.from_yaml(DEFAULT_YAML_PATH)
