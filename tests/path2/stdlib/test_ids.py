from path2.stdlib._ids import default_event_id


def test_format_kind_start_end():
    assert default_event_id("chain", 3, 7) == "chain_3_7"


def test_single_bar():
    assert default_event_id("vc", 5, 5) == "vc_5_5"
