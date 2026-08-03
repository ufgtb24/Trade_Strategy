"""ParamsBase.from_yaml 的报错文案必须指向实际被读的文件。

多参数文件上线后(web 扫描面板可选 exp_*.yaml),报错若仍硬编码 "params.yaml"
前缀,用户会去改错文件。既有测试只 match 字段名,不锚前缀,故此处新增。
"""
import os
import tempfile

import pytest

from path2_apps.bo_only.params import Params


def _write_tmp_yaml(text: str, name: str) -> str:
    d = tempfile.mkdtemp()
    path = os.path.join(d, name)
    with open(path, "w") as f:
        f.write(text)
    return path


def test_unknown_section_msg_names_actual_file():
    path = _write_tmp_yaml("bo:\n  total_window: 10\ntypoooo:\n  x: 1\n", "exp_wide.yaml")
    try:
        with pytest.raises(ValueError) as ei:
            Params.from_yaml(path)
        msg = str(ei.value)
        assert "exp_wide.yaml" in msg
        assert not msg.startswith("params.yaml")
    finally:
        os.unlink(path)


def test_unknown_field_msg_names_actual_file():
    path = _write_tmp_yaml("bo:\n  total_windooow: 10\n", "exp_wide.yaml")
    try:
        with pytest.raises(ValueError) as ei:
            Params.from_yaml(path)
        msg = str(ei.value)
        assert "exp_wide.yaml" in msg
        assert "total_windooow" in msg
        assert not msg.startswith("params.yaml")
    finally:
        os.unlink(path)


def test_scalar_root_raises_value_error_names_actual_file():
    """根是标量(如裸数字)→ 此前 set(data) 抛 TypeError 逃出 from_yaml,变成裸 500;
    改为源头 isinstance 守卫后收窄为 ValueError,与其余结构错误同一条 400 路径。"""
    path = _write_tmp_yaml("5\n", "exp_wide.yaml")
    try:
        with pytest.raises(ValueError) as ei:
            Params.from_yaml(path)
        msg = str(ei.value)
        assert "exp_wide.yaml" in msg
        assert "根必须是映射" in msg
    finally:
        os.unlink(path)


def test_scalar_section_raises_value_error_names_actual_file():
    """section 值是标量(如 bo: 5)→ 此前 set(sect_data) 抛 TypeError;同上收窄为 ValueError。"""
    path = _write_tmp_yaml("bo: 5\n", "exp_wide.yaml")
    try:
        with pytest.raises(ValueError) as ei:
            Params.from_yaml(path)
        msg = str(ei.value)
        assert "exp_wide.yaml" in msg
        assert "必须是映射" in msg
    finally:
        os.unlink(path)
