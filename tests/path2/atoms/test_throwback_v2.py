from path2.atoms.throwback import (
    ThrowbackEvent, ThrowbackSegment, ThrowbackDetector,
)

def _seg(s, e, outcome="rise"):
    return ThrowbackSegment(start_idx=s, end_idx=e,
                            confirm_idx=s, anchor_bo_id="bo_1", outcome=outcome)

def test_container_model():
    segs = (_seg(10, 12), _seg(15, 18, "break"))
    c = ThrowbackEvent(start_idx=10, end_idx=18, confirm_idx=10,
                       segments=segs, anchor_bo_id="bo_1", outcome="break")
    assert c.child_slots() == {"segments": segs}
    # Task 6:容器不再 override 样本(删 override)——基类默认 = 容器整段 span(含段间
    # 间隙 13-14);间隙排除契约已移至 eval 路径协议(_resolve_end_events 逐段解析,
    # 见 path2/eval.py 与 path2_apps/bottom_burst/dag_spec.py::eval_meta)。
    assert list(c.sample_bar_indices()) == list(range(10, 19))
    assert c.confirm_idx == c.start_idx == 10

def test_detect_structure_real_data():
    import pickle
    from path2_apps.bottom_burst.dag_spec import load_params
    from path2_web.data import slice_window
    df = slice_window(pickle.load(open("datasets/pkls/AA.pkl", "rb")), "2024-09-19", "2026-03-08")
    # bb app tb 已换代 ThrowbackDetectorV4(2026-08-16),本测试自持 V2 参数
    # (旧三代不动,不再借 bb 的 throwback_kwargs)
    det = ThrowbackDetector(max_start_gap=30)
    # bo_stream: 用 BODetector 产流(多流化后走 run_bundle 取 bo 流)
    from path2.atoms.breakout import BODetector
    from path2.runner import run_bundle
    bos = list(run_bundle(BODetector(**load_params().bo_kwargs()), df)["bo"])
    out = list(det.detect(bos, df))
    for c in out:
        assert c.confirm_idx == c.start_idx == c.segments[0].start_idx   # 确认型
        assert c.end_idx == c.segments[-1].end_idx                        # 末段 exit
        assert all(s.confirm_idx == s.start_idx for s in c.segments)      # 段确认型
        # 实例流:同窗口多 bo 可多条(同 span 多实例,由物化标注按流序编号);
        # 容器对象彼此独立,不再合并
        assert len({id(c) for c in out}) == len(out)
