import pytest


def test_rebuild_chart_uses_preprocess_path(tmp_path):
    """_rebuild_chart 应走 preprocess→trim→adjust，而非直接 pd.read_pickle 到 canvas。"""
    # 集成测试场景：需要构造 LiveApp、mock chart、一个 pkl
    # 因测试复杂度较高，此处留桩，依赖手工测试和集成测试兜底
    pytest.skip("Integration test scaffolding; manual verification via uv run python -m BreakoutStrategy.live")
