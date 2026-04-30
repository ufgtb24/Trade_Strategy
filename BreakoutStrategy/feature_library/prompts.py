"""nl_description 生成所用 prompt 模板。

SYSTEM_PROMPT 定义 GLM-4V-Flash 的角色（K 线分析师）+ 输出规范
（结构化自然语言段落，不包含 JSON / markdown 代码块）。
build_user_message 把 meta dict 拼成"图像 + 上下文文本"的 user 消息。

D-08：OHLC 相对参考改用突破日 close（BO close）作锚点，与 chart.png Y 轴 BO close pivot 统一，
避免 GLM-4V cross-attention 时遇到两套不一致的相对参考系。
"""

from typing import Any


SYSTEM_PROMPT = (
    "You are an expert technical analyst describing US stock K-line breakout charts. "
    "Given a chart image and quantitative context, write a precise, structured "
    "natural-language description (Chinese) that will be used as input to a downstream "
    "feature induction system.\n\n"
    "Required output structure (plain text, no markdown code blocks):\n"
    "1. 一段总览（突破前后的整体走势特征）\n"
    "2. 盘整阶段细节（形态 / 量能 / 紧致度，引用上下文中的数值）\n"
    "3. 突破日特征（K 线形态 / 量能跳变 / 与盘整边界的位置关系）\n"
    "4. 上下文中的隐含规律假说（不强制，可空）\n\n"
    "约束：\n"
    "- 不要输出 JSON / markdown 代码块 / 标题符号\n"
    "- 数值引用时保留 1-2 位小数\n"
    "- 字段为 N/A 时跳过该数值，不要编造\n"
    "- 篇幅 200~400 中文字符\n"
)


def build_user_message(meta: dict[str, Any]) -> str:
    """构造发送给 GLM-4V-Flash 的 user 文本（与图像同消息）。

    归一化方案 B：脱敏 ticker / bo_date / 绝对价位与成交量。
    OHLCV 改为相对突破日 close 的百分比（与 chart.png Y 轴 BO close pivot 统一）。
    若 bo['close'] 缺失或非正则跳过相对价段（降级行为）。
    5 个盘整字段已是无量纲（%、比值、bar 数），保留原值。

    Args:
        meta: sample_meta dict（落盘 meta.yaml 仍含原始 ticker/bo_date/价位
              用于人类追溯，本函数仅在内存中脱敏 prompt 副本）。

    Returns:
        脱敏后的纯文本字符串。
    """
    bo = meta["breakout_day"]
    consol = meta["consolidation"]
    bo_close = bo.get("close")

    def fmt_pct(v) -> str:
        if not isinstance(v, (int, float)) or isinstance(v, bool):
            return "N/A"
        return f"{v:+.2f}%"

    def fmt_num(v) -> str:
        if isinstance(v, bool):
            return "N/A"
        return f"{v:.2f}" if isinstance(v, (int, float)) else "N/A"

    # OHLC → 相对 BO close 的 %（close 锚点 = 0%，与 chart.png Y 轴零点统一）
    if isinstance(bo_close, (int, float)) and not isinstance(bo_close, bool) and bo_close > 0:
        open_pct  = (bo['open']  - bo_close) / bo_close * 100
        high_pct  = (bo['high']  - bo_close) / bo_close * 100
        low_pct   = (bo['low']   - bo_close) / bo_close * 100
        ohlc_line = (
            f"突破日 OHLC（相对突破日 close 的 %，close 锚点 = 0%）："
            f"open={fmt_pct(open_pct)} "
            f"high={fmt_pct(high_pct)} "
            f"low={fmt_pct(low_pct)} "
            f"close=+0.00%\n"
        )
    else:
        ohlc_line = "突破日 OHLC：N/A（bo_close 缺失，已跳过相对价段）\n"

    return (
        f"样本类型：股票 K 线突破样本（已脱敏 ticker / 日期 / 绝对价）\n"
        f"{ohlc_line}"
        f"\n盘整阶段量化字段（无量纲）：\n"
        f"- 持续时长（bars）：{fmt_num(consol['consolidation_length_bars'])}\n"
        f"- 高度百分比：{fmt_num(consol['consolidation_height_pct'])}%\n"
        f"- 距 52 周高点：{fmt_num(consol['consolidation_position_vs_52w_high'])}%\n"
        f"- 量能比（盘整 / 盘整前 60 bars）：{fmt_num(consol['consolidation_volume_ratio'])}\n"
        f"- 紧致度（高度 / ATR14）：{fmt_num(consol['consolidation_tightness_atr'])}\n"
        f"\n请按 SYSTEM_PROMPT 要求描述这张 K 线图。"
    )
