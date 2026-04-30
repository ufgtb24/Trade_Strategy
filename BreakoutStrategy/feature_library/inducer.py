"""Inducer batch 模式：N 张样本一次 GLM-4V-Flash 调用 → 候选 features。

输入：sample_ids（每个对应 samples/<id>/{chart.png, meta.yaml} 已存在）+ GLM4VBackend
输出：list[Candidate]

错误处理：
- backend 失败（返回空字符串）→ 返回 []
- LLM 输出非合法 YAML → log warning + 返回 []
- candidate.supporting_sample_ids 含 batch 外的 ID → 过滤
- 过滤后 K < 2 → 整条 candidate 丢弃
"""

import logging

import yaml

from BreakoutStrategy.feature_library import paths
from BreakoutStrategy.feature_library.feature_models import Candidate
from BreakoutStrategy.feature_library.glm4v_backend import (
    GLM4V_MAX_IMAGES, GLM4VBackend,
)
from BreakoutStrategy.feature_library.inducer_prompts import (
    INDUCER_SYSTEM_PROMPT, build_batch_user_message,
)

logger = logging.getLogger(__name__)

MIN_K = 2  # K < 2 的 candidate 被过滤（spec INDUCER_SYSTEM_PROMPT 约束）
RAW_RESPONSE_EXCERPT_LEN = 500


def batch_induce(
    sample_ids: list[str],
    backend: GLM4VBackend,
    *,
    max_batch_size: int = GLM4V_MAX_IMAGES,
) -> list[Candidate]:
    """对 N 个 sample 做 Inducer batch 归纳。

    Args:
        sample_ids: 样本 ID 列表（必须每个对应 samples/<id>/{chart.png, meta.yaml} 已存在）
        backend: GLM4VBackend 实例
        max_batch_size: 单次 GLM 调用塞图上限（默认 GLM4V_MAX_IMAGES = 5）

    Returns:
        candidates 列表（可能为空）

    Raises:
        ValueError: sample_ids 数量超过 max_batch_size
        FileNotFoundError: 某 sample 的 chart.png / meta.yaml 缺失
    """
    if len(sample_ids) > max_batch_size:
        raise ValueError(
            f"sample_ids count {len(sample_ids)} exceeds max_batch_size {max_batch_size}"
        )

    # 加载每个 sample 的 chart_path + meta dict
    chart_paths = []
    metas = []
    for sid in sample_ids:
        chart = paths.chart_png_path(sid)
        meta_p = paths.meta_yaml_path(sid)
        if not chart.exists() or not meta_p.exists():
            raise FileNotFoundError(
                f"sample {sid} artifacts missing: "
                f"chart={chart.exists()}, meta={meta_p.exists()}"
            )
        chart_paths.append(chart)
        metas.append(yaml.safe_load(meta_p.read_text(encoding="utf-8")))

    user_message, id_map = build_batch_user_message(metas, return_id_map=True)
    raw = backend.batch_describe(
        chart_paths=chart_paths,
        user_message=user_message,
        system_prompt=INDUCER_SYSTEM_PROMPT,
    )

    if not raw:
        logger.warning("[Inducer] backend.batch_describe 返回空字符串")
        return []

    return _parse_candidates(raw, batch_sample_ids=sample_ids, id_map=id_map)


def _strip_code_fence(raw: str) -> str:
    """去除 LLM 回复中常见的 ```yaml ... ``` 或 ``` ... ``` 包裹。"""
    stripped = raw.strip()
    # 匹配 ```yaml 或 ``` 开头（大小写不敏感）
    if stripped.startswith("```"):
        # 去掉第一行（含 fence 标记）
        first_newline = stripped.find("\n")
        if first_newline != -1:
            stripped = stripped[first_newline + 1:]
        # 去掉结尾的 ```
        if stripped.endswith("```"):
            stripped = stripped[: stripped.rfind("```")].rstrip()
    return stripped


def _parse_candidates(
    raw: str,
    batch_sample_ids: list[str],
    id_map: dict[str, str] | None = None,
) -> list[Candidate]:
    """从 LLM 原始 YAML 输出解析 + 过滤为 Candidate 列表。

    Args:
        raw: LLM 返回的原始文本
        batch_sample_ids: 本次 batch 的真实 sample_id 列表（用于幻觉过滤）
        id_map: 匿名图序 → 真实 sample_id 的映射（归一化方案 B）；
                GLM 返回 "[1]"/["[2]"] 时，先翻译回真实 ID 再过滤，
                否则幻觉过滤会错误地拒绝所有合法候选。
    """
    cleaned = _strip_code_fence(raw)
    try:
        data = yaml.safe_load(cleaned)
    except yaml.YAMLError as e:
        logger.warning(f"[Inducer] YAML 解析失败: {e}; raw={raw[:200]}...")
        return []

    if not isinstance(data, dict) or "candidates" not in data:
        logger.warning(f"[Inducer] LLM 输出 schema 错（缺 candidates 键）: {raw[:200]}...")
        return []

    candidates_raw = data.get("candidates") or []
    if not isinstance(candidates_raw, list):
        logger.warning(f"[Inducer] candidates 不是 list: {type(candidates_raw)}")
        return []

    batch_ids_set = set(batch_sample_ids)
    N = len(batch_sample_ids)
    out: list[Candidate] = []
    excerpt = raw[:RAW_RESPONSE_EXCERPT_LEN]

    for c_raw in candidates_raw:
        if not isinstance(c_raw, dict):
            continue
        text = c_raw.get("text")
        sup_ids = c_raw.get("supporting_sample_ids", [])
        if not text or not isinstance(sup_ids, list):
            continue
        # 把匿名图序 [1]/[2] 翻译回真实 sample_id（归一化方案 B）。
        # GLM-4V 实际输出 supporting_sample_ids 时常见 3 种形式,统一归一到
        # id_map 的键格式 "[N]" 再查表:
        #   - 裸整数 list   [1, 2, 3]            (YAML 解析后最常见,本次 bug 触发原因)
        #   - 数字字符串   ["1", "2"]
        #   - 带括号字符串 ["[1]", "[2]"]        (与 id_map 直接匹配)
        # 必须在幻觉过滤之前,否则 batch_ids_set 含真实 ID 而 sup_ids 含 [N],
        # 导致所有合法候选被错误拒绝。
        if id_map:
            translated = []
            for s in sup_ids:
                key: object
                if isinstance(s, bool):
                    # bool 是 int 子类,需提前排除;否则 True → "[True]" 显然错误
                    key = s
                elif isinstance(s, int):
                    key = f"[{s}]"
                elif isinstance(s, str):
                    stripped = s.strip()
                    if stripped.startswith("[") and stripped.endswith("]"):
                        key = stripped
                    elif stripped.isdigit():
                        key = f"[{stripped}]"
                    else:
                        # 可能是 GLM 违反 SYSTEM_PROMPT 直接输出真 sample_id,
                        # 留给下面的 batch_ids_set 检查。
                        key = stripped
                else:
                    key = s
                if isinstance(key, str) and key in id_map:
                    translated.append(id_map[key])
                else:
                    logger.debug(
                        "[Inducer] supporting_id %r (normalized=%r) 不在 id_map 中,fallback "
                        "原值(GLM 可能违规或幻觉)",
                        s, key,
                    )
                    translated.append(s)
            sup_ids = translated
        # 过滤幻觉 ID
        valid_sup = [s for s in sup_ids if s in batch_ids_set]
        K = len(valid_sup)
        if K < MIN_K:
            if K == 0 and sup_ids:
                logger.warning(
                    f"[Inducer] candidate '{text}' 全部 supporting_ids 不在 batch 内, "
                    f"hallucinated={sup_ids}"
                )
            continue
        out.append(Candidate(
            text=str(text).strip(),
            supporting_sample_ids=valid_sup,
            K=K, N=N,
            raw_response_excerpt=excerpt,
        ))

    return out
