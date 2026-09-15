# -*- coding: utf-8 -*-
"""tune-gates · 样本使用账本 `docs/sample_usage/<app>.jsonl`。

账本回答一件事:**哪段行情的标签,被哪些假设看过、看了几次**。它是确认窗守卫、取窗、
失效判断的唯一事实来源,git 跟踪、只追加、永不删(`.gitattributes` 设 `merge=union`,
多分支并行追加不冲突)。

一行一条记录,公共字段见 `COMMON_FIELDS`;`kind` 决定 `data` 里必须有哪些键:
  open         开局核对:训练窗、两段确认窗、数据起止(不烧)
  ruling       人工裁定(不烧)
  edge         优势检查(不烧,计次)
  select       筛选 / 联合识别 / 单格查询,每次调用一条(烧涉及的轴)
  preregister  冻结验证清单(不烧)
  extrapolate  在确认窗上开一次(该窗对清单内假设用尽)
  decide       写正式参数(带 selects_on / provisional / depends_on)
  discover     研究发现(烧该条目的轴)
  verify       学习端判定(计次)
  reconcile    学习端对账(计次)

「烧」= 该窗的标签(买点区间 + 其后 label_horizon 个交易日)参与过这条轴的假设提出、
取值挑选或做不做的决定。重叠判定一律把 label 后缀算进窗口。

写盘:产物先写完、记录最后写;`append` 校验 schema,并核 `ref` 里每个产物文件存在且
sha256 一致,然后写一行 + flush + fsync。读盘:只容忍**截断的尾行**(写到一半进程被杀),
中间行损坏直接报错——账本坏了,守卫就不能信它。工程验证不写账本。

轴名:参数轴 `<section>.<field>`(params.yaml 的键);
不对应参数的特征 `feature:<特征名>`。
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
from datetime import datetime
from pathlib import Path

import pandas as pd

SKILL_DIR = Path(__file__).resolve().parent
REPO = Path(subprocess.check_output(["git", "rev-parse", "--show-toplevel"], text=True, cwd=SKILL_DIR).strip())

SCHEMA = 1
KINDS = ("open", "ruling", "edge", "select", "preregister", "extrapolate", "decide", "discover", "verify", "reconcile")
BURN_KINDS = ("discover", "select", "verify", "reconcile", "extrapolate")
WINDOW_KINDS = ("open", "edge", "select", "extrapolate", "discover", "verify", "reconcile")   # 读过标签 → 必须带窗口
RULING_TOPICS = ("ranges", "delta", "mechanism", "delete_gate", "adoption_rule", "power_notified",
                 "open_low_power", "veto", "expand_range")
CONFIRM_NAMES = ("backward", "forward")
SELECT_TOOLS = ("screen", "find", "cell")
# 尺子 = 标签 / 基线 / 分层的定义代码;任一文件变了,所有判定都要重做
RULER_FILES = ("path2/eval.py", "path2/calc/atr.py",
               ".claude/skills/tune-gates/edge_core.py", ".claude/skills/tune-gates/inference.py")

COMMON_FIELDS = ("schema", "ts", "actor", "kind", "app", "round", "fc", "axes", "window", "label_horizon",
                 "stock_rule", "head_buffer", "git_head", "base_fingerprint", "source_fingerprint",
                 "ruler_fingerprint", "n_looks", "ref", "data", "note")
FINGERPRINT_FIELDS = ("git_head", "base_fingerprint", "source_fingerprint", "ruler_fingerprint")
DATA_KEYS = {
    "open": ("data_start", "data_end", "n_probed", "train", "confirm"),
    "ruling": ("topic", "value"),
    "edge": ("points", "verdict"),
    "select": ("tool",),
    "preregister": ("manifest_hash", "manifest", "expected_power", "survivorship"),
    "extrapolate": ("manifest_hash", "confirm_window", "results"),
    "decide": ("params", "selects_on", "provisional", "depends_on"),
}
AXIS_RE = re.compile(r"^(?:[A-Za-z_]\w*\.[A-Za-z_]\w*|feature:\S+)$")
FC_RE = re.compile(r"^FC-\d{3,}$")
SHA_RE = re.compile(r"^[0-9a-f]{64}$")


# ---------------------------------------------------------------- 路径与指纹

def ledger_dir() -> Path:
    """账本目录:环境变量 TUNE_LEDGER_DIR 优先(冒烟 / 单测指向临时目录),否则 REPO/docs/sample_usage。"""
    env = os.environ.get("TUNE_LEDGER_DIR")
    return Path(env) if env else REPO / "docs" / "sample_usage"


def ledger_path(app: str) -> Path:
    return ledger_dir() / f"{app}.jsonl"


def _resolve(path) -> Path:
    p = Path(path)
    return p if p.is_absolute() else REPO / p


def sha256_file(path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def ruler_fingerprint(repo: Path = REPO) -> str:
    """按 RULER_FILES 顺序 hash(相对路径 + \\0 + 字节 + \\0)。任一文件缺失 → FileNotFoundError。"""
    h = hashlib.sha256()
    for rel in RULER_FILES:
        p = Path(repo) / rel
        if not p.is_file():
            raise FileNotFoundError(f"尺子文件缺失: {rel}(标签 / 基线 / 分层定义代码不全,算不出尺子指纹)")
        h.update(rel.encode() + b"\0" + p.read_bytes() + b"\0")
    return h.hexdigest()


def _study_path(app: str, window: str) -> Path:
    import study_io
    return study_io.study_path(app, window)


def fingerprints_for(mod, base: dict) -> dict:
    """四个指纹的唯一算法:{git_head, base_fingerprint, source_fingerprint, ruler_fingerprint}。

    mod = pattern 模块;base = 底座参数(正式参数 ⊕ 宽进覆盖)。底座 / 源码指纹与 classification 生成时
    同一算法。窗口声明还没写出来(准入发生在写声明之前)或参数文件是临时副本时,调用方直接给底座。
    study_io 在函数内懒 import,避免模块级循环依赖。"""
    import study_io
    spec = mod.build_pattern(mod.Params.from_dict(base, strict=True))
    return {"git_head": study_io._git_head(),
            "base_fingerprint": study_io.canonical_hash(base),
            "source_fingerprint": study_io.source_fingerprint(study_io.source_files(mod, spec))["hash"],
            "ruler_fingerprint": ruler_fingerprint()}


def current_fingerprints(app: str, window: str) -> dict:
    """按窗口声明现算当前代码与底座的四个指纹(`fingerprints_for`),不读 classification 里记录的旧值——
    拿它和记录里的指纹比,才看得出「之后改过」。"""
    import study_io
    study = study_io.load_study(_study_path(app, window))
    mod = study_io.import_app(study)
    return fingerprints_for(mod, study_io.base_snapshot(mod, study))


# ---------------------------------------------------------------- 记录与校验

def make_record(kind: str, app: str, **fields) -> dict:
    """补 schema / ts 与默认值(fc=[], axes=[], ref={}, data={}, note="", n_looks=0, stock_rule="all")。
    其余公共字段由调用方给;不在这里校验,`append` 时统一校验。"""
    rec = {"schema": SCHEMA, "ts": datetime.now().isoformat(timespec="seconds"), "kind": kind, "app": app,
           "fc": [], "axes": [], "ref": {}, "data": {}, "note": "", "n_looks": 0, "stock_rule": "all"}
    rec.update(fields)
    return rec


def _fail(msg: str):
    raise ValueError(f"账本记录不合法: {msg}")


def _date(v, what: str) -> pd.Timestamp:
    try:
        return pd.Timestamp(v)
    except (TypeError, ValueError):
        _fail(f"{what} 不是日期: {v!r}")


def _check_window(w, what: str, extra: tuple = ()) -> None:
    if not isinstance(w, dict) or not {"start", "end", *extra} <= set(w):
        _fail(f"{what} 必须是含 start / end{''.join(' / ' + k for k in extra)} 的对象,实际 {w!r}")
    if _date(w["start"], f"{what}.start") > _date(w["end"], f"{what}.end"):
        _fail(f"{what} 起点晚于终点: {w['start']} > {w['end']}")
    for k in extra:
        _date(w[k], f"{what}.{k}")


def _is_int(v) -> bool:
    return isinstance(v, int) and not isinstance(v, bool)


def validate_record(rec: dict) -> None:
    """schema 校验;不合法 → ValueError。不核 ref 哈希(那只在 append 时核一次)。"""
    if not isinstance(rec, dict):
        _fail(f"不是 JSON 对象: {rec!r}")
    missing = [k for k in COMMON_FIELDS if k not in rec]
    if missing:
        _fail(f"缺少字段 {missing}")
    extra = sorted(set(rec) - set(COMMON_FIELDS))
    if extra:
        _fail(f"多出未知字段 {extra}(字段名拼错?)")
    if rec["schema"] != SCHEMA:
        _fail(f"schema 版本 {rec['schema']!r},本代码只认 {SCHEMA}")
    if not isinstance(rec["ts"], str):
        _fail(f"ts 必须是 ISO 时间字符串: {rec['ts']!r}")
    try:
        datetime.fromisoformat(rec["ts"])
    except ValueError:
        _fail(f"ts 不是 ISO 时间: {rec['ts']!r}")
    kind = rec["kind"]
    if kind not in KINDS:
        _fail(f"未知记录类型 {kind!r},只能是 {KINDS}")
    for k in ("actor", "app", "stock_rule"):
        if not isinstance(rec[k], str) or not rec[k]:
            _fail(f"{k} 必须是非空字符串: {rec[k]!r}")
    if rec["round"] is not None and not (_is_int(rec["round"]) or (isinstance(rec["round"], str) and rec["round"])):
        _fail(f"round 必须是非空字符串、整数或 null: {rec['round']!r}")
    if not isinstance(rec["fc"], list) or not all(isinstance(x, str) and FC_RE.match(x) for x in rec["fc"]):
        _fail(f"fc 必须是 FC-xxx 编号列表: {rec['fc']!r}")
    if not isinstance(rec["axes"], list) or not all(isinstance(x, str) and AXIS_RE.match(x) for x in rec["axes"]):
        _fail(f"axes 必须是轴名列表(参数轴 section.field,特征 feature:名): {rec['axes']!r}")
    if kind in WINDOW_KINDS or rec["window"] is not None:
        _check_window(rec["window"], "window")
    lh = rec["label_horizon"]
    if (kind in WINDOW_KINDS or lh is not None) and not (_is_int(lh) and lh > 0):
        _fail(f"label_horizon 必须是正整数: {lh!r}")
    hb = rec["head_buffer"]
    if hb is not None and not (_is_int(hb) and hb >= 0):
        _fail(f"head_buffer 必须是非负整数或 null: {hb!r}")
    for k in FINGERPRINT_FIELDS:
        if rec[k] is not None and not (isinstance(rec[k], str) and rec[k]):
            _fail(f"{k} 必须是非空字符串或 null: {rec[k]!r}")
    if not (_is_int(rec["n_looks"]) and rec["n_looks"] >= 0):
        _fail(f"n_looks 必须是非负整数: {rec['n_looks']!r}")
    ref = rec["ref"]
    if not isinstance(ref, dict) or not all(isinstance(p, str) and isinstance(h, str) and SHA_RE.match(h)
                                            for p, h in ref.items()):
        _fail(f"ref 必须是 {{产物路径: sha256}}: {ref!r}")
    if not isinstance(rec["note"], str):
        _fail(f"note 必须是字符串: {rec['note']!r}")
    data = rec["data"]
    if not isinstance(data, dict):
        _fail(f"data 必须是对象: {data!r}")
    lack = [k for k in DATA_KEYS.get(kind, ()) if k not in data]
    if lack:
        _fail(f"{kind} 记录的 data 缺少 {lack}")
    _check_data(kind, rec, data)
    try:
        json.dumps(rec, ensure_ascii=False, allow_nan=False)
    except (TypeError, ValueError) as e:
        _fail(f"含不能写成标准 JSON 的值(NaN / 日期对象等): {e}")


def _check_data(kind: str, rec: dict, data: dict) -> None:
    if kind == "open":
        _date(data["data_start"], "data.data_start"); _date(data["data_end"], "data.data_end")
        if not (_is_int(data["n_probed"]) and data["n_probed"] > 0):
            _fail(f"open 的 n_probed 必须是正整数: {data['n_probed']!r}")
        _check_window(data["train"], "data.train", ("label_end",))
        if not isinstance(data["confirm"], dict) or set(data["confirm"]) != set(CONFIRM_NAMES):
            _fail(f"open 的 data.confirm 必须恰有 {CONFIRM_NAMES} 两段: {data['confirm']!r}")
        for name in CONFIRM_NAMES:
            _check_window(data["confirm"][name], f"data.confirm.{name}", ("label_end",))
    elif kind == "ruling":
        if data["topic"] not in RULING_TOPICS:
            _fail(f"ruling 的 topic {data['topic']!r} 不在 {RULING_TOPICS}")
    elif kind == "select":
        if data["tool"] not in SELECT_TOOLS:
            _fail(f"select 的 tool {data['tool']!r} 不在 {SELECT_TOOLS}")
        if rec["n_looks"] < 1:
            _fail("select 记录的 n_looks 至少为 1(每次挑选都要计次)")
    elif kind == "preregister":
        ep = data["expected_power"]
        if not isinstance(ep, dict) or not all(isinstance(ep.get(n), (int, float)) and not isinstance(ep.get(n), bool)
                                               for n in CONFIRM_NAMES):
            _fail(f"preregister 的 expected_power 必须给 {CONFIRM_NAMES} 两段的数值: {ep!r}")
    elif kind == "extrapolate":
        if data["confirm_window"] not in CONFIRM_NAMES:
            _fail(f"extrapolate 的 confirm_window 必须是 {CONFIRM_NAMES} 之一: {data['confirm_window']!r}")
    elif kind == "decide":
        if not isinstance(data["params"], dict) or not all(isinstance(v, list) and len(v) == 2
                                                           for v in data["params"].values()):
            _fail(f"decide 的 params 必须是 {{参数键: [旧值, 新值]}}: {data['params']!r}")
        if not isinstance(data["selects_on"], list) or not all(isinstance(x, str) and AXIS_RE.match(x)
                                                               for x in data["selects_on"]):
            _fail(f"decide 的 selects_on 必须是轴名列表: {data['selects_on']!r}")
        if not isinstance(data["provisional"], bool):
            _fail(f"decide 的 provisional 必须是布尔值: {data['provisional']!r}")
        if not isinstance(data["depends_on"], dict):
            _fail(f"decide 的 depends_on 必须是 {{参数键: 决策时取值}}: {data['depends_on']!r}")
    elif kind in ("discover", "verify", "reconcile"):
        if not rec["fc"]:
            _fail(f"{kind} 记录必须关联至少一条登记簿条目(fc 非空)")


# ---------------------------------------------------------------- 读写

def _parse_lines(raw: bytes, path) -> tuple[list[dict], int]:
    """返回 (记录列表, 截断尾行起点字节偏移;无截断尾行时为 len(raw))。"""
    lines = raw.split(b"\n")
    tail = lines.pop()                      # 以换行结尾时 tail == b""
    recs = []
    for i, line in enumerate(lines, 1):
        try:
            recs.append(json.loads(line.decode("utf-8")))
        except (UnicodeDecodeError, json.JSONDecodeError) as e:
            raise ValueError(f"{path} 第 {i} 行损坏(不是合法 JSON): {e}——账本中间行坏了,不能继续用,需人工修复") from e
    if not tail:
        return recs, len(raw)
    try:
        recs.append(json.loads(tail.decode("utf-8")))
        return recs, len(raw)
    except (UnicodeDecodeError, json.JSONDecodeError):
        return recs, len(raw) - len(tail)   # 写到一半被打断的尾行:丢弃


def validate_file(path) -> list[dict]:
    """逐行解析并校验 schema;只容忍截断的尾行。任何一行不合法 → ValueError(带行号)。"""
    recs, _ = _parse_lines(Path(path).read_bytes(), path)
    for i, rec in enumerate(recs, 1):
        try:
            validate_record(rec)
        except ValueError as e:
            raise ValueError(f"{path} 第 {i} 行: {e}") from e
    return recs


def read(app: str) -> list[dict]:
    """读某 app 的全部记录(按写入顺序);文件不存在 → []。"""
    p = ledger_path(app)
    return validate_file(p) if p.exists() else []


def append(rec: dict, *, check_refs: bool = True) -> dict:
    """校验后追加一行。check_refs 时 ref 里每个文件(相对 REPO 或绝对路径)必须存在且 sha256 一致。

    若文件末尾残留上次被打断的半行,先截掉它再写,免得新记录粘在半行后面把中间行弄坏。"""
    validate_record(rec)
    if check_refs:
        for path, sha in rec["ref"].items():
            p = _resolve(path)
            if not p.is_file():
                _fail(f"引用的产物文件不存在: {path}(产物要先写完,记录最后写)")
            if sha256_file(p) != sha:
                _fail(f"引用的产物文件内容与记录的哈希不一致: {path}")
    p = ledger_path(rec["app"])
    p.parent.mkdir(parents=True, exist_ok=True)
    line = (json.dumps(rec, ensure_ascii=False, allow_nan=False) + "\n").encode("utf-8")
    with open(p, "a+b") as f:
        size = f.seek(0, os.SEEK_END)
        if size:
            f.seek(0)
            raw = f.read()
            _, good = _parse_lines(raw, p)
            if good < size:
                f.truncate(good)
            elif not raw.endswith(b"\n"):
                f.write(b"\n")
        f.write(line)
        f.flush()
        os.fsync(f.fileno())
    return rec


# ---------------------------------------------------------------- 窗口运算

def label_end(buy_end, horizon: int, calendar) -> pd.Timestamp:
    """buy_end 之后第 horizon 个交易日(buy_end 本身不算)。超出日历末日的部分按工作日外推。"""
    cal = pd.DatetimeIndex(calendar)
    t = pd.Timestamp(buy_end)
    pos = cal.searchsorted(t, side="right")
    n_after = len(cal) - pos
    if n_after >= horizon:
        return cal[pos + horizon - 1]
    anchor = cal[-1] if n_after > 0 else max(t, cal[-1])
    return anchor + pd.offsets.BDay(horizon - n_after)


def overlaps(win_a: dict, win_b: dict, horizon: int, calendar) -> bool:
    """两窗各自 [start, label_end(end)] 闭区间是否相交。"""
    a0, b0 = pd.Timestamp(win_a["start"]), pd.Timestamp(win_b["start"])
    a1, b1 = label_end(win_a["end"], horizon, calendar), label_end(win_b["end"], horizon, calendar)
    return a0 <= b1 and b0 <= a1


def burned(app: str, window: dict, axes: list[str] | None = None, calendar=None) -> list[dict]:
    """与 window 重叠(两边都带 label 后缀,后缀长度取各条记录自己的 label_horizon)、且涉及 axes
    的「烧」类记录。axes=None 不按轴过滤(含不针对具体轴的方法结论)。calendar 缺省用数据目录的交易日历。"""
    hits = []
    for rec in read(app):
        if rec["kind"] not in BURN_KINDS or (axes is not None and not set(axes) & set(rec["axes"])):
            continue
        if calendar is None:
            import holdout
            calendar = holdout.default_calendar()
        if overlaps(rec["window"], window, rec["label_horizon"], calendar):
            hits.append(rec)
    return hits


def looks(app: str, axes: list[str]) -> int:
    """涉及 axes 中任一条轴的全部记录的 n_looks 之和。同族(池内 |Spearman| ≥ 0.3)由调用方并进 axes。"""
    want = set(axes)
    return sum(rec["n_looks"] for rec in read(app) if want & set(rec["axes"]))


def latest(app: str, kind: str, **match) -> dict | None:
    """该 app 账本里按写入顺序最后一条 kind 记录;match 按顶层字段等值过滤(如 round=2)。没有 → None。"""
    if kind not in KINDS:
        raise ValueError(f"未知记录类型 {kind!r},只能是 {KINDS}")
    bad = sorted(set(match) - set(COMMON_FIELDS))
    if bad:
        raise ValueError(f"只能按账本公共字段过滤,{bad} 不是公共字段")
    for rec in reversed(read(app)):
        if rec["kind"] == kind and all(rec[k] == v for k, v in match.items()):
            return rec
    return None
