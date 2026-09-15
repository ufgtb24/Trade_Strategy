# -*- coding: utf-8 -*-
"""网格提案、定范围(propose_ranges)、准入安装(install_study)+ study.py 的确定性渲染。

**为什么要确定性**:study.py 的整份文件 sha256 是扫描结果的准入校验
(study_io.check_study_matches / check_run_matches_classification)。同一份 grid
渲染两次若字节不同,重跑一次接入就让已有扫描结果作废、必须重扫数小时。
所以:不写时间戳、所有 dict 按 sorted 键序输出、浮点用 repr 保证往返一致。
"""
from __future__ import annotations

import itertools
import json
import re
import time
from functools import partial
from pathlib import Path


def levels_for(default):
    """按默认值机械地铺一组候选档位。**默认值必在其中**——工作点要落进网格,
    否则 ref_point_from_base 与 build_classification 的「工作点取值必须在档位表里」守卫会拒。

    这是**机械建议不是判断**:哪个参数值得扫、档位该多宽,需要对这个走势的先验知识,
    由人复核(定范围阶段由 propose_ranges 给出候选,用户在开工确认时拍板)。非数值型返回 None,交人指定。

    **不产出跨零档**:0.5x 乘子对小整数默认值(如 1)取整会下溢到 0 甚至变号——0 对
    「根数/个数」这类参数几乎必然非法(2026-08-31 真实 app 冒烟实测命中:burst.min_bos、
    tb.stop_confirm_bars 两个默认值为 1 的字段因此被 classify() 拒、判成"探不出来",其中
    tb.stop_confirm_bars 正是参照格事故里的那个参数)。单纯剔掉非法档会让候选不足 3 个
    (`levels_for(1)` 剔完只剩 `{1, 2}`),所以剔除后按需向上延长乘子阶梯(继续 3.5x、
    4.5x……)补足到 ≥3 档,直到凑够为止(`levels_for(1) == [1, 2, 4]`)——原有四条契约
    (默认值必在档位中 / 至少 3 档 / 升序去重 / 非数值型返回 None)一条不破。
    """
    if isinstance(default, bool) or not isinstance(default, (int, float)):
        return None
    if default == 0:
        return None                                   # 0 无法按乘子铺档,交人指定
    is_int = isinstance(default, int)

    def _round(v):
        return int(round(v)) if is_int else float(f"{v:.4g}")

    def _same_side_of_zero(v) -> bool:
        return v > 0 if default > 0 else v < 0

    mults = [0.5, 1.0, 1.5, 2.5]
    out = {default}
    i = 0
    while True:
        while i < len(mults):
            v = _round(default * mults[i]); i += 1
            if _same_side_of_zero(v):
                out.add(v)
        if len(out) >= 3:
            break
        mults.append(mults[-1] + 1.0)                 # 阶梯不够,按需向上延长
    return sorted(out)


def propose(mod, base: dict, *, scan_grid: dict | None = None,
            where_levels: dict | None = None) -> dict:
    """列出这个 app 的可调参数、推荐档位与**实测**的维度分类,供 Claude 翻译成人话。

    base 是底座快照(study_io.base_snapshot 的输出):{section: {field: value}}。
    kind 由 classify() 探针实测得出(W=where 阈值 / F=过滤型 / D=构造参数需真扫 / E=边参数),
    **不凭参数名猜**——用人话说就是「改了必须重扫」(D/E)还是「可以事后切档位」(W/F)。

    **逐维探测,不批量**:`classify()` 在生产路径(build_classification)上就该响亮失败——
    但这里是探索性的机械建议,一个字段探不出来不该让整份提案陪葬。批量一次性把全部字段
    塞进同一个 scan_grid 送 classify() 会踩两类问题:①某字段的机械候选档位与另一字段的
    默认值组合起来违反该 app 自身的构造不变式(如 `min_side_bars*2 > total_window`),
    `build_pattern()` 直接抛异常;②只要 base 里有任何一个 where 阈值型(W)字段,批量调用
    就会撞上 `classify()` 末尾「W 维不许进 SCAN_GRID」的守卫,整批报错——这两个问题同源,
    改成逐维探测一并解决:每一维先当 D/F 维试(`classify(..., {dim: levels}, {})`),
    失败再当 W 维试(`classify(..., {}, {dim: levels})`);两次都失败就判定这一维**探不出来**
    (`kind=None`),连同**两次**探测的异常信息一并记进 `reason`(两次都可能是真因,见下)。
    非数值型/零值字段(`levels_for` 返回 None)同样给出 `reason`,不参与探测。

    两次尝试都捕**`Exception`**而不只是 `ValueError`:探测期真正执行到的是 app 自己的
    detector 构造代码(`classify()` → `probe_dim()` → `mod.build_pattern()`),它用什么
    异常类型表达"这组参数不合法"是该 app 的自由(`assert` 会抛 `TypeError`/`AssertionError`
    而非 `ValueError`)——只要 `reason` 里如实带上异常类型与消息,窄到 `ValueError` 反而是
    这里没有理由自己加的限制,会让本轮刚修好的"探不出来只崩一维、不崩全局"退化回去。

    **`reason` 同时带上两次尝试的异常**,不只是第一次:第一次(当 D/F 维试)与第二次(当
    W 维试)失败的原因通常不同,谁是真因取决于这一维实际是什么类型——对一个纯 where 阈值
    参数,第一次会失败在"这是 where 阈值,不该进 SCAN_GRID"(而它已经在第二次尝试的路上),
    只记第一条反而会让 `SKILL.md` 要求原样转述给用户的那句话,指向一件 `propose()` 自己
    刚试过且失败了的事。

    每个参数条目另带 `levels_probe`(`multivar_core.probe_levels` 的输出):逐档是否构造得出来、
    出错时的异常原文、等价档(state_key 相同)、买点 node 与首部缓冲是否随档变化。非数值型/零值
    字段没有候选档位,`levels_probe` 为 None。
    """
    from multivar_core import classify, probe_levels
    trial = {}
    for section in sorted(base):
        for field in sorted(base[section]):
            lv = levels_for(base[section][field])
            if lv:
                trial[(section, field)] = lv
    trial.update(scan_grid or {})
    trial.update(where_levels or {})

    kinds, reasons = {}, {}
    for dim, levels in trial.items():
        try:
            kinds[dim] = classify(mod, base, {dim: levels}, {}).kinds[dim]
        except Exception as e_d:
            try:
                kinds[dim] = classify(mod, base, {}, {dim: levels}).kinds[dim]
            except Exception as e_w:
                kinds[dim] = None
                reasons[dim] = f"{type(e_d).__name__}: {e_d} | {type(e_w).__name__}: {e_w}"

    params = []
    for section in sorted(base):
        for field in sorted(base[section]):
            dim = (section, field)
            default = base[section][field]
            levels = levels_for(default)
            if levels is None:
                kind, reason = None, "非数值型或值为 0,levels_for 未生成候选档位,交人指定"
            else:
                kind, reason = kinds.get(dim), reasons.get(dim)
            params.append({"section": section, "field": field, "default": default,
                           "levels": levels, "kind": kind, "reason": reason,
                           "levels_probe": None if levels is None else probe_levels(mod, base, dim, levels)})
    return {"params": params}


def ref_point_from_base(base: dict, scan_grid: dict, kinds: dict, where_levels: dict | None = None,
                        scope: str = "all") -> dict:
    """工作点 = 正式参数在网格上的落点,自动推出来,**不接受手写**。

    base 必须是正式参数值(params.yaml 的解析结果,**未套** WIDE_OVERRIDES)——宽进覆盖是扫描时
    放开的底座,不是正在用的参数。

    为什么自动:REF_POINT 的定义就是「正式参数落在网格的哪一格」,有唯一正确答案。
    手写它等于给一个确定的问题引入手滑机会——2026-08-30 真出过一次:生产值已从 2
    改成 1,而手写的 REF_POINT 还停在 2,被误当成「需要用户拍板的语义决定」挂了一轮。

    scope="all":覆盖 SCAN_GRID 与 WHERE_LEVELS 的全部轴(新窗口一律如此);scope="D":只取
    SCAN_GRID 里的 D 维(只覆盖 D 维的旧窗口,仅供测试)。正式值不在档位里就响亮失败——静默取
    最近档会让工作点偷偷变成另一个格,而工作点是所有增量的基准。
    """
    if scope == "all":
        axes = [*scan_grid.items(), *(where_levels or {}).items()]
    elif scope == "D":
        axes = [(d, lv) for d, lv in scan_grid.items() if kinds.get(d) == "D"]
    else:
        raise ValueError(f"scope 只能是 'all' 或 'D',实际 {scope!r}")
    ref = {}
    for (section, field), levels in axes:
        v = base.get(section, {}).get(field)
        if v not in levels:
            raise SystemExit(
                f"正式参数 {section}.{field}={v!r} 不在档位 {levels} 里——工作点必须精确落在"
                "网格上(它是所有增量的基准)。请把该正式值加进档位,或改用含它的档位。")
        ref[f"{section}.{field}"] = v
    return ref


def _fmt(v) -> str:
    """确定性地把一个值渲染成 Python 字面量。dict 按 sorted 键序,保证字节稳定。

    不识别的类型一律 `raise TypeError`,不落到 `repr(v)` 兜底:`repr` 对 `set` 这类
    迭代序不确定的类型会按 `PYTHONHASHSEED` 渲染出不同字节串——同一份网格在新进程里
    渲染出不同 sha256,会把该 app 已有的扫描结果**静默**作废。这条红线的全部要害就在于
    它的失败必须是响亮的,不能是静默的。"""
    if v is None or isinstance(v, (bool, int, float, str)):
        return repr(v)
    if isinstance(v, dict):
        items = sorted(v.items(), key=lambda kv: repr(kv[0]))
        return "{" + ", ".join(f"{_fmt(k)}: {_fmt(x)}" for k, x in items) + "}"
    if isinstance(v, (list, tuple)):
        body = ", ".join(_fmt(x) for x in v)
        return f"[{body}]" if isinstance(v, list) else f"({body},)" if len(v) == 1 else f"({body})"
    raise TypeError(f"_fmt 不支持的类型 {type(v).__name__}: {v!r}——study.py 渲染必须确定性,"
                    "不支持迭代序不确定的类型(如 set);如需支持,先证明其字面量渲染跨进程稳定")


def render_study(*, app_module: str, base_yaml: str, wide_overrides: dict, scan_grid: dict,
                 where_levels: dict, ref_point: dict, tight_wheres: dict, design: str = "grid") -> str:
    """渲染 apps/<app>/windows/<window>/study.py 的源码文本。**确定性:同输入同字节。**"""
    return f'''# -*- coding: utf-8 -*-
"""tune-gates · 研究声明(由 tune.install 生成)。

改这个文件会让已有扫描结果作废——它的整份文件哈希是长表准入校验。若要手改,必须在
第一次扫描之前改完;扫描之后再改,就等于要开一份新的扫描结果(换一个窗口),请重新走
一次接入流程。

REF_POINT 是工作点:正式参数在全部轴档位上的落点,由 tune.install 自动推出。
DESIGN 决定扫哪些检测组合:'grid' = 全部笛卡尔积;'screen' = 工作点 + 单参数翻转 + 两两翻转。
"""

APP_MODULE = {app_module!r}
BASE_YAML = {base_yaml!r}

WIDE_OVERRIDES = {_fmt(wide_overrides)}

SCAN_GRID = {_fmt(scan_grid)}

WHERE_LEVELS = {_fmt(where_levels)}

REF_POINT = {_fmt(ref_point)}

TIGHT_WHERES = {_fmt(tight_wheres)}

DESIGN = {design!r}
'''


# ================================================================ 参数准入与定范围
# 准入不看收益:依据全是代码事实(逐档构造、买点 node、首部缓冲、等价档)、学习端判定与无标签的买点计数,
# 在任何人看各档收益之前就能算完。install_study 执行准入表(机械闸 3),propose_ranges 把同一套事实摊给人看。

STAGES = {"screen": "screen", "grid": "grid"}     # 调参阶段 → 研究设计
USEFUL = "确实有用"                                 # 学习端 verify 记录里唯一放行多档的判定
CAT_USEFUL, CAT_IN_SERVICE, CAT_NEW = "确实有用", "在役未审定", "未在役且未审定"
PREDICATE_KINDS = ("W", "F")
SCREEN_MAX_LEVELS = 3                               # 筛选阶段检测参数:正式值 + 松一档 + 紧一档
KEEP_BAND = (0.3, 0.7)                              # 松 / 紧一档的买点事件保留比例(少的一侧 / 多的一侧)
PROBE_MAX_WORKERS = 8
PROBE_SEED = 0


def _outputs_dir() -> Path:
    import study_io as S
    return S.REPO / "outputs" / "tune_gates"


def _key(dim: tuple) -> str:
    return f"{dim[0]}.{dim[1]}"


def classify_one(mod, base: dict, dim: tuple, levels) -> tuple:
    """单独给一维分类,返回 (kind, (node, field, op) 或 None, 失败原因或 None)。

    先当检测 / 过滤型维试,再当 where 阈值试。过滤型维的底座自检要求底座值恰为最松档,底座值不在
    档位一端时这两次都会失败,于是把底座值依次换成档位两端(含 None)再试——换底座值只为过这道
    自检,所以这几次只采信判成过滤型的结果。全部失败 → kind=None,原因带上每次尝试的异常原文。"""
    from multivar_core import apply_overrides, classify
    tries = [(base, {dim: levels}, {}), (base, {}, {dim: levels})]
    ends = [v for v in levels if v is None]
    nums = [v for v in levels if v is not None]
    try:
        ends += [min(nums), max(nums)] if nums else []
    except TypeError:
        pass
    base_v = base.get(dim[0], {}).get(dim[1])
    tries += [(apply_overrides(base, {}, {dim: v}), {dim: levels}, {}) for v in dict.fromkeys(ends) if v != base_v]
    errors = []
    for i, (b, grid, where) in enumerate(tries):
        try:
            cls = classify(mod, b, grid, where)
        except Exception as e:  # noqa: BLE001 —— app 用什么异常表达"这组参数不合法"是它的自由
            errors.append(f"{type(e).__name__}: {e}")
            continue
        kind = cls.kinds[dim]
        if i >= 2 and kind != "F":
            errors.append(f"换底座值后判成 {kind},不采信")
            continue
        return kind, cls.where_fields.get(dim) or cls.filter_fields.get(dim), None
    return None, None, " | ".join(errors)


def level_rows(mod, base: dict, dim: tuple, levels, *, head_buffer: int) -> list[dict]:
    """逐档事实:`multivar_core.probe_levels` 的每档结果再补四项——
      ruler      合法且买点 node 与底座不同(换了量什么)
      window_ok  合法且首部缓冲需求不超过本窗的 head_buffer
      same_as    与之构造出同一个 pattern 的代表档值(自己是代表时为 None;代表优先取底座值)
      text       这一档不能用的人话原因(非法 > 尺子 > 首部缓冲 > 等价),能用为 None
    """
    from multivar_core import probe_levels
    key = _key(dim)
    end0 = mod.eval_meta(params=mod.Params.from_dict(base, strict=True))["end_node"]
    base_v = base.get(dim[0], {}).get(dim[1])
    rows = probe_levels(mod, base, dim, levels)
    rep = {r["state_key"]: r["value"] for r in rows if r["legal"] and r["value"] == base_v}
    for r in rows:
        v = r["value"]
        r["ruler"] = bool(r["legal"] and r["end_node"] != end0)
        r["window_ok"] = bool(r["legal"] and r["head_buffer"] <= head_buffer)
        r["same_as"] = None
        if r["legal"]:
            first = rep.setdefault(r["state_key"], v)
            r["same_as"] = None if first == v else first
        if not r["legal"]:
            r["text"] = f"{key} = {v!r} 这一档搭不出 pattern(参数校验或搭建 pattern 时报错:{r['error']})"
        elif r["ruler"]:
            r["text"] = (f"{key} = {v!r} 会把买点换到 {r['end_node']} 上(正式值下是 {end0}),等于换了量什么——"
                         "这是尺子,不能拿收益来挑")
        elif not r["window_ok"]:
            r["text"] = (f"{key} = {v!r} 需要 {r['head_buffer']} 个交易日的首部缓冲,本窗只留了 {head_buffer} 个,"
                         "这一档在本窗算不准")
        elif r["same_as"] is not None:
            r["text"] = f"{key} = {v!r} 和 {r['same_as']!r} 搭出来的是同一个 pattern,只留一个"
        else:
            r["text"] = None
    return rows


def code_fingerprints(mod, base: dict) -> dict:
    """当前代码的四个指纹(`ledger.fingerprints_for`);底座直接给——窗口声明还没写出来(准入发生在写声明
    之前)或参数文件是临时副本时也能算。base = 正式参数 ⊕ 宽进覆盖。"""
    import ledger
    return ledger.fingerprints_for(mod, base)


def axis_verdicts(app: str, axes, fingerprints) -> tuple[dict, set]:
    """学习端对这些轴的有效判定。

    只认 `data.code` 里源码指纹与尺子指纹都与当前一致的 verify 记录——判定之后 detector 代码或标签定义
    变过,判定就作废;同一轴多条有效记录取最后一条。fingerprints 是无参函数,只在确有相关 verify 记录时
    才调用(现算指纹要搭 pattern、读源码)。
    返回 ({轴: {"bucket","ts","suggested_levels"}}, 只有作废判定的轴集合)。"""
    import ledger
    want = set(axes)
    recs = [r for r in ledger.read(app) if r["kind"] == "verify" and want & set(r["axes"])]
    if not recs:
        return {}, set()
    fps = fingerprints()
    valid, seen = {}, set()
    for r in recs:
        code = r["data"].get("code") or {}
        ok = (code.get("source_fingerprint") == fps["source_fingerprint"]
              and code.get("ruler_fingerprint") == fps["ruler_fingerprint"])
        for a in want & set(r["axes"]):
            seen.add(a)
            if ok:
                valid[a] = {"bucket": r["data"].get("bucket"), "ts": r["ts"],
                            "suggested_levels": r["data"].get("suggested_levels")}
    return valid, seen - set(valid)


def _gate_category(key: str, formal, off, verdict: dict | None, stale: bool, *, off_known: bool = True) -> tuple[str, str]:
    """一道闸的准入类别与人话。off = 关到最松的取值;正式值 ≠ off 即在役。
    off_known=False:off 只是候选里最松的一个(还没有优势检查记录),只用来判在不在役,不当关闸取值说给人。"""
    if verdict and verdict["bucket"] == USEFUL:
        return CAT_USEFUL, f"学习端判定 {key} 确实有用({verdict['ts']}),可以取多档找最合适的位置"
    why = ("它有过学习端判定,但判定之后代码或标签定义变过,判定作废" if stale else
           f"学习端最近的判定是「{verdict['bucket']}」" if verdict else "学习端还没判定过它")
    if formal != off:
        off_word = (f"「关到最松({off!r})」" if off_known else
                    "「关掉」(关闸取值以优势检查放开闸时用的值为准,现在还没有优势检查记录)")
        return CAT_IN_SERVICE, (f"{key} 这道闸正在用(正式值 {formal!r}),{why}——只能比「开着({formal!r})」和"
                                f"{off_word}两档,用来查删了亏不亏")
    return CAT_NEW, (f"{key} 现在没有在用(正式值 {formal!r} 就是最松档),{why}——不能进调参;"
                     "想加这道闸,先交给学习端验证")


def _as_loose_as(v, ref, op: str) -> bool:
    """v 是否不比 ref 紧(按运算符语义;< / <= 下 None = 不设闸 = 最松)。"""
    if v == ref:
        return True
    if op in (">=", ">"):
        return v is not None and ref is not None and v <= ref
    if v is None:
        return True
    return ref is not None and v >= ref


def admission(mod, base_yaml_dict: dict, *, wide_overrides: dict, scan_grid: dict, where_levels: dict,
              stage: str, head_buffer: int, verdicts: dict, stale=frozenset()) -> dict:
    """机械闸 3:参数准入表。返回 {"axes": {参数键: {"kind","category","text"}}, "refusals": [人话...]},
    refusals 非空 = 这份网格不能落地。

    - 每条轴逐档:非法档、尺子(某档换了买点 node)、首部缓冲超本窗 → 拒绝;
    - 检测参数(D):stage="screen" 时每维 ≤3 档、含正式值、没有与别的档等价的档(等价的翻转恒为零,
      白占多重比较名额);
    - 谓词类(where 阈值 W / 过滤型 F):最松档按运算符从声明档位里算;有效判定「确实有用」→ 允许多档;
      在役(正式值 ≠ 最松档)且未审定 → 档位必须恰为 [最松档, 正式值];未在役且未审定 → 拒绝;
      where 阈值在扫描底座里的取值不得比最松档紧(否则更松那几档的买点在扫描时就被拦掉,事后切不出来);
    - 只改边的参数(E)暂不支持进网格。
    verdicts / stale 由 `axis_verdicts` 给出。"""
    from multivar_core import apply_overrides, classify, loosest_level
    if stage not in STAGES:
        raise ValueError(f"调参阶段只能是 {tuple(STAGES)} 之一,实际 {stage!r}")
    base = apply_overrides(base_yaml_dict, wide_overrides, {})
    try:
        cls = classify(mod, base, scan_grid, where_levels)
    except Exception as e:  # noqa: BLE001
        return {"axes": {}, "refusals": [f"网格声明本身有问题,分不出参数类型:{type(e).__name__}: {e}"]}
    fields = {**cls.where_fields, **cls.filter_fields}
    axes, refusals = {}, []
    for dim, levels in [*scan_grid.items(), *where_levels.items()]:
        key, kind = _key(dim), cls.kinds[dim]
        formal = base_yaml_dict[dim[0]][dim[1]]
        rows = level_rows(mod, base, dim, levels, head_buffer=head_buffer)
        rulers = [r["value"] for r in rows if r["ruler"]]
        if rulers:
            refusals.append(f"{key} 取 {rulers} 时买点换到了别的 node 上——它是尺子(决定量什么),不能进网格")
        refusals += [r["text"] for r in rows if not r["legal"] or (not r["ruler"] and not r["window_ok"])]
        if kind == "D":
            cat, text = None, f"{key} 是检测参数:准入只看逐档合法性"
            if stage == "screen":
                if len(levels) > SCREEN_MAX_LEVELS:
                    refusals.append(f"筛选阶段每个检测参数最多 {SCREEN_MAX_LEVELS} 档(正式值 + 松一档 + 紧一档),"
                                    f"{key} 给了 {len(levels)} 档: {list(levels)}")
                if formal not in levels:
                    refusals.append(f"筛选阶段的检测参数档位必须含正式值:{key} 的正式值 {formal!r} 不在 {list(levels)} 里")
                refusals += [r["text"] for r in rows if r["legal"] and not r["ruler"] and r["same_as"] is not None]
        elif kind in PREDICATE_KINDS:
            op = fields[dim][2]
            try:
                off = loosest_level(levels, op)
            except TypeError:
                refusals.append(f"{key} 的档位 {list(levels)} 里混了 None,对运算符 {op} 的闸没有意义")
                axes[key] = {"kind": kind, "category": None, "text": ""}
                continue
            if kind == "W" and not _as_loose_as(base[dim[0]][dim[1]], off, op):
                refusals.append(f"{key} 在扫描底座里取 {base[dim[0]][dim[1]]!r},比档位里最松的 {off!r} 还紧——"
                                f"底座没放开,更松那几档的买点在扫描时就被 where 拦掉了;请在宽进覆盖里把它放到 {off!r} 或更松")
            cat, text = _gate_category(key, formal, off, verdicts.get(key), key in stale)
            if cat == CAT_IN_SERVICE and not (len(levels) == 2 and set(levels) == {off, formal}):
                refusals.append(f"{text};现在给的是 {list(levels)}")
            elif cat == CAT_NEW:
                refusals.append(text)
        else:
            cat, text = None, f"{key} 改档只改变事件之间的约束(边),暂不支持进网格"
            refusals.append(text)
        axes[key] = {"kind": kind, "category": cat, "text": text}
    return {"axes": axes, "refusals": refusals}


def _setup_window(app: str, window: str, study_p: Path, apps_dir: Path) -> dict:
    """由刚写好的窗口声明生成分类表(与 tune.setup 同一组 study_io 调用)。"""
    import study_io as S
    study = S.load_study(study_p)
    cl = S.build_classification(app, window, study, S.import_app(study), study_p)
    S.write_classification(app, window, cl, apps_dir=apps_dir)
    return {"app": app, "window": window, "design": cl["design"],
            "kinds": cl["kinds"], "filter_fields": cl["filter_fields"],
            "where_fields": cl["where_fields"], "end_node": cl["end_node"],
            "bound_nodes": cl["bound_nodes"], "detection_combos": cl["detection_combos"],
            "source_files": cl["fingerprints"]["source"]["files"]}


def install_study(app: str, *, window: str, stage: str, app_module: str, base_yaml: str, wide_overrides: dict,
                  scan_grid: dict, where_levels: dict, tight_wheres: dict, cfg, apps_dir=None) -> dict:
    """过准入表(机械闸 3)后把网格落地成 apps/<app>/windows/<window>/study.py,随即生成分类表。

    stage 决定研究设计:"screen" → DESIGN="screen"(工作点 + 单翻转 + 两两翻转),"grid" → 笛卡尔积。
    准入没过 → SystemExit(人话列出全部原因),一个文件都不写。首部缓冲按 cfg.head_buffer 核。

    **写 study.py 会让该窗口已有的扫描结果作废**(它的哈希是准入校验)——调用方须先确认用户知道。

    REF_POINT 不是入参:它是工作点,由正式参数(params.yaml,未套宽进覆盖)在全部轴档位上的落点自动推出
    (见 ref_point_from_base 的 docstring,那里记着手写它导致的一次真实事故)。

    **写盘是原子的**:生成分类表时还有好几道静态守卫(TIGHT_WHERES 键须在网格内 / negation 目标上的
    谓词轴等),任何一道失败时 study.py 都已经落盘、旧文件已被覆盖——对有扫描结果的窗口这是真损失。
    故写盘前先把原文件字节读进内存(不存在则记 None),生成失败时原样写回(不存在则删掉刚建的文件)并
    重新抛出原异常;连回滚本身都失败会响亮报出、不吞。"""
    import importlib
    import study_io as S
    from multivar_core import apply_overrides, classify
    from path2 import config
    if stage not in STAGES:
        raise ValueError(f"调参阶段只能是 {tuple(STAGES)} 之一,实际 {stage!r}")
    apps_dir = Path(apps_dir) if apps_dir else S.APPS_DIR
    config.set_runtime_checks(True)
    mod = importlib.import_module(app_module)
    formal = mod.Params.from_yaml(S.app_dir(mod) / base_yaml).to_dict()
    base = apply_overrides(formal, wide_overrides, {})
    keys = [_key(d) for d in [*scan_grid, *where_levels]]
    verdicts, stale = axis_verdicts(app, keys, lambda: code_fingerprints(mod, base))
    adm = admission(mod, formal, wide_overrides=wide_overrides, scan_grid=scan_grid, where_levels=where_levels,
                    stage=stage, head_buffer=cfg.head_buffer, verdicts=verdicts, stale=stale)
    if adm["refusals"]:
        raise SystemExit("这份网格没过参数准入,没有写任何文件:\n- " + "\n- ".join(adm["refusals"]))
    kinds = classify(mod, base, scan_grid, where_levels).kinds
    ref_point = ref_point_from_base(formal, scan_grid, kinds, where_levels, scope="all")
    study_p = S.study_path(app, window, apps_dir)
    study_p.parent.mkdir(parents=True, exist_ok=True)
    original = study_p.read_bytes() if study_p.exists() else None
    study_p.write_text(render_study(
        app_module=app_module, base_yaml=base_yaml, wide_overrides=wide_overrides,
        scan_grid=scan_grid, where_levels=where_levels, ref_point=ref_point,
        tight_wheres=tight_wheres, design=STAGES[stage]), encoding="utf-8")
    try:
        summary = _setup_window(app, window, study_p, apps_dir)
    except BaseException as e_setup:
        try:
            if original is None:
                study_p.unlink()
            else:
                study_p.write_bytes(original)
        except OSError as e_restore:
            raise RuntimeError(
                f"{study_p} 写入后生成分类表失败({type(e_setup).__name__}: {e_setup}),回滚也"
                f"失败({type(e_restore).__name__}: {e_restore})——该文件现处于不可信状态,"
                "请手动核对/从 git 还原后重试"
            ) from e_setup
        raise
    return {**summary, "stage": stage, "study_path": str(study_p), "admission": adm["axes"]}


# ---------------------------------------------------------------- 定范围:候选档位来源

_SEC_RE = re.compile(r"^([A-Za-z_]\w*):")
_KEY_RE = re.compile(r"^([ \t]+)([A-Za-z_]\w*):[^#]*(#.*)?$")
# 带正负号的数通常是效果差值,带单位的是计数 / 比例,都不是参数取值
_NUM_RE = re.compile(r"(?<![\w.+\-±])(\d+(?:\.\d+)?)(?![\w.]|\s*(?:点|%|个|股|年|月|日|号|次|倍|pt))")


def yaml_comment_values(text: str) -> dict:
    """params.yaml 注释里出现过的数值,当历史取值的线索:{参数键: [数值...]}。

    只认「section 下缩进的 key: 值  # 注释」行及其紧随的、缩进更深的续行注释;日期与年份、带单位
    (点 / % / 个……)与带正负号的数不算。这是候选来源不是结论,每个值之后还要过逐档合法性。"""
    out, sec, cur, indent = {}, None, None, 0
    for line in text.splitlines():
        m_sec = _SEC_RE.match(line)
        m_key = _KEY_RE.match(line) if sec else None
        if m_sec:
            sec, cur = m_sec.group(1), None
            continue
        if m_key:
            cur, indent, comment = f"{sec}.{m_key.group(2)}", len(m_key.group(1)), m_key.group(3) or ""
        elif cur and line.lstrip().startswith("#") and len(line) - len(line.lstrip()) > indent:
            comment = line
        else:
            cur = None
            continue
        for tok in _NUM_RE.findall(comment):
            val = float(tok) if "." in tok else int(tok)
            if isinstance(val, int) and 1900 <= val <= 2100:
                continue
            out.setdefault(cur, []).append(val)
    return out


def _typed(x, like, numeric_hint):
    """把候选值换成与正式值同类型;换不了 → (False, None)。None 原样保留(不设闸是合法候选)。"""
    if x is None:
        return True, None
    if isinstance(x, bool) or not isinstance(x, (int, float)) or x != x:
        return False, None
    t = like if like is not None else numeric_hint
    if isinstance(t, bool) or not isinstance(t, (int, float)):
        return False, None
    if isinstance(t, int):
        return True, int(round(x))
    return True, float(x)


def _level_order(v):
    return (v is not None, v if v is not None else 0)


def _candidate_pool(formal_v, code_v, sources: list) -> dict | None:
    """{候选值: [来源...]};正式值一定在里面。非数值参数(字符串 / 布尔)返回 None。"""
    hint = formal_v if formal_v is not None else code_v
    if isinstance(hint, bool) or (hint is not None and not isinstance(hint, (int, float))):
        return None
    pool = {formal_v: ["正式值"]}
    for name, values in sources:
        for x in values or ():
            ok, v = _typed(x, formal_v, hint)
            if ok:
                pool.setdefault(v, [])
                if name not in pool[v]:
                    pool[v].append(name)
    return pool


def _edge_distribution(edge_dir: Path, column: str) -> dict | None:
    """优势检查样本里该闸字段的 p10 / p50 / p90(按样本 bar 行,只读这一列,不碰任何标签列)。"""
    import numpy as np
    import pyarrow.parquet as pq
    parts = sorted((edge_dir / "bars").glob("part-*.parquet"))
    chunks = []
    for part in parts:
        if column in pq.read_schema(part).names:
            chunks.append(pq.read_table(part, columns=[column]).column(0).to_numpy(zero_copy_only=False))
    if not chunks:
        return None
    x = np.concatenate(chunks).astype(float)
    x = x[np.isfinite(x)]
    if not len(x):
        return None
    p10, p50, p90 = np.quantile(x, [0.1, 0.5, 0.9])
    return {"p10": float(p10), "p50": float(p50), "p90": float(p90), "n": int(len(x))}


def _flat_overrides(d: dict) -> dict:
    return {f"{sec}.{k}": v for sec, kv in (d or {}).items() for k, v in kv.items()}


# ---------------------------------------------------------------- 定范围:无标签探针

_PROBE_CACHE: dict = {}


def _probe_stock(pkl_path: str, *, app_module: str, configs: list, start_date: str, end_date: str,
                 head_buffer: int, price_min, price_max, volume_min):
    """一只股票上逐组参数只跑检测,数训练窗内的买点事件(买点 node 事件区间组,同一组只计一次)。

    行情只切到训练窗末日(前面带首部缓冲),其后的数据一根都不读;不调用任何标签函数。
    过滤口径与扫描一致:训练窗内平均成交量不过 volume_min 的股票不计;买点事件至少一根起点落在训练窗内、
    且其中某个事件起点收盘价在价格区间内才计。返回 (每组计数, 检测耗时秒) 或 None(股票被过滤)。"""
    import importlib
    import pandas as pd
    from path2 import config
    from path2.dag.engine import analyze
    from path2.eval import _resolve_end_events
    from path2_web.data import slice_window
    from path2_web.scan import TRADING_TO_CALENDAR_RATIO
    config.set_runtime_checks(True)
    ck = (app_module, json.dumps(configs, sort_keys=True, default=str))
    if ck not in _PROBE_CACHE:
        mod = importlib.import_module(app_module)
        built = []
        for c in configs:
            p = mod.Params.from_dict(c, strict=True)
            built.append((p, mod.build_pattern(p), mod.eval_meta(params=p)["end_node"]))
        _PROBE_CACHE.clear()
        _PROBE_CACHE[ck] = built
    s, e = pd.Timestamp(start_date), pd.Timestamp(end_date)
    buf_start = s - pd.Timedelta(days=round(head_buffer * TRADING_TO_CALENDAR_RATIO))
    win = slice_window(pd.read_pickle(pkl_path), buf_start, e)
    if len(win) == 0:
        return None
    if volume_min is not None:
        sw = win[(win["date"] >= s) & (win["date"] <= e)]
        if len(sw) == 0 or sw["volume"].mean() <= volume_min:
            return None
    dates, closes = win["date"], win["close"]
    t0 = time.perf_counter()
    counts = []
    for p, spec, end_node in _PROBE_CACHE[ck]:
        spans = set()
        for m in analyze(spec, win, p).matches:
            evs = _resolve_end_events(m, end_node)
            if not any(s <= dates.iat[ev.start_idx] <= e for ev in evs):
                continue
            if not any((price_min is None or closes.iat[ev.start_idx] >= price_min)
                       and (price_max is None or closes.iat[ev.start_idx] <= price_max) for ev in evs):
                continue
            spans.add(tuple((ev.start_idx, ev.end_idx) for ev in evs))
        counts.append(len(spans))
    return counts, time.perf_counter() - t0


def _probe_counts(app_module: str, configs: list, cfg, sample_stocks: int) -> dict:
    """无标签探针:确定性抽 sample_stocks 只股票(种子固定),逐组参数数训练窗内的买点事件。
    返回 {"counts": 与 configs 对齐的总数, "n_sampled", "n_effective"(未被过滤的股数),
          "sec_per_analysis"(单股单组检测耗时,秒), "seconds"(墙钟), "n_universe"(数据目录全部股数)}。"""
    import numpy as np
    from concurrent.futures import ProcessPoolExecutor
    from path2_web.scan import _list_pkls
    pkls = _list_pkls(cfg.data_dir, cfg.ticker_regex)
    if not pkls:
        raise SystemExit(f"数据目录 {cfg.data_dir} 里没有股票数据,数不了买点事件")
    pick = np.sort(np.random.default_rng(PROBE_SEED).choice(len(pkls), size=min(sample_stocks, len(pkls)),
                                                            replace=False))
    paths = [str(pkls[i]) for i in pick]
    fn = partial(_probe_stock, app_module=app_module, configs=configs, start_date=cfg.start_date,
                 end_date=cfg.end_date, head_buffer=cfg.head_buffer, price_min=cfg.price_min,
                 price_max=cfg.price_max, volume_min=cfg.volume_min)
    workers = max(1, min(int(cfg.workers), PROBE_MAX_WORKERS, len(paths)))
    t0 = time.perf_counter()
    if workers == 1:
        results = [fn(x) for x in paths]
    else:
        with ProcessPoolExecutor(workers) as ex:
            results = list(ex.map(fn, paths))
    kept = [r for r in results if r is not None]
    counts = np.sum([r[0] for r in kept], axis=0) if kept else np.zeros(len(configs))
    return {"counts": [int(c) for c in counts], "n_sampled": len(paths), "n_effective": len(kept),
            "sec_per_analysis": (sum(r[1] for r in kept) / (len(kept) * len(configs))) if kept else None,
            "seconds": time.perf_counter() - t0, "n_universe": len(pkls)}


# ---------------------------------------------------------------- 定范围:主函数

def _loose_order(values, op: str) -> list:
    """从最松到最紧排序(< / <= 下 None 最松;>= / > 下不收 None)。"""
    if op in (">=", ">"):
        return sorted(v for v in values if v is not None)
    return [None] * (None in values) + sorted((v for v in values if v is not None), reverse=True)


def _suggest_detect(key: str, cands: list, n0: int, *, floor: int) -> dict:
    """检测参数:在保留比例落在 KEEP_BAND 内的候选里,松 / 紧各挑保留比例最接近 50% 的一个。
    正式值上的买点事件数 n0 不到 floor(Settings.min_segments_floor,买点事件下限)时不给建议。
    保留比例 = 两组参数买点事件数之比(少 / 多),只是计数之比,不是两组买点的重合度。"""
    lo, hi = KEEP_BAND
    if n0 < floor:
        return {"loose": None, "tight": None, "candidates": cands,
                "why": f"探针在正式值上只数到 {n0} 个买点事件,不到买点事件下限 {floor} 个,各档的保留比例都是噪声,"
                       "不给松紧建议;加大抽样股数再看"}
    pick = {}
    for side in ("松", "紧"):
        ok = [c for c in cands if c["direction"] == side and c["keep_ratio"] is not None and lo <= c["keep_ratio"] <= hi]
        pick[side] = min(ok, key=lambda c: abs(c["keep_ratio"] - 0.5))["value"] if ok else None
    parts = []
    for side, word in (("松", "买点变多"), ("紧", "买点变少")):
        if pick[side] is None:
            seen = [f"{c['value']!r}:{c['keep_ratio']:.0%}" for c in cands
                    if c["direction"] == side and c["keep_ratio"] is not None]
            parts.append(f"{side}一档:没有保留比例落在 {lo:.0%}~{hi:.0%} 的候选"
                         + (f"(候选 {', '.join(seen)})" if seen else "(没有让" + word + "的候选)")
                         + ",需要的话由人补一个中间值")
        else:
            c = next(c for c in cands if c["value"] == pick[side])
            parts.append(f"{side}一档建议 {pick[side]!r}:买点事件 {c['n_events']} 个 / 正式值 {n0} 个,"
                         f"少的一边是多的一边的 {c['keep_ratio']:.0%}")
    return {"loose": pick["松"], "tight": pick["紧"], "candidates": cands, "why": ";".join(parts)}


def _suggest_gate(key: str, formal, usable: list, op: str, cat: str, off, dist) -> dict:
    """闸:确实有用 → 正式值两侧各取最近一档;在役未审定 → 只有关闸这一档(off=None 表示关闸取值未知,
    不猜);未在役且未审定 → 不建议。"""
    out = {"loose": None, "tight": None, "distribution": dist}
    if cat == CAT_NEW:
        out["why"] = "不进调参,不给档位建议"
    elif cat == CAT_IN_SERVICE:
        out["loose"] = off
        out["why"] = (f"只许开 / 关两档:[{off!r}, {formal!r}]" if off is not None or None in usable else
                      "只许开 / 关两档;关闸取值以优势检查放开闸时用的值为准,现在还没有优势检查记录")
    else:
        order = _loose_order(set(usable) | {formal}, op)
        i = order.index(formal)
        out["loose"] = order[i - 1] if i > 0 else None
        out["tight"] = order[i + 1] if i + 1 < len(order) else None
        out["why"] = f"学习端判定确实有用:正式值 {formal!r} 两侧最近的可用档是 {out['loose']!r}(松)与 {out['tight']!r}(紧)"
    return out


def propose_ranges(app: str, app_module: str, *, base_yaml: str = "params.yaml", cfg, sample_stocks: int = 200) -> dict:
    """定范围:在任何人看各档收益之前,把「这个 app 的参数能怎么调」算清楚。**不读、不输出任何收益。**

    候选档位来自:代码默认值、params.yaml 注释里出现过的数值、按正式值机械铺的阶梯(levels_for)、
    学习端有效判定给的建议档、优势检查放开闸时用的值与其样本里闸字段的 p10/p50/p90。
    返回六部分:
      ruler          ① 尺子:不可调的运行口径(cfg 里进口径的字段)、标签 / 基线 / 分层代码文件、逐档换了买点
                        node 的参数、首部缓冲需求超过本窗的档
      legality       ② 逐档合法性:每档能不能用(人话原因)、等价档分组、可用档
      admission      ③ 学习端准入:闸按有效判定归「确实有用 / 在役未审定(只许开关)/ 未在役且未审定(拒绝)」,
                        检测参数不看学习端
      suggestions    ④ 建议松 / 紧一档:检测参数用无标签探针数买点事件(抽 sample_stocks 只股票、只跑检测),
                        要求保留 30%~70%;闸见 _suggest_gate
      screen_design  ⑤ 按建议档展开筛选设计的检测组合数(1 + Σ替代档 + 两两)与预计耗时
      readonly_gates ⑥ 只读闸清单:参数键 → node.field + 运算符 + 正式值
    另附 probe(探针样本量与耗时)与 unclassified(判断不了类型的参数及原因)。"""
    import importlib
    import ledger
    import study_io as S
    from multivar_core import apply_overrides
    from path2 import config
    config.set_runtime_checks(True)
    mod = importlib.import_module(app_module)
    yaml_p = S.app_dir(mod) / base_yaml
    formal = mod.Params.from_yaml(yaml_p).to_dict()
    code_default = mod.Params.default().to_dict()
    comments = yaml_comment_values(yaml_p.read_text(encoding="utf-8"))
    edge_dir = _outputs_dir() / app / "edge"
    edge_meta = edge_dir / "run_meta.json"
    edge_wide = _flat_overrides(json.loads(edge_meta.read_text(encoding="utf-8")).get("wide_overrides")
                                if edge_meta.exists() else {})
    keys = [f"{s}.{f}" for s in formal for f in formal[s]]
    verdicts, stale = axis_verdicts(app, keys, lambda: code_fingerprints(mod, formal))

    legality, admission_out, suggestions, gates, unclassified = {}, {}, {}, [], {}
    ruler_params, window_illegal, detect = [], {}, {}
    for sec in formal:
        for field in formal[sec]:
            dim, key, v = (sec, field), f"{sec}.{field}", formal[sec][field]
            verdict = verdicts.get(key)
            sources = [("代码默认值", [code_default.get(sec, {}).get(field)]),
                       ("参数文件注释", comments.get(key)),
                       ("按正式值铺的阶梯", levels_for(v) if v is not None else None),
                       ("学习端建议档", (verdict or {}).get("suggested_levels")),
                       ("优势检查放开的值", [edge_wide[key]] if key in edge_wide else None)]
            pool = _candidate_pool(v, code_default.get(sec, {}).get(field), sources)
            if pool is None:
                unclassified[key] = "不是数值参数,工具不给档位建议,需要时由人指定"
                continue
            kind, fld, reason = (classify_one(mod, formal, dim, sorted(pool, key=_level_order)) if len(pool) > 1 else
                                 (None, None, "只有正式值这一个候选取值,判断不了它属于哪类参数,需要人给一个别的取值"))
            dist = None
            if kind in PREDICATE_KINDS and (edge_dir / "bars").is_dir():
                dist = _edge_distribution(edge_dir, f"{fld[0]}.{fld[1]}")
                if dist:
                    pool = _candidate_pool(v, code_default.get(sec, {}).get(field),
                                           sources + [("优势检查样本分位", [dist["p10"], dist["p50"], dist["p90"]])])
            levels = sorted(pool, key=_level_order)
            rows = level_rows(mod, formal, dim, levels, head_buffer=cfg.head_buffer)
            usable = [r["value"] for r in rows if r["text"] is None]
            groups = {}
            for r in rows:
                if r["legal"] and not r["ruler"]:
                    groups.setdefault(r["same_as"] if r["same_as"] is not None else r["value"], []).append(r["value"])
            legality[key] = {
                "formal": v,
                "levels": [{"value": r["value"], "sources": pool[r["value"]], "usable": r["text"] is None,
                            "text": r["text"], "end_node": r["end_node"], "head_buffer": r["head_buffer"]} for r in rows],
                "equivalent": [g for g in groups.values() if len(g) > 1],
                "usable": usable}
            if any(r["ruler"] for r in rows):
                ruler_params.append(key)
            bad_hb = [r["value"] for r in rows if r["legal"] and not r["ruler"] and not r["window_ok"]]
            if bad_hb:
                window_illegal[key] = bad_hb
            if kind is None:
                unclassified[key] = f"判断不了它属于哪类参数:{reason}"
                continue
            if kind in PREDICATE_KINDS:
                node, fname, op = fld
                gates.append({"param": key, "node": node, "field": fname, "op": op, "formal": v})
                # 关闸取值只认优势检查放开闸时用的值;还没做优势检查时,候选里最松的那个只拿来判在不在役
                off_known = key in edge_wide
                off = edge_wide[key] if off_known else _loose_order(set(usable) | {v}, op)[0]
                cat, text = _gate_category(key, v, off, verdict, key in stale, off_known=off_known)
                admission_out[key] = {"kind": kind, "category": cat, "text": text, "off": off if off_known else None}
                suggestions[key] = _suggest_gate(key, v, usable, op, cat, off if off_known else None, dist)
            elif key in ruler_params:
                admission_out[key] = {"kind": kind, "category": "尺子",
                                      "text": f"{key} 某些取值会换掉买点所在的 node,等于换了量什么,不能进网格"}
            elif kind == "D":
                admission_out[key] = {"kind": kind, "category": "检测参数",
                                      "text": f"{key} 是检测参数:改了要重新检测,准入不看学习端,只看合法性与买点保留比例"}
                alts = [x for x in usable if x != v]
                if alts:
                    detect[key] = (dim, alts)
            else:
                admission_out[key] = {"kind": kind, "category": "暂不支持",
                                      "text": f"{key} 改档只改变事件之间的约束(边),暂不支持进网格"}

    probe = None
    if detect:
        index = [(key, x) for key, (_d, alts) in detect.items() for x in alts]
        configs = [formal] + [apply_overrides(formal, {}, {detect[key][0]: x}) for key, x in index]
        probe = _probe_counts(app_module, configs, cfg, sample_stocks)
        n0 = probe["counts"][0]
        per = {}
        for (key, x), n in zip(index, probe["counts"][1:]):
            big = max(n, n0)
            srcs = {r["value"]: r["sources"] for r in legality[key]["levels"]}
            per.setdefault(key, []).append({
                "value": x, "sources": srcs[x], "n_events": n, "keep_ratio": (min(n, n0) / big) if big else None,
                "direction": "紧" if n < n0 else "松" if n > n0 else "不变"})
        for key, cands in per.items():
            suggestions[key] = _suggest_detect(key, cands, n0, floor=cfg.min_segments_floor)

    alts = {k: [x for x in (s["loose"], s["tight"]) if x is not None]
            for k, s in suggestions.items() if admission_out[k]["kind"] == "D"}
    alts = {k: a for k, a in alts.items() if a}
    n_alt = [len(a) for a in alts.values()]
    n_combos = 1 + sum(n_alt) + sum(a * b for a, b in itertools.combinations(n_alt, 2))
    screen = {"alts": alts, "n_combos": n_combos, "seconds_est": None, "basis": "没有可调的检测参数,不用新检测"}
    if probe and probe["sec_per_analysis"] is not None:
        workers = max(1, int(cfg.workers))
        frac = probe["n_effective"] / probe["n_sampled"]
        screen["seconds_est"] = probe["sec_per_analysis"] * n_combos * probe["n_universe"] * frac / workers
        screen["basis"] = (f"按无标签探针实测的单股单组检测耗时 × {n_combos} 个检测组合 × 全部 {probe['n_universe']} 只股票"
                           f"(约 {frac:.0%} 过成交量过滤)÷ {workers} 个进程估算;没算标签,扫描端会复用上游事件流,只作量级参考")

    probe_out = None if probe is None else {
        "n_sampled": probe["n_sampled"], "n_effective": probe["n_effective"], "n_formal_events": probe["counts"][0],
        "window": {"start": cfg.start_date, "end": cfg.end_date}, "seconds": probe["seconds"],
        "low_count": probe["counts"][0] < cfg.min_segments_floor}
    return {
        "app": app, "app_module": app_module, "base_yaml": base_yaml,
        "ruler": {"run_caliber": {k: getattr(cfg, k) for k in S.RUN_CALIBER if hasattr(cfg, k)},
                  "ruler_files": list(ledger.RULER_FILES), "ruler_params": ruler_params,
                  "head_buffer": cfg.head_buffer, "window_illegal": window_illegal},
        "legality": legality, "admission": admission_out, "suggestions": suggestions,
        "screen_design": screen, "readonly_gates": gates,
        "probe": probe_out, "unclassified": unclassified,
    }
