# path2_apps/new_step/dag_spec.py
"""new_step dag 声明(第二版):旧平台 → 一两根放量大阳线的阶跃 → 站上新平台,新平台上逐日买。

pattern 的意思(取自标注里 new_step 的定义与样本):像跃迁函数——一根或几根大幅上涨、放量的强势 K 线,
比左右两侧的波动都高,把股价从旧平台抬到一个更高的新平台;右侧企稳后站上新平台。买入理由:没追涨、
波动小、守在新平台最低点之上、收阳线。

拓扑:
  节点: plateau(唯一有 detector 的 node:PlateauDetector,只吃 K 线;复合事件,一天一个实例)
        └ 子结构 node(由 plateau 物化,不求解,children 声明槽 → node):
            old   → old_plat   旧平台段 [s-L, s-1]
            step  → step       阶跃段 [s, e](一段阶跃的每个前缀各一个)
            new   → new_plat   新平台段 [e+1, t-1]
            today → today      当天 [t, t](点事件,买点)
  边:   无(零边 pattern:全部有 detector 的 node 都求解,只有 plateau 有 detector,故每个通过
        where 的 plateau 实例就是一个 hit)
  买点: plateau.today(eval_meta 的 end_node)

约束归宿(用户的词 → where 名 / 读的字段;阈值全在 params 的 plateau section):
  旧平台 / 阶跃 / 新平台 / 当天怎么切     -> PlateauDetector(old_window, strong_k, max_step_bars, max_days)
  旧平台平                               -> where old_flat   : plateau.old_flat_ratio <= old_flat_max
  大涨幅                                 -> where step_big   : step.rise >= step_rise_min
  阶跃比两侧(左右)的波动都强             -> where step_strong: step.vs_left >= vs_left_min
                                                              且 plateau.vs_right >= vs_right_min
  平台交界放量                           -> where step_vol   : step.vol_ratio >= step_vol_min
  守在新平台最低点之上(新平台守住)       -> where new_hold   : plateau.keep_ratio >= keep_min
  波动小                                 -> where new_calm   : plateau.calm_ratio <= calm_max
  没追涨(当天收盘在阶跃以来最高价之下)   -> where no_chase   : plateau.vs_high < vs_high_max
  收阳线                                 -> where bull_close : today.body > body_min
  站上新平台(收盘没跌回旧平台价位)       -> PlateauDetector 族尾:收盘 <= 旧平台价位即这一族结束

where 全挂在 plateau(决定能否命中);子结构 node step / today 另挂诊断层 where(只影响带子档位显示,
不进求解),与父 where 共用同一谓词对象:step 挂 step_big / vs_left(step_strong 的左侧那半)/ step_vol,
today 挂 bull_close。
"""
from __future__ import annotations

from typing import Optional

from path2.dag.nodes import NodeSpec
from path2.dag.spec import PatternSpec
from path2.stdlib.app import make_app
from path2.dag import where as W

from .plateau import PlateauDetector, OldPlatform, Step, NewPlatform, Today
from .params import Params, load_params, DEFAULT_YAML_PATH    # noqa: F401 re-export 供 web worker(registry 注册 .dag_spec 而非包 init)


def build_pattern(params: Params) -> PatternSpec:
    """参数化声明工厂:给定 params 造 PatternSpec。detector 实例 + where 阈值在此闭合。"""
    p = params.plateau
    # 作用在子段本身的内层谓词:父 where 经 W.child 委托,子结构 node 的诊断层 where 直接挂同一对象
    rise_ok = W.attr("rise", ">=", p.step_rise_min)
    vs_left_ok = W.attr("vs_left", ">=", p.vs_left_min)
    vol_ok = W.attr("vol_ratio", ">=", p.step_vol_min)
    body_ok = W.attr("body", ">", p.body_min)

    nodes = (
        NodeSpec("plateau",
                 PlateauDetector(**params.plateau_kwargs()),
                 where=(
                     ("old_flat",    W.attr("old_flat_ratio", "<=", p.old_flat_max)),
                     ("step_big",    W.child("step", rise_ok)),
                     ("step_strong", W.all(W.child("step", vs_left_ok),
                                           W.attr("vs_right", ">=", p.vs_right_min))),
                     ("step_vol",    W.child("step", vol_ok)),
                     ("new_hold",    W.attr("keep_ratio", ">=", p.keep_min)),
                     ("new_calm",    W.attr("calm_ratio", "<=", p.calm_max)),
                     ("no_chase",    W.attr("vs_high", "<", p.vs_high_max)),
                     ("bull_close",  W.child("today", body_ok)),
                 ),
                 children={"old": "old_plat", "step": "step", "new": "new_plat", "today": "today"}),
        NodeSpec("old_plat", event_cls=OldPlatform),
        NodeSpec("step", event_cls=Step,
                 where=(("step_big", rise_ok), ("vs_left", vs_left_ok), ("step_vol", vol_ok))),
        NodeSpec("new_plat", event_cls=NewPlatform),
        NodeSpec("today", event_cls=Today,
                 where=(("bull_close", body_ok),)),
    )
    return PatternSpec(pattern_id="new_step", nodes=nodes, edges=())


analyze, has_hit, PATTERN_DAG = make_app(default_params=Params.default, build_pattern=build_pattern)


def eval_meta(params: Optional[Params] = None) -> dict:
    """评估元数据(path2_web 协议):买点 = plateau 容器 today 槽的当天;
    首部缓冲 = 实例当天 t 最远回看的根数:plateau 跨度起点 s - L(L = old_window),开段时
    还要读 r_{s-L} 即 close_{s-L-1};t ≤ e + max_days、e ≤ s + max_step_bars - 1,故从 s-L-1
    到 t 含两端最多 max_days + max_step_bars + old_window + 1 根。"""
    p = (params or Params.default()).plateau
    return {
        "end_node": "plateau.today",
        "head_buffer_trading_days": p.max_days + p.max_step_bars + p.old_window + 1,
    }
