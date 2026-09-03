# -*- coding: utf-8 -*-
"""网格提案 + study.py 的确定性渲染。

**为什么要确定性**:study.py 的整份文件 sha256 是扫描结果的准入校验
(study_io.check_study_matches / check_run_matches_classification)。同一份 grid
渲染两次若字节不同,重跑一次接入就让已有扫描结果作废、必须重扫数小时。
所以:不写时间戳、所有 dict 按 sorted 键序输出、浮点用 repr 保证往返一致。
"""
from __future__ import annotations


def levels_for(default):
    """按默认值机械地铺一组候选档位。**默认值必在其中**——参照格要落进网格,
    否则 build_classification 的「REF_POINT 必须恰好覆盖全部 D 维」守卫会拒。

    这是**机械建议不是判断**:哪个参数值得扫、档位该多宽,需要对这个走势的先验知识,
    由人复核(见 SKILL.md「网格提案」一节)。非数值型返回 None,交人指定。

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
    """
    from multivar_core import classify
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
                           "levels": levels, "kind": kind, "reason": reason})
    return {"params": params}


def ref_point_from_base(base: dict, scan_grid: dict, kinds: dict) -> dict:
    """参照格 = 生产参数在网格上的落点,自动推出来,**不接受手写**。

    为什么自动:REF_POINT 的定义就是「生产参数落在网格的哪一格」,有唯一正确答案。
    手写它等于给一个确定的问题引入手滑机会——2026-08-30 真出过一次:生产值已从 2
    改成 1,而手写的 REF_POINT 还停在 2,被误当成「需要用户拍板的语义决定」挂了一轮。

    只取 D 维:build_classification 校验「REF_POINT 必须恰好覆盖全部 D 维」。
    生产值不在档位里就响亮失败——静默取最近档会让参照格偷偷变成另一个格,
    而参照格是所有增量的基准。
    """
    ref = {}
    for (section, field), levels in scan_grid.items():
        if kinds.get((section, field)) != "D":
            continue
        v = base.get(section, {}).get(field)
        if v not in levels:
            raise SystemExit(
                f"生产值 {section}.{field}={v!r} 不在档位 {levels} 里——参照格必须精确落在"
                "网格上(它是所有增量的基准)。请把该生产值加进档位,或改用含它的档位。")
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
                 where_levels: dict, ref_point: dict, tight_wheres: dict) -> str:
    """渲染 apps/<app>/study.py 的源码文本。**确定性:同输入同字节。**

    FLAG_RULES 恒为空列表:它的取值是 lambda,渲染函数无法确定性地把闭包/函数体转成
    源码文本,所以不接受入参、也不推导——需要它的 app 必须在渲染后手改(见输出文本里
    的头部说明,以及 tune.install 的 docstring)。
    """
    return f'''# -*- coding: utf-8 -*-
"""tune-gates · study 声明(由 tune.install 生成)。

改这个文件会让已有扫描结果作废——它的整份文件哈希是长表准入校验。若要手改
(例如补充 FLAG_RULES:渲染器无法把 lambda 确定性地转成源码,只能留空由人补),
必须在第一次扫描之前改完;扫描之后再改,就等于要开一份新的扫描结果,请重新走
一次接入流程。

FLAG_RULES 的写法:格级机制标记,cell(点号键 dict)→ 标记文本或 None,用于
cells.csv 的 flags 列。cell 是 region_core.cell_coords() 的输出,两套键名不同、
别按直觉都写参数名:
  - combo 轴(来自 SCAN_GRID 的 D 维)用参数名 "<section>.<param>"(与 SCAN_GRID 键一致)
  - pred 轴(F/W 维)用长表列名 "<node_id>.<field>"(classify() 探出来的 detector
    字段名,node_id 是 dag 里的节点名、field 是该 node 上的属性名——通常不等于参数名)
写错会在 cells.csv 阶段裸 KeyError。
"""

APP_MODULE = {app_module!r}
BASE_YAML = {base_yaml!r}

WIDE_OVERRIDES = {_fmt(wide_overrides)}

SCAN_GRID = {_fmt(scan_grid)}

WHERE_LEVELS = {_fmt(where_levels)}

REF_POINT = {_fmt(ref_point)}

TIGHT_WHERES = {_fmt(tight_wheres)}

FLAG_RULES = []
'''
