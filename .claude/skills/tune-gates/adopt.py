# -*- coding: utf-8 -*-
"""tune-gates · 定案写入:把用户批准的参数改动写进 params.yaml,并在账本追加一条 decide 记录。

两步有先后:先写参数文件,再写账本(decide 的 ref 带写后参数文件的 sha256);账本写失败就把参数文件
原样还原,不留「参数改了、账本没记」的半截状态。confirm=False 时只返回改动 diff 与检查结果,一个文件都不写。

三道机械闸:
  闸 4  报这组参数在训练数据上一共被比较过几次(账本 looks),供用户掂量挑出来的好结果里有多少运气;
  闸 5  改动涉及闸(where 阈值 / 过滤型参数)时,账本里必须已有该参数的发现记录(登记簿待验证行已登记);
        未经独立验证的定案,参数文件注释与 decide 记录双标注(provisional=True);
  闸 6  decide 记下 depends_on:定案时背景参数的取值快照,之后它们变了,状态检查会报需复核。

已落地的暂定定案做完事后独立验证(两段确认窗都开过)后,结论也经本模块落账:changes 的新值全部等于参数文件现值
即为「落地定案的验证结论记账」——值不变,注释块末尾追加一行验证结论,decide 记录带 landed_confirmation / validation。
撤回已落地定案走普通路径(新值 = 定案前的旧值)。

参数文件只按行替换值、保留注释,只认「section 下缩进的 key: 值  # 注释」这种行;别的写法报错,请人手改。
"""
from __future__ import annotations

import difflib
import hashlib
import re
import subprocess
import sys
from datetime import date
from pathlib import Path

import yaml

SKILL_DIR = Path(__file__).resolve().parent
REPO = Path(subprocess.check_output(["git", "rev-parse", "--show-toplevel"], text=True, cwd=SKILL_DIR).strip())
sys.path.insert(0, str(REPO)); sys.path.insert(0, str(SKILL_DIR))

UNVERIFIED = "未经独立验证"
PROVISIONAL = "暂定"
CONFIRMED = "已确认"
_PLAIN_WORD = re.compile(r"^[A-Za-z_][\w\-]*$")
# 「 值」或「 值  # 注释」;值不许以引号 / 括号 / 块标记开头(那是 yaml 的其他写法,按行替换会弄坏)
_VALUE_RE = re.compile(r"^(?P<sp> +)(?P<val>[^\s#'\"\[\]{}|>&*!%@`][^#]*?)(?:(?P<pad> +)(?P<comment>#.*))?$")


def _scalar(v) -> str:
    """把一个取值写成 yaml 标量文本,并回读核对类型与值都不变。"""
    if v is None:
        s = "null"
    elif isinstance(v, bool):
        s = "true" if v else "false"
    elif isinstance(v, int):
        s = str(v)
    elif isinstance(v, float):
        s = repr(v)
        if not isinstance(yaml.safe_load(s), float):          # 1e-05 这类写法 yaml 会读成字符串
            s = format(v, ".17f").rstrip("0")
    elif isinstance(v, str) and _PLAIN_WORD.match(v):
        s = v
    else:
        raise ValueError(f"{v!r} 不是工具能写进参数文件的简单取值(数、null、true/false、不带空格与符号的单词)")
    back = yaml.safe_load(s)
    if back != v or type(back) is not type(v):
        raise ValueError(f"{v!r} 写成 {s!r} 后读回来变成了 {back!r},工具不写这种取值,请手动改")
    return s


def _find_key_line(lines: list, sec: str, field: str, key: str) -> int:
    heads = [i for i, ln in enumerate(lines) if re.match(rf"^{re.escape(sec)}:\s*(#.*)?$", ln)]
    if len(heads) != 1:
        raise ValueError(f"参数文件里没有(或不止一处)独占一行的「{sec}:」,{key} 没法按行改,请手动改")
    hits = []
    for i in range(heads[0] + 1, len(lines)):
        ln = lines[i]
        if ln and not ln[0].isspace() and not ln.startswith("#"):
            break
        if re.match(rf"^ +{re.escape(field)}:", ln):
            hits.append(i)
    if len(hits) != 1:
        raise ValueError(f"参数文件的 {sec} 段里没有(或不止一处){field} 这一行——没写进文件的参数工具不会替你加行,"
                         "请先手动写上再定案")
    return hits[0]


def edit_params_yaml(text: str, changes: dict, *, note: str | None = None) -> str:
    """按 section 定位「  key: 值  # 注释」行,只换值、保留注释;note 非空时追加在该参数注释块的末尾
    (有注释则另起一行、与注释对齐;没有注释则写在本行行尾)。

    changes = {参数键(section.field): 新值}。不认识的格式(流式列表 / 带引号 / 块标量 / 嵌套映射 / 参数没写在
    文件里)→ ValueError(人话)。改完回读核对每个参数确实变成了新值。"""
    lines = text.split("\n")
    for key, new in changes.items():
        sec, _, field = key.partition(".")
        if not sec or not field or "." in field:
            raise ValueError(f"参数键要写成 section.field,实际 {key!r}")
        i = _find_key_line(lines, sec, field, key)
        indent = len(lines[i]) - len(lines[i].lstrip(" "))
        head = f"{' ' * indent}{field}:"
        m = _VALUE_RE.match(lines[i][len(head):])
        ok, parsed = m is not None, None
        if ok:
            try:
                parsed = yaml.safe_load(m.group("val"))
                ok = not isinstance(parsed, (dict, list))
            except yaml.YAMLError:
                ok = False
        if not ok:
            raise ValueError(f"参数文件里 {key} 这一行不是「key: 值  # 注释」的写法,工具不改这种行,请手动改: {lines[i]!r}")
        old_val = m.group("val").rstrip()
        new_val = old_val if parsed == new and type(parsed) is type(new) else _scalar(new)   # 值不变就不动原文
        line = head + m.group("sp") + new_val
        comment_col = None
        if m.group("comment"):
            pad = m.group("pad")
            width = len(old_val) + len(pad) - len(new_val)
            line += " " * max(width, min(len(pad), 2))
            comment_col = len(line)
            line += m.group("comment")
        lines[i] = line
        if note:
            j = i + 1
            while j < len(lines) and re.match(r"^ +#", lines[j]) and len(lines[j]) - len(lines[j].lstrip(" ")) > indent:
                comment_col = len(lines[j]) - len(lines[j].lstrip(" "))
                j += 1
            if comment_col is None:
                lines[i] += f"  # {note}"
            else:
                lines.insert(j, " " * comment_col + f"# {note}")
    out = "\n".join(lines)
    data = yaml.safe_load(out) or {}
    for key, new in changes.items():
        sec, _, field = key.partition(".")
        got = (data.get(sec) or {}).get(field)
        if got != new or type(got) is not type(new):
            raise ValueError(f"{key} 改完读回来是 {got!r},不是 {new!r}——参数文件格式不在工具支持范围内,请手动改")
    return out


def _ref_path(p: Path) -> str:
    p = p.resolve()
    try:
        return str(p.relative_to(REPO))
    except ValueError:
        return str(p)


def _ts(v):
    from datetime import datetime
    try:
        return datetime.fromisoformat(str(v))
    except ValueError:
        return None


def _landed_refusals(recs: list, current: dict, validation, verified: bool) -> list[str]:
    """给已落地定案记独立验证结论的前提,返回拒绝理由(空 = 放行)。current = {参数键: 现值}。

    ① 每个参数最近一条 decide 的新值等于现值(确实是已落地的定案);② validation 给全,账本里有该清单的预注册,
    且 validation 指向的两条开窗记录(确认窗分别为往前 / 前向、清单哈希一致)都在、都晚于这些 decide;③ verified。"""
    import holdout
    import ledger
    out, decided = [], []
    for key, v in current.items():
        last = next((r for r in reversed(recs) if r["kind"] == "decide" and key in r["data"]["params"]), None)
        landed_v = None if last is None else last["data"]["params"][key][1]
        if last is None or not (landed_v == v and type(landed_v) is type(v)):
            why = "账本里没有它的定案记录" if last is None else f"它最近一次定案的新值是 {landed_v!r}"
            out.append(f"{key} 的现值 {v!r} 不是已落地的定案({why})——新值等于现值只用于给已落地定案记独立验证结论")
        else:
            decided.append(last["ts"])
    if not verified:
        out.append("给已落地定案记独立验证结论,必须是验证过的(verified=True);没做独立验证就不用记")
    ok_shape = (isinstance(validation, dict) and isinstance(validation.get("manifest_hash"), str)
                and isinstance(validation.get("extrapolate"), dict)
                and set(validation["extrapolate"]) == set(ledger.CONFIRM_NAMES))
    if not ok_shape:
        out.append("缺独立验证的出处:要给 validation = {manifest_hash: 清单哈希, extrapolate: {backward: 开窗记录时间, "
                   "forward: 开窗记录时间}}")
        return out
    mh, ext = validation["manifest_hash"], validation["extrapolate"]
    if not any(r["kind"] == "preregister" and r["data"]["manifest_hash"] == mh for r in recs):
        out.append(f"账本里没有这份验证清单({mh[:12]}…)的预注册记录")
    last_decide = max(decided, key=lambda t: _ts(t) or _ts("0001-01-01")) if decided else None
    for cw in ledger.CONFIRM_NAMES:
        word = holdout.WINDOW_WORDS[cw]
        hit = next((r for r in recs if r["kind"] == "extrapolate" and r["ts"] == ext[cw]
                    and r["data"]["confirm_window"] == cw and r["data"]["manifest_hash"] == mh), None)
        if hit is None:
            out.append(f"账本里找不到这份清单在{word}上的开窗记录(记录时间 {ext[cw]!r})")
        elif last_decide is not None and not (_ts(hit["ts"]) and _ts(last_decide) and _ts(hit["ts"]) > _ts(last_decide)):
            out.append(f"{word}上的开窗记录({hit['ts']})不晚于这次定案({last_decide}),不是对这次定案的验证")
    return out


def adopt(app: str, *, window: str, changes: dict, provisional: bool, verified: bool, selects_on: list,
          depends_on: dict, reason: str, confirm: bool = False, yaml_path=None, apps_dir=None,
          validation: dict | None = None) -> dict:
    """用户批准后写正式参数与 decide 记录。

    app / window 定位研究声明(取 pattern 模块、参数文件名与宽进覆盖);yaml_path 缺省 = 该 pattern 的参数文件,
    测试可给临时副本;apps_dir 缺省 = skill 的 apps 目录。changes = {参数键: 新值};selects_on = 定案依据挑选过
    的轴;depends_on = {背景参数键: 定案时取值}(必须与参数文件现值一致,且不含被改的参数);reason 进注释与账本。

    返回 {"app","window","yaml_path","changes": {键: [旧, 新]},"diff","checks","refusals","written","record"};
    checks 含 looks(闸 4)、kinds(每个改动参数的类型)、provisional(闸 5 后的实际值)、verified、depends_on。
    confirm=False:只返回,不写任何东西;confirm=True 且有拒绝理由 → SystemExit(人话),不写任何东西;
    confirm=True 且无拒绝 → 先写参数文件,再追加 decide(ref = 写后参数文件的 sha256),账本写失败则还原参数文件。

    **落地定案的验证结论记账**:changes 里每个参数的新值都等于现值时走这条路,前提(见 _landed_refusals)全部满足才放行——
    该参数最近一条 decide 的新值等于现值;validation = {"manifest_hash", "extrapolate": {"backward": 记录 ts,
    "forward": 记录 ts}} 指向账本里该清单的预注册与两条晚于那条 decide 的开窗记录;verified=True。
    写入时值不变,注释块末尾追加「<日期> 独立验证:<reason>;<暂定|已确认>」(provisional 决定用词),decide 的
    params = {键: [现值, 现值]},另带 landed_confirmation=True 与 validation;不查闸 5(没有改闸)。
    部分参数等于现值、部分不等 → 拒绝(两种记账不混在一次调用里)。validation 只在这条路上使用。"""
    import grid_propose
    import ledger
    import study_io as S
    from multivar_core import apply_overrides
    apps_dir = Path(apps_dir) if apps_dir else S.APPS_DIR
    study_p = S.study_path(app, window, apps_dir)
    if not study_p.exists():
        raise SystemExit(f"{app} 的 {window} 窗口还没有研究声明,不知道要改哪个 pattern 的参数")
    study = S.load_study(study_p)
    mod = S.import_app(study)
    yaml_p = Path(yaml_path) if yaml_path else S.app_dir(mod) / study.BASE_YAML
    original = yaml_p.read_bytes()
    text = original.decode("utf-8")
    formal = mod.Params.from_dict(yaml.safe_load(text) or {}, strict=True).to_dict()

    refusals, params, unchanged = [], {}, {}
    if not changes:
        refusals.append("没有要改的参数")
    if not str(reason).strip():
        refusals.append("定案理由不能为空:它会写进参数文件注释与账本")
    for key, new in changes.items():
        sec, _, field = key.partition(".")
        if field not in formal.get(sec, {}):
            refusals.append(f"{key} 不是这个 pattern 的参数")
            continue
        old = formal[sec][field]
        if old == new and type(old) is type(new):
            unchanged[key] = old
            continue
        params[key] = [old, new]
    landed = bool(unchanged) and not params
    if unchanged and params:
        refusals.append(f"{sorted(unchanged)} 的新值等于现值(给已落地定案记验证结论),{sorted(params)} 要改值(新定案)——"
                        "两种记账不混在一次调用里,请分两次")
    recs = ledger.read(app)
    if landed:
        params = {k: [v, v] for k, v in unchanged.items()}
        refusals += _landed_refusals(recs, unchanged, validation, verified)
    bad_axes = [a for a in selects_on if not (isinstance(a, str) and ledger.AXIS_RE.match(a))]
    if bad_axes:
        refusals.append(f"定案依据的轴名不合法(参数轴写 section.field,特征写 feature:名): {bad_axes}")
    for k, v in depends_on.items():
        sec, _, field = k.partition(".")
        if k in changes:
            refusals.append(f"{k} 既是被改的参数又记成背景参数——背景快照只记没改的参数")
        elif field not in formal.get(sec, {}):
            refusals.append(f"背景参数 {k} 不是这个 pattern 的参数")
        elif formal[sec][field] != v:
            refusals.append(f"背景参数 {k} 记的取值 {v!r} 与参数文件现值 {formal[sec][field]!r} 不同——"
                            "背景快照必须是定案时的真实取值")

    provisional_eff = bool(provisional) or not verified
    tags = "".join(f";{t}" for t, on in ((PROVISIONAL, provisional_eff), (UNVERIFIED, not verified)) if on)
    today = date.today().isoformat()
    new_text = text
    try:
        for key, (old, new) in params.items():
            note = (f"{today} 独立验证:{reason};{PROVISIONAL if provisional_eff else CONFIRMED}" if landed else
                    f"{today} 定案(原 {old!r}):{reason}{tags}")
            new_text = edit_params_yaml(new_text, {key: new}, note=note)
    except ValueError as e:
        refusals.append(str(e))
        new_text = None
    new_dict = None
    if new_text is not None and params:
        try:
            p_new = mod.Params.from_dict(yaml.safe_load(new_text) or {}, strict=True)
            mod.build_pattern(p_new)
            new_dict = p_new.to_dict()
        except Exception as e:  # noqa: BLE001 —— app 用什么异常表达"这组参数不合法"是它的自由
            refusals.append(f"改完之后这组参数搭不出 pattern({type(e).__name__}: {e})")

    kinds = {}
    for key, (old, new) in ({} if landed else params).items():
        kind, _fields, why = grid_propose.classify_one(mod, formal, tuple(key.split(".", 1)), [old, new])
        kinds[key] = kind
        if kind is None:
            refusals.append(f"判断不了 {key} 是不是闸({why}),不能自动定案")
        elif kind in grid_propose.PREDICATE_KINDS and not any(
                r["kind"] == "discover" and key in r["axes"] for r in recs):
            refusals.append(f"{key} 是一道闸:改闸或删闸之前,登记簿里要先有它的待验证行(账本里要有这条参数的发现记录),"
                            "现在还没有——先登记,再定案")

    looks = ledger.looks(app, list(changes))
    diff = "" if new_text is None else "".join(difflib.unified_diff(
        text.splitlines(True), new_text.splitlines(True), fromfile=str(yaml_p), tofile=str(yaml_p)))
    out = {"app": app, "window": window, "yaml_path": str(yaml_p), "changes": params, "diff": diff,
           "checks": {"looks": looks,
                      "looks_text": f"这组参数在训练数据上一共被比较过 {looks} 次(次数越多,挑出来的好结果越可能含运气)",
                      "kinds": kinds, "provisional": provisional_eff, "verified": bool(verified),
                      "depends_on": dict(depends_on)},
           "refusals": refusals, "written": False, "record": None}
    if not confirm:
        return out
    if refusals:
        raise SystemExit("没有写入任何东西:\n- " + "\n- ".join(refusals))

    new_bytes = new_text.encode("utf-8")
    fps = grid_propose.code_fingerprints(mod, apply_overrides(new_dict, study.WIDE_OVERRIDES, {}))
    rec = ledger.make_record(
        "decide", app, actor="tune.adopt", round=None, axes=sorted(params), window=None, label_horizon=None,
        head_buffer=None, **fps, ref={_ref_path(yaml_p): hashlib.sha256(new_bytes).hexdigest()},
        data={"params": params, "selects_on": list(selects_on), "provisional": provisional_eff,
              "depends_on": dict(depends_on), "verified": bool(verified), "reason": reason,
              "window": window, "looks": looks,
              **({"landed_confirmation": True, "validation": validation} if landed else {})},
        note=reason)
    ledger.validate_record(rec)
    yaml_p.write_bytes(new_bytes)
    try:
        ledger.append(rec)
    except BaseException:
        yaml_p.write_bytes(original)
        raise
    out.update(written=True, record=rec)
    return out
