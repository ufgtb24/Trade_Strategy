"""Params.to_dict / from_dict 往返与宽严校验(bottom_breakout_burst + bo_only)。"""
import pytest

from path2_apps.bottom_breakout_burst.params import Params as BbbParams
from path2_apps.bo_only.params import Params as BoOnlyParams


class TestBbbToDict:
    def test_roundtrip_default(self):
        p = BbbParams.default()
        d = p.to_dict()
        assert d["bo"]["total_window"] == 10
        assert d["burst"]["gap_max"] == 5
        assert BbbParams.from_dict(d) == p

    def test_roundtrip_modified(self):
        p = BbbParams.default()
        d = p.to_dict()
        d["bo"]["total_window"] = 15
        p2 = BbbParams.from_dict(d)
        assert p2.bo.total_window == 15
        assert p2.tb == p.tb  # 未动 section 不变

    def test_from_dict_strict_raises_unknown_field(self):
        d = BbbParams.default().to_dict()
        d["bo"]["nonexistent_field"] = 1
        with pytest.raises(ValueError, match="nonexistent_field"):
            BbbParams.from_dict(d, strict=True)

    def test_from_dict_lenient_drops_unknown(self):
        d = BbbParams.default().to_dict()
        d["bo"]["nonexistent_field"] = 1
        d["ghost_section"] = {"x": 1}
        p = BbbParams.from_dict(d, strict=False)   # 不 raise
        assert p.bo.total_window == 10

    def test_from_dict_missing_fields_use_default(self):
        p = BbbParams.from_dict({"bo": {"total_window": 20}})
        assert p.bo.total_window == 20
        assert p.bo.min_side_bars == 2          # default 兜底
        assert p.burst.gap_max == 5             # 整 section 缺失兜底


class TestBoOnlyToDict:
    def test_roundtrip(self):
        p = BoOnlyParams.default()
        d = p.to_dict()
        assert d["bo"]["total_window"] == 10
        d["bo"]["total_window"] = 25
        assert BoOnlyParams.from_dict(d).bo.total_window == 25

    def test_strict_raises(self):
        with pytest.raises(ValueError):
            BoOnlyParams.from_dict({"bo": {"bogus": 1}}, strict=True)

    def test_lenient_drops(self):
        p = BoOnlyParams.from_dict({"bo": {"bogus": 1}}, strict=False)
        assert p.bo.total_window == 10
