# -*- coding: utf-8 -*-
"""feature-study · app adapter 模板。复制为 apps/<你的 app>/adapter.py 后填四个常量与 observe()。

骨架(extract_skeleton.py)按文件路径加载这份声明(importlib.util.spec_from_file_location,
不走 sys.path、不建 __init__.py——tune-gates/apps/ 下可能存在同名 app 目录,走
sys.path 会撞命名空间包)。骨架本身走势-无关,一切 pattern 特异的东西(节点名、
几何算式、已知信号列)都封在这一个文件里。

布局与 .claude/skills/tune-gates/apps/<app>/ 对齐(同仓两个 skill 用同一套心智模型)。
"""

# 提供 Params / build_pattern / eval_meta 的模块(是模块,不是包)
APP_MODULE = "path2_apps.<你的 app>.dag_spec"

# 覆盖 scan 快照里的参数取值,按 yaml section 分组、结构与 Params.from_dict 对齐,
# 例如 {"<section>": {"<field>": <value>}}。
# ⚠ 这是「某一次 scan 快照」的属性,不是「这个 app」的属性:Params.from_dict 对快照里
# 缺失的键会注入「当前代码默认值」,scan 早于某参数引入时该参数会被静默启用,重放
# match 集必失配。起手留空;换用哪份 scan,就去核对该 scan 的 params_snapshot 里
# 是否已含你要覆盖的键,再决定这里要不要写、写什么——换 scan 必须重核这个常量。
PARAM_OVERRIDES = {}

# 哪几列构成一条观测的身份,交给骨架事后 drop_duplicates 去重(取代原骨架里逐条
# 手写的 seen/key 流式去重)。
# 前提(写死,不满足就不能这样去重):这几列必须函数决定 end_node 事件与 observe()
# 的全部返回值——这是「流式去重改成事后 drop_duplicates」语义等价的依据;若两条
# match 的 DEDUP_COLS 取值相同、却算出不同的几何或不同的 label,等价性就断了。
DEDUP_COLS = ("symbol", "<能唯一确定一条观测的列名...>")

# 已知有信号的列名(来源 = docs/feature_candidates.md 已关闭段判定「有信号」的条目)。
# 起手留空,随登记簿关闭条目逐步长起来——关闭一条,就在这里加一条列名,并在
# observe() 里实现它的计算。
KNOWN_SIGNALS: list[str] = []


def observe(m, evs, win, cols) -> dict | None:
    """从一条 match 里取出本 app 特异的观测列。

    参数:
      m: 一条 match(res.matches 的元素)。
      evs: {instance_id: event} 全事件字典。
      win: 切好的 OHLCV DataFrame。
      cols: 骨架每股预算一次的 types.SimpleNamespace,字段 = high/low/close/open/
        volume/atr/n——前五个是整列 ndarray(win[...].to_numpy(float)),atr 是
        calculate_atr(high, low, close, 14) 的整列 ndarray,n = len(win)。

    返回:
      dict:仅本 app 特异的列。骨架另行注入五个通用列(symbol / label / entry_idx /
        entry_date / c0_atr_pct),本函数不许再产出它们。
      None:这条 match 不进样本(如边界不足、除数非正等)。
    """
    raise NotImplementedError("在此实现 observe():从 m.node_index 取事件、用 cols 算几何、返回观测 dict")
