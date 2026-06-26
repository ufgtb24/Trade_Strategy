"""per-role 诊断的 web 封装:调 path2.dag.diagnose → 序列化 RoleDiagnostics(§7.4)。"""
from __future__ import annotations

from path2.dag import diagnose as _diagnose
from path2_web.serialize import _clause_to_dict


def _attr_row(row) -> dict:
    return {
        "event_id": row.event.event_id,
        "start_idx": row.event.start_idx,
        "end_idx": row.event.end_idx,
        "clauses": {cid: _clause_to_dict(w) for cid, w in row.clauses.items()},
    }


def _rel_row(row) -> dict:
    return {
        "src": row.src,
        "kind": row.kind,
        "total_src": row.total_src,
        "ok_count": len(row.ok_src),
        "ok_src_ids": [e.event_id for e in row.ok_src],
    }


def serialize_diagnostics(diag) -> dict:
    """RoleDiagnostics → {roles:{node_id:{attr,rel}}, note}。"""
    return {
        "roles": {
            nid: {
                "attr": [_attr_row(r) for r in rd.attr],
                "rel": [_rel_row(r) for r in rd.rel],
            }
            for nid, rd in diag.roles.items()
        },
        "note": diag.note,
    }


def diagnose_symbol(spec, df, params, *, symbol: str, pattern_id: str) -> dict:
    """对单股跑 per-role 诊断并序列化。spec 须与 params 一致(where 在 build_pattern 时闭合 params)。"""
    diag = _diagnose(spec, df, params)
    out = serialize_diagnostics(diag)
    out["symbol"] = symbol
    out["pattern_id"] = pattern_id
    return out
