"""共享 ParamsBase 形式协议:三 app 的 to_dict / from_dict / from_yaml 行为一致。

覆盖抽取后的不变式:
- 三 app 的 Params 都继承 ParamsBase(形式协议单一来源);
- to_dict → from_dict 往返相等(sandbox try_conplex_where 此前缺 to_dict/from_dict,
  抽取后获得该能力——正是 snapshot 消失 bug 的结构性修复);
- from_dict(strict=True) 对未知字段 raise;
- from_yaml 校验未知顶层 section(bo_only 此前不校验,抽取后统一升级)。
"""
import importlib

import pytest

APPS = ["bottom_burst", "bo_only", "try_conplex_where", "bb_v1", "bb_v3"]


def _params_cls(app):
    return importlib.import_module(f"path2_apps.{app}.params").Params


@pytest.mark.parametrize("app", APPS)
def test_all_apps_subclass_params_base(app):
    from path2_apps._params_base import ParamsBase
    assert issubclass(_params_cls(app), ParamsBase)


@pytest.mark.parametrize("app", APPS)
def test_to_dict_from_dict_roundtrip(app):
    P = _params_cls(app)
    p = P.default()
    assert P.from_dict(p.to_dict()) == p


@pytest.mark.parametrize("app", APPS)
def test_from_dict_strict_rejects_unknown_field(app):
    P = _params_cls(app)
    d = P.default().to_dict()
    d["bo"]["__nope__"] = 1
    with pytest.raises(ValueError, match="__nope__"):
        P.from_dict(d, strict=True)


@pytest.mark.parametrize("app", APPS)
def test_from_yaml_rejects_unknown_top_section(app, tmp_path):
    P = _params_cls(app)
    y = tmp_path / "p.yaml"
    y.write_text("__ghost_section__: {x: 1}\n", encoding="utf-8")
    with pytest.raises(ValueError, match="__ghost_section__"):
        P.from_yaml(y)
