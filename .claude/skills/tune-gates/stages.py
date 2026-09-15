# -*- coding: utf-8 -*-
"""tune-gates · 调参进行到哪一步:阶段推导与半截状态(`tune.status` 的实现)。

**只读**:不写任何文件、不写账本、不读任何标签列——扫描结果只读 symbol 列、提交清单与口径记录。

阶段(`STAGES`,按流程先后):
  open               开局核对:划定训练数据与两段留出的验证数据
  edge               优势检查
  ranges             定范围裁定:档位范围 + 最小关心改进
  screen             筛选
  mechanism          机制复核裁定(最近一次筛选里要动的改动带提醒时才需要)
  joint              联合调参
  preregister        冻结验证清单(调参的验证清单;学习端单独冻结的闸清单不算)
  validate_backward  打开训练期之前留出的验证数据
  validate_forward   打开训练期之后留出的验证数据
  decide             定案(写正式参数,或整体否决、维持现役)

每个阶段给出 {name, done, valid, why, evidence};evidence["scope"] ∈ required / skipped / unknown(是否在必做
作用域)。完成证据以账本记录为主、产物为辅:写盘顺序是产物先写完、记录最后写,所以有记录就说明产物完整,有产物
没记录才是半截。有效性按记录里的三个指纹与训练窗判断——检测源码、尺子(标签 / 基线 / 分层代码)、底座(正式参数
⊕ 该窗口的放开值);git 版本只作证据。记录里没记指纹的项(回填记录)核对不了,不算失效。某阶段失效后,其后已完成
的阶段跟着作废(开局核对除外,它只管留出的验证数据有没有被用过)。

轮次:一轮从选参(优势检查、筛选、联合调参、单格查询及它们的裁定)开始,到定案或整体否决结束。定案包括两种
  特殊写法:对已落地定案做完事后验证后的结论记账(确认 / 暂定采纳),以及把本组更早的改动改回原值(撤回)。
  - 最后一条定案(或否决)之后又有选参记录 → 新一轮进行中,阶段证据只取那之后的记录;
  - 否则上一轮已收尾:阶段证据取那一轮的记录,定案之前没做的选参步骤跳过、不再补做;定案之后补做的验证
    (冻结清单、打开验证数据)仍算这一轮。定案前底座变了是定案本身造成的(定案已落地时不算失效)。
  开局核对取账本里最新的一条;新一轮沿用它的前提是它划出的验证数据没被别的清单打开过。

「继续」(`next`)按下列顺序检查,命中即给出:
  1. 有被打断的长任务:扫描输出目录(窗口目录与优势检查目录)里有不在提交清单里的分片、有分片却没有提交清单、
     已完成股票(已提交分片的 symbol ∪ 过滤名单 ∪ 空名单)不等于应扫全集、一致性验证日志没有结论行、延迟标签
     没补全 → 续跑。没有提交清单且口径记录缺新口径键的目录是旧格式扫描结果:只提示不能续跑、只能重扫。
     确认窗扫描目录(按窗口名前缀认)不是训练扫描,归验证阶段:属于本轮验证清单 → 再开那段验证数据续跑;
     清单还没冻结完 → 重新冻结清单续跑;没用上的清单留下的 → 只提示。
  2. 指纹漂移:底座 == 最后一条定案记下的底座 → 定案已落地(提示);否则正式参数被改过,记录对不上的阶段失效
     → 确认后重做。检测源码或尺子变了、训练数据范围变了 → 同样逐阶段失效。新一轮沿用的开局核对,其验证数据
     已被别的清单打开过 → 重新开局核对。仍在生效的定案,背景参数快照与现值不同 → 复核。
  3. 待落账的人工裁定:优势检查做完没有范围 / 最小关心改进裁定;筛选带提醒没有机制复核裁定;冻结了清单没告知
     预期把握(或把握不足一半没同意开窗);两段验证数据都开了没有定案 → 带着证据重问。
  4. 最早未完成的阶段:产物在、记录缺(含验证结果文件) → 重跑这一步补上记录(固定种子、扫描结果复用,结论不变,
     不算多挑一次;验证结果没记开窗记录 = 这段还没算打开过);删闸裁定之后没重算筛选 → 按删闸后的参数在同一批扫描上重做筛选;验证数据开了、
     清单里的闸子族没补检 → 补检。
  5. 全部完成 → 定案日期,以及下一次可做独立验证的最早日期(暂定定案到期 → 复验)。
"""
from __future__ import annotations

import importlib
import json
import re
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd

SKILL_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SKILL_DIR))

import ledger  # noqa: E402

REPO = ledger.REPO
sys.path.insert(0, str(REPO))

import edge  # noqa: E402
import holdout  # noqa: E402
import multivar_scan as MS  # noqa: E402
import screen  # noqa: E402
import study_io as S  # noqa: E402
from multivar_core import apply_overrides  # noqa: E402

STAGES = ("open", "edge", "ranges", "screen", "mechanism", "joint", "preregister", "validate_backward",
          "validate_forward", "decide")
STAGE_WORDS = {"open": "开局核对", "edge": "优势检查", "ranges": "定范围", "screen": "筛选", "mechanism": "机制复核",
               "joint": "联合调参", "preregister": "冻结验证清单",
               "validate_backward": f"打开{holdout.WINDOW_WORDS['backward']}",
               "validate_forward": f"打开{holdout.WINDOW_WORDS['forward']}", "decide": "定案"}
CONFIRM_OF = {"validate_backward": "backward", "validate_forward": "forward"}
SELECTION_TOPICS = ("ranges", "delta", "mechanism", "delete_gate", "adoption_rule", "expand_range")
NEW_CALIBER_KEYS = ("label_mode", "ruler_fingerprint")   # 新格式扫描的口径记录才有的键
DEFAULT_DECIDE_WINDOW = "main"                          # 定案记录没写窗口时按它找研究声明
LOW_POWER = 0.5                                         # 预期把握低于它,开验证数据前要用户同意(同确认窗守卫)
RECHECK_SPAN = pd.DateOffset(years=1)                   # 暂定定案:前向验证数据之后再攒满这么长的买点才复验
TOPIC_WORDS = {"ranges": "档位范围", "delta": "最小关心改进", "mechanism": "机制复核",
               "power_notified": "预期把握的告知", "open_low_power": "把握不足一半时开不开这段验证数据",
               "decide": "确认写入正式参数还是整体否决"}
DRIFT_WORDS = {"base": "之后正式参数(或放开值)改过", "source": "之后检测代码改过",
               "ruler": "之后涨跌结果与基线的算法改过", "window": "不是在这次开局核对划定的训练数据上做的"}
FLAG_WORDS = {"did": "效果依赖其他闸开不开", "year": "两年明显不一样", "time": "不同时间段效果不一致",
              "drift": "可能换成了另一批股票"}
STAGE_ACTIONS = {"open": "open_round", "edge": "edge", "ranges": "ask_ruling", "screen": "screen",
                 "mechanism": "ask_ruling", "joint": "find", "preregister": "preregister",
                 "validate_backward": "validate", "validate_forward": "validate", "decide": "adopt"}
NEXT_KEYS = ("stage", "window", "working_point", "topic", "confirm_window", "earliest", "basis")


# ---------------------------------------------------------------- 小工具

def _topic(rec: dict):
    return rec["data"].get("topic") if rec["kind"] == "ruling" else None


def _is_close(rec: dict) -> bool:
    return rec["kind"] == "decide" or _topic(rec) == "veto"


def _is_selection(rec: dict) -> bool:
    return rec["kind"] in ("edge", "select") or _topic(rec) in SELECTION_TOPICS


def _kind(kind: str):
    return lambda rec: rec["kind"] == kind


def _round_manifest(rec: dict) -> bool:
    """调参的验证清单(带确认窗扫描声明);学习端单独冻结的闸清单没有它。"""
    return rec["kind"] == "preregister" and "confirm_scan" in rec["data"]["manifest"]


def _select(tool: str):
    return lambda rec: rec["kind"] == "select" and rec["data"].get("tool") == tool


def _ruling(topic: str, manifest_hash: str | None = None):
    return lambda rec: _topic(rec) == topic and (manifest_hash is None or rec["data"].get("manifest_hash") == manifest_hash)


def _last(recs: list, lo: int, hi: int, pred) -> int | None:
    """recs[lo:hi] 里最后一条满足 pred 的下标。"""
    for i in range(min(hi, len(recs)) - 1, max(lo, 0) - 1, -1):
        if pred(recs[i]):
            return i
    return None


def _same(recorded, now):
    """True 一致 / False 变了 / None 核对不了(记录没记,或现值无从算起)。"""
    return None if recorded is None or now is None else recorded == now


def _span(win: dict) -> dict:
    return {"start": win["start"], "end": win["end"]}


def _flat(params: dict) -> dict:
    return {f"{sec}.{k}": v for sec, kv in params.items() if isinstance(kv, dict) for k, v in kv.items()}


def _v(x) -> str:
    return "不设" if x is None else str(x)


def _day(t) -> str:
    return pd.Timestamp(t).strftime("%Y-%m-%d")


def _rec_ev(recs: list, i: int | None) -> dict | None:
    if i is None:
        return None
    r = recs[i]
    return {"line": i + 1, "ts": r["ts"], "actor": r["actor"], "git_head": r["git_head"]}


def _stage(done: bool, valid, why: str, evidence: dict | None = None, scope: str = "required") -> dict:
    return {"done": done, "valid": valid, "why": why, "evidence": {"scope": scope, **(evidence or {})}}


def _half(kind: str, stage: str | None, why: str, *, blocking: bool, action: str | None = None, **extra) -> dict:
    return {"kind": kind, "stage": stage, "blocking": blocking, "why": why, "action": action, **extra}


def _changes(recs: list, idx: list) -> str:
    """改了哪些参数(人话);新旧值相同的项(验证结论记账)不算改动。"""
    return ";".join(f"{k} 从 {_v(old)} 改成 {_v(new)}" for i in idx if recs[i]["kind"] == "decide"
                    for k, (old, new) in recs[i]["data"]["params"].items() if old != new)


def _reverts(recs: list, decides: list) -> bool:
    """最后一条定案是不是把同组更早定案的改动全部改回了原值(撤回)。"""
    *earlier, last = decides
    return bool(earlier) and all(any(recs[i]["data"]["params"].get(k) == [new, old] for i in earlier)
                                 for k, (old, new) in recs[last]["data"]["params"].items())


def _decision(recs: list, idx: list) -> dict:
    """一组收尾记录(定案 / 否决,按写入顺序)的结论:{"status","provisional","verified","date","last_date","changes"}。

    status:
      veto         整体否决、维持现役
      confirmed    经过独立验证且不暂定
      provisional  经过独立验证、暂定采纳
      withdrawn    最后一条定案把本组更早的改动改回了原值(撤回)
      unverified   还没经过独立验证
    验证结论记账的定案(data.landed_confirmation)优先于同组更早定案的标记;date = 本组第一条定案的日期,
    last_date = 最后一条记录的日期;changes 不含撤回那条本身。"""
    last = recs[idx[-1]]
    decides = [i for i in idx if recs[i]["kind"] == "decide"]
    out = {"date": recs[decides[0]]["ts"][:10] if decides else last["ts"][:10], "last_date": last["ts"][:10],
           "changes": _changes(recs, decides)}
    if last["kind"] == "ruling":
        return {**out, "status": "veto", "provisional": False, "verified": True}
    conf = [i for i in decides if recs[i]["data"].get("landed_confirmation")]
    if conf:
        prov = bool(recs[conf[-1]]["data"]["provisional"])
        return {**out, "status": "provisional" if prov else "confirmed", "provisional": prov, "verified": True}
    if _reverts(recs, decides):
        return {**out, "status": "withdrawn", "changes": _changes(recs, decides[:-1]), "provisional": False,
                "verified": True}
    prov = any(recs[i]["data"]["provisional"] for i in decides)
    if not recs[decides[-1]]["data"].get("verified"):
        return {**out, "status": "unverified", "provisional": prov, "verified": False}
    return {**out, "status": "provisional" if prov else "confirmed", "provisional": prov, "verified": True}


def _status_words(dn: dict) -> str:
    if dn["status"] == "unverified":
        return "暂定、还没经过独立验证" if dn["provisional"] else "还没经过独立验证"
    return {"veto": "整体否决", "confirmed": "已通过独立验证", "provisional": "独立验证后暂定采纳",
            "withdrawn": "独立验证后已撤回"}[dn["status"]]


# ---------------------------------------------------------------- 现值

class _Now:
    """当前代码与参数下的现值(指纹、正式参数、交易日历),按需计算并缓存。算不出时记下原因,不带崩状态检查。"""

    def __init__(self, app: str, apps_dir: Path, cfg, calendar):
        self.app, self.apps_dir, self.cfg = app, apps_dir, cfg
        self._calendar = None if calendar is None else pd.DatetimeIndex(calendar)
        self._cache: dict = {}

    def _memo(self, key, fn):
        if key not in self._cache:
            try:
                self._cache[key] = fn()
            except Exception as e:  # noqa: BLE001 —— app 用什么异常表达「搭不出」是它的自由,原因写进 why
                self._cache[key] = {"error": f"{type(e).__name__}: {e}"}
        return self._cache[key]

    def ruler(self):
        got = self._memo("ruler", lambda: {"fp": ledger.ruler_fingerprint()})
        return got.get("fp", "!" + got.get("error", ""))

    def window(self, name: str | None) -> dict | None:
        """窗口声明 name 下的 {"fps": 四指纹, "formal": {参数键: 正式值}};声明不在 → None。"""
        if not name or not S.study_path(self.app, name, self.apps_dir).exists():
            return None

        def calc():
            study = S.load_study(S.study_path(self.app, name, self.apps_dir))
            mod = S.import_app(study)
            formal = mod.Params.from_yaml(S.app_dir(mod) / study.BASE_YAML).to_dict()
            return {"fps": ledger.fingerprints_for(mod, S.base_snapshot(mod, study)), "formal": _flat(formal)}
        return self._memo(("window", name), calc)

    def app_level(self, wide: dict | None) -> dict:
        """按 pattern 发现约定找 app 模块(与优势检查同一取法),正式参数 ⊕ wide 下的现值。"""
        def calc():
            mod = importlib.import_module(edge._app_module(self.app))
            formal = mod.Params.from_yaml(S.app_dir(mod) / "params.yaml").to_dict()
            return {"fps": ledger.fingerprints_for(mod, apply_overrides(formal, wide or {}, {})),
                    "formal": _flat(formal)}
        return self._memo(("app", S.canonical_hash(wide or {})), calc)

    def calendar(self) -> pd.DatetimeIndex:
        if self._calendar is None:
            self._calendar = holdout.trading_calendar(REPO / self.cfg.data_dir)
        return self._calendar


def _fp(entry: dict | None, key: str):
    if entry is None:
        return None
    return "!" + entry["error"] if "error" in entry else entry["fps"][key]


# ---------------------------------------------------------------- 轮次

class _Round:
    """按写入顺序切出当前轮。closed = 最后一条定案 / 否决之后没有选参记录。
    lo = 本轮第一条记录的下标;sel_hi = 选参证据的上界(收尾轮 = 定案处);group = 收尾的那组定案 / 否决。"""

    def __init__(self, recs: list):
        closes = [i for i, r in enumerate(recs) if _is_close(r)]
        self.close = closes[-1] if closes else None
        after = recs[self.close + 1:] if self.close is not None else recs
        self.closed = self.close is not None and not any(_is_selection(r) for r in after)
        if self.closed:
            sel = [i for i in range(self.close) if _is_selection(recs[i])]
            prev = [i for i in closes if sel and i < sel[-1]]
            self.lo = prev[-1] + 1 if prev else 0
            self.sel_hi = self.close
            self.group = [i for i in closes if i > (sel[-1] if sel else self.lo - 1)]
        else:
            self.lo = self.close + 1 if self.close is not None else 0
            self.sel_hi = len(recs)
            self.group = []


# ---------------------------------------------------------------- 1. 被打断的长任务

def _scan_states(root: Path, cfg, confirm_role) -> list:
    """扫描输出目录逐个体检:优势检查目录 edge/ 与每个带 longtable/ 的窗口目录。

    确认窗扫描目录不是训练扫描:confirm_role(窗口名) → {"confirm_window", "role"}(不是确认窗 → None)。
    role = current(属于本轮验证清单,续跑 = 再开那段验证数据)/ freezing(清单还没冻结完,续跑 = 重新冻结清单)/
    stale(没用上的清单留下的,只提示)。"""
    out, universes = [], {}
    if not root.is_dir():
        return out
    for d in sorted(p for p in root.iterdir() if p.is_dir()):
        conf = confirm_role(d.name)
        found = _dir_states(d, cfg, universes, conf)
        for h in found if conf else ():
            h["confirm_window"] = conf["confirm_window"]
            if conf["role"] == "stale":
                h.update(blocking=False, action=None, why=h["why"] + "(一份没用上的验证清单留下的,不影响现在的流程)")
            else:
                h["stage"] = "preregister" if conf["role"] == "freezing" else f"validate_{conf['confirm_window']}"
                if h["action"] != "rescan":
                    h["action"] = "preregister" if conf["role"] == "freezing" else "validate"
        out += found
    return out


def _dir_states(d: Path, cfg, universes: dict, conf: dict | None) -> list:
    """一个扫描输出目录的半截状态;universes 缓存各股票范围的应扫全集。"""
    if d.name == edge.WINDOW:
        shard_dirs, symbol_dirs, meta_p, what = edge.SHARD_DIRS, edge.SHARD_DIRS, d / "run_meta.json", "优势检查的扫描"
    elif (d / "longtable").is_dir():
        shard_dirs, symbol_dirs, meta_p = MS.SHARD_DIRS, ("longtable", "baseline"), d / "longtable" / "run_meta.json"
        what = f"{holdout.WINDOW_WORDS[conf['confirm_window']]}的扫描" if conf else f"「{d.name}」这批扫描"
    else:
        return []
    if not meta_p.exists():
        return []
    meta = json.loads(meta_p.read_text(encoding="utf-8"))
    committed = MS.committed_shards(d)
    parts = [p for sub in shard_dirs for p in sorted((d / sub).glob("part-*.parquet"))]
    tmps = [p for sub in shard_dirs for p in sorted((d / sub).glob("part-*.parquet.tmp"))]
    if committed is None and (parts or tmps):
        if d.name != edge.WINDOW and not all(k in meta for k in NEW_CALIBER_KEYS):
            return [_half("legacy_scan", None, f"{what}是旧格式,不能接着扫;以后要用得重新扫描",
                          blocking=False, window=d.name)]
        return [_half("scan_without_commit_list", None,
                      f"{what}在第一批结果提交之前被打断,已经写下的结果判断不了是否完整,不能接着扫",
                      blocking=True, action="rescan", window=d.name)]
    out = []
    orphans = sorted({p.name.removesuffix(".tmp") for p in parts + tmps if p.name not in (committed or set())})
    if orphans:
        out.append(_half("uncommitted_shards", None,
                         f"{what}上次写到一半被打断,有 {len(orphans)} 批结果没写完(续跑时先删掉这几批、重扫这几批股票)",
                         blocking=True, action="resume_scan", window=d.name, evidence={"shards": orphans}))
    if "ticker_regex" in meta:
        regex, basis, where = meta["ticker_regex"], "按上次扫描用的股票范围", "run_meta"
    else:
        regex, basis, where = cfg.ticker_regex, "扫描记录里没写股票范围,按当前设置的股票范围", "settings"
    if regex not in universes:
        from path2_web.scan import _list_pkls
        universes[regex] = {p.stem for p in _list_pkls(str(REPO / cfg.data_dir), regex)}
    universe = universes[regex]
    done, _ = MS._done_symbols(d, symbol_dirs)
    missing = universe - done
    if missing:
        scope = "全部股票" if regex is None else f"代码匹配 {regex} 的股票"
        out.append(_half("scan_interrupted", None,
                         f"{what}还有 {len(missing)} 只股票没扫完({basis}算:{scope},应扫 {len(universe)} 只,"
                         "含上次出错待重试的)",
                         blocking=True, action="resume_scan", window=d.name,
                         evidence={"n_missing": len(missing), "n_universe": len(universe),
                                   "ticker_regex": regex, "universe_basis": where}))
    log = d / "compare_longtable.log"
    if (conf is None and d.name != edge.WINDOW and log.exists()
            and not any("mismatch=" in ln for ln in log.read_text(encoding="utf-8").splitlines())):
        out.append(_half("compare_incomplete", None, f"{what}的一致性验证没跑完,没有得出结论",
                         blocking=True, action="rerun_compare", window=d.name))
    if conf and (d / "labels").is_dir():
        segs = {p.name for p in (d / "segments").glob("part-*.parquet") if p.name in (committed or set())}
        lack = sorted(segs - {p.name for p in (d / "labels").glob("part-*.parquet")})
        if lack:
            out.append(_half("labels_incomplete", None, f"{what}的涨跌结果只补算了一部分,还差 {len(lack)} 批",
                             blocking=True, action="validate", window=d.name, evidence={"shards": lack}))
    return out


# ---------------------------------------------------------------- 推导

class _Derivation:
    def __init__(self, app: str, recs: list, now: _Now, cfg, root: Path):
        self.app, self.recs, self.now, self.cfg, self.root = app, recs, now, cfg, root
        r = self.rnd = _Round(recs)
        n = len(recs)
        self.i_open = _last(recs, 0, n, _kind("open"))
        self.i_edge = _last(recs, r.lo, r.sel_hi, _kind("edge"))
        self.i_ranges = _last(recs, r.lo, r.sel_hi, _ruling("ranges"))
        self.i_delta = _last(recs, r.lo, r.sel_hi, _ruling("delta"))
        self.i_screen = _last(recs, r.lo, r.sel_hi, _select("screen"))
        self.i_delete = _last(recs, r.lo, r.sel_hi, lambda rec: _topic(rec) == "delete_gate" and bool(rec["data"]["value"]))
        self.stale = self.i_screen is not None and self.i_delete is not None and self.i_delete > self.i_screen
        self.i_mech = (None if self.i_screen is None
                       else _last(recs, self.i_screen + 1, r.sel_hi, _ruling("mechanism")))
        self.i_find = _last(recs, r.lo, r.sel_hi, _select("find"))
        self.i_pre = _last(recs, r.lo, n, _round_manifest)
        self.hash = recs[self.i_pre]["data"]["manifest_hash"] if self.i_pre is not None else None
        self.i_power = None if self.hash is None else _last(recs, 0, n, _ruling("power_notified", self.hash))
        self.i_x = {w: None if self.hash is None else _last(
            recs, self.i_pre + 1, n, lambda rec, w=w: rec["kind"] == "extrapolate"
            and rec["data"]["manifest_hash"] == self.hash and rec["data"]["confirm_window"] == w)
            for w in ledger.CONFIRM_NAMES}
        self.i_dec = _last(recs, 0, n, _kind("decide"))
        self.landed = None
        if self.i_dec is not None:
            dec = recs[self.i_dec]
            self.dec_window = dec["data"].get("window") or DEFAULT_DECIDE_WINDOW
            self.landed = _same(dec["base_fingerprint"], _fp(now.window(self.dec_window), "base_fingerprint"))
        self.train = recs[self.i_open]["data"]["train"] if self.i_open is not None else None
        sc = recs[self.i_screen]["data"] if self.i_screen is not None and not self.stale else None
        self.no_candidates = (not r.closed and sc is not None and not sc.get("joint_axes") and self.i_delete is None)
        self.decision = _decision(recs, r.group) if r.closed else None
        self.stages: dict = {}
        self.awaiting_validation = False

    # ---- 比对 ----
    def _explained(self, i: int) -> bool:
        return self.landed is True and self.i_dec is not None and i < self.i_dec

    def _same_train(self, win: dict | None):
        if self.train is None or win is None:
            return None
        if _span(win) == _span(self.train):
            return True
        cal = self.now.calendar()

        def trading(w):
            days = cal[(cal >= pd.Timestamp(w["start"])) & (cal <= pd.Timestamp(w["end"]))]
            return (days[0], days[-1]) if len(days) else (w["start"], w["end"])
        return trading(win) == trading(self.train)

    def _check(self, i: int, base_entry: dict | None, src_entry: dict | None, *, window: bool) -> dict:
        rec = self.recs[i]
        drift = {"source": _same(rec["source_fingerprint"], _fp(src_entry, "source_fingerprint")),
                 "ruler": _same(rec["ruler_fingerprint"], self.now.ruler()),
                 "base": _same(rec["base_fingerprint"], _fp(base_entry, "base_fingerprint")),
                 "window": self._same_train(rec["window"]) if window else None}
        if drift["base"] is False and self._explained(i):
            drift["base"] = None
            drift["base_note"] = "这一步做在定案之前,之后底座的变化来自定案本身"
        errors = [e["error"] for e in (base_entry, src_entry) if e and "error" in e]
        if errors:
            drift["error"] = errors[0]
        return drift

    def _done(self, i: int, drift: dict, why: str, evidence: dict | None = None) -> dict:
        bad = [k for k in ("base", "source", "ruler", "window") if drift.get(k) is False]
        if drift.get("error"):
            why += f";现在的代码或参数算不出对照值({drift['error']})"
        elif bad:
            why += ";" + "、".join(DRIFT_WORDS[k] for k in bad)
        return _stage(True, not bad, why, {"record": _rec_ev(self.recs, i), "drift": drift, **(evidence or {})})

    def _confirm_role(self, name: str) -> dict | None:
        """确认窗扫描目录(confirm_<往前|前向>_<冻结的扫描声明哈希前 8 位>)归哪份清单;不是确认窗 → None。"""
        import tune
        m = re.fullmatch(rf"{re.escape(tune.CONFIRM_PREFIX)}({'|'.join(ledger.CONFIRM_NAMES)})_[0-9a-f]{{8}}", name)
        if m is None:
            return None
        owners = [i for i, rec in enumerate(self.recs)
                  if _round_manifest(rec) and tune._confirm_name(m.group(1), rec["data"]["manifest"]["confirm_scan"]) == name]
        if owners:
            role = "current" if self.i_pre in owners else "stale"
        else:
            role = "freezing" if self.i_pre is None else "stale"
        return {"confirm_window": m.group(1), "role": role}

    def _window_users(self, i_open: int) -> dict:
        conf = self.recs[i_open]["data"]["confirm"]
        return {w: [i for i, rec in enumerate(self.recs)
                    if rec["kind"] == "extrapolate" and _span(rec["window"]) == _span(conf[w])]
                for w in ledger.CONFIRM_NAMES}

    # ---- 阶段 ----
    def _pre_decide(self, why: str) -> tuple[str, str]:
        if self.rnd.closed:
            return "skipped", "这一轮已经定案,定案之前没做这一步,不再补做"
        return "required", why

    def _flags(self) -> list | None:
        """最近一次筛选里要动的改动(工作点上分辨得出的检测参数翻转、删了不亏的闸)带的提醒;结果文件不在 → None。"""
        p = Path(self.recs[self.i_screen]["data"].get("out_dir", "")) / "result.json"
        p = p if p.is_absolute() else REPO / p
        if not p.is_file():
            return None
        out = []
        for row in json.loads(p.read_text(encoding="utf-8")).get("contrasts", []):
            if row.get("base") != "working" or not ((row.get("kind") == "d_flip" and row.get("survive"))
                                                     or (row.get("kind") == "gate_off" and row.get("ni_pass"))):
                continue
            hit = [k for k, on in (("did", row.get("did_z") is not None and abs(row["did_z"]) >= screen.Z_FLAG),
                                   ("year", row.get("flag_year") is True), ("time", row.get("flag_time") is True),
                                   ("drift", row.get("flag_drift") is True)) if on]
            if hit:
                out.append({"param": row.get("axis"), "level": row.get("level"), "flags": hit})
        return out

    def _validation_scope(self) -> tuple[str, str | None]:
        r = self.rnd
        if not r.closed:
            if self.no_candidates and self.i_pre is None:
                return "skipped", "筛选里没有分辨得出的改动,没有要验证的候选"
            return "required", None
        status = self.decision["status"]
        complete = self.i_pre is not None and all(i is not None for i in self.i_x.values())
        if self.i_pre is not None and (self.i_pre > r.close or complete or status == "unverified"):
            return "required", None
        if status == "veto":
            return "skipped", "上一轮已经整体否决"
        if status == "withdrawn":
            return "skipped", "定案已经撤回"
        if status != "unverified":
            return "skipped", "定案时已标明经过独立验证"
        if self.i_open is not None and not any(self._window_users(self.i_open).values()):
            return "required", None
        return "skipped", "开局核对留出的验证数据已经用过,要等攒出新数据才能再验证"

    def build(self) -> None:
        recs, r, now, st = self.recs, self.rnd, self.now, self.stages
        # 开局核对
        if self.i_open is None:
            st["open"] = _stage(False, None, "还没做开局核对:训练数据与留出的验证数据都没划定")
        else:
            op = recs[self.i_open]
            users = self._window_users(self.i_open)
            other = [i for us in users.values() for i in us if recs[i]["data"]["manifest_hash"] != self.hash]
            ev = {"record": _rec_ev(recs, self.i_open), "train": _span(op["data"]["train"]),
                  "confirm": {w: _span(op["data"]["confirm"][w]) for w in ledger.CONFIRM_NAMES},
                  "opened_at_lines": {w: [i + 1 for i in us] for w, us in users.items()}}
            if not r.closed and other:
                st["open"] = _stage(True, False, "这次开局核对留出的验证数据已经被别的验证清单打开过,这一轮不能再用;"
                                                 "要等攒出新数据后重新开局核对", ev)
            else:
                st["open"] = _stage(True, True, f"训练数据取 {op['data']['train']['start']} 到 "
                                                f"{op['data']['train']['end']} 的买点", ev)
        # 优势检查
        if self.i_edge is None:
            scope, why = self._pre_decide("还没做优势检查")
            st["edge"] = _stage(False, None, why, scope=scope)
        else:
            e = recs[self.i_edge]
            wide = e["data"].get("wide_overrides")
            entry = now.app_level(wide)
            drift = self._check(self.i_edge, entry if wide is not None else None, entry, window=True)
            verdict = edge.VERDICT_WORDS.get(e["data"]["verdict"], str(e["data"]["verdict"]))
            st["edge"] = self._done(self.i_edge, drift, f"优势检查的结论:{verdict}", {"verdict": e["data"]["verdict"]})
        # 定范围
        have = {"ranges": self.i_ranges, "delta": self.i_delta}
        missing = [t for t, i in have.items() if i is None]
        ev = {"rulings": {t: _rec_ev(recs, i) for t, i in have.items()}}
        if not missing:
            st["ranges"] = _stage(True, True, "档位范围与最小关心改进都已裁定", ev)
        else:
            scope, why = self._pre_decide(f"还没裁定{'、'.join(TOPIC_WORDS[t] for t in missing)}")
            st["ranges"] = _stage(False, None, why, {**ev, "missing": missing}, scope)
        # 筛选
        if self.i_screen is None or self.stale:
            scope, why = self._pre_decide("删闸裁定之后还没在新参数上重算筛选" if self.stale else "还没做筛选")
            st["screen"] = _stage(False, None, why, {"record": _rec_ev(recs, self.i_screen),
                                                      "delete_gate_ruling": _rec_ev(recs, self.i_delete)}, scope)
        else:
            sc = recs[self.i_screen]
            entry = now.window(sc["data"].get("window_name"))
            drift = self._check(self.i_screen, entry, entry or now.app_level(None), window=True)
            surv = sc["data"].get("survivors") or []
            st["screen"] = self._done(self.i_screen, drift, f"筛选里分辨得出的改动:{'、'.join(surv) if surv else '没有'}",
                                      {"window": sc["data"].get("window_name"), "joint_axes": sc["data"].get("joint_axes")})
        # 机制复核
        if not st["screen"]["done"]:
            if r.closed:
                st["mechanism"] = _stage(False, None, "这一轮已经定案,定案之前没做这一步,不再补做", scope="skipped")
            else:
                st["mechanism"] = _stage(False, None, "要等筛选结果出来,才知道要不要机制复核", scope="unknown")
        else:
            flags = self._flags()
            if flags == []:
                st["mechanism"] = _stage(False, None, "最近一次筛选里要动的改动都没有带提醒(" + "、".join(FLAG_WORDS.values())
                                         + "),不需要机制复核", {"flags": []}, "skipped")
            else:
                need = ("筛选结果文件不在了,看不出要不要复核,按需要处理" if flags is None else
                        ";".join(f"{f['param']}:{'、'.join(FLAG_WORDS[k] for k in f['flags'])}" for f in flags))
                ev = {"flags": flags, "record": _rec_ev(recs, self.i_mech)}
                if self.i_mech is not None:
                    st["mechanism"] = _stage(True, True, f"已对带提醒的改动做过机制复核({need})", ev)
                else:
                    scope, why = self._pre_decide(f"筛选里要动的改动带提醒,需要机制复核:{need}")
                    st["mechanism"] = _stage(False, None, why, ev, scope)
        # 联合调参
        if self.i_find is not None:
            f = recs[self.i_find]
            entry = now.window(f["data"].get("window_name"))
            drift = self._check(self.i_find, entry, entry or now.app_level(None), window=True)
            st["joint"] = self._done(self.i_find, drift, "联合调参已做", {"window": f["data"].get("window_name")})
        elif r.closed:
            st["joint"] = _stage(False, None, "这一轮已经定案,定案之前没做这一步,不再补做", scope="skipped")
        elif st["screen"]["done"] and not recs[self.i_screen]["data"].get("joint_axes"):
            st["joint"] = _stage(False, None, "筛选里没有要一起调的参数,不做联合调参", scope="skipped")
        elif self.i_pre is not None:
            st["joint"] = _stage(False, None, "候选直接取自筛选里分辨得出的单个改动,没做联合调参", scope="skipped")
        else:
            st["joint"] = _stage(False, None, "还没做联合调参")
        # 冻结验证清单、两段验证数据
        scope, skip_why = self._validation_scope()
        if r.closed and scope == "required" and not all(i is not None for i in self.i_x.values()):
            self.awaiting_validation = True
        if self.i_pre is None:
            why = skip_why or "还没冻结验证清单"
            if self.awaiting_validation:
                why = ("定案已落地、待独立验证" if self.landed else "上次定案还没经过独立验证") + ",先冻结验证清单"
            st["preregister"] = _stage(False, None, why, scope=scope)
        else:
            p = recs[self.i_pre]
            drift = self._check(self.i_pre, None, now.app_level(None), window=False)
            power = p["data"]["expected_power"]
            st["preregister"] = self._done(
                self.i_pre, drift, "验证清单已冻结(预期把握:" + "、".join(
                    f"{holdout.WINDOW_WORDS[w]}约 {power[w]:.0%}" for w in ledger.CONFIRM_NAMES) + ")",
                {"manifest_hash": self.hash, "power_notified": _rec_ev(recs, self.i_power)})
            st["preregister"]["evidence"]["scope"] = scope
        for s, w in CONFIRM_OF.items():
            if self.i_x[w] is None:
                why = skip_why or ("还没冻结验证清单" if self.i_pre is None else f"还没{STAGE_WORDS[s]}")
                st[s] = _stage(False, None, why, scope=scope)
            else:
                drift = self._check(self.i_x[w], None, now.app_level(None), window=False)
                st[s] = self._done(self.i_x[w], drift, f"已{STAGE_WORDS[s]}")
                st[s]["evidence"]["scope"] = scope
        # 定案
        if r.closed:
            last = recs[r.group[-1]]
            if last["kind"] == "ruling":
                st["decide"] = _stage(True, True, f"{last['ts'][:10]} 整体否决,维持现役参数",
                                      {"record": _rec_ev(recs, r.group[-1])})
            else:
                entry = now.window(self.dec_window)
                drift = self._check(self.i_dec, entry, entry or now.app_level(None), window=False)
                if drift["base"] is False:
                    drift["base_note"] = "正式参数在定案之后被改过"
                dn = self.decision
                when = f"{dn['last_date']} " if dn["last_date"] != dn["date"] else ""
                st["decide"] = self._done(self.i_dec, drift, f"{dn['date']} 定案:{dn['changes']}({when}{_status_words(dn)})",
                                          {"records": [_rec_ev(recs, i) for i in r.group], "window": self.dec_window,
                                           **dn})
        elif self.no_candidates:
            st["decide"] = _stage(False, None, "筛选里没有分辨得出的改动,维持现役参数", scope="skipped")
        else:
            st["decide"] = _stage(False, None, "还没定案")
        # 失效顺延:某阶段自身失效,其后已完成的阶段跟着作废(开局核对只管验证数据用没用过,不顺延)
        broken = None
        for s in STAGES[1:]:
            if not st[s]["done"]:
                continue
            if st[s]["valid"] is False:
                broken = broken or s
            elif broken:
                st[s]["valid"] = False
                st[s]["why"] += f";前面的「{STAGE_WORDS[broken]}」已失效,这一步跟着作废"
                st[s]["evidence"]["invalid_by"] = broken

    # ---- 2. 指纹漂移 ----
    def _param_diff(self) -> str:
        dec = self.recs[self.i_dec]
        entry = self.now.window(self.dec_window)
        formal = entry["formal"] if entry and "error" not in entry else {}
        diffs = [f"{k} 定案时是 {_v(new)}、现在是 {_v(formal[k])}"
                 for k, (_, new) in dec["data"]["params"].items() if k in formal and formal[k] != new]
        diffs += [f"{k} 定案时是 {_v(v)}、现在是 {_v(formal[k])}"
                  for k, v in dec["data"]["depends_on"].items() if k in formal and formal[k] != v]
        return ";".join(diffs) if diffs else "改动不在这次定案涉及的参数里(可能是别的参数,或研究声明里的放开值)"

    def _drift_states(self) -> list:
        out, recs = [], self.recs
        if self.landed is True:
            out.append(_half("params_landed", "decide", f"{recs[self.i_dec]['ts'][:10]} 的定案已经写进正式参数",
                             blocking=False))
        own = {s: self.stages[s]["evidence"].get("drift", {}) for s in STAGES if self.stages[s]["done"]}
        bad = {k: [s for s in STAGES if own.get(s, {}).get(k) is False] for k in ("base", "source", "ruler", "window")}
        first = next((s for s in STAGES if any(s in v for v in bad.values())), None)
        if bad["base"]:
            what = (f"最后一次定案之后正式参数被改过({self._param_diff()})" if self.landed is False
                    else "正式参数(或研究声明里的放开值)在这些步骤之后被改过")
            out.append(_half("params_changed", first, f"{what},{'、'.join(STAGE_WORDS[s] for s in bad['base'])}的结论对不上了",
                             blocking=True, action="confirm_redo", stages=bad["base"]))
        elif self.landed is False:
            out.append(_half("params_changed", None, f"最后一次定案之后正式参数被改过({self._param_diff()});"
                                                     "这一轮的步骤都做在改动之后,不受影响", blocking=False))
        code = [s for s in STAGES if s in bad["source"] or s in bad["ruler"]]
        if code:
            out.append(_half("code_changed", first, f"检测代码或涨跌结果的算法在{'、'.join(STAGE_WORDS[s] for s in code)}之后改过,"
                                                    "这些结论要重做", blocking=True, action="confirm_redo", stages=code))
        if bad["window"]:
            out.append(_half("window_changed", first, f"{'、'.join(STAGE_WORDS[s] for s in bad['window'])}不是在这次开局核对"
                                                     "划定的训练数据上做的", blocking=True, action="confirm_redo",
                             stages=bad["window"]))
        if self.stages["open"]["done"] and self.stages["open"]["valid"] is False:
            out.append(_half("confirm_windows_used", "open", self.stages["open"]["why"], blocking=True,
                             action="open_round"))
        for i, rec in enumerate(recs):
            if rec["kind"] != "decide":
                continue
            entry = self.now.window(rec["data"].get("window") or DEFAULT_DECIDE_WINDOW)
            if not entry or "error" in entry:
                continue
            formal = entry["formal"]
            if any(formal.get(k) != new for k, (_, new) in rec["data"]["params"].items()):
                continue   # 已被之后的改动取代,不再生效
            diff = {k: [v, formal.get(k)] for k, v in rec["data"]["depends_on"].items() if formal.get(k) != v}
            if diff:
                out.append(_half("background_changed", "decide",
                                 f"{rec['ts'][:10]} 的定案({_changes(recs, [i])})依赖的背景参数变了:"
                                 + ";".join(f"{k} 定案时是 {_v(a)}、现在是 {_v(b)}" for k, (a, b) in diff.items()),
                                 blocking=True, action="review_background", evidence={"line": i + 1, "diff": diff}))
        return out

    # ---- 3. 待落账的裁定 ----
    def _pending(self) -> list:
        out, recs, st = [], self.recs, self.stages
        if not self.rnd.closed:
            if st["edge"]["done"] and st["edge"]["valid"] and not st["ranges"]["done"]:
                missing = st["ranges"]["evidence"]["missing"]
                out.append(_half("ruling_pending", "ranges",
                                 f"优势检查做完了({st['edge']['why']}),还没裁定{'、'.join(TOPIC_WORDS[t] for t in missing)}",
                                 blocking=True, action="ask_ruling", topic=missing[0]))
            if (st["screen"]["done"] and st["screen"]["valid"] and st["mechanism"]["evidence"]["scope"] == "required"
                    and not st["mechanism"]["done"]):
                out.append(_half("ruling_pending", "mechanism", st["mechanism"]["why"], blocking=True,
                                 action="ask_ruling", topic="mechanism"))
        if self.i_pre is None or st["preregister"]["valid"] is False:
            return out
        pre = recs[self.i_pre]
        if self.i_power is None:
            out.append(_half("ruling_pending", "preregister", "验证清单已经冻结,预期把握还没告诉你", blocking=True,
                             action="ask_ruling", topic="power_notified"))
        else:
            for w in ledger.CONFIRM_NAMES:
                if self.i_x[w] is not None:
                    continue
                power = pre["data"]["expected_power"][w]
                if power < LOW_POWER and _last(recs, 0, len(recs), _ruling("open_low_power", self.hash)) is None:
                    out.append(_half("ruling_pending", f"validate_{w}",
                                     f"按这份清单,{holdout.WINDOW_WORDS[w]}验证出结果的预期把握只有约 {power:.0%},不到一半",
                                     blocking=True, action="ask_ruling", topic="open_low_power", confirm_window=w))
                break
        opened = [self.i_x[w] for w in ledger.CONFIRM_NAMES]
        if all(i is not None for i in opened) and _last(recs, max(opened) + 1, len(recs), _is_close) is None:
            out.append(_half("ruling_pending", "decide", "两段留出的验证数据都打开了,还没拍板", blocking=True,
                             action="ask_ruling", topic="decide"))
        return out

    # ---- 4. 最早未完成的阶段 ----
    def _unrecorded(self) -> dict:
        """产物在、记录缺的阶段 → 产物路径。选参阶段只在本轮进行中时查(收尾轮定案之前的步骤不再补做),
        不看确认窗扫描目录;验证阶段查本轮清单那段确认窗下的验证结果文件(不论轮次是否收尾)。"""
        seen = {(p, h) for rec in self.recs for p, h in rec["ref"].items()}
        out = {}
        if not self.rnd.closed and self.root.is_dir():
            floor = {"edge": self.i_edge, "screen": self.i_screen, "joint": self.i_find}
            cands = {"edge": [self.root / edge.WINDOW / "edge_report.md"],
                     "screen": [p for p in sorted(self.root.glob(f"*/{screen.SCREEN_DIR_PREFIX}*/report.md"))
                                if self._confirm_role(p.parent.parent.name) is None],
                     "joint": [p for p in sorted(self.root.glob("*/region_report.md"))
                               if self._confirm_role(p.parent.name) is None]}
            for s, paths in cands.items():
                since = [datetime.fromisoformat(self.recs[i]["ts"]) for i in (self.rnd.close, floor[s]) if i is not None]
                hits = [screen.artifact_path(p) for p in paths if p.is_file()
                        and not (since and datetime.fromtimestamp(p.stat().st_mtime) <= max(since))
                        and (screen.artifact_path(p), ledger.sha256_file(p)) not in seen]
                if hits:
                    out[s] = hits
        if self.i_pre is not None:
            import tune
            decl = self.recs[self.i_pre]["data"]["manifest"]["confirm_scan"]
            for s, w in CONFIRM_OF.items():
                p = self.root / tune._confirm_name(w, decl) / f"{self.hash[:12]}_{w}.json"
                if (self.i_x[w] is None and p.is_file()
                        and (screen.artifact_path(p), ledger.sha256_file(p)) not in seen):
                    out[s] = [screen.artifact_path(p)]
        return out

    def _gate_family_pending(self, w: str) -> bool:
        if self.i_pre is None or self.i_x[w] is None or not self.recs[self.i_pre]["data"]["manifest"].get("gate_family"):
            return False
        return _last(self.recs, 0, len(self.recs), lambda rec: rec["kind"] == "verify"
                     and rec["data"].get("manifest_hash") == self.hash and rec["data"].get("confirm_window") == w) is None

    def _stage_states(self, unrecorded: dict) -> list:
        out = []
        for s, paths in unrecorded.items():
            extra = {"evidence": {"paths": paths}}
            if s in CONFIRM_OF:
                extra["confirm_window"] = CONFIRM_OF[s]
                why = (f"上次{STAGE_WORDS[s]}的检验结果已经写出、但没记进账本,所以这段还不算打开过;重跑这一步补上记录,"
                       "扫描结果复用,结论不变,也不算多开一次")
            else:
                if s != "edge":      # 筛选 / 联合调参的结果按窗口放:<窗口>/screen_…/report.md、<窗口>/region_report.md
                    extra["window"] = Path(paths[0]).parent.parent.name if s == "screen" else Path(paths[0]).parent.name
                why = f"上次{STAGE_WORDS[s]}的结果已经写出、但没记进账本;重跑这一步补上记录,扫描结果复用,结论不变,也不算多挑一次"
            out.append(_half("artifact_unrecorded", s, why, blocking=not self.stages[s]["done"],
                             action=STAGE_ACTIONS[s], **extra))
        if self.stale:
            off = self.recs[self.i_delete]["data"]["value"]
            what = "、".join(f"{k} = {_v(v)}" for k, v in off.items()) if isinstance(off, dict) else str(off)
            out.append(_half("screen_stale_after_delete", "screen",
                             f"按删闸后的参数(关掉 {what})在同一批扫描上重算筛选,不需要新扫描", blocking=True,
                             action="screen", window=self.recs[self.i_screen]["data"].get("window_name"),
                             working_point=off))
        opened = [w for w in ledger.CONFIRM_NAMES if self.i_x[w] is not None]
        if self.i_pre is not None and len(opened) < len(ledger.CONFIRM_NAMES):
            lack = [w for w in ledger.CONFIRM_NAMES if self.i_x[w] is None]
            out.append(_half("validation_incomplete", f"validate_{lack[0]}",
                             f"验证清单已冻结,{'、'.join(holdout.WINDOW_WORDS[w] for w in lack)}还没打开",
                             blocking=True, action="validate", confirm_window=lack[0]))
        for w in opened:
            if self._gate_family_pending(w):
                out.append(_half("gate_family_unchecked", f"validate_{w}",
                                 f"{holdout.WINDOW_WORDS[w]}已经打开,清单里保留的闸还没在上面补检",
                                 blocking=True, action="gate_family_check", confirm_window=w))
        return out

    def _step4(self, unrecorded: dict, states: list) -> dict | None:
        for s in STAGES:
            stg = self.stages[s]
            if stg["evidence"]["scope"] == "skipped":
                continue
            if stg["done"] and stg["valid"] is not False:
                if s in CONFIRM_OF:
                    gf = next((h for h in states if h["kind"] == "gate_family_unchecked" and h["stage"] == s), None)
                    if gf:
                        return gf
                continue
            if unrecorded.get(s):
                return next(h for h in states if h["kind"] == "artifact_unrecorded" and h["stage"] == s)
            if s == "screen" and self.stale:
                return next(h for h in states if h["kind"] == "screen_stale_after_delete")
            extra = {"stage": s}
            if s in CONFIRM_OF:
                extra["confirm_window"] = CONFIRM_OF[s]
            elif s in ("ranges", "mechanism"):
                extra["topic"] = "mechanism" if s == "mechanism" else stg["evidence"].get("missing", ["ranges"])[0]
            return {"action": STAGE_ACTIONS[s], "why": stg["why"], **extra}
        return None

    # ---- 5. 全部完成 ----
    def _recheck_date(self) -> tuple | None:
        """(最早可做独立验证的日期, 依据)。按这一轮所用开局核对的前向验证数据推:其涨跌结果看到的那天之后
        再攒满 RECHECK_SPAN 的买点,再等一个标签窗长看到它们的涨跌结果。"""
        recs, used = self.recs, None
        if self.i_x["forward"] is not None:
            win = _span(recs[self.i_x["forward"]]["window"])
            used = _last(recs, 0, len(recs), lambda rec: rec["kind"] == "open"
                         and _span(rec["data"]["confirm"]["forward"]) == win)
        i = used if used is not None else self.i_open
        if i is None:
            return None
        op = recs[i]
        fwd, horizon = op["data"]["confirm"]["forward"], op["label_horizon"]
        buy_end = pd.Timestamp(fwd["label_end"]) + RECHECK_SPAN
        date = ledger.label_end(buy_end, horizon, self.now.calendar())
        basis = (f"开局核对时数据到 {op['data']['data_end']},训练期之后留出的验证数据是 {fwd['start']} 到 {fwd['end']} "
                 f"的买点、涨跌结果看到 {fwd['label_end']};在那之后再攒满 1 年的买点(到 {_day(buy_end)}),"
                 f"再等 {horizon} 个交易日看到它们的涨跌结果")
        return date, basis

    def _step5(self) -> tuple[dict, list]:
        r, dn = self.rnd, self.decision
        if not r.closed:
            return {"action": "none", "why": "这一轮筛选里没有分辨得出的改动,维持现役参数"}, []
        if dn["status"] == "veto":
            return {"action": "none", "why": f"{dn['last_date']} 整体否决,维持现役参数;没有待验证的定案"}, []
        head = f"{dn['date']} 定案({dn['changes']})"
        if dn["status"] == "withdrawn":
            return {"action": "none", "why": f"{head}经独立验证后于 {dn['last_date']} 撤回,正式参数已改回原值;"
                                             "没有待验证的定案"}, []
        got = self._recheck_date()
        if got is None:
            return {"action": "none", "why": f"{head};没有开局核对记录,推不出下一次可做独立验证的日期"}, []
        date, basis = got
        extra = {"earliest": _day(date), "basis": basis}
        if dn["status"] == "confirmed":
            return {"action": "none", "why": f"{head}已通过独立验证;下一次可做独立验证的最早日期是 {_day(date)}({basis})",
                    **extra}, []
        if dn["status"] == "unverified":
            why = f"{head}还没经过独立验证,但留出的验证数据已经用过;最早 {_day(date)} 起可以用新数据验证({basis})"
        else:
            why = f"{head}经独立验证后暂定采纳,要等攒够新数据复验;最早 {_day(date)} 起可以复验({basis})"
        data_end = self.now.calendar()[-1]
        if data_end >= date:
            h = _half("revalidation_due", "decide", f"{why};现在数据已经到 {_day(data_end)},到期了", blocking=True,
                      action="revalidate", **extra)
            return {"action": "revalidate", "why": h["why"], **extra}, [h]
        return {"action": "none", "why": why, **extra}, []

    # ---- 汇总 ----
    def result(self) -> dict:
        self.build()
        scans = _scan_states(self.root, self.cfg, self._confirm_role)
        drift = self._drift_states()
        pending = self._pending()
        unrecorded = self._unrecorded()
        stage_states = self._stage_states(unrecorded)
        half = scans + drift + pending + stage_states
        step, nxt = None, None
        for k, group in ((1, scans), (2, drift), (3, pending)):
            hit = next((h for h in group if h["blocking"]), None)
            if hit:
                step, nxt = k, hit
                break
        if nxt is None:
            nxt = self._step4(unrecorded, stage_states)
            step = 4 if nxt else None
        if nxt is None:
            nxt, due = self._step5()
            half += due
            step = 5
        nxt = {"action": nxt["action"], "why": nxt["why"], **{k: nxt[k] for k in NEXT_KEYS if nxt.get(k) is not None}}
        return {"app": self.app,
                "stages": [{"name": s, **self.stages[s]} for s in STAGES],
                "next": nxt, "half_states": half, "text": self._text(step, nxt, half)}

    def _words(self, nxt: dict) -> str:
        a = nxt["action"]
        stage = STAGE_WORDS.get(nxt.get("stage"), "")
        cw = holdout.WINDOW_WORDS.get(nxt.get("confirm_window"), "")
        return {"resume_scan": "接着把没扫完的扫描跑完(已完成的部分不重扫)",
                "rescan": "清掉这批判断不了是否完整的扫描结果,重新扫描",
                "rerun_compare": "重新做一致性验证",
                "confirm_redo": f"先和你确认这些改动是不是有意的;是的话,从「{stage}」开始重做",
                "review_background": "在现在的背景参数下复核这条定案",
                "ask_ruling": f"请你裁定:{TOPIC_WORDS.get(nxt.get('topic'), '')}",
                "gate_family_check": f"在{cw}上补检清单里保留的闸(同一份清单,不算再开一次)",
                "open_round": "做开局核对", "edge": "做优势检查", "screen": "做筛选", "find": "做联合调参",
                "preregister": "冻结验证清单(写明要验证哪些改动、按什么规则判,在打开验证数据之前定死)",
                "validate": f"打开{cw}做独立验证",
                "adopt": "定案",
                "revalidate": "该暂定定案到期复验:先重新开局核对,划出新的验证数据",
                "none": "眼下没有要做的"}[a]

    def _text(self, step: int, nxt: dict, half: list) -> str:
        """给用户看的摘要:只说业务层的话。"""
        recs = self.recs
        if step == 1:
            head = "有没跑完的长任务。"
        elif step == 2:
            head = {"params_changed": "正式参数被改过。", "code_changed": "代码变了。",
                    "window_changed": "训练数据的范围变了。", "confirm_windows_used": "留出的验证数据已经用过。",
                    "background_changed": "已定案改动依赖的背景参数变了。"
                    }[next(h for h in half if h["blocking"] and h["action"] == nxt["action"])["kind"]]
        elif step == 3:
            head = "有一项裁定还没落账。"
        elif step == 4 and self.awaiting_validation:
            head = "定案已落地、待独立验证。" if self.landed else "上次定案还没经过独立验证。"
        elif step == 4:
            head = f"进行到「{STAGE_WORDS[nxt['stage']]}」。" if nxt.get("stage") else "有一步没做完。"
        else:
            head = "暂定定案到期复验。" if nxt["action"] == "revalidate" else "全部完成。"
        lines = [head]
        if self.landed and self.i_dec is not None and step != 1:
            group = [i for i in range(self.i_dec + 1) if recs[i]["kind"] == "decide"
                     and not any(_is_selection(recs[j]) for j in range(i, self.i_dec + 1))]
            dn = _decision(recs, group)
            lines.append(f"{dn['date']} 的定案已经写进正式参数:{dn['changes']}({_status_words(dn)})。")
        if step == 4 and self.awaiting_validation and self.i_pre is None and self.i_open is not None:
            conf = recs[self.i_open]["data"]["confirm"]
            lines.append("开局核对留出的两段验证数据都还没用过("
                         + ";".join(f"{holdout.WINDOW_WORDS[w]}:{conf[w]['start']} 到 {conf[w]['end']} 的买点"
                                    for w in ledger.CONFIRM_NAMES) + "),现在就可以做独立验证。")
        elif not (step == 4 and self.awaiting_validation):
            lines.append(nxt["why"] + "。")
        lines.append(f"下一步:{self._words(nxt)}。")
        lines += [f"附注:{h['why']}。" for h in half if not h["blocking"] and h["kind"] != "params_landed"]
        return "\n".join(lines)


def derive(app: str, *, cfg=None, apps_dir=None, out_root=None, calendar=None) -> dict:
    """推导 app 的调参进度。**只读,不写任何文件。**

    参数:
        cfg: tune.Settings(用到 data_dir、ticker_regex——应扫全集按它们列股票);缺省 = Settings()。
        apps_dir / out_root: 研究声明根目录(缺省 skill 的 apps/)、输出根目录(缺省 outputs/tune_gates)。
        calendar: 交易日历(缺省按 cfg.data_dir 探测;训练窗对比与复验日期要用)。
    返回 {"app", "stages": [{"name","done","valid","why","evidence"}...], "next": {"action","why", 可选
    "stage","window","working_point","topic","confirm_window","earliest","basis"}, "half_states": [...], "text"}。
    next["action"] 取值:resume_scan / rescan / rerun_compare / preregister / validate(1;确认窗扫描或标签没做完,
    续跑 = 重新冻结清单或再开那段验证数据)、confirm_redo / review_background / open_round(2)、ask_ruling(3,
    topic ∈ ranges / delta / mechanism / power_notified / open_low_power / decide)、gate_family_check /
    open_round / edge / screen / find / preregister / validate / adopt(4;产物在记录缺时也是重跑该步本身,带
    window / confirm_window;删闸之后重算筛选是 screen,带 window 与 working_point = 删闸裁定的取值)、
    revalidate / none(5)。
    half_states 每项 {"kind","stage","blocking","why","action", ...};blocking=False 的只作提示。
    text 是给用户看的人话摘要(业务层说法)。
    """
    if cfg is None:
        import tune
        cfg = tune.Settings()
    apps_dir = Path(apps_dir) if apps_dir else S.APPS_DIR
    root = (Path(out_root) if out_root else REPO / "outputs" / "tune_gates") / app
    return _Derivation(app, ledger.read(app), _Now(app, apps_dir, cfg, calendar), cfg, root).result()
