"""Inducer batch 模式 prompt 模板。

INDUCER_SYSTEM_PROMPT 定义 Inducer 角色 + YAML 输出格式 + K≥2 等约束。
build_batch_user_message 把 N 个 sample 的 meta dict 拼成图序对应的 user 消息；
归一化方案 B：脱敏 ticker / bo_date / 绝对价，仅保留无量纲形态信息。

D-08：OHLC 相对参考改用突破日 close（BO close）作锚点（原为 consolidation.pivot_close），
与 chart.png Y 轴 BO close pivot 统一，避免图像通道与文本通道使用不同零点。
"""

from typing import Any, overload


INDUCER_SYSTEM_PROMPT = (
    "你是 K 线形态归纳专家。我会给你一批同一个研究主题的 K 线图（每张图含突破日 / 盘整起点标注），"
    "还有每张图的关键数值上下文（已脱敏 ticker / 日期 / 绝对价，仅保留无量纲形态信息）。"
    "你的任务是找出这批图共有的、有判别意义的形态规律。\n\n"
    "输出严格遵守以下 YAML 格式（不含 markdown 代码块、不含 ```yaml 围栏）：\n\n"
    "candidates:\n"
    "  - text: \"<规律的自然语言描述，30~100 字>\"\n"
    "    supporting_sample_ids: [<支持该规律的图序列表，如 [1], [2]>]\n"
    "  - text: \"...\"\n"
    "    supporting_sample_ids: [...]\n\n"
    "约束：\n"
    "- 至少需要 2 张图同时呈现某规律才能列为 candidate（K ≥ 2）\n"
    "- 如果你认为没有跨图共性，输出 candidates: []\n"
    "- 不要输出 batch 总样本数 N，由调用方推断\n"
    "- 不要使用 markdown 代码块、列表标题、解释段落\n"
    "- 单条 candidate 的 text 应可独立理解（不要\"如上所述\"之类的引用）\n"
    "- supporting_sample_ids 的元素必须严格使用 user 消息中给出的 [1] / [2] / ... 匿名图序\n"
)


@overload
def build_batch_user_message(samples_meta: list[dict[str, Any]]) -> str: ...
@overload
def build_batch_user_message(
    samples_meta: list[dict[str, Any]], *, return_id_map: bool,
) -> tuple[str, dict[str, str]]: ...


def build_batch_user_message(
    samples_meta: list[dict[str, Any]],
    *,
    return_id_map: bool = False,
):
    """构造发送给 GLM-4V-Flash 的 batch user 文本（与 N 张图同消息）。

    归一化方案 B：每个 sample 用 [1] / [2] 匿名编号；不输出 ticker / bo_date /
    绝对价（OHLC 改为相对突破日 close 的 %，与 chart.png Y 轴 BO close pivot 统一）；
    保留 5 个无量纲盘整字段。

    Args:
        samples_meta: N 个 sample 的 meta dict 列表（落盘 meta.yaml 含原始
                      ticker/bo_date/价位用于人类追溯，本函数仅在 prompt 副本
                      中脱敏）。
        return_id_map: True 时同时返回 {"[1]": "BO_AAPL_..."} 映射，
                       供 inducer 把 GLM 返回的 supporting_sample_ids
                       从 [1]/[2] 反查回真实 sample_id。

    Returns:
        return_id_map=False: 脱敏后的 user message 字符串
        return_id_map=True: (user message, id_map dict)
    """

    def fmt_num(v) -> str:
        if isinstance(v, bool):
            return str(v)
        return f"{v:.2f}" if isinstance(v, (int, float)) else "N/A"

    def fmt_pct(v) -> str:
        if not isinstance(v, (int, float)) or isinstance(v, bool):
            return "N/A"
        return f"{v:+.2f}%"

    lines = [
        f"我给你 {len(samples_meta)} 张 K 线图，按顺序匿名编号 [1] ~ [{len(samples_meta)}]：\n"
    ]
    id_map: dict[str, str] = {}
    for i, meta in enumerate(samples_meta, start=1):
        anon = f"[{i}]"
        id_map[anon] = meta["sample_id"]
        bo = meta["breakout_day"]
        consol = meta["consolidation"]
        bo_close = bo.get("close")
        # OHLC → 相对 BO close 的 %（close 锚点 = 0%，与 chart.png Y 轴零点统一）
        if isinstance(bo_close, (int, float)) and not isinstance(bo_close, bool) and bo_close > 0:
            open_pct  = (bo['open']  - bo_close) / bo_close * 100
            high_pct  = (bo['high']  - bo_close) / bo_close * 100
            low_pct   = (bo['low']   - bo_close) / bo_close * 100
            ohlc_segment = (
                f"breakout_day_pct(vs bo_close): "
                f"open={fmt_pct(open_pct)} "
                f"high={fmt_pct(high_pct)} "
                f"low={fmt_pct(low_pct)} "
                f"close=+0.00%"
            )
        else:
            ohlc_segment = "breakout_day_pct: N/A (bo_close missing)"

        lines.append(
            f"\n{anon}\n"
            f"    {ohlc_segment}\n"
            f"    consolidation: length={fmt_num(consol['consolidation_length_bars'])} bars, "
            f"height={fmt_num(consol['consolidation_height_pct'])}%, "
            f"vs_52w_high={fmt_num(consol['consolidation_position_vs_52w_high'])}%, "
            f"volume_ratio={fmt_num(consol['consolidation_volume_ratio'])}, "
            f"tightness_atr={fmt_num(consol['consolidation_tightness_atr'])}"
        )
    lines.append("\n\n请按 SYSTEM_PROMPT 要求归纳这批样本的共性规律。")
    msg = "".join(lines)
    if return_id_map:
        return msg, id_map
    return msg
