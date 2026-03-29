"""
聚合公式参数化评估脚本

支持两种模式：
1. ORIGINAL: 复现当前 analyzer.py 逻辑
2. PROPOSED: 带 impact emphasis + 调整参数
"""

import json
import math

# ── Impact 映射 ──
IMPACT_MAP = {
    "negligible": 0.05,
    "low": 0.20,
    "medium": 0.50,
    "high": 0.80,
    "extreme": 1.00,
}


def impact_emphasis(iv: float, emph: float) -> float:
    """
    超线性 impact 强调：高于 medium 的 impact 获得指数增强。

    金融直觉：极端事件（FDA 批准、破产）的市场冲击是非线性的，
    单条 extreme 新闻的影响力远大于多条 low 新闻的线性累加。
    这与量化金融中的跳跃扩散模型和厚尾分布一致。

    iv ≤ 0.5 (medium 及以下): 不变
    iv > 0.5 (high/extreme): 指数增强
    """
    return iv * math.exp(emph * max(0.0, iv - 0.5))


def summarize(items: list[dict], params: dict) -> dict:
    """复现/改进 _summarize 逻辑"""
    emph = params.get("EMPH", 0.0)  # 0 = no emphasis (original)
    la = params["LA"]
    w0 = params["W0_RHO"]
    delta = params["DELTA"]
    k = params["K"]
    scarcity_n = params["SCARCITY_N"]
    gamma = params["GAMMA"]
    beta = params["BETA"]
    beta_pos = params["BETA_POS"]
    k_neu = params["K_NEU"]
    opp_neg = params["OPP_NEG"]
    conflict_pow = params["CONFLICT_POW"]
    conflict_cap = params["CONFLICT_CAP"]
    la_neg_conf = params.get("LA_NEG_CONF", 1.0)  # negative confidence multiplier

    pos_impacts_raw = []
    neg_impacts_raw = []
    pos_impacts_emph = []
    neg_impacts_emph = []
    neu_count = 0

    for it in items:
        s = it["s"]
        iv = IMPACT_MAP[it["impact"]]
        iv_e = impact_emphasis(iv, emph)
        if s == "positive":
            pos_impacts_raw.append(iv)
            pos_impacts_emph.append(iv_e)
        elif s == "negative":
            neg_impacts_raw.append(iv)
            neg_impacts_emph.append(iv_e)
        else:
            neu_count += 1

    n_p, n_n, n_u = len(pos_impacts_raw), len(neg_impacts_raw), neu_count

    # w_p, w_n 使用 emphasized values (影响 rho 和 opp_penalty)
    w_p = sum(pos_impacts_emph)
    w_n = sum(neg_impacts_emph)

    # Step 1: rho（使用 emphasized weights + LA，统一用于方向和 certainty）
    w_n_adj = w_n * la
    rho_denom = w_p + w_n_adj + n_u * w0
    rho = (w_p - w_n_adj) / rho_denom if rho_denom > 0 else 0.0

    # Step 2: sentiment label
    if rho > delta:
        sentiment = "positive"
    elif rho < -delta:
        sentiment = "negative"
    else:
        sentiment = "neutral"

    # Step 3: confidence
    # evidence: 混合 mean + impact-weighted mean（大样本让高 impact 贡献更多）
    # 金融直觉：大量新闻中，强信号（high/extreme）比弱信号（low）更能代表真实市场影响
    n_dir = n_p + n_n
    w_p_raw = sum(pos_impacts_raw)
    w_n_raw = sum(neg_impacts_raw)
    sum_raw = w_p_raw + w_n_raw
    evidence_mean = sum_raw / n_dir if n_dir > 0 else 0.0

    # 大样本引入 impact-weighted mean（阈值 = SCARCITY_N × 3）
    blend_threshold = scarcity_n * 3
    alpha = min(1.0, blend_threshold / n_dir) if n_dir > 0 else 1.0
    if alpha < 1.0 and sum_raw > 0:
        sum_sq = sum(iv*iv for iv in pos_impacts_raw) + sum(iv*iv for iv in neg_impacts_raw)
        evidence_iw = sum_sq / sum_raw
        evidence = alpha * evidence_mean + (1.0 - alpha) * evidence_iw
    else:
        evidence = evidence_mean

    scarcity = min(1.0, n_dir / scarcity_n)

    # opp_penalty 使用 emphasized weights（弱 impact 反对信号惩罚更轻）
    w_total_emph = w_p + w_n
    if sentiment == "positive":
        sufficiency = (1.0 - math.exp(-evidence / k)) * scarcity
        certainty = min(abs(rho) * (1 + beta_pos), 1.0)
        opp_penalty = gamma * (w_n / w_total_emph) if w_n > 0 else 0.0
        base_conf = certainty * sufficiency * (1.0 - opp_penalty)
    elif sentiment == "negative":
        sufficiency = (1.0 - math.exp(-evidence / k)) * scarcity
        certainty = min(abs(rho) * (1 + beta), 1.0)
        opp_penalty = opp_neg * (w_p / w_total_emph) if w_p > 0 else 0.0
        base_conf = certainty * sufficiency * (1.0 - opp_penalty)
        base_conf *= la_neg_conf  # 损失厌恶：负面 confidence 放大
    else:
        if n_p == 0 and n_n == 0:
            base_conf = 1.0 * (1.0 - math.exp(-n_u / k_neu))
        else:
            balance = 1.0 - abs(w_p_raw - w_n_raw) / (w_p_raw + w_n_raw) if (w_p_raw + w_n_raw) > 0 else 0.0
            balance = balance ** conflict_pow
            base_conf = balance * conflict_cap

    confidence = round(max(0.0, min(1.0, base_conf)), 4)
    s_sign = 1 if sentiment == "positive" else (-1 if sentiment == "negative" else 0)
    s_score = round(s_sign * confidence, 4)

    return {
        "sentiment": sentiment,
        "score": s_score,
        "rho": round(rho, 4),
        "confidence": confidence,
        "n_p": n_p, "n_n": n_n, "n_u": n_u,
        "w_p": round(w_p, 4), "w_n": round(w_n, 4),
        "scarcity": round(scarcity, 4),
        "evidence": round(evidence, 4),
        "certainty": round(min(abs(rho) * (1 + (beta_pos if sentiment == "positive" else beta)), 1.0), 4) if sentiment != "neutral" else 0,
        "sufficiency": round((1.0 - math.exp(-evidence / k)) * scarcity, 4) if n_dir > 0 else 0,
    }


ORIGINAL_PARAMS = {
    "W0_RHO": 0.1, "DELTA": 0.1, "K": 0.55, "SCARCITY_N": 3,
    "GAMMA": 0.40, "BETA": 2.2, "BETA_POS": 1.15,
    "K_NEU": 2.47, "OPP_NEG": 0.20, "LA": 1.02,
    "CONFLICT_POW": 3.0, "CONFLICT_CAP": 0.15,
    "EMPH": 0.0, "LA_NEG_CONF": 1.0,
}

PROPOSED_PARAMS = {
    "W0_RHO": 0.1,
    "DELTA": 0.06,
    "K": 0.55,
    "SCARCITY_N": 1.5,
    "GAMMA": 0.70,
    "BETA": 0.8,
    "BETA_POS": 0.30,     # (derived from BETA*0.375)
    "K_NEU": 2.47,
    "OPP_NEG": 0.35,
    "LA": 1.22,
    "CONFLICT_POW": 3.0,
    "CONFLICT_CAP": 0.15,
    "EMPH": 2.1,
    "LA_NEG_CONF": 1.35,
}


def evaluate(scenarios, baseline, params, label=""):
    bl_map = {b["id"]: b for b in baseline}
    total_abs_diff = 0.0
    direction_matches = 0
    results = []

    print(f"\n{'='*120}")
    print(f"  {label}")
    print(f"{'='*120}")
    print(f"{'ID':>3} | {'BL Sent':>10} | {'Fm Sent':>10} | {'BL Score':>9} | {'Fm Score':>9} | {'Diff':>7} | {'|Diff|':>6} | {'Match':>5}")
    print("-" * 90)

    for sc in scenarios:
        sid = sc["id"]
        bl = bl_map[sid]
        result = summarize(sc["items"], params)

        bl_score = bl["sentiment_score"]
        fm_score = result["score"]
        diff = fm_score - bl_score
        abs_diff = abs(diff)
        total_abs_diff += abs_diff

        bl_sent = bl["sentiment"]
        fm_sent = result["sentiment"]
        match = bl_sent == fm_sent
        direction_matches += 1 if match else 0
        flag = "Yes" if match else "**NO**"

        print(f"{sid:>3} | {bl_sent:>10} | {fm_sent:>10} | {bl_score:>+9.4f} | {fm_score:>+9.4f} | {diff:>+7.4f} | {abs_diff:>6.4f} | {flag:>5}")

        results.append({
            "id": sid, "bl_sent": bl_sent, "fm_sent": fm_sent,
            "bl_score": bl_score, "fm_score": fm_score,
            "diff": diff, "abs_diff": abs_diff, "match": match,
            **result,
        })

    n = len(scenarios)
    mad = total_abs_diff / n
    print("-" * 90)
    print(f"Direction match: {direction_matches}/{n} ({direction_matches/n*100:.1f}%)")
    print(f"MAD: {mad:.4f}")
    print(f"Max |diff|: {max(r['abs_diff'] for r in results):.4f} (ID {max(results, key=lambda r: r['abs_diff'])['id']})")

    mismatch_ids = [r["id"] for r in results if not r["match"]]
    if mismatch_ids:
        print(f"Direction mismatches: {mismatch_ids}")

    # 分类分析
    pos_diffs = [r["diff"] for r in results if r["match"] and r["bl_sent"] == "positive"]
    neg_diffs = [r["diff"] for r in results if r["match"] and r["bl_sent"] == "negative"]
    if pos_diffs:
        print(f"Positive matched: avg_diff={sum(pos_diffs)/len(pos_diffs):+.4f}, avg_|diff|={sum(abs(d) for d in pos_diffs)/len(pos_diffs):.4f}")
    if neg_diffs:
        print(f"Negative matched: avg_diff={sum(neg_diffs)/len(neg_diffs):+.4f}, avg_|diff|={sum(abs(d) for d in neg_diffs)/len(neg_diffs):.4f}")

    return results, mad, direction_matches


def evaluate_silent(scenarios, baseline, params):
    """Silent evaluation, returns (results, mad, direction_matches)"""
    bl_map = {b["id"]: b for b in baseline}
    total_abs_diff = 0.0
    direction_matches = 0
    results = []

    for sc in scenarios:
        sid = sc["id"]
        bl = bl_map[sid]
        result = summarize(sc["items"], params)
        bl_score = bl["sentiment_score"]
        fm_score = result["score"]
        diff = fm_score - bl_score
        abs_diff = abs(diff)
        total_abs_diff += abs_diff
        match = bl["sentiment"] == result["sentiment"]
        direction_matches += 1 if match else 0
        results.append({"id": sid, "abs_diff": abs_diff, "match": match})

    return results, total_abs_diff / len(scenarios), direction_matches


def sweep(scenarios, baseline):
    """Parameter sweep to find best combo"""
    import itertools

    best_mad = 1.0
    best_params = None

    base = dict(PROPOSED_PARAMS)

    # 精细扫描最关键的参数
    for emph in [1.5, 2.0, 2.5, 3.0]:
        for la in [1.10, 1.15, 1.20, 1.25]:
            for k in [0.40, 0.50, 0.55, 0.60]:
                for scn in [1.3, 1.5, 1.8, 2.0]:
                    for beta in [1.2, 1.5, 1.8, 2.2]:
                        for beta_pos in [0.3, 0.5, 0.8]:
                            for gamma in [0.50, 0.60, 0.70]:
                                for la_neg in [1.0, 1.10, 1.20, 1.30]:
                                    p = dict(base)
                                    p.update({
                                        "EMPH": emph, "LA": la, "K": k,
                                        "SCARCITY_N": scn, "BETA": beta,
                                        "BETA_POS": beta_pos, "GAMMA": gamma,
                                        "LA_NEG_CONF": la_neg,
                                    })
                                    _, mad, dm = evaluate_silent(scenarios, baseline, p)
                                    if dm >= 42 and mad < best_mad:
                                        best_mad = mad
                                        best_params = dict(p)
                                        best_dm = dm

    print(f"\n{'='*80}")
    print(f"  BEST: MAD={best_mad:.4f}, direction={best_dm}/43")
    print(f"{'='*80}")
    for k, v in sorted(best_params.items()):
        if v != base.get(k):
            print(f"  {k}: {base.get(k)} → {v}")
        else:
            print(f"  {k}: {v}")
    return best_params


def main():
    with open("scripts/experiments/impact_scenarios.json") as f:
        scenarios = json.load(f)
    with open("scripts/experiments/impact_baseline.json") as f:
        baseline = json.load(f)

    # Original
    evaluate(scenarios, baseline, ORIGINAL_PARAMS, "ORIGINAL (current analyzer.py)")

    # Sweep
    import sys
    if "--sweep" in sys.argv:
        best = sweep(scenarios, baseline)
        evaluate(scenarios, baseline, best, "BEST (from sweep)")
    else:
        # Proposed
        evaluate(scenarios, baseline, PROPOSED_PARAMS, "PROPOSED (emphasis + LA adjustments)")


if __name__ == "__main__":
    main()
