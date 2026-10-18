"""看图工作流的两种模式:正式模式与调试模式。

调试模式(用户 2026-10-18 定):已有数据里最早的一年 2021-10-01..2022-09-30 划作调试段,只用来调试看图工作流——
看图、建卡、跑对照页都行,不进正式账、不算尝试。防的是:还没把工具做好,就在调试时把训练段的样本和尝试次数
用掉;也防调试时看到 2022-10 起的预检段、训练段或验证段。

选模式:环境变量 CHART_WORKFLOW_MODE = debug → 调试模式;不设或 formal → 正式模式;别的值 → ModeError 停下
(拼错了不悄悄当正式模式跑)。网页由启动脚本 scripts/path2/run_path2_web_debug.py 设好再起前后端;会话在调试时
跑命令行工具,每条命令前同样带上 CHART_WORKFLOW_MODE=debug。

调试模式下(正式模式的行为不变):
- 看图范围 = 调试段 [DEBUG_START, DEBUG_END],是这里的代码常量。chart_workflow.config.load_config 把训练段起止、
  看图下界、对照页的内圈年份强制写成调试段(配置文件、命令行覆盖都改不了),读数据口 loader 读任何行情都截到
  DEBUG_END(read_ceiling)。前瞻收益本来就要求观察期的每一根都在读到的行情里,行情截到 DEBUG_END,走不完的
  就不算,不会拿后面的数据补。环境变量只选模式、不带日期,改不了上界。
- 记账类文件写调试账(chart_workflow.state):默认在主目录的 outputs/chart_workflow_debug/,不进 git;环境变量
  CHART_WORKFLOW_DEBUG_STATE_ROOT 可指到临时目录(测试与冒烟用)。正式模式的环境变量 CHART_WORKFLOW_STATE_ROOT
  调试模式不认。调试账的标记文件是 DEBUG_LEDGER.md(正式账是 STATE_ROOT.md),两种模式都拒绝对方的标记。
  调试账不进 git、能清空重来,所以没有水位,也不查别的分支(state 模块说明);正式水位调试模式一律不读不写。
  新建与清空见 chart_workflow.debugroot。
- 可重算的产物放在正式那份旁边、名字加 _debug 的目录(debug_variant):清单、缓存、数据错误登记
  outputs/chart_workflow → outputs/chart_workflow_debug;网页的扫描结果 outputs/path2_web → outputs/path2_web_debug。
- 清单名必须以 dbg- 开头,正式模式拒绝这个前缀(check_list_id):会话在调试时忘了带模式环境变量,命令当场报错,
  不会把测试清单、测试尝试悄悄记进正式账。
- 清单文件与网页扫描结果带 mode = debug 标记;两种模式只打开自己的(正式的清单不带标记)。
- 卡成立日清单(chart_workflow.cardhits:卡说成立的天列成清单、逐张标「是 / 不是」、归类、小结)只在调试模式下用,
  东西只写调试账;正式模式下这些命令、这种清单、网页上的「是 / 不是」一律拒绝。
- 看过记录两种模式各记各的(chart_workflow.views 模块说明):调试模式只记调试段以内的图窗,越出的要到正式模式下记;
  正式模式不收整张都在调试段里的图窗。不分界面,不认 --allow-outside,补记也一样。
"""
from __future__ import annotations

import os
from pathlib import Path

FORMAL = "formal"
DEBUG = "debug"
ENV_VAR = "CHART_WORKFLOW_MODE"

DEBUG_START = "2021-10-01"          # 调试段起点(已有数据从 2021-10 开始)
DEBUG_END = "2022-09-30"            # 调试段终点:调试模式下读任何行情的硬上限
DEBUG_YEARS = ("2021", "2022")      # 调试段跨的年份(对照页的内圈年份)
DEBUG_LABEL = "调试模式：2021-10～2022-09，不进正式账"
DEBUG_LIST_PREFIX = "dbg-"
DEBUG_SUFFIX = "_debug"


class ModeError(ValueError):
    """模式环境变量的值不认识,或清单 / 扫描属于另一种模式。"""


def current() -> str:
    """当前模式:FORMAL 或 DEBUG。环境变量的值不认识 → ModeError。每次现读(测试会切换)。"""
    v = (os.environ.get(ENV_VAR) or "").strip()
    if v in ("", FORMAL):
        return FORMAL
    if v == DEBUG:
        return DEBUG
    raise ModeError(f"环境变量 {ENV_VAR}={v!r} 不认识:只能是 {DEBUG}(调试模式)或不设 / {FORMAL}(正式模式)")


def is_debug() -> bool:
    return current() == DEBUG


def read_ceiling(hard_end: str) -> str:
    """读行情的上限:调试模式 = min(hard_end, DEBUG_END);正式模式 = hard_end(loader.HARD_END)。"""
    return min(hard_end, DEBUG_END) if is_debug() else hard_end


def debug_variant(path) -> Path:
    """正式那份目录旁边、名字加 _debug 的目录:outputs/chart_workflow → outputs/chart_workflow_debug。"""
    p = Path(path)
    return p.parent / (p.name + DEBUG_SUFFIX)


def check_list_id(list_id: str) -> None:
    """清单名与当前模式对得上:调试模式必须以 dbg- 开头,正式模式不得以它开头;对不上 → ModeError。"""
    debug_named = str(list_id).startswith(DEBUG_LIST_PREFIX)
    if is_debug() and not debug_named:
        raise ModeError(f"调试模式的清单名必须以 {DEBUG_LIST_PREFIX} 开头: {list_id!r}")
    if not is_debug() and debug_named:
        raise ModeError(f"{list_id!r} 是调试模式的清单名({DEBUG_LIST_PREFIX} 开头),正式模式不收;"
                        f"调试时每条命令前带上 {ENV_VAR}={DEBUG}")


def doc_mode(doc: dict) -> str:
    """清单或扫描标记里写的模式:写了 debug 就是 DEBUG,没写或写 formal 是 FORMAL,别的值 → ModeError。"""
    v = doc.get("mode") if isinstance(doc, dict) else None
    if v in (None, FORMAL):
        return FORMAL
    if v == DEBUG:
        return DEBUG
    raise ModeError(f"mode 标记不认识: {v!r}")


def foreign_reason(doc: dict, what: str) -> str | None:
    """这份清单 / 扫描不属于当前模式时的说明(给用户看);属于当前模式 → None。"""
    try:
        theirs = doc_mode(doc)
    except ModeError as e:
        return f"这份{what}的{e}"
    mine = current()
    if theirs == mine:
        return None
    if mine == DEBUG:
        return f"这份{what}属于正式模式,调试模式打不开"
    return f"这份{what}属于调试模式,正式模式打不开"


def apply_to_workflow_config(cfg: dict, formal_root: Path) -> dict:
    """调试模式下把 chart_workflow 配置的看图范围换成调试段、产物目录换成 formal_root 旁边的 _debug 那份
    (formal_root:配置里 root 锚到 repo root 之后的路径),就地改并返回;正式模式原样返回,一个键都不加。"""
    if not is_debug():
        return cfg
    cfg["train_start"] = DEBUG_START
    cfg["train_end"] = DEBUG_END
    cfg["view_floor"] = DEBUG_START
    cfg["contrast"]["inner_years"] = list(DEBUG_YEARS)
    cfg["root"] = str(debug_variant(formal_root))
    cfg["mode"] = DEBUG
    return cfg
