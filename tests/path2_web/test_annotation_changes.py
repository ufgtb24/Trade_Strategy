"""一个 pattern 自上次以来的变化(path2_web/annotation/changes.py 的 pattern_changes,spec 6.14 第 2 条)。

钉住的要求:
- 只认这个 pattern 的样本(新旧任一状态里在它下面)、这些样本新旧成员框的并集、pattern 本身;
- 样本新增 / 删除 / 挪进 / 挪出各记一条,两边都在时一个改了的字段一条(members_edited 不单列);
- 成员框新增 / 删除 / 起止、特征、属性改动;只是成员关系变了记在样本的 members 上;
- 别的 pattern 的样本、不是成员的框、没变的东西不出现;两份相同的状态没有变化。
状态直接手写成 read_annotations(...)["state"] 的形状。
"""
from __future__ import annotations

from path2_web.annotation.changes import pattern_changes


def _state(samples=(), boxes=(), patterns=()):
    """一只股票 AAA 上的样本与框;patterns 是 [{name, definition?}]。"""
    return {"features": [], "patterns": list(patterns),
            "charts": [{"symbol": "AAA", "boxes": list(boxes), "samples": list(samples)}]}


def _s(oid, pattern="p", judgment="pos", members=(), **extra):
    return {"id": oid, "date": "2025-06-10", "pattern": pattern, "judgment": judgment, "members": list(members),
            **extra}


def _b(oid, start="2025-06-01", end="2025-06-05", feature=None, **extra):
    return {"id": oid, "feature": feature, "start": start, "end": end, **extra}


def _ch(changes):
    return [(c["kind"], c["id"], c["change"]) for c in changes]


def test_same_state_no_changes():
    st = _state([_s("s-pc-1", members=["b-pc-2"])], [_b("b-pc-2")], [{"name": "p", "definition": "d"}])
    assert pattern_changes(st, st, "p") == []


def test_samples_added_removed_moved_and_edited():
    old = _state([_s("s-pc-1"), _s("s-pc-2"), _s("s-pc-3", pattern="q"), _s("s-pc-4"), _s("s-pc-5", note="a"),
                  _s("s-pc-6", pattern="q")])
    new = _state([_s("s-pc-1", judgment="neg"),                     # 改判
                  _s("s-pc-3"),                                       # 从 q 挪进
                  _s("s-pc-4", pattern=None),                         # 挪到 unsorted
                  _s("s-pc-5", note="b"),                             # 改 note
                  _s("s-pc-6", pattern="q", judgment="neg"),          # 别的 pattern 的改动不管
                  _s("s-pc-7")])                                      # 新增
    # s-pc-2 删掉了
    assert _ch(pattern_changes(old, new, "p")) == [
        ("sample", "s-pc-1", "judgment"), ("sample", "s-pc-2", "removed"), ("sample", "s-pc-3", "moved_in"),
        ("sample", "s-pc-4", "moved_out"), ("sample", "s-pc-5", "note"), ("sample", "s-pc-7", "added")]


def test_members_change_is_on_the_sample_and_members_edited_not_listed():
    old = _state([_s("s-pc-1", members=["b-pc-2"])], [_b("b-pc-2"), _b("b-pc-3")])
    new = _state([_s("s-pc-1", members=["b-pc-2", "b-pc-3"], members_edited=True)], [_b("b-pc-2"), _b("b-pc-3")])
    assert _ch(pattern_changes(old, new, "p")) == [("sample", "s-pc-1", "members")]


def test_member_boxes_old_or_new_are_compared():
    old = _state([_s("s-pc-1", members=["b-pc-2", "b-pc-3", "b-pc-4"]), _s("s-pc-9", pattern="q", members=["b-pc-8"])],
                 [_b("b-pc-2"), _b("b-pc-3"), _b("b-pc-4", attrs={"w-pc-1": True}), _b("b-pc-8"), _b("b-pc-7")])
    new = _state([_s("s-pc-1", members=["b-pc-2", "b-pc-4", "b-pc-5"]), _s("s-pc-9", pattern="q", members=["b-pc-8"])],
                 [_b("b-pc-2", start="2025-05-30", feature="w-pc-1"),            # 起点、特征改了
                  _b("b-pc-4", attrs={"w-pc-1": False}),                         # 属性改了
                  _b("b-pc-5"),                                                 # 新框
                  _b("b-pc-8", end="2025-06-06"),                               # 别的 pattern 的样本的框
                  _b("b-pc-7", end="2025-06-06")])                              # 不是成员的框
    # b-pc-3 连同成员关系一起删掉
    assert _ch(pattern_changes(old, new, "p")) == [
        ("sample", "s-pc-1", "members"),
        ("box", "b-pc-2", "feature"), ("box", "b-pc-2", "start"), ("box", "b-pc-3", "removed"),
        ("box", "b-pc-4", "attrs"), ("box", "b-pc-5", "added")]


def test_moved_out_sample_boxes_still_compared():
    """挪出去的样本,它旧的成员框照样比(新旧任一状态里在这个 pattern 下的样本都算)。"""
    old = _state([_s("s-pc-1", members=["b-pc-2"])], [_b("b-pc-2")])
    new = _state([_s("s-pc-1", pattern="q", members=["b-pc-2"])], [_b("b-pc-2", end="2025-06-04")])
    assert _ch(pattern_changes(old, new, "p")) == [("sample", "s-pc-1", "moved_out"), ("box", "b-pc-2", "end")]


def test_pattern_definition_and_existence():
    p1 = {"name": "p", "definition": "旧说法"}
    assert _ch(pattern_changes(_state(patterns=[p1]), _state(patterns=[{**p1, "definition": "新说法"}]), "p")) == \
        [("pattern", "p", "definition")]
    assert _ch(pattern_changes(_state(), _state(patterns=[p1]), "p")) == [("pattern", "p", "added")]
    assert _ch(pattern_changes(_state(patterns=[p1]), _state(), "p")) == [("pattern", "p", "removed")]
    other = {"name": "q", "definition": "x"}
    assert pattern_changes(_state(patterns=[other]), _state(patterns=[{**other, "definition": "y"}]), "p") == []
