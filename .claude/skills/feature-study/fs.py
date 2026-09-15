# -*- coding: utf-8 -*-
"""feature-study 调用面:状态 → 预注册 → 取数判定 → 关闭登记 → 对账。

    status(app)                     只读:每条轴的状态、未关闭的登记条目、待对账、需复核、验证数据与分辨力、优势检查结论
    plan(app, window, extra=None)   冻结闸子族(gate_family)+ 不读标签的功效预检,写 plan.json(轮外单独研究可同时写 preregister)
    run(plan_path)                  训练窗读 tune-gates 长表 / 确认窗按冻结清单补检 → 闸式判定(同批特征一起做多重比较)→ verdicts
    close(plan_path, verdicts)      写 verify + 登记簿关闭行 + 已知信号增删提示 + 三栏输出
    reconcile(app, fc, ...)         对账:第二步集合拆解 + 计数 + 按股自助 CI,第三步可做与否;写 reconcile

观测单位 = 买点事件(同一段买点只计一次);标签 = 首次穿越率 up/(up+down+both);估计量内部一律是比例。
账本经 tune-gates 的 ledger.py 读写(环境变量 TUNE_LEDGER_DIR 可改目录);登记簿路径可注入。

与账本的约定(写入方):plan 在轮外写 preregister(轮内只产闸子族,交执行端合并进同一份清单);
close 写 verify(确认窗上的 verify 在 data 里带 manifest_hash 与 confirm_window,守卫据此判断这一段检没检过);
reconcile 写 reconcile;status、run 不写账本。产物先写完、记录最后写。
"""
from __future__ import annotations

import contextlib
import dataclasses
import importlib
import io
import json
import math
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

sys.path.insert(0, str(Path(__file__).resolve().parent))

import extract  # noqa: E402
import run_battery as RB  # noqa: E402

REPO = extract.REPO
ledger = RB.load_tune_gates("ledger")
REGISTRY = REPO / "docs" / "feature_candidates.md"
OUT_ROOT = REPO / "outputs" / "feature_study"
LABEL_METRIC = "first_passage"
BUCKETS = ("确实有用", "没用删了不亏", "判不了")
BUCKET_WORDS = {"确实有用": "确实有用", "没用删了不亏": "没用，删了也不亏", "判不了": "判不了"}


# ── 可替换的取数口(单测用 monkeypatch 换成假树) ──

def _adapter(app: str):
    return extract.load_adapter(app)


def _classification(app: str, window: str) -> dict:
    return RB.load_tune_gates("study_io").load_classification(app, window)


def _run_meta(app: str, window: str) -> dict:
    return RB.load_tune_gates("study_io").load_run_meta(extract.longtable_dir(app, window))


def _formal(cl: dict) -> dict:
    return extract.formal_params(cl)


def _fingerprints(app: str, window: str) -> dict:
    return ledger.current_fingerprints(app, window)


def _calendar():
    return RB.load_tune_gates("holdout").default_calendar()


def resolve_delta(app: str) -> float:
    """最小关心改进 δ(比例),与调参执行端同一个取法(tune-gates 的 tune.resolve_delta):该 app 账本里最近一条
    δ 裁定(取值单位是点);没有裁定时取 tune-gates Settings 的 min_effect_pt。"""
    return RB.load_tune_gates("tune").resolve_delta(app)


def _event_fields(cl: dict, param: str) -> set:
    """该参数所影响的 detector 所在模块里,全部事件类(path2.core.Event 的 dataclass 子类)的字段名。"""
    from path2.core import Event
    S = RB.load_tune_gates("study_io")
    mod = importlib.import_module(cl["app_module"])
    spec = mod.build_pattern(mod.Params.from_yaml(S.app_dir(mod) / cl["base_yaml"]))
    nodes = set(cl["detector_nodes"].get(param, []))
    fields = set()
    for n in spec.nodes:
        if n.node_id in nodes and n.detector is not None:
            for obj in vars(sys.modules[type(n.detector).__module__]).values():
                if isinstance(obj, type) and issubclass(obj, Event) and dataclasses.is_dataclass(obj):
                    fields |= {f.name for f in dataclasses.fields(obj)}
    return fields


# ── 小工具 ──

def _jsonable(obj):
    """转成标准 JSON 能写的值:numpy 标量 → Python 数,NaN / inf → None,日期 → 字符串,字典键 → 字符串。"""
    if isinstance(obj, dict):
        return {k if isinstance(k, str) else ("None" if k is None else f"{k:g}" if isinstance(k, float) else str(k)):
                _jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_jsonable(v) for v in obj]
    if isinstance(obj, (bool, np.bool_)):
        return bool(obj)
    if isinstance(obj, (int, np.integer)):
        return int(obj)
    if isinstance(obj, (float, np.floating)):
        return float(obj) if np.isfinite(obj) else None
    if isinstance(obj, (pd.Timestamp, np.datetime64, datetime)):
        return str(pd.Timestamp(obj).date())
    return obj


def _rel(path) -> str:
    p = Path(path).resolve()
    try:
        return str(p.relative_to(REPO))
    except ValueError:
        return str(p)


def _window(meta: dict) -> dict:
    return {"start": str(meta["start_date"]), "end": str(meta["end_date"])}


def _label(meta: dict) -> dict:
    return {"metric": LABEL_METRIC, "formula": "up/(up+down+both)", "k": meta["first_passage_k"],
            "horizon": meta["label_horizon"], "unit": "买点事件", "weight": "买点 bar"}


def _pt(x) -> str:
    return "—" if x is None or not np.isfinite(x) else f"{x * 100:+.2f}"


# ── 登记簿与账本读数 ──

_FC_HEAD = re.compile(r"^### (FC-\d+) · (.+)$")
_FC_CLOSED = re.compile(r"^- (FC-\d+) · ")


def registry_state(path) -> dict:
    """登记簿:{"pending": {编号: 名称}(待验证段 ### 标题), "closed": 已关闭段出现过的编号, "open": 未关闭编号}。"""
    pending, closed, section = {}, set(), None
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if line.startswith("## "):
            section = line[3:].strip()
        elif section == "待验证" and (m := _FC_HEAD.match(line)):
            pending[m[1]] = m[2].strip()
        elif section == "已关闭" and (m := _FC_CLOSED.match(line)):
            closed.add(m[1])
    return {"pending": pending, "closed": closed, "open": sorted(set(pending) - closed)}


def _known_signal_review(recs: list, adapter) -> list:
    """已知信号的判定记录:标签口径不是首次穿越、或找不到带标签口径的判定记录 → 待复核。"""
    out = []
    for s in adapter.KNOWN_SIGNALS:
        axis = f"feature:{s}"
        judged = [r for r in recs if r["kind"] == "verify" and axis in r["axes"]
                  and isinstance(r["data"].get("label"), dict) and r["data"]["label"].get("metric")]
        if not judged:
            out.append({"signal": s, "reason": "找不到带标签口径的判定记录"})
        elif judged[-1]["data"]["label"]["metric"] != LABEL_METRIC:
            out.append({"signal": s, "reason": f"最近一次判定的标签口径是 {judged[-1]['data']['label']['metric']},不是首次穿越"})
    return out


def _pending_reconcile(recs: list, adapter, open_fc: list) -> list:
    """定案挑选落在的轴(参数本身 + PARAM_FEATURES 声明的对应特征)上有未关闭的登记条目,且定案之后没有对账记录。"""
    out = []
    for dec in (r for r in recs if r["kind"] == "decide"):
        keys = set(dec["data"]["params"]) | set(dec["data"]["selects_on"])
        axes = keys | {f"feature:{adapter.PARAM_FEATURES[k]}" for k in keys if k in adapter.PARAM_FEATURES}
        related = sorted({fc for r in recs if r["kind"] == "discover" and set(r["axes"]) & axes
                          for fc in r["fc"] if fc in open_fc})
        done = any(r["kind"] == "reconcile" and r["ts"] >= dec["ts"] and set(r["axes"]) & keys for r in recs)
        if related and not done:
            out.append({"params": sorted(keys), "fc": related, "decided": dec["ts"]})
    return out


def _needs_recheck(recs: list, formal: dict | None) -> list:
    """每个参数最近一次定案的背景快照(depends_on)与现在的正式参数不同 → 需复核。"""
    if formal is None:
        return []
    latest = {}
    for r in recs:
        if r["kind"] == "decide":
            for k in r["data"]["params"]:
                latest[k] = r
    out = []
    for k, r in latest.items():
        changed = {p: {"decided": v, "now": formal.get(p)} for p, v in r["data"]["depends_on"].items()
                   if formal.get(p) != v}
        if changed:
            out.append({"param": k, "decided": r["ts"], "changed": changed})
    return out


def _source_changed_since(ts: str, files: list) -> bool:
    out = subprocess.run(["git", "log", f"--since={ts}", "--format=%H", "--", *files],
                         cwd=REPO, capture_output=True, text=True, check=True).stdout
    return bool(out.strip())


def _axis_state(axis: str, recs: list, cur: dict | None, cur_err: str, cl: dict | None) -> dict:
    """一条轴的状态:有效 / 进行中 / 已失效 / 未开始,附原因与最近一次判定。"""
    verifies = [(i, r) for i, r in enumerate(recs) if r["kind"] == "verify" and axis in r["axes"]]
    pre = [i for i, r in enumerate(recs) if r["kind"] == "preregister" and axis in r["axes"]]
    last_i, last = verifies[-1] if verifies else (-1, None)
    brief = None if last is None else {"ts": last["ts"], "verdict": last["data"].get("verdict"),
                                       "bucket": last["data"].get("bucket")}
    if pre and pre[-1] > last_i:          # 账本只追加:行序即时间序(同一秒内的两条也分得清先后)
        return {"state": "进行中", "reason": "已预注册,还没关闭", "last_verify": brief}
    if last is None:
        return {"state": "未开始", "reason": "", "last_verify": None}
    if last["source_fingerprint"] and last["ruler_fingerprint"]:
        if cur is None:
            return {"state": "有效", "reason": f"当前指纹算不出,未核对({cur_err})", "last_verify": brief}
        changed = [w for w, k in (("源码", "source_fingerprint"), ("尺子", "ruler_fingerprint")) if last[k] != cur[k]]
        if changed:
            return {"state": "已失效", "reason": f"{'、'.join(changed)}变了,判定作废,需重验", "last_verify": brief}
        if last["base_fingerprint"] != cur["base_fingerprint"]:
            return {"state": "有效", "reason": "正式参数变了,需在新工作点上补算", "last_verify": brief}
        return {"state": "有效", "reason": "", "last_verify": brief}
    files = (cl or {}).get("fingerprints", {}).get("source", {}).get("files")
    if not files:
        return {"state": "有效", "reason": "判定记录没有指纹,也拿不到 detector 源码清单,未核对", "last_verify": brief}
    if _source_changed_since(last["ts"], files):
        return {"state": "已失效", "reason": "判定之后有提交改过 detector 源码", "last_verify": brief}
    return {"state": "有效", "reason": "判定记录没有指纹,按提交历史核对未发现源码改动", "last_verify": brief}


# ── status ──

def status(app: str, *, window: str = "main", registry=None) -> dict:
    """只读状态报告(不写任何文件)。

    返回 {"axes": {轴: 状态}, "open_fc", "known_signal_review", "pending_reconcile", "needs_recheck",
         "windows", "resolution", "edge", "text"}:
      - 轴状态按判定记录的指纹核对:源码或尺子变了 → 已失效;正式参数变了 → 有效但需补算;有预注册未关闭 → 进行中;
        没有指纹的历史判定 → 查判定之后有没有提交改过 detector 源码。
      - 已知信号的判定记录标签口径不是首次穿越、或找不到带口径的判定记录 → 待复核。
      - 定案背景快照与现在的正式参数不同 → 需复核。
    """
    recs = ledger.read(app)
    adapter = _adapter(app)
    reg = registry_state(REGISTRY if registry is None else registry)
    try:
        cl = _classification(app, window)
    except (Exception, SystemExit):
        cl = None
    try:
        cur, cur_err = _fingerprints(app, window), ""
    except (Exception, SystemExit) as e:
        cur, cur_err = None, str(e)
    try:
        formal = _formal(cl) if cl is not None else None
    except Exception:
        formal = None

    axes = set(adapter.PARAM_FEATURES) | {f"feature:{s}" for s in adapter.KNOWN_SIGNALS}
    for r in recs:
        axes |= set(r["axes"])
    axis_states = {a: _axis_state(a, recs, cur, cur_err, cl) for a in sorted(axes)}

    op = ledger.latest(app, "open")
    windows = None
    if op is not None:
        opened = {r["data"]["confirm_window"] for r in recs if r["kind"] == "extrapolate"}
        windows = {"train": op["data"]["train"],
                   "confirm": {n: {**op["data"]["confirm"][n], "opened": n in opened} for n in ("backward", "forward")}}
    edge = ledger.latest(app, "edge")
    resolution = (edge["data"].get("resolution") if edge else None)
    out = {
        "app": app,
        "axes": axis_states,
        "open_fc": reg["open"],
        "known_signal_review": _known_signal_review(recs, adapter),
        "pending_reconcile": _pending_reconcile(recs, adapter, reg["open"]),
        "needs_recheck": _needs_recheck(recs, formal),
        "windows": windows,
        "resolution": None if resolution is None else {
            "x_single": resolution.get("x_single"), "x_screen": resolution.get("x_screen"),
            "r_bar_source": resolution.get("r_bar_source")},
        "edge": None if edge is None else {"ts": edge["ts"], "verdicts": edge["data"].get("verdicts"),
                                           "source_note": edge["data"].get("source_note")},
    }
    out["text"] = _status_text(out)
    return out


def _status_text(st: dict) -> str:
    counts = {}
    for a in st["axes"].values():
        counts[a["state"]] = counts.get(a["state"], 0) + 1
    lines = [f"「{st['app']}」学习端状态"]
    lines.append("轴:" + ",".join(f"{k} {v} 条" for k, v in counts.items()) if counts else "轴:还没有任何记录")
    for name, a in st["axes"].items():
        if a["state"] == "已失效" or a["reason"]:
            lines.append(f"  · {name}:{a['state']}{'(' + a['reason'] + ')' if a['reason'] else ''}")
    lines.append(f"登记簿里还没关闭的条目:{'、'.join(st['open_fc']) or '无'}")
    for k in st["known_signal_review"]:
        lines.append(f"已知信号「{k['signal']}」待复核:{k['reason']}")
    for p in st["pending_reconcile"]:
        lines.append(f"待对账:{'、'.join(p['params'])} 的定案与 {'、'.join(p['fc'])} 落在同一条轴上")
    for n in st["needs_recheck"]:
        diff = ",".join(f"{k} {v['decided']}→{v['now']}" for k, v in n["changed"].items())
        lines.append(f"需复核:{n['param']} 的定案是在旧背景下做的({diff})")
    if st["windows"]:
        for n, w in st["windows"]["confirm"].items():
            word = "训练期之前" if n == "backward" else "训练期之后"
            lines.append(f"{word}留出的验证数据 {w['start']}..{w['end']}:{'已打开过' if w['opened'] else '还没用过'}")
    else:
        lines.append("还没做开局核对,没有划出验证数据")
    if st["resolution"] and st["resolution"].get("x_single") is not None:
        lines.append(f"单个预写改动能分辨的最小效果约 {st['resolution']['x_single'] * 100:.1f} 个点(估计)")
    if st["edge"]:
        lines.append(f"优势检查({st['edge']['ts']}):{st['edge']['verdicts']}"
                     + (f";{st['edge']['source_note']}" if st["edge"]["source_note"] else ""))
    else:
        lines.append("还没做优势检查")
    return "\n".join(lines)


# ── plan ──

def _gate_cuts(axis: dict, working) -> list:
    """预注册切点:工作点现值 + 档位表里除机制下限(最松档)以外的档,≤4 个,按松→紧排。"""
    floor = axis["levels"][0]
    first = [working] if working is not None and working != floor else []
    others = [lv for lv in axis["levels"][1:] if lv is not None and lv != working]
    return RB._gate_spec((axis["column"], axis["op"], (first + others)[:RB.MAX_CUTS]))[2]


def _single_axis_fc(recs: list, param: str) -> list:
    return sorted({fc for r in recs if r["kind"] == "discover" and r["axes"] == [param] for fc in r["fc"]})


def _read_label_free(app: str, window: str, cl: dict, combo: dict, columns: list) -> tuple[pd.DataFrame, list, list]:
    """不读任何标签列地读长表(功效预检用):返回 (行, 买点事件键列, 买点 node 的 start/end 列)。"""
    S = RB.load_tune_gates("study_io")
    shards = sorted(extract.longtable_dir(app, window).glob("part-*.parquet"))
    if not shards:
        raise SystemExit(f"窗口 {window} 还没有长表:先扫描")
    names = pq.ParquetFile(shards[0]).schema_arrow.names
    seg = S.segment_cols(cl, names)
    end = cl["end_node"]
    span = [f"{end}.start", f"{end}.end"]
    if "." in end or not set(span) <= set(names):
        raise ValueError("长表里没有买点 node 的起止列,数不出每个买点事件有几根买点 bar,做不了不读标签的功效预检")
    cols = list(dict.fromkeys(["symbol", *combo, *seg, *span, *columns]))
    parts = [pq.read_table(sp, columns=cols, filters=[(k, "==", v) for k, v in combo.items()]).to_pandas()
             for sp in shards]
    df = pd.concat([p.assign(symbol=p["symbol"].astype(str)) for p in parts if len(p)], ignore_index=True)
    return df, seg, span


def _power_precheck(rows: pd.DataFrame, seg: list, span: list, gates: list, *, deff: float, s_dec: float,
                    delta: float) -> None:
    """不读标签的功效预检(就地写进每道闸的 "power"):

    池 = 其余闸按工作点过滤后的买点事件;买点 bar 数 = 买点 node 的 end − start + 1;
    D_池 ≈ s_dec × 池内买点 bar 数;r = 切点保留的买点 bar 占比;
    SE ≈ √(p0(1−p0)·deff/D_池·(1−r)/r),MDE = 2.8·SE;MDE ≤ δ 的切点进族。deff、s_dec 取优势检查实测值。
    """
    key = rows.groupby(["symbol", *[c for c in seg if c != "symbol"]], sort=False, observed=True).ngroup().to_numpy()
    bars = pd.Series((rows[span[1]] - rows[span[0]] + 1).to_numpy(float)).groupby(key).first().to_numpy()
    fields = {g["column"]: pd.to_numeric(rows[g["column"]], errors="coerce").to_numpy(float) for g in gates}

    def any_ev(mask):
        out = np.zeros(len(bars), dtype=bool)
        out[key[mask]] = True
        return out

    for g in gates:
        other = np.ones(len(rows), dtype=bool)
        for h in gates:
            if h is not g and h["working"] is not None:
                other &= RB._cmp(fields[h["column"]], h["op"], h["working"])
        b_pool = bars[any_ev(other)].sum()
        g["power"] = []
        for t in g["cuts"]:
            r = bars[any_ev(other & RB._cmp(fields[g["column"]], g["op"], t))].sum() / b_pool if b_pool > 0 else np.nan
            mde = (RB.budget.x_single(math.sqrt(RB.P0 * (1 - RB.P0) * deff / (s_dec * b_pool) * (1 - r) / r))
                   if 0 < r < 1 else float("nan"))
            g["power"].append({"cut": t, "keep_ratio": float(r), "mde": float(mde),
                               "in_family": bool(np.isfinite(mde) and mde <= delta)})
        g["expected"] = "进族" if any(p["in_family"] for p in g["power"]) else "判不了(样本不够)"


def default_plan_dir(app: str, window: str, gate_family: dict) -> Path:
    """plan.json 的缺省目录:outputs/feature_study/<app>/<window>/<闸子族内容哈希前 12 位>/(同一份清单落同一目录)。"""
    return OUT_ROOT / app / window / RB.load_tune_gates("study_io").canonical_hash(gate_family)[:12]


def plan(app: str, window: str, extra=None, *, config: dict | None = None, delta: float | None = None,
         in_round: bool = True, out_dir=None, registry=None) -> dict:
    """冻结闸子族,读标签之前做完功效预检;写 plan.json,返回 gate_family 对象。

    参数:
        window: 做功效预检的训练窗口(tune-gates 窗口名)。
        extra: 用户随开工确认加的想法,列表元素二选一:
            {"param": 闸参数键, "cuts": [...](可省,缺省按档位表), "fc": [...](可省)} —— 加一道候选闸或改在役闸的切点;
            {"features": [...], "binaries": [...], "csv": dataset.csv 路径, "fc": [...]} —— 同批验证的连续 / 二元特征。
        config: 候选配置 K 相对正式参数的改动 {参数键: 值};缺省 = 正式参数本身。
        delta: 最小关心改进(比例);None = resolve_delta(app)(账本里的 δ 裁定,没有则取 tune-gates Settings)。
        in_round: True = 调参轮内,返回的 gate_family 由执行端原样并进同一份验证清单(manifest["gate_family"]),不写账本;
            False = 轮外单独研究,另写一条 preregister(manifest = {"gate_family": ...})。
        out_dir: plan.json 所在目录;缺省 default_plan_dir。

    gate_family 结构(标准 JSON):
        app / window / window_dates:app、做功效预检的训练窗口名及其买点区间
        label:标签口径 {metric: "first_passage", formula: "up/(up+down+both)", k, horizon, unit: "买点事件", weight: "买点 bar"}
        population:条件总体 = 候选配置 K —— {"rule", "combo": {检测参数键: 值}, "working": {闸参数键: 值}};
            判一道闸时只放开这道闸,其余检测参数与闸都取 K 的值
        gates:[{"param": 参数键, "column": 长表闸字段列 node.field, "op": 运算符, "cuts": 切点(≤4 个,松→紧,读标签前冻结),
                "working": 这道闸在 K 里的取值(None = 不在 K 里的候选闸), "fc": 关联登记条目, "source": "在役闸"|"候选",
                "power": [{"cut", "keep_ratio", "mde", "in_family"}], "expected": "进族"|"判不了(样本不够)"}, ...]
            在役闸 = K 里取值不在机制下限(最松档)的 where 阈值与过滤型参数
        features:同批特征 {"csv", "features", "binaries", "fc"} 或 None
        delta:最小关心改进;q:BH 阈值(0.05);correction:闸内 Simes 合成闸级 p,闸间(连同同批特征)BH,
            族 = 功效预检进族的闸 + 同批特征
        power:功效预检口径 {deff, s_dec, p0, source, edge_ts}(设计效应与定向占比取本 app 最近一次优势检查实测;没有就拒绝)
        open_fc / known_signal_review / pending_reconcile:这一批要一并处理的未关闭登记条目、待复核已知信号、待对账项
    plan.json = {"gate_family", "gate_family_hash", "in_round", "created"}。
    """
    recs = ledger.read(app)
    delta = resolve_delta(app) if delta is None else float(delta)
    cl = _classification(app, window)
    meta = _run_meta(app, window)
    formal = _formal(cl)
    unknown = sorted(set(config or {}) - set(formal))
    if unknown:
        raise ValueError(f"候选配置里 {unknown} 不是这个 app 的参数")
    K = {**formal, **(config or {})}
    adapter = _adapter(app)
    edge = ledger.latest(app, "edge")
    if edge is None or not isinstance(edge["data"].get("resolution"), dict):
        raise SystemExit("还没做过优势检查:不知道这份数据的设计效应,算不出每道闸能分辨多大的效果。先做优势检查。")
    res = edge["data"]["resolution"]
    deff, s_dec = float(res["deff"]), float(res["s_dec"])

    axes = {a["param"]: a for a in extract.gate_axes(cl)}
    combo = {k: K[k] for k, kind in cl["kinds"].items() if kind == "D"}
    working = {p: K[p] for p in axes}
    gates = []
    for p, a in axes.items():
        if working[p] is not None and working[p] != a["levels"][0]:
            gates.append({"param": p, "column": a["column"], "op": a["op"], "cuts": _gate_cuts(a, working[p]),
                          "working": working[p], "fc": _single_axis_fc(recs, p), "source": "在役闸"})
    features = None
    for item in extra or []:
        if "features" in item:
            features = {"csv": str(item["csv"]), "features": list(item["features"]),
                        "binaries": list(item.get("binaries", [])), "fc": list(item.get("fc", []))}
        elif "param" in item:
            p = item["param"]
            if p not in axes:
                raise ValueError(f"{p} 不是这个窗口里的闸(可选 {sorted(axes)})")
            a = axes[p]
            g = next((g for g in gates if g["param"] == p), None)
            if g is None:
                w = working[p] if working[p] is not None and working[p] != a["levels"][0] else None
                g = {"param": p, "column": a["column"], "op": a["op"], "cuts": _gate_cuts(a, w), "working": w,
                     "fc": _single_axis_fc(recs, p), "source": "候选"}
                gates.append(g)
            if "cuts" in item:
                g["cuts"] = RB._gate_spec((a["column"], a["op"], item["cuts"]))[2]
            if item.get("fc"):
                g["fc"] = sorted(set(item["fc"]))
        else:
            raise ValueError(f"看不懂的附加项 {item!r}:要么给 param(闸),要么给 features(特征)")

    if gates:
        rows, seg, span = _read_label_free(app, window, cl, combo, [g["column"] for g in gates])
        _power_precheck(rows, seg, span, gates, deff=deff, s_dec=s_dec, delta=delta)

    reg = registry_state(REGISTRY if registry is None else registry)
    gate_family = _jsonable({
        "app": app, "window": window, "window_dates": _window(meta), "label": _label(meta),
        "population": {"rule": "候选配置 K:判一道闸时只放开这道闸,其余检测参数与闸都取 K 的值",
                       "combo": combo, "working": working},
        "gates": gates, "features": features,
        "delta": delta, "q": RB.Q_FDR, "correction": "闸内 Simes 合成闸级 p,闸间(连同同批特征)BH",
        "power": {"deff": deff, "s_dec": s_dec, "p0": RB.P0, "source": "优势检查实测", "edge_ts": edge["ts"]},
        "open_fc": reg["open"],
        "known_signal_review": _known_signal_review(recs, adapter),
        "pending_reconcile": _pending_reconcile(recs, adapter, reg["open"]),
    })
    S = RB.load_tune_gates("study_io")
    out = Path(out_dir) if out_dir is not None else default_plan_dir(app, window, gate_family)
    out.mkdir(parents=True, exist_ok=True)
    path = out / "plan.json"
    path.write_text(json.dumps({"gate_family": gate_family, "gate_family_hash": S.canonical_hash(gate_family),
                                "in_round": in_round, "created": datetime.now().isoformat(timespec="seconds")},
                               ensure_ascii=False, indent=1) + "\n", encoding="utf-8")

    if not in_round:
        manifest = {"gate_family": gate_family}
        powers = [max(RB.inference.power_normal(delta, c["mde"] / RB.budget.SINGLE_MULT)
                      for c in g["power"] if c["in_family"]) for g in gates if g.get("expected") == "进族"]
        expected = float(min(powers)) if powers else 0.0
        ledger.append(ledger.make_record(
            "preregister", app, actor="feature-study", round=None,
            fc=sorted({fc for g in gates for fc in g["fc"]} | set((features or {}).get("fc", []))),
            axes=sorted({g["param"] for g in gates}), window=_window(meta),
            label_horizon=int(meta["label_horizon"]), head_buffer=int(meta["head_buffer"]),
            **_fingerprints(app, window), n_looks=0, ref={_rel(path): ledger.sha256_file(path)},
            data={"manifest_hash": S.canonical_hash(manifest), "manifest": manifest,
                  "expected_power": {"backward": expected, "forward": expected},
                  "survivorship": {"checked": False, "reason": "闸子族只影响下一轮准入,不做幸存者偏差预检"}},
            note="学习端轮外预注册:清单只含闸子族,两段预期把握同值"))
    print(f"闸子族清单已冻结:{len(gates)} 道闸{'、同批特征 ' + str(len(features['features'] + features['binaries'])) + ' 个' if features else ''} → {path}")
    return gate_family


# ── run ──

def _frozen_gate_family(app: str, manifest_hash: str) -> dict:
    mine = [r for r in ledger.read(app) if r["kind"] == "preregister" and r["data"]["manifest_hash"] == manifest_hash]
    gf = mine[-1]["data"]["manifest"].get("gate_family") if mine and isinstance(mine[-1]["data"]["manifest"], dict) else None
    if not gf:
        raise ValueError("找不到这份冻结验证清单里的闸子族(清单哈希对不上,或清单没带闸)")
    return gf


def _confirm_rows(app, confirm_window, combo, gate_cols, *, manifest_hash):
    """确认窗取数的缺省入口:经 tune-gates 读这份验证清单那段确认窗的扫描结果(开窗时已补算标签)。"""
    return RB.load_tune_gates("tune").confirm_rows(app, confirm_window, combo, gate_cols, manifest_hash=manifest_hash)


def run(plan_path, *, confirm_window: str | None = None, manifest_hash: str | None = None, load_rows=None,
        B: int = 300, seed: int = 0) -> dict:
    """按冻结的闸子族判定,结果写 plan.json 同目录的 verdicts.json(确认窗上写 verdicts_<确认窗>.json)。

    训练窗(confirm_window=None):extract.build_from_longtable 从 tune-gates 长表取数(过普通守卫);
        清单带同批特征时,闸级 p 与特征的原始 p 同族做多重比较。
    确认窗(confirm_window = "backward" | "forward",同一次开窗的补检):
        1. 必须给 manifest_hash;账本里这份冻结清单的 gate_family 必须与本地 plan.json 的逐字一致;
        2. 读取区间 = 开局核对记录里这段确认窗的买点区间,先过守卫 purpose="gate_family"
           (这一段已按这份清单开过、清单带闸子族、这一段还没检过闸子族才放行);
        3. 行由 load_rows(app, confirm_window, combo, gate_cols) 提供,形状同 build_from_longtable 的返回
           (标签来自延迟标签扫描后现算的四态);缺省经 tune-gates 读这份清单那段确认窗的扫描结果;
           时间窗零点 = 这段确认窗的起点;
        4. 同批特征在确认窗上没有取数入口 → 清单带特征时拒绝。
    判第 g 道闸的条件总体:K 的检测组合里,不在闸子族里的闸按 K 的取值过滤;闸子族里的闸由 gate_judgment 按工作点逐道放开。
    进族切点严格按清单里读标签前的功效预检(gates[].power[].in_family)冻结;现场按池实测的功效只作诊断,不改族。
    """
    plan_path = Path(plan_path)
    p = json.loads(plan_path.read_text(encoding="utf-8"))
    gf = p["gate_family"]
    app, window = gf["app"], gf["window"]
    cl = _classification(app, window)
    adapter = _adapter(app)
    gates, feat = gf["gates"], gf.get("features")
    if not gates and not feat:
        raise ValueError("清单里既没有闸也没有特征,没东西可判")
    S = RB.load_tune_gates("study_io")
    axes = extract.gate_axes(cl)

    if confirm_window is None:
        meta = _run_meta(app, window)
        sample = {"window": _window(meta), "label_horizon": int(meta["label_horizon"]),
                  "head_buffer": int(meta["head_buffer"]), "first_passage_k": meta["first_passage_k"]}
        load = lambda combo: extract.build_from_longtable(app, window, combo, working=gf["population"]["working"])  # noqa: E731
    else:
        if not manifest_hash:
            raise ValueError("在留作验证的数据上补检闸,要给冻结验证清单的哈希(manifest_hash)")
        if S.canonical_hash(_frozen_gate_family(app, manifest_hash)) != p["gate_family_hash"] \
                or S.canonical_hash(gf) != p["gate_family_hash"]:
            raise ValueError("本地的闸子族清单与冻结的验证清单里的不一致,不能按它在留作验证的数据上检验")
        if feat:
            raise ValueError("清单带同批特征,留作验证的数据上还没有特征的取数入口;这类清单只能在训练窗上判")
        op = ledger.latest(app, "open")
        if op is None:
            raise ValueError(f"「{app}」还没做开局核对,没有留作验证的数据")
        cw = op["data"]["confirm"][confirm_window]
        RB.load_tune_gates("holdout").guard_label_access(app, cw["start"], cw["end"], "gate_family",
                                                         manifest_hash=manifest_hash, confirm_window=confirm_window)
        sample = {"window": {"start": cw["start"], "end": cw["end"]}, "label_horizon": int(op["label_horizon"]),
                  "head_buffer": op["head_buffer"], "first_passage_k": gf["label"]["k"]}
        loader = load_rows or (lambda a, cw, combo, cols: _confirm_rows(a, cw, combo, cols, manifest_hash=manifest_hash))
        load = lambda combo: loader(app, confirm_window, combo, [a["column"] for a in axes])  # noqa: E731

    gate_res, tv, soft, rows, pop, controls = {}, {}, {}, None, None, []
    feat_p = {}
    if feat:
        with contextlib.redirect_stdout(io.StringIO()):
            pre = RB.run_battery(feat["csv"], feat["features"], label_type="first_passage",
                                 binaries=feat["binaries"], controls=_feature_controls(feat["csv"], adapter),
                                 label_horizon=sample["label_horizon"], train_start=sample["window"]["start"])
        feat_p = {f"feature:{m}": v["p_raw"] for m, v in pre.items()}
    if gates:
        rows = load(gf["population"]["combo"])
        lacking = [c for c in ("M", "c0_atr_pct") if c not in rows.columns]
        if lacking:
            raise SystemExit(f"数据缺 {lacking} 列(旧格式长表):闸式判定要按波动率分层和控制,先按新口径重扫这个窗口")
        point = extract.working_point(cl, gf["population"]["working"])
        judged = {g["column"] for g in gates}
        absent = [a["column"] for a in axes if a["column"] not in judged and a["column"] not in rows.columns]
        if absent:
            raise ValueError(f"数据里缺闸字段列 {absent},条件总体过滤不了")
        pop = np.ones(len(rows), dtype=bool)
        for a in axes:
            if a["column"] not in judged:
                pop &= RB._cmp(pd.to_numeric(rows[a["column"]], errors="coerce").to_numpy(float), a["op"],
                               point[a["column"]])
        controls = ["c0_atr_pct"] + [s for s in adapter.KNOWN_SIGNALS if s in rows.columns]
        recs, cal = ledger.read(app), _calendar()
        for g in gates:
            hits = [r for r in recs if r["kind"] in ("discover", "select") and g["param"] in r["axes"]
                    and ledger.overlaps(r["window"], sample["window"], r["label_horizon"], cal)]
            tv[g["column"]] = not hits
            soft[g["param"]] = [{"kind": r["kind"], "ts": r["ts"], "fc": r["fc"]} for r in hits]
        seg = S.segment_cols(cl, rows.columns)
        family = {g["column"]: [c["cut"] for c in g["power"] if c["in_family"]] for g in gates}
        gate_res = RB.gate_judgment(rows, [(g["column"], g["op"], g["cuts"], g["working"]) for g in gates],
                                    population_mask=pop, seg_cols=seg, controls=controls, delta=gf["delta"],
                                    train_start=sample["window"]["start"], label_horizon=sample["label_horizon"],
                                    B=B, seed=seed, extra_pvals=feat_p, time_verified=tv, family=family)
    feat_res = None
    if feat:
        gate_p = {c: r["stats"]["simes_p"] for c, r in gate_res.items() if r["stats"]["power_ok"]}
        feat_res = RB.run_battery(feat["csv"], feat["features"], label_type="first_passage",
                                  binaries=feat["binaries"], controls=_feature_controls(feat["csv"], adapter),
                                  label_horizon=sample["label_horizon"], train_start=sample["window"]["start"],
                                  extra_pvals=gate_p)

    result = {
        "gate_family_hash": p["gate_family_hash"], "app": app, "window": window,
        "confirm_window": confirm_window, "manifest_hash": manifest_hash, "sample": sample,
        "ts": datetime.now().isoformat(timespec="seconds"),
        "controls": controls,
        "absent_signals": [s for s in adapter.KNOWN_SIGNALS if rows is not None and s not in rows.columns],
        "n_rows": 0 if rows is None else len(rows), "n_population_rows": 0 if pop is None else int(pop.sum()),
        "gates": {g["param"]: {**gate_res[g["column"]], "param": g["param"], "column": g["column"], "fc": g["fc"],
                               "time_verified": tv[g["column"]], "soft_conflicts": soft[g["param"]]} for g in gates},
        "features": feat_res,
    }
    path = plan_path.parent / ("verdicts.json" if confirm_window is None else f"verdicts_{confirm_window}.json")
    path.write_text(json.dumps(_jsonable(result), ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    for g in gates:
        r = result["gates"][g["param"]]
        print(f"{g['param']:28s} {r['verdict']:6s} {BUCKET_WORDS[r['bucket']]}"
              f"{'(' + r['reason'] + ')' if r['reason'] else ''}  形状 {r['shape']}")
    return {**result, "path": str(path)}


def _feature_controls(csv, adapter) -> list:
    cols = pd.read_csv(csv, nrows=0).columns
    return ["c0_atr_pct"] + [s for s in adapter.KNOWN_SIGNALS if s in cols]


# ── close ──

def _insert_pending(text: str, fc: str, name: str, app: str, g: dict, sample: dict) -> str:
    """在「## 已关闭」段之前补一条待验证条目(原来没有登记条目的闸先登记、再关闭)。"""
    marker = "\n## 已关闭"
    if marker not in text:
        raise ValueError("登记簿里找不到「## 已关闭」段")
    cuts = "、".join(RB._fmt(c) for c in g["cuts"])
    w = sample["window"]
    entry = (f"### {fc} · {name}\n"
             f"- **app / 轴**：{app} / `{g['param']}`\n"
             f"- **口径**：`{g['column']} {g['op']} 切点`，预注册切点 {cuts}（读标签前冻结），工作点现值 {RB._fmt(g['working']) if g['working'] is not None else '未启用'}\n"
             f"- **方向**：未预设（闸式判定）\n"
             f"- **机器可复现的发现样本**：无——学习端闸式判定直接立项，发现样本即验证样本（{w['start']}..{w['end']}，horizon {sample['label_horizon']}，股票 all）；查询次数 {len(g['cuts'])}\n"
             f"- **执行端动作**：未执行\n"
             f"- **状态**：`exploratory`\n")
    head, tail = text.split(marker, 1)
    head = head.rstrip("\n")
    sep = ""
    if head.endswith("---"):
        head, sep = head[:-3].rstrip("\n"), "---\n"
    return f"{head}\n\n{entry}\n{sep}\n## 已关闭{tail}"


def _sample_words(sample: dict, confirm_window: str | None) -> str:
    w = sample["window"]
    where = "" if confirm_window is None else f"（{RB.load_tune_gates('holdout').WINDOW_WORDS[confirm_window]}）"
    return f"验证样本 {w['start']}..{w['end']}{where}，股票 all"


def _label_words(sample: dict) -> str:
    return (f"首次穿越率 = up/(up+down+both)，k={sample['first_passage_k']:g}、horizon={sample['label_horizon']}，"
            "同一段买点只计一次，按买点 bar 汇总")


def _closing_line(fc: str, name: str, g: dict, r: dict, sample: dict, fps: dict, v_path: Path,
                  confirm_window: str | None) -> str:
    short = lambda h: (h or "无")[:12]  # noqa: E731
    note = BUCKET_WORDS[r["bucket"]] + (f"；{r['reason']}" if r.get("reason") else "")
    if r.get("time_flags"):
        note += "；" + "、".join(r["time_flags"])
    return (f"- {fc} · {name} · `{g['column']} {g['op']} 切点`（{'、'.join(RB._fmt(c) for c in g['cuts'])}）· "
            f"{_label_words(sample)} · {r['verdict']}（{note}）· {_sample_words(sample, confirm_window)} · "
            f"git_head {fps['git_head']}，底座 {short(fps['base_fingerprint'])}，源码 {short(fps['source_fingerprint'])}，"
            f"尺子 {short(fps['ruler_fingerprint'])} · → `{_rel(v_path)}`")


def close(plan_path, verdicts, *, registry=None) -> dict:
    """关闭一批判定:登记簿追加关闭行(没有登记条目的闸先补登记)、每道闸 / 每个特征写一条 verify、
    提示 KNOWN_SIGNALS 增删、输出对用户的三栏(确实有用 / 没用删了不亏 / 判不了)。

    verdicts:run() 的返回值或 verdicts 文件路径;一律从文件读,保证账本引用的哈希就是这份内容。
    记录的窗口 = 这次判定读的买点区间;确认窗上的判定,verify 的 data 另带 manifest_hash 与 confirm_window
    (守卫据此知道这一段已经检过闸子族);训练窗上的 verify 不带这两个键。
    """
    plan_path = Path(plan_path)
    p = json.loads(plan_path.read_text(encoding="utf-8"))
    gf = p["gate_family"]
    v_path = Path(verdicts) if isinstance(verdicts, (str, Path)) else Path(verdicts["path"])
    v = json.loads(v_path.read_text(encoding="utf-8"))
    if v["gate_family_hash"] != p["gate_family_hash"]:
        raise ValueError("这份判定结果不是按这份闸子族清单跑出来的,不能关闭")
    app, window = gf["app"], gf["window"]
    sample, cw = v["sample"], v["confirm_window"]
    opened = {} if cw is None else {"manifest_hash": v["manifest_hash"], "confirm_window": cw}
    adapter = _adapter(app)
    fps = _fingerprints(app, window)
    reg_path = REGISTRY if registry is None else Path(registry)
    text = reg_path.read_text(encoding="utf-8")
    reg = registry_state(reg_path)
    next_no = max([int(n) for n in re.findall(r"FC-(\d+)", text)] or [0]) + 1
    plan_sha = ledger.sha256_file(plan_path)
    ref = {_rel(plan_path): plan_sha, _rel(v_path): ledger.sha256_file(v_path)}
    common = dict(actor="feature-study", round=None, window=sample["window"], label_horizon=int(sample["label_horizon"]),
                  head_buffer=sample["head_buffer"], **fps, ref=ref, note="")
    plan_ref = {"path": _rel(plan_path), "sha256": plan_sha}

    columns = {b: [] for b in BUCKETS}
    records, closing, hints = [], [], []
    for g in gf["gates"]:
        r = v["gates"][g["param"]]
        fcs = list(g["fc"])
        names = {fc: reg["pending"].get(fc, f"[闸存在性] {g['param']}") for fc in fcs}
        if not fcs:
            fc = f"FC-{next_no:03d}"
            next_no += 1
            names[fc] = f"[闸存在性] {g['param']}"
            text = _insert_pending(text, fc, names[fc], app, g, sample)
            fcs = [fc]
        closing += [_closing_line(fc, names[fc], g, r, sample, fps, v_path, cw) for fc in fcs]
        columns[r["bucket"]].append({"axis": g["param"], "verdict": r["verdict"], "reason": r["reason"],
                                     "suggested_levels": r["suggested_levels"], "ni": r["ni"]})
        node, field = g["column"].split(".", 1)
        st = r["stats"]
        data = {"axis": {"node": node, "field": field, "op": g["op"]}, "param": g["param"], "label": gf["label"],
                "population": {"rule": gf["population"]["rule"],
                               "params_snapshot": {"combo": gf["population"]["combo"],
                                                   "working": gf["population"]["working"]}},
                "code": dict(fps),
                "sample": {"window": sample["window"], "stock_rule": "all", "head_buffer": sample["head_buffer"],
                           "by_year": st["pool_by_year"], "soft_conflicts": r["soft_conflicts"], "mde": st["mde_measured"]},
                "verdict": r["verdict"], "direction": r["direction"], "time_flags": r["time_flags"],
                "bucket": r["bucket"], "reason": r["reason"], "curve": r["curve"], "shape": r["shape"],
                "effective_interval": r["effective_interval"], "suggested_levels": r["suggested_levels"], "ni": r["ni"],
                "stats": {"simes_p": st["simes_p"], "bh_q": st["bh_q"], "family_size": st["family_size"],
                          "controls": st["controls"], "plan_ref": plan_ref},
                **opened}
        records.append(ledger.make_record("verify", app, fc=fcs, axes=[g["param"]], n_looks=len(g["cuts"]),
                                          data=_jsonable(data), **common))
        if r["verdict"] == "有信号+":
            hints.append(f"「{g['column']}」判定有信号+:如果要把它当已知信号长期控制,加进 apps/{app}/adapter.py 的 "
                         "KNOWN_SIGNALS,并在 observe() 里实现")

    feat = gf.get("features")
    for m, fr in (v.get("features") or {}).items():
        fcs = list(feat.get("fc", [])) if feat else []
        if not fcs:
            raise ValueError(f"特征「{m}」没有关联的登记条目:先在登记簿待验证段登记,再在清单的 features.fc 里写上编号")
        closing += [f"- {fc} · {reg['pending'].get(fc, m)} · 特征 `{m}` · {_label_words(sample)} · {fr['verdict']} · "
                    f"{_sample_words(sample, cw)} · git_head {fps['git_head']} · → `{_rel(v_path)}`" for fc in fcs]
        records.append(ledger.make_record(
            "verify", app, fc=fcs, axes=[f"feature:{m}"], n_looks=1, **common,
            data=_jsonable({"axis": {"node": None, "field": m, "op": None}, "param": None, "label": gf["label"],
                            "verdict": fr["verdict"], "direction": fr["direction"], "time_flags": fr["time_flags"],
                            "shape": fr["shape"], "code": dict(fps),
                            "stats": {"p_raw": fr["p_raw"], "bh_q": fr["q_fdr"], "family_size": fr["family_size"],
                                      "z_ctrl": fr["z_ctrl"], "plan_ref": plan_ref},
                            **opened})))
        is_sig = fr["verdict"].startswith("有信号")
        if m in adapter.KNOWN_SIGNALS and not is_sig:
            hints.append(f"已知信号「{m}」这次判定为「{fr['verdict']}」:考虑从 KNOWN_SIGNALS 移出")
        elif m not in adapter.KNOWN_SIGNALS and is_sig:
            hints.append(f"「{m}」判定有信号:考虑加进 KNOWN_SIGNALS,并在 observe() 里实现")

    for rec in records:
        ledger.validate_record(rec)
    text = text.rstrip("\n") + "\n\n" + "\n\n".join(closing) + "\n"
    reg_path.write_text(text, encoding="utf-8")
    for rec in records:
        ledger.append(rec)

    lines = []
    for b in BUCKETS:
        items = "、".join(f"{c['axis']}{'(' + c['reason'] + ')' if c['reason'] else ''}" for c in columns[b])
        lines.append(f"{BUCKET_WORDS[b]}:{items or '无'}")
    text_out = "\n".join(lines + hints)
    print(text_out)
    return {"columns": columns, "hints": hints, "n_records": len(records), "registry": str(reg_path), "text": text_out}


# ── reconcile ──

def _change_for(recs: list, fc: str, adapter) -> dict:
    """从账本推出这条登记条目要对账的参数改动:条目涉及的轴(参数本身或 PARAM_FEATURES 对应的特征)上最近一次定案。"""
    axes = {a for r in recs if fc in r["fc"] for a in r["axes"]}
    feats = {a.split(":", 1)[1] for a in axes if a.startswith("feature:")}
    cands = {a for a in axes if not a.startswith("feature:")} | {p for p, f in adapter.PARAM_FEATURES.items() if f in feats}
    for r in reversed(recs):
        if r["kind"] == "decide" and set(r["data"]["params"]) & cands:
            return {k: v for k, v in r["data"]["params"].items() if k in cands}
    raise ValueError(f"说不清 {fc} 要对账的是哪个参数改动:请用 change={{参数键: [旧值, 新值]}} 指明")


def _events(rows: pd.DataFrame, seg: list, point: dict | None) -> pd.DataFrame:
    """买点事件集合:point({列: (op, 值)})下任一行过全部闸的买点事件;point=None 不过滤。"""
    m = np.ones(len(rows), dtype=bool)
    for col, (op, val) in (point or {}).items():
        m &= RB._cmp(pd.to_numeric(rows[col], errors="coerce").to_numpy(float), op, val)
    return rows[m].drop_duplicates(["symbol", *seg])[["symbol", *seg, "year", *RB.STATES]].reset_index(drop=True)


def decompose(old_all, old, new_all, new, seg, *, B: int = 300, seed: int = 0) -> list:
    """一个参数改动前后买点事件集合的逐年拆解(按买点事件去重、按股自助 CI)。

    old / new = 改动前 / 后过闸的买点事件;old_all / new_all = 同一检测组合里不看闸的全部买点事件。
    掉出组 = old − new(其中「段没了」= 不在 new_all;「过不了闸」= 还在 new_all);新进组 = new − old(同理分两类)。
    总变化 = r(new) − r(old);只删掉出组 = r(old − 掉出组) − r(old);只加新进组 = r(old ∪ 新进组) − r(old)。
    CI:按股 multinomial 权重重抽 B 次,取 2.5% / 97.5% 分位。
    """
    keycols = ["symbol", *seg]
    key = lambda df: pd.MultiIndex.from_frame(df[keycols])  # noqa: E731
    rng = np.random.default_rng(seed)
    out = []
    for y in sorted(set(old["year"]) | set(new["year"])):
        O, Nw = old[old["year"] == y], new[new["year"] == y]
        in_new, in_old = key(O).isin(key(Nw)), key(Nw).isin(key(O))
        dropped, added, common = O[~in_new], Nw[~in_old], O[in_new]
        still = key(dropped).isin(key(new_all[new_all["year"] == y]))
        before = key(added).isin(key(old_all[old_all["year"] == y]))
        sets = {"old": O, "new": Nw, "common": common, "old_added": pd.concat([O, added])}
        syms = sorted(set(O["symbol"]) | set(Nw["symbol"]))
        code = {s: i for i, s in enumerate(syms)}
        S = len(syms)

        def ud(df):
            c = df["symbol"].map(code).to_numpy()
            up = df["up"].to_numpy(float)
            return (np.bincount(c, weights=up, minlength=S),
                    np.bincount(c, weights=up + df["down"].to_numpy(float) + df["both"].to_numpy(float), minlength=S))

        UD = {k: ud(v) for k, v in sets.items()}

        def diffs(W):
            with np.errstate(divide="ignore", invalid="ignore"):
                R = {k: (W @ U) / (W @ D) for k, (U, D) in UD.items()}
            return {"total": R["new"] - R["old"], "drop_only": R["common"] - R["old"], "add_only": R["old_added"] - R["old"]}

        pt = diffs(np.ones((1, S)))
        bs = diffs(rng.multinomial(S, np.full(S, 1.0 / S), size=B).astype(float))
        count = lambda df: {"events": len(df), "up": int(df["up"].sum()),  # noqa: E731
                            "dir": int((df["up"] + df["down"] + df["both"]).sum())}
        row = {"year": y}
        for k in ("total", "drop_only", "add_only"):
            row[k] = float(pt[k][0])
            row[f"{k}_ci95"] = [float(np.nanpercentile(bs[k], 2.5)), float(np.nanpercentile(bs[k], 97.5))]
        row["dropped"] = {**count(dropped), "segment_gone": int((~still).sum()), "failed_gates": int(still.sum())}
        row["added"] = {**count(added), "new_segment": int((~before).sum()), "passed_gates": int(before.sum())}
        row["common"] = count(common)
        out.append(row)
    return out


def step3_availability(cl: dict, adapter, param: str) -> dict:
    """对账第三步(伪闸重放)可做与否:参数在 PARAM_FEATURES 里有对应特征,且该特征字段在当前 detector 事件上存在。"""
    feat = adapter.PARAM_FEATURES.get(param)
    if not feat or feat not in _event_fields(cl, param):
        return {"available": False, "feature": feat, "message": f"{param} 缺少对应的特征字段，第三步暂不可做"}
    return {"available": True, "feature": feat,
            "message": "特征字段已具备;伪闸重放要在验证数据上做,写进验证清单(描述性,不进族)后执行"}


def reconcile(app: str, fc: str, *, change: dict | None = None, window: str = "main", working: dict | None = None,
              B: int = 300, seed: int = 0, out_dir=None) -> dict:
    """冲突对账:检测参数改动 vs 登记簿条目。

    参数:
        change: {检测参数键: [旧值, 新值]};None = 从账本推(该条目涉及的轴上最近一次定案)。
        window: 用哪个窗口的长表拆解。
        working: {闸参数键: 值},覆盖工作点闸取值(缺省 = 正式参数)。
    第二步:工作点与宽进点(闸取最松档)两个底座,逐年拆出掉出组 / 新进组 / 共同组的计数与首次穿越率变化(decompose)。
    第三步:只判可做与否(step3_availability)。
    产物写 JSON 后追加一条 reconcile 记录。返回 {"change", "table", "reading", "step3", "path"}。
    """
    recs = ledger.read(app)
    adapter = _adapter(app)
    cl = _classification(app, window)
    meta = _run_meta(app, window)
    formal = _formal(cl)
    change = _change_for(recs, fc, adapter) if change is None else dict(change)
    if len(change) != 1:
        raise ValueError(f"一次对账只拆一个参数改动,实际给了 {sorted(change)}")
    (param, (old_v, new_v)), = change.items()
    if cl["kinds"].get(param) != "D":
        raise ValueError(f"{param} 不是检测参数:闸阈值的改动用闸式判定事后切就能看,不需要集合拆解")

    base = {k: formal[k] for k, kind in cl["kinds"].items() if kind == "D"}
    axes = extract.gate_axes(cl)
    wk = {a["param"]: formal[a["param"]] for a in axes}
    wk.update(working or {})
    bases = {"工作点": {a["column"]: (a["op"], wk[a["param"]]) for a in axes},
             "宽进": {a["column"]: (a["op"], a["levels"][0]) for a in axes}}
    rows_old = extract.build_from_longtable(app, window, {**base, param: old_v}, working=wk)
    rows_new = extract.build_from_longtable(app, window, {**base, param: new_v}, working=wk)
    seg = RB.load_tune_gates("study_io").segment_cols(cl, rows_old.columns)
    old_all, new_all = _events(rows_old, seg, None), _events(rows_new, seg, None)
    table = []
    for name, point in bases.items():
        for row in decompose(old_all, _events(rows_old, seg, point), new_all, _events(rows_new, seg, point), seg,
                             B=B, seed=seed):
            table.append({"base": name, **row})

    step3 = step3_availability(cl, adapter, param)
    excl0 = lambda r: r["total_ci95"][0] > 0 or r["total_ci95"][1] < 0  # noqa: E731
    work = [r for r in table if r["base"] == "工作点"]
    wide = [r for r in table if r["base"] == "宽进"]
    tail = "" if step3["available"] else "(第三步未做,还不能排除选择效应)"
    if any(excl0(r) for r in wide):
        reading = "疑似选择效应:宽进底座上也有显著变化" + tail
    elif any(excl0(r) for r in work):
        reading = "疑似结构 / 交互效应:宽进底座上没有显著变化,只在工作点闸阵下出现" + tail
    else:
        reading = "拆不开:两个底座上都没有显著变化"

    result = {"fc": fc, "change": {param: [old_v, new_v]}, "working": wk, "table": table, "reading": reading,
              "step3": step3, "label": _label(meta), "window": _window(meta)}
    out = Path(out_dir) if out_dir is not None else OUT_ROOT / app / window
    out.mkdir(parents=True, exist_ok=True)
    path = out / f"reconcile_{fc}_{datetime.now().strftime('%Y%m%dT%H%M%S')}.json"
    path.write_text(json.dumps(_jsonable(result), ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    ledger.append(ledger.make_record(
        "reconcile", app, actor="feature-study", round=None, fc=[fc], axes=[param], window=_window(meta),
        label_horizon=int(meta["label_horizon"]), head_buffer=int(meta["head_buffer"]), **_fingerprints(app, window),
        n_looks=1, ref={_rel(path): ledger.sha256_file(path)},
        data=_jsonable({"change": {param: [old_v, new_v]}, "step": "集合拆解(第二步)", "label": _label(meta),
                        "working": wk, "table": table, "reading": reading, "step3": step3["message"]}),
        note=""))
    for r in table:
        print(f"{r['base']} {r['year']}:总变化 {_pt(r['total'])} 点 [{_pt(r['total_ci95'][0])}, {_pt(r['total_ci95'][1])}],"
              f"只删掉出组 {_pt(r['drop_only'])},只加新进组 {_pt(r['add_only'])};"
              f"掉出 {r['dropped']['events']} 个买点事件,新进 {r['added']['events']} 个")
    print(reading)
    print(step3["message"])
    return {**result, "path": str(path)}
