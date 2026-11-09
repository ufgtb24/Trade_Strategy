"""一个 pattern 的标注自上次以来改了什么(spec 6.14「会话每轮的固定动作」第 2 条)。

会话每轮开头定格(mapping 会话段的 snapshot.seen,见 path2_web/mapping.py),下一轮用
`read_annotations(cfg, as_of=seen)` 读出当时的状态,和现在的状态一起交给 pattern_changes 求差。
会话求差、后端的 GET /annotations/changes(以后页面的 `edited n`)都用这一个函数。纯计算,不读文件、不读行情。

比哪些东西
----------
- pattern 本身:定义等字段(名字是它的编号,不比);
- 这个 pattern 的样本:旧状态或新状态里 pattern 是它的样本——新增、删除、挪进、挪出,两边都在它下面时比各字段;
- 这些样本的成员框:旧状态里这些样本的成员 ∪ 新状态里这些样本的成员——新增、删除、各字段改动。
  只是成员关系变了(框本身没改)记在样本的 members 上,不记在框上。

每条变化 {kind, id, change}:
- kind:pattern / sample / box;id:pattern 名或样本、框编号;
- change:added(旧状态没有)/ removed(新状态没有)/ moved_in、moved_out(样本挪进、挪出这个 pattern,
  不再另报字段)/ 其余是改了的字段名,一个字段一条(样本如 judgment、members、note;框如 start、end、feature、
  attrs;pattern 如 definition、flags)。样本的 members_edited 随 members 一起变,不单列。
按 pattern、样本、框的次序排,同类按编号、再按 change 排。
"""
from __future__ import annotations

from typing import Mapping, Optional

_KIND_ORDER = {"pattern": 0, "sample": 1, "box": 2}
_SKIP = {
    "pattern": {"name"},
    "sample": {"id", "pattern", "members_edited"},
    "box": {"id"},
}


def _by_id(state: Mapping, key: str) -> dict:
    """状态里全部样本或框,按编号:{id: 对象(带上所在股票 symbol)}。"""
    return {o["id"]: {**o, "symbol": c["symbol"]} for c in state.get("charts", []) for o in c.get(key, [])}


def _field_changes(kind: str, oid: str, old: Mapping, new: Mapping) -> list[dict]:
    """同一对象新旧两份值里改了的字段,一个字段一条(缺的键当 None)。"""
    keys = sorted((set(old) | set(new)) - _SKIP[kind])
    return [{"kind": kind, "id": oid, "change": k} for k in keys if old.get(k) != new.get(k)]


def _added_removed(kind: str, oid: str, old: Optional[Mapping], new: Optional[Mapping]) -> list[dict]:
    """旧有新无 → removed;旧无新有 → added;两边都在 → 各字段改动;两边都没有 → 无。"""
    if old is None and new is None:
        return []
    if old is None:
        return [{"kind": kind, "id": oid, "change": "added"}]
    if new is None:
        return [{"kind": kind, "id": oid, "change": "removed"}]
    return _field_changes(kind, oid, old, new)


def pattern_changes(old_state: Mapping, new_state: Mapping, pattern: str) -> list[dict]:
    """pattern 在两份重放状态之间的变化:[{kind, id, change}](取值见模块说明)。

    参数:old_state、new_state 是 read_annotations(...)["state"](旧的通常带 as_of 读出);pattern 是标注里的
    pattern 名。只认这个 pattern 的样本、它们的成员框和 pattern 本身,别的 pattern、别的框不管。
    """
    out: list[dict] = []
    pats_old = {p["name"]: p for p in old_state.get("patterns", [])}
    pats_new = {p["name"]: p for p in new_state.get("patterns", [])}
    out += _added_removed("pattern", pattern, pats_old.get(pattern), pats_new.get(pattern))

    s_old, s_new = _by_id(old_state, "samples"), _by_id(new_state, "samples")
    mine_old = {i: s for i, s in s_old.items() if s["pattern"] == pattern}
    mine_new = {i: s for i, s in s_new.items() if s["pattern"] == pattern}
    for sid in mine_old.keys() | mine_new.keys():
        old, new = mine_old.get(sid), mine_new.get(sid)
        if old is not None and new is not None:
            out += _field_changes("sample", sid, old, new)
        elif old is None:   # 现在在这个 pattern 下:原来没有这个样本是新增,原来在别处是挪进
            out.append({"kind": "sample", "id": sid, "change": "moved_in" if sid in s_old else "added"})
        else:
            out.append({"kind": "sample", "id": sid, "change": "moved_out" if sid in s_new else "removed"})

    b_old, b_new = _by_id(old_state, "boxes"), _by_id(new_state, "boxes")
    box_ids = {b for s in mine_old.values() for b in s["members"]} | \
              {b for s in mine_new.values() for b in s["members"]}
    for bid in box_ids:
        out += _added_removed("box", bid, b_old.get(bid), b_new.get(bid))

    return sorted(out, key=lambda c: (_KIND_ORDER[c["kind"]], c["id"], c["change"]))
