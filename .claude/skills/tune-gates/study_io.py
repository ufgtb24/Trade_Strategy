# -*- coding: utf-8 -*-
"""tune-gates · study / classification / run_meta 的文件约定与推导 helper。

本模块是唯一知道下列路径与 schema 的地方,Claude 侧的唯一调用面是 tune.py
(内部由 app_setup / multivar_scan / compare_longtable / region_find 转发调用):
  apps/<app>/study.py             人写的 8 项声明(换 app 唯一要改的地方)
  apps/<app>/classification.json  app_setup 生成:分类 + 推导字段 + 双指纹(人不改)
  <longtable_dir>/run_meta.json   multivar_scan 写:run 级口径单源(compare/region 读)
本文件永远在 skill 目录内;入口脚本原地运行(不复制),经模块级 sys.path.insert 找到它。
不含算法——classify/推导用的全是 multivar_core 的既有函数。
"""
from __future__ import annotations

import hashlib
import importlib
import importlib.util
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd

REPO = Path(subprocess.check_output(["git", "rev-parse", "--show-toplevel"], text=True).strip())
SKILL_DIR = Path(__file__).resolve().parent
APPS_DIR = SKILL_DIR / "apps"
sys.path.insert(0, str(REPO)); sys.path.insert(0, str(SKILL_DIR))

from multivar_core import apply_overrides, col_of  # noqa: E402

STUDY_NAMES = ("APP_MODULE", "BASE_YAML", "WIDE_OVERRIDES", "SCAN_GRID", "WHERE_LEVELS",
               "REF_POINT", "TIGHT_WHERES", "FLAG_RULES")


def require(value, name: str) -> None:
    """调用参数的硬闸:入参未填直接退出,既防误跑也让通用区零 app 专名。"""
    if value is None:
        raise SystemExit(f"{name} 未填:该参数现在由调用方作为函数入参传给 tune.scan / tune.compare 等,"
                          "不再有文件可编辑——检查调用处是否漏传")


def dotted(dim: tuple) -> str:
    return col_of(dim)


def undotted(s: str) -> tuple:
    sec, field = s.split(".", 1)
    return (sec, field)


def load_study(path: Path):
    """从文件路径加载 study 模块(不经 sys.path,避免多个 app 的 study.py 同名互相遮蔽)。"""
    path = Path(path)
    spec = importlib.util.spec_from_file_location(f"tune_gates_study_{path.parent.name}", path)
    mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
    missing = [n for n in STUDY_NAMES if not hasattr(mod, n)]
    if missing:
        raise ValueError(f"{path} 缺少声明: {missing}")
    return mod


def append_exposure(app: str, record: dict, apps_dir: Path = APPS_DIR) -> Path:
    """把一次识别运行追加进 apps/<app>/exposure.jsonl(只追加,不覆盖)。

    这是**识别端的运行审计日志**,不是 resume 状态:丢了它算出来的数字一个都不变,
    变的只是人解读三口径时手上有没有"这批数据已经看过几次"的背景。

    为什么落 apps/<app>/ 而不是 outputs/:outputs 在 gitignore 里跨轮不持久;
    且 RUN_CALIBER 含 study_fingerprint,改 study.py 就强制换 OUT_DIR、历史会碎成多份,
    而改网格恰恰是最该被记住的那次跨轮动作。

    record 里约定留一个 "note" 键(默认空串):ledger.md 是 multivar_scan.py 每次运行
    无条件全量覆写的机器产物,人写进去的裁定下一轮就被无声抹掉;这里只追加、跨轮持久,
    是唯一能承载"指纹不一致但我裁定复用"这类跨轮记录的地方。
    """
    d = Path(apps_dir) / app
    if not d.is_dir():
        raise SystemExit(f"{d} 不存在:app 未接入,无处记录运行历史")
    p = d / "exposure.jsonl"
    with p.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
    return p


def import_app(study):
    return importlib.import_module(study.APP_MODULE)


def app_dir(mod) -> Path:
    return Path(mod.__file__).resolve().parent


def base_snapshot(mod, study) -> dict:
    """底座快照 = BASE_YAML 全量参数 ⊕ WIDE_OVERRIDES。这就是「搜索空间之外的一切」。"""
    base = mod.Params.from_yaml(app_dir(mod) / study.BASE_YAML).to_dict()
    return apply_overrides(base, study.WIDE_OVERRIDES, {})


from multivar_core import (check_predicate_axes, classify, detection_combos, loosest_level, node_col)  # noqa: E402
from path2.dag._solve import compile_plan  # noqa: E402


def _git_head() -> str:
    return subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], text=True, cwd=REPO).strip()


def _reject_e_dims(scan_grid: dict, kinds: dict) -> None:
    """E 维(改档只改边拓扑、不改 detector 状态也不改 where)暂不支持进 SCAN_GRID。

    region 侧的 `derived_axes` 只把 D 维当 combo 轴(F/W 维走 preds、E 维两边都不认)——
    `multivar_core.classify`/`build_classification` 都不拒绝 E 维进 SCAN_GRID,但一旦真的
    放进去:长表里确实有这一列(`row_columns`/`multivar_scan` 的 combo_cols 用的是
    `kinds != "F"`,E 维会被真扫、真写列),`region_find` 却读不到这根轴,不同 E 值的行会
    被静默聚合进同一个格(格坐标不再唯一对应一组参数取值);`compare_longtable.pred_mask`
    在 D/F/W 之外的 else 分支上还会对这根轴裸 `KeyError`。宁可在这里响亮拒绝,也不要
    等这两处在下游悄悄错。"""
    e_dims = [dotted(d) for d in scan_grid if kinds[d] == "E"]
    if e_dims:
        raise ValueError(f"E 维(改档改变边拓扑)暂不支持进 SCAN_GRID: {e_dims}——"
                         "region 侧不会把它当轴,格会静默把不同 E 值混进同一格")


def build_classification(app: str, study, mod, study_path: Path) -> dict:
    """跑 classify + 全部静态守卫 + 推导,返回 classification.json 的 dict(含源码/底座/study 三指纹)。

    守卫在这里响亮失败,不等到扫描:E 维不许进 SCAN_GRID / REF_POINT 恰好覆盖 D 维 /
    TIGHT_WHERES 键在网格内 / 共享 detector 实例 / negation dst 谓词轴。"""
    base = base_snapshot(mod, study)
    cls = classify(mod, base, study.SCAN_GRID, study.WHERE_LEVELS)
    _reject_e_dims(study.SCAN_GRID, cls.kinds)
    d_dims = {dotted(d) for d in study.SCAN_GRID if cls.kinds[d] == "D"}
    if set(study.REF_POINT) != d_dims:
        raise ValueError(f"REF_POINT 必须恰好覆盖全部 D 维: 期望 {sorted(d_dims)},实际 {sorted(study.REF_POINT)}")
    grid_dims = set(study.SCAN_GRID) | set(study.WHERE_LEVELS)
    for name, w in study.TIGHT_WHERES.items():
        extra = set(w) - grid_dims
        if extra:
            raise ValueError(f"TIGHT_WHERES[{name!r}] 含网格外的维 {sorted(extra)}")
    # 与 scan_one_stock 同一套 override 造 spec0(F 维最松档),守卫与列集才与生产同源
    filter_min = {d: loosest_level(study.SCAN_GRID[d], cls.filter_fields[d][2])
                  for d in study.SCAN_GRID if cls.kinds[d] == "F"}
    spec0 = mod.build_pattern(mod.Params.from_dict(apply_overrides(base, {}, filter_min), strict=True))
    det_nodes = [n for n in spec0.nodes if n.detector is not None]
    if len({id(n.detector) for n in det_nodes}) != len(det_nodes):
        raise ValueError("多 node 共享 detector 实例:反转循环不支持,请拆成独立实例")
    check_predicate_axes(spec0, {**cls.where_fields, **cls.filter_fields})
    p0 = mod.Params.from_dict(base, strict=True)
    end_node = mod.eval_meta(params=p0)["end_node"]
    bound = sorted({nid for w in compile_plan(spec0).wcc_plans for nid in w.comp})
    fps = {"source": source_fingerprint(source_files(mod, spec0)),
           "base": canonical_hash(base), "study": file_sha256(study_path)}
    return {
        "app": app, "app_module": study.APP_MODULE, "base_yaml": study.BASE_YAML,
        "kinds": {dotted(d): k for d, k in cls.kinds.items()},
        "detector_nodes": {dotted(d): list(v) for d, v in cls.detector_nodes.items()},
        "filter_fields": {dotted(d): list(v) for d, v in cls.filter_fields.items()},
        "where_fields": {dotted(d): list(v) for d, v in cls.where_fields.items()},
        "scan_grid": {dotted(d): list(v) for d, v in study.SCAN_GRID.items()},
        "where_levels": {dotted(d): list(v) for d, v in study.WHERE_LEVELS.items()},
        "wide_overrides": study.WIDE_OVERRIDES, "ref_point": dict(study.REF_POINT),
        "end_node": end_node, "bound_nodes": bound,
        "detection_combos": len(detection_combos(study.SCAN_GRID, cls)),
        "ref_params": base, "fingerprints": fps,
        "generated_at": datetime.now().isoformat(timespec="seconds"), "git_head": _git_head(),
    }


def write_classification(app: str, data: dict, apps_dir: Path = APPS_DIR) -> Path:
    p = Path(apps_dir) / app / "classification.json"; p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, ensure_ascii=False, indent=1, default=str) + "\n")
    return p


def load_classification(app: str, apps_dir: Path = APPS_DIR) -> dict:
    p = Path(apps_dir) / app / "classification.json"
    if not p.exists():
        raise SystemExit(f"{p} 不存在:先跑 tune.setup({app!r})")
    return json.loads(p.read_text())


def derived_axes(cl: dict) -> tuple:
    """region 侧的轴:combo_levels = D 维(SCAN_GRID 序);preds = F 维(SCAN_GRID 序)+ W 维(WHERE_LEVELS 序)。"""
    combo = {d: lv for d, lv in cl["scan_grid"].items() if cl["kinds"][d] == "D"}
    preds = [(node_col(*cl["filter_fields"][d][:2]), cl["filter_fields"][d][2], lv)
             for d, lv in cl["scan_grid"].items() if cl["kinds"][d] == "F"]
    preds += [(node_col(*cl["where_fields"][d][:2]), cl["where_fields"][d][2], lv)
              for d, lv in cl["where_levels"].items()]
    return combo, preds


def _cmp(x, v, op: str):
    return (x >= v) if op == ">=" else (x < v) if op == "<" else (x > v) if op == ">" else (x <= v)


def pred_mask(df: pd.DataFrame, assignments: dict, cl: dict) -> pd.Series:
    """长表行掩码:D 维按列等值;F/W 维按 classification 的字段与 op;value None = 不加谓词。
    与 test_multivar_equiv._pred / _rows_keys 同语义(向量化)。"""
    m = pd.Series(True, index=df.index)
    for dim, v in assignments.items():
        key = dotted(dim); kind = cl["kinds"][key]
        if kind == "D":
            m &= df[key] == v
        else:
            if v is None:
                continue
            n, f, op = (cl["filter_fields"] if kind == "F" else cl["where_fields"])[key]
            m &= _cmp(df[node_col(n, f)], v, op)
    return m


def file_sha256(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def canonical_hash(obj) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, default=str).encode()).hexdigest()


def source_files(mod, spec) -> list:
    """源码指纹范围:app 包目录全部 .py ∪ spec 各 detector 所在模块文件。引擎(path2/dag)不进指纹。"""
    files = set(app_dir(mod).glob("*.py"))
    for n in spec.nodes:
        if n.detector is not None:
            files.add(Path(sys.modules[type(n.detector).__module__].__file__).resolve())
    return sorted(files)


def source_fingerprint(files: list) -> dict:
    h = hashlib.sha256()
    rel = []
    for f in sorted(files, key=lambda p: str(Path(p).resolve().relative_to(REPO))):
        r = str(Path(f).resolve().relative_to(REPO)); rel.append(r)
        h.update(r.encode() + b"\0" + Path(f).read_bytes() + b"\0")
    return {"hash": h.hexdigest(), "files": rel}


def _flat(d: dict) -> dict:
    return {f"{sec}.{k}": v for sec, kv in d.items() for k, v in kv.items()}


def snapshot_diff(old: dict, new: dict, cl: dict) -> list:
    """逐条 diff 两份底座快照,每条打「后果标签」:在网格内的只影响参照格坐标;不在网格内的是
    全部检测组合共用的底座常量,变了整张长表过期。"""
    fo, fn = _flat(old), _flat(new)
    grid = {**cl["scan_grid"], **cl["where_levels"]}
    out = []
    for k in sorted(set(fo) | set(fn)):
        o, n = fo.get(k), fn.get(k)
        if k in fo and k in fn and o == n:
            continue
        if k not in fo:
            lab = "新增 · 未进网格 · 将以新值作底座常量"
        elif k not in fn:
            lab = "删除 · build 时 Params.from_dict(strict) 会失败"
        elif k in grid:
            lab = f"{cl['kinds'][k]} 维 · 网格档位覆盖 · 仅参照格坐标需核对"
        else:
            lab = "底座常量 · 全部检测组合受影响 · 长表过期"
        out.append((k, o, n, lab))
    return out


def check_report(app: str, study, mod, cl: dict, study_path: Path) -> str:
    """三行指纹对比报告(source / base / study 各一行,附上次生成时间);指纹只是证据,重生成
    与否由用户裁定——协议见 SKILL.md「入口协议」。当前无接线中的调用方(只有测试覆盖)。"""
    base_now = base_snapshot(mod, study)
    spec0 = mod.build_pattern(mod.Params.from_dict(base_now, strict=True))
    src_now = source_fingerprint(source_files(mod, spec0))
    old_src = cl["fingerprints"]["source"]
    if src_now["hash"] == old_src["hash"]:
        l1 = "source:    一致"
    else:
        # classification 只存聚合哈希(不为逐文件 diff 再存一份 per-file 哈希),故列「范围内全部文件」供人配合 git diff 看
        l1 = "source:    已变更 · 范围内文件: [" + ", ".join(src_now["files"]) + "]"
    diffs = snapshot_diff(cl["ref_params"], base_now, cl)
    if not diffs:
        l2 = "base:      一致"
    else:
        l2 = f"base:      已变更({len(diffs)} 项)\n" + "\n".join(
            f"             {k:24s} {o!s:>8} → {n!s:<8} [{lab}]" for k, o, n, lab in diffs)
    l3 = "study:     一致" if file_sha256(study_path) == cl["fingerprints"]["study"] else "study:     已变更"
    l4 = f"上次生成:  {cl['generated_at']} @ {cl['git_head']}"
    return "\n".join([l1, l2, l3, l4])


def check_study_matches(cl: dict, study_path: Path) -> None:
    if file_sha256(study_path) != cl["fingerprints"]["study"]:
        raise SystemExit(f"study.py 已改,与 classification.json 不一致:先重跑 tune.setup({cl['app']!r})")


RUN_CALIBER = ("app", "start_date", "end_date", "head_buffer", "label_horizon", "first_passage_k",
               "price_min", "price_max", "volume_min", "study_fingerprint")


def write_run_meta(longtable_dir: Path, meta: dict) -> None:
    """run 级口径单源。已存在且任一口径字段不同 → 拒绝(续跑必须同口径,否则长表混窗)。"""
    p = Path(longtable_dir) / "run_meta.json"; p.parent.mkdir(parents=True, exist_ok=True)
    if p.exists():
        old = json.loads(p.read_text())
        bad = [k for k in RUN_CALIBER if old.get(k) != meta.get(k)]
        if bad:
            raise SystemExit(f"{p} 已存在且口径不同: {bad}(旧 {[old.get(k) for k in bad]} / 新 {[meta.get(k) for k in bad]});"
                             "换口径请换 OUT_DIR,不要在同一长表上混窗续跑")
    p.write_text(json.dumps(meta, ensure_ascii=False, indent=1) + "\n")


def load_run_meta(longtable_dir: Path) -> dict:
    p = Path(longtable_dir) / "run_meta.json"
    if not p.exists():
        raise SystemExit(f"{p}: run_meta.json 不存在——该长表不是 multivar_scan 新版产出,或路径填错")
    return json.loads(p.read_text())


def check_run_matches_classification(meta: dict, cl: dict) -> None:
    if meta.get("study_fingerprint") != cl["fingerprints"]["study"]:
        raise SystemExit("长表的 study 指纹与当前 classification.json 不一致:长表是在另一份 study 下扫的,"
                         "只能用那份分类去切它(重扫或换回那份 study)")


def check_regenerable(longtable_dir: Path, apps_dir: Path = APPS_DIR) -> tuple[bool, list[str]]:
    """判断一份长表能否用**当前代码**重新生成。五条链依次核,不短路(除两处必要早退外),
    一次报全部原因。

    **返回值的真实语义**:`True` = "未发现不可再生的证据",**不是**"一定可再生"。`False` 有
    两种来源,判定强度不同,但都按不可再生处理:一种是**发现了确凿的不可再生证据**(如底座
    文件缺席、指纹不符);另一种是**判不了**(classification 缺关键字段、import app 失败、
    底座指纹未记录等)——判不了不是证据,但也不等于可再生,一律并入 `False`。语义轴是
    `regenerable=True` ⟹ 调用方据此判定"可以删",所以危险的方向是**假阳**(明明不可再生却
    报 `True`)——它落在**删除**一侧,不是"多留垃圾"一侧。下游任何拿本函数结果去做删除决策
    的代码,都不能把 `True` 当唯一依据(例如清理工具应再叠一道人工确认或"进没进 git"的旁证)。

    仍然存在的已知盲区(全部落在删除侧,即可能误判为 `True`——假阳):
      - 链 5 比的是 `base_snapshot` 产出的 **Params 解析后语义快照**,不是 yaml 文件字节:
        yaml 里改注释、改 Params 不消费的键,或换成解析结果等价的写法,链 5 都抓不到差异——
        这是「底座内容被改但文件还在」真正残留的缝隙(`base_snapshot` 从设计上就故意忽略
        这类字节级差异,见 `test_base_fingerprint_ignores_yaml_comments`;但如果某个被判定
        为"语义等价"的字段实际上另有隐藏影响,这条链发现不了)。
      - 引擎(`path2/dag`)的改动:`source_files()` 明确不收引擎文件进指纹,引擎改写后长表
        可能再生不出来,五条链都不会报。
      - app 包新增 `.py` 文件:第 4 条 source 指纹重算走的是 classification **记录的**
        文件清单,不是重新 glob 当前目录,新文件不在清单里就不参与重算。
      - spec 拓扑变化让 classification 记录的文件清单本身过期(structural drift):这是
        source 指纹机制的固有边界,同样落在删除侧,不是"只让东西留下来"那一侧。

    `run_meta.json` 或 `classification.json` 内容损坏(不是合法 JSON)时,本函数会**抛异常而
    不是返回 False**;链 5 里 `import_app` 若在 import 期抛出 `BaseException`(而非
    `Exception`,例如模块顶层 `sys.exit()`)同样会穿透本函数的 `except Exception` 直接向上抛。
    三种情形都是**异常 ≠ 判定可删**,调用方必须自己接住(Task 9 的 `_regenerable` 已经这么做)。

    五条链:
      1. run_meta.json 存在吗(不存在 = 归属不明,只报不删)
      2. study 指纹是否仍与当前 study.py 一致(**不依赖** classification,故排在
         classification 存在性检查之前,避免被那条早退连带吞掉)
      3. 该 app 的 classification.json 还在吗(不在 = 无法核对以下两条链,必要早退)
      4. BASE_YAML 指向的底座文件是否存在;source 指纹按 classification 记录的**文件清单**
         重算是否仍一致(不需要 import app——source_fingerprint 只是按序读那些文件的字节);
         classification 缺 base_yaml/app_module 声明,或缺源码文件清单,都视为"无法核对"、
         计入 reason(判不了 ≠ 可再生)
      5. 底座**内容**是否仍与 classification 记录的一致(需要 import app 重算
         `base_snapshot`,第 4 条只查存在性抓不住"内容被改但文件还在"的情形):任何失败
         (import 失败 / yaml 读不了 / Params 报错 / 字段缺失)一律计入 reason、判不可再生,
         绝不静默放过

    返回:
        (regenerable: bool, reasons: list[str])
    """
    reasons = []
    lt = Path(longtable_dir)
    meta_p = lt / "run_meta.json"
    if not meta_p.exists():
        reasons.append(f"{meta_p} 不存在:该长表归属不明(不是 multivar_scan 新版产出),只报不删")
        return False, reasons
    meta = json.loads(meta_p.read_text(encoding="utf-8"))
    app = meta.get("app")
    if not app:
        reasons.append(f"{meta_p} 里没有 app 字段:归属不明,只报不删")
        return False, reasons

    # 链 2(study 指纹):不依赖 classification.json,提到「classification 是否还在」的
    # 早退之前先做,避免链 2 被链 3 的早退连带吞掉(评审 Minor 1)。
    study_p = Path(apps_dir) / app / "study.py"
    if not study_p.exists():
        reasons.append(f"{study_p} 不存在:声明已删,无法再生")
    elif file_sha256(study_p) != meta.get("study_fingerprint"):
        reasons.append("study.py 已改(指纹与长表记录不符):当前声明产不出这份长表")

    cl_p = Path(apps_dir) / app / "classification.json"
    if not cl_p.exists():
        reasons.append(f"{cl_p} 不存在:app 已退役或未接入,无法核对再生条件")
        return False, reasons
    cl = json.loads(cl_p.read_text(encoding="utf-8"))

    base_yaml = cl.get("base_yaml")
    app_module = cl.get("app_module", "")
    if base_yaml and app_module:
        pkg_rel = Path(*app_module.split(".")[:-1])
        base_p = REPO / pkg_rel / base_yaml
        if not base_p.exists():
            reasons.append(f"底座 {base_p.relative_to(REPO)} 不存在(被删或改名):当前代码跑不出这份长表")
    else:
        reasons.append("classification.json 缺 base_yaml/app_module 声明:无法核对底座文件是否还在(判不了 ≠ 可再生)")

    recorded = cl.get("fingerprints", {}).get("source", {})
    files = recorded.get("files") or []
    if files:
        paths = [REPO / f for f in files]
        if all(p.exists() for p in paths):
            now = source_fingerprint(paths)["hash"]
            if now != recorded.get("hash"):
                reasons.append(f"源码指纹不符(记录 {recorded.get('hash', '')[:16]}… / 现在 {now[:16]}…):"
                               "detector 或 app 代码已被改写,当前代码产不出这份长表")
        else:
            miss = [str(p.relative_to(REPO)) for p in paths if not p.exists()]
            reasons.append(f"源码文件已不存在: {miss}")
    else:
        reasons.append("classification.json 未记录源码文件清单(fingerprints.source.files 缺失或为空):"
                       "无法核对源码是否被改写(判不了 ≠ 可再生)")

    # 链 5(底座内容):链 4 只查底座文件存在性,查不出"内容被改但文件还在"——必须 import app
    # 重算 base_snapshot 才能比对内容。任何失败都判不可再生,绝不静默放过(评审 Important 1b)。
    try:
        study = load_study(study_p)
        mod = import_app(study)
        base_now = base_snapshot(mod, study)
        recorded_base = cl.get("fingerprints", {}).get("base")
        if recorded_base is None:
            reasons.append("classification.json 未记录底座指纹(fingerprints.base 缺失):"
                           "无法核对底座内容是否变过(判不了 ≠ 可再生)")
        elif canonical_hash(base_now) != recorded_base:
            reasons.append("底座内容(yaml ⊕ WIDE_OVERRIDES 展开后快照)与 classification 记录的不一致:"
                           "当前代码算出的底座跟长表生成时不同,产不出同一份数据")
    except Exception as e:
        reasons.append(f"重算底座快照失败({type(e).__name__}: {e}):无法确认底座内容未变,保守判不可再生")

    return (not reasons), reasons
