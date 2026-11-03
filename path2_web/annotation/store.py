"""标注存储:按机器追加批次文件,读的时候重放出当前状态。

为什么这样存
------------
标注是唯一靠用户手工做出来、丢了补不回的东西;pc 和 upc 两台机器都标,标注目录用 Syncthing 同步。所以:
- 每次保存只新增一个文件,从不修改或删除已有文件:两台同步时不会互相改坏;
- 文件名、对象编号都带机器名:两台各自新建不会撞名、撞号;
- 当前状态 = 把全部文件里的操作按(时间戳、机器名、序号)排好重放一遍:和文件的列举顺序无关,
  同一组文件在任何机器上重放出同一个状态。

批次文件
--------
文件名 `<机器名>-<时间戳>-<序号>.json`,例如 `pc-20261103T142530.123Z-7.json`:
- 机器名:配置的 machine(缺省取主机名,只许字母、数字、下划线,见 path2_web.config.machine_name);
- 时间戳:保存时刻的 UTC,精确到毫秒,定长,按字符串比就是先后。写入时取「当前时刻」与「目录里已有文件的
  最晚时间戳 + 1 毫秒」中较晚的那个:写的人看到过的修改一定排在它前面,两台机器的钟不准也不会把先后重放反;
- 序号:这台机器的第几个批次文件,接在本机已有的最大序号之后。

内容:
    {"schema": "path2_web.annotation/1",
     "data_fingerprint": <保存时本机训练段副本的指纹,读不到为 null>,
     "ops": [{"ts", "machine", "kind", "id", "base", "value"}, ...]}

每条操作(op)把一个对象改成新值:
- ts、machine:同文件名里的时间戳与机器名(每条操作自带,单拿出来也说得清是谁、什么时候改的);
- kind:feature(词)/ pattern / box(框)/ sample(样本);
- id:对象编号。词、框、样本的编号是 `w-<机器名>-<n>`、`b-<机器名>-<n>`、`s-<机器名>-<n>`。n 取自计数器:
  三种对象、两台机器共用一个序列,接在全部文件里用过的最大号之后,删掉的对象的号也不再用;编号带机器名,
  两台在同步前各自取号也不会撞。pattern 没有编号,用名字;
- base:写这条操作时看到的这个对象的最后一次修改,写成 `<那个文件名去掉 .json>#<第几条,从 0 起>`;新建为 null;
- value:改完后的整个对象;null 表示删除。

「改特征名」「合并」「拆回」都是新记的操作:改名 = 写一条 feature;合并 = 同一批里改写涉及的框、删掉被并的词;
拆回 = 再写一批把它们改回去(被删的词用原编号、base 取它被删的那次修改)。旧记录从不回头改。
读的时候从文件里认出还能拆回的合并(merges):同一批里删掉一个词、又把一些框从这个词改成别的词(当特征或当
属性),并且这个词到现在还没有放回词表。每条带上被删的词、并进的词和那些框改前改后的值,任何机器、刷新之后都能拆回。

重放与冲突
----------
文件按(时间戳、机器名、序号)排序,文件内按操作先后,逐条把对象设成 value。某条操作的 base 不是这个对象
当时的最后一次修改,说明写它的人没看到那次修改(两台机器同步前各改了一次,或读过标注之后另一台的文件才同步到):
照样后改的那次生效,同时记一条冲突(conflicts),写明对象、两次修改各是哪台机器什么时候做的。冲突只由文件
决定,任何机器重放出的冲突都一样;每条冲突以后一次修改的引用 later.ref 为准,前后两次读到的是同一条。
base 指向的修改本机还没有(那个文件还没同步到)时,不算冲突、照样生效,记进 unsynced:同步完它就消失,
到时如果真有冲突会出现在 conflicts 里。unsynced 为空,说明每条修改依据的文件本机都有。

状态的形状(会话读的就是它)
--------------------------
    {machine, data_fingerprint,
     features: [{id, name, definition?}],
     patterns: [{name, definition?, flags?}],
     charts:   [{symbol,
                 boxes:   [{id, feature, start, end, attrs?, note?, detach?, attach?}],
                 samples: [{id, date, pattern, judgment, members[], members_edited?, note?}]}]}

- machine 是读的这台机器;data_fingerprint 是标注所依据的训练段副本指纹:全部批次记的都是同一个时取它,
  批次之间不一致或还没有批次时为 null。拿它和本机副本的指纹比,就知道标注和眼下读的 K 线是不是同一份;
- 日期一律是 YYYY-MM-DD 字符串,不存 K 线下标;框不存系统事件编号;
- feature 是特征编号,框还没起名时为 null;attrs 是特征编号 → true / false,键不在就是 null(没看过);
- pattern 为 null 表示 unsorted;members 是冻结后的成员框编号,读的人不用重算推断;
- patterns[].flags 的形状是 [{feature, mapping_row}],本模块只校验形状、不解释它;
- 词、pattern 按第一次出现的先后排;charts 按代码排,框按(起点、终点、编号),样本按(样本日、编号)。

保存时的校验
------------
一批操作整体通过才写文件,否则一条也不写,BatchRejected.reasons 列出全部原因(code、message,以及涉及的
op 序号或样本、框编号):
- bad_op:形状不对。每种对象的必填键、可选键、取值类型;日期必须是真实日期且不晚于训练段末日 TRAIN_END;
  删除或基于一个从没出现过的对象;
- duplicate_op:一批里同一个对象出现了两次(多次修改要合成最后的值再送,否则后一条会和前一条记成冲突);
- bad_new_id:没出现过的词、框、样本编号不带本机机器名;
- id_taken:出现过的(含已删的)词、框、样本编号被当成新建(base 为 null)再用;
- 因果(防依据里混进样本日当天还看不到的东西):
  - member_crosses_sample_date:本批动到的样本,有成员框的终点晚于样本日;
  - box_crosses_sample_date:本批动到的框,改完后终点晚于以它为成员的某个样本的样本日;
  - member_missing:样本的成员框不在这只股票上(不存在或已删)。删掉仍是成员的框,要在同一批里把它从
    那个样本的成员里拿掉。
  不越界地改框起止、删样本、改词名、合并都照常放行。
两台机器各自合规的修改,合起来也可能让某个成员框越过样本日;读的时候把这种情况列在 violations 里,不改数据。

数据指纹
--------
每批记下保存时本机训练段副本的指纹(path2_web.snapshot_fingerprint.read_fingerprint,配置键 view_dataset_dir)。
读的时候和本机的比:有任何一批不同,或本机读不到指纹,fingerprint.consistent 为 false;状态照常返回,不拦。
本模块不读行情。

怎么用
------
- 读(会话、GET /annotations 用的是同一个函数):`read_annotations(cfg)`,cfg 是 path2_web.config.load_config()
  的结果。返回 {state, conflicts, unsynced, violations, fingerprint, merges, revs, next_seq, ignored_files};
  会话只要状态时取 `read_annotations(load_config())["state"]`。会话不写标注文件。
- 写(POST /annotations/batch 调它):`append_batch(cfg, ops)`,ops 是 [{kind, id, base, value}]。
  base 取读结果的 revs[kind][id](没有就是 null);新对象的编号用读结果的 next_seq 依次往上取。
- 标注目录不存在时读写都报 AnnotationDirMissing,不自动创建:worktree 里少了指向主目录的软链时,
  自动建目录会把标注写进随 worktree 一起删掉的地方。
- 文件名合格、内容读不懂的批次文件报 AnnotationFileError 并指出是哪个文件,整个读取失败:跳过它会让
  状态缺一块,之后的修改又以缺了的状态为依据。文件名不合格的非隐藏文件不参与重放,列在 ignored_files 里。
- 每次读都把全部文件重放一遍。
"""
from __future__ import annotations

import datetime as dt
import json
import os
import re
import threading
from dataclasses import dataclass, field
from pathlib import Path

from path2_web.config import MACHINE_PATTERN, annotation_dir, machine_name, view_dataset_dir
from path2_web.data import TRAIN_END, check_symbol
from path2_web.snapshot_fingerprint import read_fingerprint

SCHEMA = "path2_web.annotation/1"
KINDS = ("feature", "pattern", "box", "sample")
JUDGMENTS = ("pos", "neg")

# 每种对象:(必填键, 可选键);两者连起来就是状态里的键序(symbol 只在文件里,状态里按它分到 charts)
_VALUE_KEYS = {
    "feature": (("id", "name"), ("definition",)),
    "pattern": (("name",), ("definition", "flags")),
    "box": (("id", "symbol", "feature", "start", "end"), ("attrs", "note", "detach", "attach")),
    "sample": (("id", "symbol", "date", "pattern", "judgment", "members"), ("members_edited", "note")),
}
_ID_LETTER = {"feature": "w", "box": "b", "sample": "s"}       # 带机器名编号的三种对象
_ID_RE = re.compile(rf"([wbs])-({MACHINE_PATTERN})-([1-9]\d*)")
_FILE_RE = re.compile(rf"({MACHINE_PATTERN})-(\d{{8}}T\d{{6}}\.\d{{3}}Z)-([1-9]\d*)\.json")
_DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")
_OP_KEYS = ("kind", "id", "base", "value")                     # 界面送来的一条操作
_STORED_OP_KEYS = ("ts", "machine", *_OP_KEYS)                 # 文件里的一条操作

_write_lock = threading.Lock()     # 同一进程里两次保存不交错(读现状 → 校验 → 写文件)


class AnnotationDirMissing(FileNotFoundError):
    """标注目录不存在。"""


class AnnotationFileError(ValueError):
    """标注目录里有文件名合格、内容读不懂的批次文件。"""


class BatchRejected(ValueError):
    """一批操作没通过校验,一条也没写。reasons:[{code, message, ...}],code 见模块说明「保存时的校验」。"""

    def __init__(self, reasons: list[dict]):
        self.reasons = reasons
        super().__init__("; ".join(r["message"] for r in reasons))


@dataclass(frozen=True)
class _Batch:
    """一个批次文件。stem 是文件名去掉 .json,也是操作引用 `<stem>#<i>` 的前缀。"""
    stem: str
    machine: str
    ts: str
    seq: int
    data_fingerprint: str | None
    ops: tuple


@dataclass
class _Replay:
    """重放的结果。values:(kind, id) → 当前值,None 为已删,键按第一次出现的先后;
    last:(kind, id) → 最后一次修改 {ref, machine, ts};conflicts、unsynced:按重放先后(模块说明「重放与冲突」)。"""
    values: dict = field(default_factory=dict)
    last: dict = field(default_factory=dict)
    conflicts: list = field(default_factory=list)
    unsynced: list = field(default_factory=list)
    merges: list = field(default_factory=list)          # 认出的合并,按重放先后(read_annotations 再筛还能拆回的)
    last_merge: dict = field(default_factory=dict)      # 词编号 → 最后一次合并掉它的那条


# ---------------------------------------------------------------- 读

def read_annotations(cfg: dict) -> dict:
    """重放标注目录里的全部批次文件,返回当前标注。会话和 GET /annotations 都经这一个函数读。

    返回 {state, conflicts, unsynced, violations, fingerprint, merges, revs, next_seq, ignored_files}:
    - state:模块说明「状态的形状」;
    - conflicts:[{kind, id, base, later: {ref, machine, ts}, earlier: {ref, machine, ts}}],
      later 是没看到 earlier 就改了同一对象的那次修改(它生效);
    - unsynced:[{kind, id, base, ref}],ref 这条修改依据的 base 本机还没有(那个文件还没同步到);
    - violations:当前状态里越过样本日、或不在这只股票上的成员框(两台机器的修改合起来造成的),格式同
      BatchRejected.reasons;
    - fingerprint:{local, local_error, recorded: [{fingerprint, batches}], consistent}。local 是本机副本的
      指纹(读不到为 null,原因在 local_error);recorded 是各批记下的指纹及批数;有任何一批与本机不同,
      或本机读不到,consistent 为 false;
    - merges:[{ref, machine, ts, feature, into, boxes: [{id, before, after}]}],还能拆回的合并(模块说明
      「改特征名」一段):feature 是被删的词删之前的值,into 是并进的词,before / after 是那些框在这一批改前、
      改后的值(带 symbol),按重放先后排;
    - revs:{kind: {id: 最后一次修改的引用}},含已删的对象,写操作时取作 base;
    - next_seq:下一个可用的编号序号;
    - ignored_files:文件名不合格、没参与重放的非隐藏文件。

    标注目录不存在 → AnnotationDirMissing;批次文件读不懂 → AnnotationFileError;机器名不合格 → ValueError。
    """
    machine = machine_name(cfg)
    batches, ignored = _load_batches(annotation_dir(cfg))
    r = _replay(batches)
    local, local_error = _local_fingerprint(cfg)
    counts: dict = {}
    for b in batches:
        counts[b.data_fingerprint] = counts.get(b.data_fingerprint, 0) + 1
    revs: dict = {kind: {} for kind in KINDS}
    for (kind, oid), last in r.last.items():
        revs[kind][oid] = last["ref"]
    recorded = next(iter(counts)) if len(counts) == 1 else None
    return {
        "state": _state(r.values, machine, recorded),
        "conflicts": r.conflicts,
        "unsynced": r.unsynced,
        "violations": _causality(r.values, touched=None),
        "fingerprint": {
            "local": local,
            "local_error": local_error,
            "recorded": [{"fingerprint": fp, "batches": n}
                         for fp, n in sorted(counts.items(), key=lambda kv: (kv[0] is None, kv[0] or ""))],
            "consistent": local is not None and all(fp == local for fp in counts),
        },
        "merges": [m for m in r.merges if r.values.get(("feature", m["feature"]["id"])) is None
                   and m is r.last_merge[m["feature"]["id"]]],
        "revs": revs,
        "next_seq": _max_seq(r.values) + 1,
        "ignored_files": ignored,
    }


def _load_batches(adir: Path) -> tuple[list[_Batch], list[str]]:
    """读标注目录:返回(按重放顺序排好的批次, 文件名不合格的非隐藏文件名)。隐藏文件(写入中的临时文件、
    Syncthing 的 .stfolder 等)不看。"""
    if not adir.is_dir():
        raise AnnotationDirMissing(
            f"标注目录不存在: {adir}(主目录里应有这个目录;worktree 里它应是指向主目录的软链,见 .worktree-prep)")
    batches, ignored = [], []
    for name in _list_names(adir):
        if name.startswith("."):
            continue
        m = _FILE_RE.fullmatch(name)
        if m is None or not (adir / name).is_file():
            ignored.append(name)
            continue
        batches.append(_parse_batch(adir / name, m.group(1), m.group(2), int(m.group(3))))
    batches.sort(key=lambda b: (b.ts, b.machine, b.seq))
    return batches, sorted(ignored)


def _list_names(adir: Path) -> list[str]:
    """标注目录里的文件名(顺序随文件系统,重放不依赖它)。"""
    return os.listdir(adir)


def _parse_batch(path: Path, machine: str, ts: str, seq: int) -> _Batch:
    """读一个批次文件并校验:顶层形状、每条操作的 ts / machine 与文件名一致、操作与对象的形状。
    不合格 → AnnotationFileError(写明文件名与全部问题)。"""
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as e:
        raise AnnotationFileError(f"批次文件读不懂: {path.name}: {e}") from None
    problems = []
    if not isinstance(doc, dict) or set(doc) != {"schema", "data_fingerprint", "ops"} or doc["schema"] != SCHEMA:
        problems.append(f"顶层应为 {{schema, data_fingerprint, ops}},schema 为 {SCHEMA}")
    else:
        if doc["data_fingerprint"] is not None and not isinstance(doc["data_fingerprint"], str):
            problems.append("data_fingerprint 应为字符串或 null")
        if not isinstance(doc["ops"], list) or not doc["ops"]:
            problems.append("ops 应为非空数组")
        else:
            for i, op in enumerate(doc["ops"]):
                if not isinstance(op, dict) or set(op) != set(_STORED_OP_KEYS):
                    problems.append(f"第 {i} 条应为 {{{', '.join(_STORED_OP_KEYS)}}}")
                elif op["ts"] != ts or op["machine"] != machine:
                    problems.append(f"第 {i} 条的 ts / machine 与文件名不一致")
                else:
                    problems += [f"第 {i} 条: {p}" for p in _op_problems(op)]
    if problems:
        raise AnnotationFileError(f"批次文件读不懂: {path.name}: " + "; ".join(problems))
    return _Batch(path.name[:-len(".json")], machine, ts, seq, doc["data_fingerprint"], tuple(doc["ops"]))


def _replay(batches: list[_Batch]) -> _Replay:
    """按给定顺序(已按时间戳、机器名、序号排好)逐条重放,每条都生效。base 指向本机没有的修改 → 记 unsynced;
    否则 base 不是当时的最后一次修改 → 记冲突。

    base 若在本机,一定已经重放过:写它的那台机器当时有 base 所在的文件,时间戳排在那个文件之后。
    每一批重放完,顺带认出其中的合并(_note_merges)。"""
    r = _Replay()
    present = {f"{b.stem}#{i}" for b in batches for i in range(len(b.ops))}
    for b in batches:
        before = {(op["kind"], op["id"]): r.values.get((op["kind"], op["id"])) for op in b.ops}
        for i, op in enumerate(b.ops):
            key = (op["kind"], op["id"])
            prev = r.last.get(key)
            this = {"ref": f"{b.stem}#{i}", "machine": b.machine, "ts": b.ts}
            if op["base"] is not None and op["base"] not in present:
                r.unsynced.append({"kind": key[0], "id": key[1], "base": op["base"], "ref": this["ref"]})
            elif op["base"] != (prev["ref"] if prev else None):
                r.conflicts.append({"kind": key[0], "id": key[1], "base": op["base"],
                                    "later": this, "earlier": prev})
            r.values[key] = op["value"]
            r.last[key] = this
        _note_merges(r, b, before)
    return r


def _note_merges(r: _Replay, b: _Batch, before: dict) -> None:
    """认出这一批里的合并:删掉一个词,同一批又把一些框从它改走(当特征的改成别的词,当属性的键拿掉)。
    before 是这一批每个对象改前的值。并进的词取第一个当特征改走的框的新特征;都是属性时取新加的属性键。"""
    for i, op in enumerate(b.ops):
        old = before[("feature", op["id"])] if op["kind"] == "feature" else None
        if op["value"] is not None or old is None:
            continue
        fid, boxes, into = op["id"], [], None
        for bop in b.ops:
            was, now = before[("box", bop["id"])] if bop["kind"] == "box" else None, bop["value"]
            if was is None or now is None:
                continue
            as_feature = was["feature"] == fid and now["feature"] != fid
            as_attr = fid in was.get("attrs", {}) and fid not in now.get("attrs", {})
            if not (as_feature or as_attr):
                continue
            boxes.append({"id": bop["id"], "before": was, "after": now})
            if into is None and as_feature:
                into = now["feature"]
        if into is None:
            into = next((k for x in boxes for k in x["after"].get("attrs", {}) if k not in x["before"].get("attrs", {})),
                        None)
        if boxes and into is not None:
            m = {"ref": f"{b.stem}#{i}", "machine": b.machine, "ts": b.ts, "feature": old, "into": into, "boxes": boxes}
            r.merges.append(m)
            r.last_merge[fid] = m


def _state(values: dict, machine: str, data_fingerprint: str | None) -> dict:
    """把重放出的对象排成「状态的形状」(模块说明)。"""
    features, patterns, charts = [], [], {}
    for (kind, _), v in values.items():
        if v is None:
            continue
        if kind == "feature":
            features.append(_ordered(kind, v))
        elif kind == "pattern":
            patterns.append(_ordered(kind, v))
        else:
            chart = charts.setdefault(v["symbol"], {"symbol": v["symbol"], "boxes": [], "samples": []})
            chart["boxes" if kind == "box" else "samples"].append(_ordered(kind, v))
    for chart in charts.values():
        chart["boxes"].sort(key=lambda b: (b["start"], b["end"], b["id"]))
        chart["samples"].sort(key=lambda s: (s["date"], s["id"]))
    return {"machine": machine, "data_fingerprint": data_fingerprint,
            "features": features, "patterns": patterns, "charts": [charts[s] for s in sorted(charts)]}


def _ordered(kind: str, v: dict) -> dict:
    """对象按固定键序拷一份,去掉 symbol(状态里按它分到 charts)。"""
    required, optional = _VALUE_KEYS[kind]
    return {k: v[k] for k in (*required, *optional) if k in v and k != "symbol"}


def _max_seq(values: dict) -> int:
    """全部文件里用过的最大编号序号(两台机器、含已删的对象),没有为 0。"""
    return max((int(_ID_RE.fullmatch(oid).group(3)) for kind, oid in values if kind in _ID_LETTER), default=0)


def _local_fingerprint(cfg: dict) -> tuple[str | None, str | None]:
    """本机训练段副本的指纹:(指纹, None),读不到时 (None, 原因)。副本目录取配置的 view_dataset_dir。"""
    if not cfg.get("view_dataset_dir"):
        return None, "配置里没有 view_dataset_dir"
    try:
        return read_fingerprint(view_dataset_dir(cfg)), None
    except (OSError, ValueError) as e:      # 没有清单(ManifestMissing)、读不了、格式不对
        return None, str(e)


# ---------------------------------------------------------------- 写

def append_batch(cfg: dict, ops, *, now: dt.datetime | None = None) -> str:
    """校验一批操作 [{kind, id, base, value}],通过就在标注目录里新写一个批次文件,返回它的文件名。

    now:保存时刻(带时区),缺省取当前 UTC 时刻;测试用它模拟两台机器的钟。
    没通过 → BatchRejected(一条也不写);标注目录不存在 → AnnotationDirMissing;机器名不合格 → ValueError。
    """
    adir, machine = annotation_dir(cfg), machine_name(cfg)
    reasons = _envelope_reasons(ops)
    if reasons:
        raise BatchRejected(reasons)
    fingerprint, _ = _local_fingerprint(cfg)
    with _write_lock:
        batches, _ = _load_batches(adir)
        r = _replay(batches)
        reasons = _batch_reasons(r, ops, machine)
        if reasons:
            raise BatchRejected(reasons)
        ts = _next_ts(now or dt.datetime.now(dt.timezone.utc), batches)
        seq = 1 + max((b.seq for b in batches if b.machine == machine), default=0)
        name = f"{machine}-{ts}-{seq}.json"
        doc = {"schema": SCHEMA, "data_fingerprint": fingerprint,
               "ops": [{"ts": ts, "machine": machine, **{k: op[k] for k in _OP_KEYS}} for op in ops]}
        _write_new(adir / name, json.dumps(doc, ensure_ascii=False, indent=1) + "\n")
    return name


def _reason(code: str, message: str, **context) -> dict:
    """一条拒绝原因:{code, message, 涉及的 op 序号或样本、框编号}。"""
    return {"code": code, "message": message, **context}


def _envelope_reasons(ops) -> list[dict]:
    """不看现有标注就能查的:每条操作与对象的形状、一批里有没有重复对象。"""
    if not isinstance(ops, list) or not ops:
        return [_reason("bad_op", "ops 应为非空数组")]
    out, seen = [], set()
    for i, op in enumerate(ops):
        if not isinstance(op, dict) or set(op) != set(_OP_KEYS):
            out.append(_reason("bad_op", f"第 {i} 条应为 {{kind, id, base, value}}", op=i))
            continue
        problems = _op_problems(op)
        out += [_reason("bad_op", f"第 {i} 条: {p}", op=i) for p in problems]
        if not problems:
            key = (op["kind"], op["id"])
            if key in seen:
                out.append(_reason("duplicate_op", f"第 {i} 条: {key[0]} {key[1]} 在这一批里出现了不止一次", op=i))
            seen.add(key)
    return out


def _batch_reasons(r: _Replay, ops: list[dict], machine: str) -> list[dict]:
    """对照现有标注查的:编号、删除与 base 的对象是否存在,以及改完以后的因果。"""
    out = []
    for i, op in enumerate(ops):
        kind, oid = op["kind"], op["id"]
        if (kind, oid) in r.values:
            if op["base"] is None and kind in _ID_LETTER:
                out.append(_reason("id_taken", f"第 {i} 条: 编号 {oid} 已经用过,新建对象请按 next_seq 取号", op=i))
        elif op["value"] is None or op["base"] is not None:
            out.append(_reason("bad_op", f"第 {i} 条: {kind} {oid} 从没出现过,不能删除或基于它修改", op=i))
        elif kind in _ID_LETTER and _ID_RE.fullmatch(oid).group(2) != machine:
            out.append(_reason("bad_new_id", f"第 {i} 条: 新建的 {oid} 不带本机机器名 {machine}", op=i))
    after = {**r.values, **{(op["kind"], op["id"]): op["value"] for op in ops}}
    return out + _causality(after, touched={(op["kind"], op["id"]) for op in ops})


def _causality(values: dict, touched: set | None) -> list[dict]:
    """成员框的因果:每个成员框都在样本这只股票上,且终点不晚于样本日。

    touched 为 None 时查全部样本(读的时候报 violations);否则只查本批动到的样本,以及成员里有本批动到的框
    的样本——别处已有的问题不拦这一批。"""
    out = []
    for (kind, sid), s in values.items():
        if kind != "sample" or s is None:
            continue
        if touched is not None and ("sample", sid) not in touched \
                and not any(("box", bid) in touched for bid in s["members"]):
            continue
        for bid in s["members"]:
            box = values.get(("box", bid))
            if box is None or box["symbol"] != s["symbol"]:
                out.append(_reason("member_missing",
                                   f"样本 {sid}({s['symbol']} {s['date']})的成员框 {bid} 不在这只股票上(不存在或已删)",
                                   sample=sid, box=bid))
            elif box["end"] > s["date"]:
                if touched is not None and ("box", bid) in touched:
                    out.append(_reason("box_crosses_sample_date",
                                       f"框 {bid} 改成 {box['start']}～{box['end']},越过了以它为成员的样本 {sid} "
                                       f"的样本日 {s['date']}", sample=sid, box=bid))
                else:
                    out.append(_reason("member_crosses_sample_date",
                                       f"样本 {sid} 的成员框 {bid} 终点 {box['end']} 晚于样本日 {s['date']}",
                                       sample=sid, box=bid))
    return out


def _next_ts(now: dt.datetime, batches: list[_Batch]) -> str:
    """这一批的时间戳:当前时刻(取到毫秒)与「已有文件最晚时间戳 + 1 毫秒」中较晚的那个。"""
    t = now.astimezone(dt.timezone.utc)
    t = t.replace(microsecond=t.microsecond // 1000 * 1000)
    if batches:
        t = max(t, _parse_ts(max(b.ts for b in batches)) + dt.timedelta(milliseconds=1))
    return t.strftime("%Y%m%dT%H%M%S") + f".{t.microsecond // 1000:03d}Z"


def _parse_ts(ts: str) -> dt.datetime:
    """`YYYYMMDDTHHMMSS.mmmZ` → 带 UTC 时区的时刻。"""
    t = dt.datetime.strptime(ts[:15], "%Y%m%dT%H%M%S").replace(tzinfo=dt.timezone.utc)
    return t.replace(microsecond=int(ts[16:19]) * 1000)


def _write_new(path: Path, text: str) -> None:
    """写一个新文件:先写隐藏的临时文件,再硬链接成正式名(正式名已存在 → FileExistsError,绝不覆盖),
    最后删掉临时文件。读的人看不到写了一半的文件。"""
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    tmp.write_text(text, encoding="utf-8")
    try:
        os.link(tmp, path)
    finally:
        tmp.unlink()


# ---------------------------------------------------------------- 形状校验

def _op_problems(op: dict) -> list[str]:
    """一条操作的 kind / id / base / value 是否合格,返回问题描述(合格为空)。不看现有标注。"""
    kind, oid, base, value = op["kind"], op["id"], op["base"], op["value"]
    if kind not in KINDS:
        return [f"kind 应为 {' / '.join(KINDS)} 之一,实为 {kind!r}"]
    if not _nonempty(oid):
        return [f"id 应为非空字符串,实为 {oid!r}"]
    out = []
    if kind in _ID_LETTER:
        m = _ID_RE.fullmatch(oid)
        if m is None or m.group(1) != _ID_LETTER[kind]:
            out.append(f"{kind} 的编号应为 {_ID_LETTER[kind]}-<机器名>-<序号>,实为 {oid!r}")
    if base is not None and not _nonempty(base):
        out.append(f"base 应为修改引用或 null,实为 {base!r}")
    if value is not None:
        out += _value_problems(kind, oid, value) if isinstance(value, dict) else ["value 应为对象或 null"]
    return out


def _value_problems(kind: str, oid: str, v: dict) -> list[str]:
    """一个对象的值是否合格:键齐全、没有多余的键、各字段类型与取值。返回问题描述(合格为空)。"""
    required, optional = _VALUE_KEYS[kind]
    missing = [k for k in required if k not in v]
    extra = sorted(set(v) - set(required) - set(optional))
    if missing or extra:
        return [f"{kind} {oid}: 缺少 {missing},多出 {extra}"]
    out = []

    def bad(msg: str) -> None:
        out.append(f"{kind} {oid}: {msg}")

    if v["name" if kind == "pattern" else "id"] != oid:
        bad("值里的编号(pattern 是名字)与 id 不一致")
    for key in ("definition", "note"):
        if key in v and not isinstance(v[key], str):
            bad(f"{key} 应为字符串")
    if kind == "feature":
        if not _nonempty(v["name"]):
            bad("name 应为非空字符串")
    elif kind == "pattern":
        flags = v.get("flags", [])
        if not isinstance(flags, list) or not all(
                isinstance(f, dict) and set(f) == {"feature", "mapping_row"} and _nonempty(f["feature"])
                for f in flags):
            bad("flags 应为 [{feature, mapping_row}]")
    elif kind == "box":
        _check_symbol(v["symbol"], bad)
        if v["feature"] is not None and not _nonempty(v["feature"]):
            bad("feature 应为特征编号或 null")
        start_ok = _check_date("start", v["start"], bad)
        end_ok = _check_date("end", v["end"], bad)
        if start_ok and end_ok and v["start"] > v["end"]:
            bad(f"start {v['start']} 晚于 end {v['end']}")
        attrs = v.get("attrs", {})
        if not isinstance(attrs, dict) or not all(_nonempty(k) and isinstance(x, bool) for k, x in attrs.items()):
            bad("attrs 应为 {特征编号: true / false}")
        if "detach" in v and v["detach"] is not True:
            bad("detach 只能是 true")
        if "attach" in v and (not _nonempty(v["attach"]) or v["attach"] == oid):
            bad("attach 应为另一个框的编号")
        if "detach" in v and "attach" in v:
            bad("detach 与 attach 互斥")
    else:  # sample
        _check_symbol(v["symbol"], bad)
        _check_date("date", v["date"], bad)
        if v["pattern"] is not None and not _nonempty(v["pattern"]):
            bad("pattern 应为 pattern 名或 null(unsorted)")
        if v["judgment"] not in JUDGMENTS:
            bad(f"judgment 应为 {' / '.join(JUDGMENTS)}")
        members = v["members"]
        if not isinstance(members, list) or not all(_nonempty(b) for b in members) \
                or len(set(members)) != len(members):
            bad("members 应为不重复的框编号数组")
        if "members_edited" in v and not isinstance(v["members_edited"], bool):
            bad("members_edited 应为 true / false")
    return out


def _nonempty(x) -> bool:
    """是非空字符串。"""
    return isinstance(x, str) and x != ""


def _check_symbol(symbol, bad) -> None:
    """代码名格式(path2_web.data.check_symbol,只查格式、不读行情);不合格经 bad 报问题。"""
    try:
        check_symbol(symbol)
    except ValueError as e:
        bad(str(e))


def _check_date(key: str, s, bad) -> bool:
    """日期:YYYY-MM-DD、真实存在、不晚于训练段末日。合格返回 True,否则经 bad 报问题。"""
    if not isinstance(s, str) or not _DATE_RE.fullmatch(s):
        bad(f"{key} 应为 YYYY-MM-DD,实为 {s!r}")
        return False
    try:
        dt.date.fromisoformat(s)
    except ValueError:
        bad(f"{key} 不是真实日期: {s}")
        return False
    if s > TRAIN_END:
        bad(f"{key} {s} 晚于训练段末日 {TRAIN_END}")
        return False
    return True
