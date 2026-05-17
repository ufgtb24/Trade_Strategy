from path2.stdlib._ids import default_event_id, span_id


def test_format_kind_start_end():
    assert default_event_id("chain", 3, 7) == "chain_3_7"


def test_single_bar():
    assert default_event_id("vc", 5, 5) == "vc_5_5"


def test_span_id_single_point_collapses():
    assert span_id("vc", 5, 5) == "vc_5"


def test_span_id_interval_keeps_both():
    assert span_id("vc", 60, 67) == "vc_60_67"


def test_default_event_id_unchanged_pins_still_hold():
    # #3 内部桩语义未漂移:s==e 仍非塌缩
    assert default_event_id("vc", 5, 5) == "vc_5_5"
    assert default_event_id("chain", 3, 7) == "chain_3_7"


def test_span_id_is_publicly_exported():
    from path2 import span_id as span_id_public
    assert span_id_public is span_id
