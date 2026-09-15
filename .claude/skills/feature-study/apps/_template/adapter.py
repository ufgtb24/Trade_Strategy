# -*- coding: utf-8 -*-
"""feature-study · app adapter 模板。复制为 apps/<你的 app>/adapter.py 后填五个常量与 observe()。

骨架(extract.py)按文件路径加载这份声明(importlib.util.spec_from_file_location,
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

# 买点事件身份:哪几列认出「同一段买点」(买点 node 解析出的事件区间组),交给骨架事后
# drop_duplicates 去重——同一段买点被多个 match(不同前缀)共享时只留一行。
# 前提(写死):这几列必须函数决定 end_node 事件,从而决定 label 与四态计数;observe() 里随前缀
# 变化的列(如锚定的上游事件几何)在去重后取数据原序第一条存活 match 的值。闸类字段要看「任一
# 前缀过闸」时不要用这份去重后的表,改用 extract.build_from_longtable(保留不同前缀的行)。
DEDUP_COLS = ("symbol", "<买点事件起点列>", "<买点事件终点列>")

# 已知有信号的列名(来源 = docs/feature_candidates.md 已关闭段判定「有信号」的条目)。
# 起手留空,随登记簿关闭条目逐步长起来——关闭一条,就在这里加一条列名,并在
# observe() 里实现它的计算。
KNOWN_SIGNALS: list[str] = []

# 参数 ↔ 特征的对应:{参数键(params.yaml 的 section.field): 特征名}。执行端写定案时据此
# 知道这次挑选落在哪个特征上;对账第三步(伪闸重放)按这里声明的特征字段去读 detector 事件。
# 特征字段必须由 detector 产出、挂在事件上;还没实现的可以先声明,observe() 不引用它。起手留空。
PARAM_FEATURES: dict[str, str] = {}


def observe(m, evs, win, cols) -> dict | None:
    """从一条 match 里取出本 app 特异的观测列。

    参数:
      m: 一条 match(res.matches 的元素)。
      evs: {instance_id: event}——detector 直接产出的事件,**不含容器 child**(如
        bottom_burst 的 "tb.segments" 展开出的每个 segment,其 instance_id 不在
        这里;要取 child 用 m.node_index[父 node].child_slots())。
      win: 切好的 OHLCV DataFrame。
      cols: 骨架每股预算一次的 types.SimpleNamespace,字段 = high/low/close/open/
        volume/atr/n——前五个是整列 ndarray(win[...].to_numpy(float)),atr 是
        calculate_atr(high, low, close, 14) 的整列 ndarray,n = len(win)。

    返回:
      dict:仅本 app 特异的列。骨架另行注入通用列(symbol / label / entry_idx / entry_date /
        year / c0_atr_pct / up / down / both / none),本函数不许再产出它们。
      None:这条 match 不进样本(如边界不足、除数非正等)。
    """
    raise NotImplementedError("在此实现 observe():从 m.node_index 取事件、用 cols 算几何、返回观测 dict")
