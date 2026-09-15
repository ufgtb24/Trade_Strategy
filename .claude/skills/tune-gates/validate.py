# -*- coding: utf-8 -*-
"""tune-gates · 独立验证:确认子族展开、预期把握、幸存者偏差、冻结清单、两段确认窗各开一次。

调参结束后,候选配置 K(若干组成改动合成的整套)要在两段留出的确认窗上各检验一次:
  1. 展开确认子族(`expand_family`):按采纳规则把 K 机械展开成要检验的配置、假设与决策映射;
  2. 开窗前算好预期把握(`expected_power` / `forward_check_power`)与幸存者偏差(`survivorship_bias`);
  3. 冻结清单(`preregister`):清单哈希 + 清单全文写进账本的 preregister 记录;
  4. 开窗检验(`validate`):过确认窗守卫后读窗口数据。往前窗做族内校正的主确认、按映射选配置;
     前向窗核对选出的配置不比改前差、方向与训练期一致;两窗齐了按判读表(`interpret`)给结论。
     每窗一条 extrapolate 记录(产物先落盘、记录最后写)。

口径(全部比例口径,0.02 = 2 点;人话输出里再乘 100):
- 观测单位 = 买点事件:每个配置格的每股计数和 U / D / N 由调用方注入(`load_window_sums`),
  已按买点事件口径去重。首次穿越率 r = ΣU / ΣD。
- 假设 = 两个配置格的首次穿越率差 est = r_a − r_b,误差按股线性化(`inference.ratio_contrast`)。
  一律单侧:优效 T = est / se;非劣效 T = (est + δ) / se(检验 est > −δ)。
- 族内校正:默认逐步 max-T(按股 bootstrap,`inference.maxT_from_sums`),备选 Holm;族内单侧 α。
- 统计口径(δ、α、校正方法、bootstrap 副本数与种子)全部冻结在清单里;开窗时只读清单,
  不读当前设置——冻结之后改设置不能改变这次检验什么、怎么检验。
"""
from __future__ import annotations

import hashlib
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

SKILL_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SKILL_DIR))

import holdout  # noqa: E402
import ledger  # noqa: E402
from inference import holm, maxT_from_sums, ratio_contrast  # noqa: E402

CHANGE_KINDS = ("detect", "delete_gate")
METHODS = ("maxT", "holm")
BASE, FULL = "base", "K"
PRIMARY = ("显著", "不显著")
MANIFEST_KEYS = ("family", "train_est", "alpha", "method", "B", "seed", "expected_power", "survivorship",
                 "fingerprints")
FAMILY_KEYS = ("changes", "strength_order", "delta", "configs", "hypotheses", "mapping")


@dataclass(frozen=True)
class Change:
    """候选配置 K 的一个组成改动。

    key: 参数键(params.yaml 的 section.field);old / new: 改前 / 改后取值。
    kind: "detect" = 检测参数改动(检验优效);"delete_gate" = 删闸(检验非劣效)。
    train_z: 训练窗两年合并、按股去簇的 z(该改动在 K 处的组成效应),决定「从强到弱」的顺序。
    """
    key: str
    old: object
    new: object
    kind: str
    train_z: float


def noninferiority_margin(cfg) -> float:
    """非劣效界 δ(比例):Settings.noninferiority_pt,未设(None)时取 min_effect_pt;两者都是点数。"""
    pt = cfg.noninferiority_pt if cfg.noninferiority_pt is not None else cfg.min_effect_pt
    return pt / 100


# ---------------------------------------------------------------- 确认子族展开

def _config_name(applied: frozenset, n: int, order: list[str]) -> str:
    """配置名只由「用了哪几项改动」决定:空 → base;全部 → K;单项 → 参数键;少一项 → K-<参数键>。
    n = 2 时「少一项」就是另一项的单项配置,n = 1 时单项就是 K,于是同一配置只有一个名字。"""
    if not applied:
        return BASE
    if len(applied) == n:
        return FULL
    if len(applied) == 1:
        return next(iter(applied))
    if len(applied) == n - 1:
        return "K-" + next(k for k in order if k not in applied)
    raise ValueError(f"默认采纳规则不会展开出含 {len(applied)} 项改动的中间配置")


def expand_family(changes: list[Change], *, delta: float, rule: str = "default") -> dict:
    """按采纳规则把候选配置 K 展开成确认子族与决策映射(开窗前冻结进清单)。

    默认规则:整套 → 按 train_z 从强到弱的每个单项 → 维持改前(平手按 changes 的给出顺序)。
    configs:{配置名: {参数键: 取值}},依次为 base、K、每个 K-<c>(强到弱)、每个单项 <c>(强到弱),同一配置只出现一次。
    hypotheses(假设 = a 优于 b 或 a 不比 b 差出 δ 以上):
        K vs base;每个 c(强到弱):K vs K−c;每个 c(强到弱):{c} vs base。两端相同的假设只保留第一次出现。
        「这个比较涉及的改动」里有检测参数 → 优效(margin = 0);只含删闸 → 非劣效(margin = δ)。
    mapping:按顺序取第一条 if_all 全部通过的 adopt;都不过 → {"else": None}(维持改前,主确认记「不显著」)。
        第一条 = K 的全部假设(K vs base 与每个 K vs K−c);其后每个单项配置一条(强到弱)。
    n = 2 时恰为 H1 K vs base、H2 K vs K−强项、H3 K vs K−弱项、H4 强项 vs base、H5 弱项 vs base。
    delta: 非劣效界(比例),由调用方从运行口径取(`noninferiority_margin`)。
    """
    if rule != "default":
        raise ValueError(f"只实现了默认采纳规则(整套 → 从强到弱逐项 → 维持改前),不认识 {rule!r}")
    if not changes:
        raise ValueError("候选配置里没有任何改动,没有可验证的东西")
    keys = [c.key for c in changes]
    if len(set(keys)) != len(keys):
        raise ValueError(f"同一个参数出现了不止一次: {keys}")
    for c in changes:
        if c.kind not in CHANGE_KINDS:
            raise ValueError(f"改动 {c.key} 的类型 {c.kind!r} 不在 {CHANGE_KINDS}")
        if not np.isfinite(c.train_z):
            raise ValueError(f"改动 {c.key} 的训练窗 z 不是有限数: {c.train_z!r}")
    if not delta > 0:
        raise ValueError(f"非劣效界 δ 必须为正: {delta!r}")
    n = len(changes)
    by_key = {c.key: c for c in changes}
    order = [c.key for c in sorted(changes, key=lambda c: -c.train_z)]   # sorted 稳定:平手保持给出顺序
    everything = frozenset(order)

    def name(applied):
        return _config_name(frozenset(applied), n, order)

    def values(applied):
        return {k: (by_key[k].new if k in applied else by_key[k].old) for k in keys}

    configs = {}
    for applied in [frozenset(), everything, *(everything - {k} for k in order), *(frozenset({k}) for k in order)]:
        configs.setdefault(name(applied), values(applied))

    pairs = ([(name(everything), BASE, order)]
             + [(FULL, name(everything - {k}), [k]) for k in order]
             + [(name({k}), BASE, [k]) for k in order])
    hyps, ids = [], {}
    for a, b, comps in pairs:
        if (a, b) in ids:
            continue
        sup = any(by_key[k].kind == "detect" for k in comps)
        hid = f"H{len(hyps) + 1}"
        ids[(a, b)] = hid
        hyps.append({"id": hid, "a": a, "b": b, "type": "superiority" if sup else "noninferiority",
                     "components": list(comps), "margin": 0.0 if sup else float(delta)})

    first = list(dict.fromkeys([ids[(FULL, BASE)]] + [ids[(FULL, name(everything - {k}))] for k in order]))
    mapping = [{"if_all": first, "adopt": FULL}]
    for k in order:
        if name({k}) != FULL:
            mapping.append({"if_all": [ids[(name({k}), BASE)]], "adopt": name({k})})
    mapping.append({"else": None})
    return {"changes": [asdict(c) for c in changes], "strength_order": order, "delta": float(delta),
            "configs": configs, "hypotheses": hyps, "mapping": mapping}


def select_config(family: dict, passed: dict) -> str | None:
    """按决策映射机械选配置:第一条 if_all 全部通过的 adopt;都不过 → None。passed = {假设 id: bool}。"""
    for item in family["mapping"]:
        if "else" in item:
            return item["else"]
        if all(passed.get(h, False) for h in item["if_all"]):
            return item["adopt"]
    return None


def family_contrasts(family: dict) -> np.ndarray:
    """(m, K) 对比系数矩阵:第 j 行 = 第 j 个假设,a 格 +1、b 格 −1;列序 = family["configs"] 的顺序。"""
    names = list(family["configs"])
    C = np.zeros((len(family["hypotheses"]), len(names)))
    for j, h in enumerate(family["hypotheses"]):
        C[j, names.index(h["a"])] = 1.0
        C[j, names.index(h["b"])] = -1.0
    return C


def _hyp_id(family: dict, a: str, b: str) -> str:
    return next(h["id"] for h in family["hypotheses"] if (h["a"], h["b"]) == (a, b))


# ---------------------------------------------------------------- 判读表

_INTERPRET = {
    ("显著", False, True): ("撤回", False, False,
                          "往前那段验证数据确认了改进,但训练期之后的新数据上比改前差出了容忍范围:撤回这次改动。"),
    ("显著", True, True): ("采纳", False, False,
                         "往前那段验证数据确认了改进,训练期之后的新数据上也没有变差、方向与训练期一致:采纳。"),
    ("显著", True, False): ("暂定采纳", True, False,
                          "往前那段验证数据确认了改进;训练期之后的新数据上没有明显变差,但方向与训练期相反:"
                          "暂定采纳,等之后的新数据攒满一年再复验。"),
    ("不显著", False, True): ("撤回", False, False,
                           "往前那段验证数据没能确认改进,训练期之后的新数据上又比改前差出了容忍范围:撤回这次改动。"),
    ("不显著", True, True): ("暂定采纳", False, False,
                          "往前那段验证数据没能确认改进;训练期之后的新数据上没有变差、方向与训练期一致:"
                          "暂定采纳(这次验证事先估计的把握见清单)。"),
    ("不显著", True, False): ("不写进正式参数", True, True,
                           "往前那段验证数据没能确认改进,训练期之后的新数据上方向还与训练期相反:不写进正式参数;"
                           "已经在正式参数里的维持暂定、不撤回,等之后的新数据攒满一年再复验。"),
}


def interpret(primary: str, forward_ni_pass: bool, forward_same_sign: bool) -> dict:
    """判读表:往前窗主确认 × 前向窗核对(非劣效、与训练期同号)→ 处置。

    主确认显著:非劣效不过 → 撤回;过且同号 → 采纳;过但反号 → 暂定采纳,前向攒满 1 年复验。
    主确认不显著:非劣效不过 → 撤回;过且同号 → 暂定采纳;过但反号 → 不写进正式参数(已在正式参数里的维持暂定),
    攒满 1 年复验。非劣效不过时不看方向。
    返回 {"outcome", "recheck_after_1y", "keep_if_already_adopted", "text"}。
    """
    if primary not in PRIMARY:
        raise ValueError(f"主确认结论只能是 {PRIMARY} 之一: {primary!r}")
    key = (primary, bool(forward_ni_pass), bool(forward_same_sign) or not forward_ni_pass)
    outcome, recheck, keep, text = _INTERPRET[key]
    return {"outcome": outcome, "recheck_after_1y": recheck, "keep_if_already_adopted": keep, "text": text}


# ---------------------------------------------------------------- 预期把握

def window_se(train_se, train_bars, window_bars) -> float:
    """确认窗 SE 估计 = 训练 SE·√(训练定向 bar / 窗口定向 bar);窗口 bar 用无标签扫描的计数。"""
    return float(train_se * np.sqrt(train_bars / window_bars))


def bootstrap_corr(U, D, contrasts, *, B: int, seed: int) -> np.ndarray:
    """训练窗按股 multinomial bootstrap 下各对比估计的相关矩阵 (m, m),供 `expected_power` 用。

    U, D: (S, K) 每股计数和;contrasts: (m, K)。全零股行先去掉(不参与重抽);
    副本里有对比为 NaN(某格 Σw·D = 0)的副本整行丢弃。"""
    U = np.asarray(U, dtype=float)
    D = np.asarray(D, dtype=float)
    C = np.atleast_2d(np.asarray(contrasts, dtype=float))
    live = (U != 0).any(axis=1) | (D != 0).any(axis=1)
    U, D = U[live], D[live]
    S = U.shape[0]
    W = np.random.default_rng(seed).multinomial(S, np.full(S, 1.0 / S), size=B).astype(float)
    with np.errstate(divide="ignore", invalid="ignore"):
        est = ((W @ U) / (W @ D)) @ C.T
    est = est[np.isfinite(est).all(axis=1)]
    return np.atleast_2d(np.corrcoef(est, rowvar=False))


def _mvn_draws(rng, corr: np.ndarray, n: int) -> np.ndarray:
    """(n, m) 标准多元正态,协方差 = corr;用特征分解开方,完全相关(奇异)的矩阵也能抽。"""
    w, V = np.linalg.eigh(corr)
    return rng.standard_normal((n, len(corr))) @ (V * np.sqrt(np.clip(w, 0, None))).T


def _maxT_pass(Z: np.ndarray, null: np.ndarray, alpha: float) -> np.ndarray:
    """逐步 max-T 的通过矩阵 (n, m)。按 Z 降序逐个检验:第 i 名的门槛 = 零分布下「第 i 名及之后
    那些检验的最大值」的 1−α 分位;某一名没过,之后的都不过。与 bootstrap 调整 p ≤ α 同一判据。"""
    n, m = Z.shape
    order = np.argsort(-Z, axis=1, kind="stable")
    bits = np.left_shift(np.int64(1), order.astype(np.int64))
    remain = np.cumsum(bits[:, ::-1], axis=1)[:, ::-1]           # 第 i 名及之后的检验集合(位掩码)
    masks, inv = np.unique(remain, return_inverse=True)
    crit = np.array([np.quantile(null[:, [j for j in range(m) if mk >> j & 1]].max(axis=1), 1 - alpha)
                     for mk in masks])
    ok = np.logical_and.accumulate(np.take_along_axis(Z, order, axis=1) >= crit[inv.reshape(n, m)], axis=1)
    out = np.zeros((n, m), dtype=bool)
    np.put_along_axis(out, order, ok, axis=1)
    return out


def _holm_pass(Z: np.ndarray, alpha: float) -> np.ndarray:
    """Holm 的通过矩阵 (n, m):单侧 p 升序,第 i 名(0 起)门槛 α/(m−i),某一名没过之后都不过。"""
    n, m = Z.shape
    p = stats.norm.sf(Z)
    order = np.argsort(p, axis=1, kind="stable")
    ok = np.logical_and.accumulate(np.take_along_axis(p, order, axis=1) <= alpha / (m - np.arange(m)), axis=1)
    out = np.zeros((n, m), dtype=bool)
    np.put_along_axis(out, order, ok, axis=1)
    return out


def expected_power(family: dict, *, effects: dict, se_window: dict, corr, alpha: float, method: str = "maxT",
                   n_sim: int = 20000, seed: int = 0) -> dict:
    """往前窗主确认的预期把握:多元正态模拟族内校正后的通过事件。

    参数:
        family: `expand_family` 输出(用其 hypotheses 与 mapping)。
        effects: {假设 id: 预期效应} = 训练估计 − optimism(扣掉训练窗挑选带来的乐观偏差)。
        se_window: {假设 id: 该窗 SE}(`window_se`)。
        corr: (m, m) 各假设估计的相关矩阵,按 hypotheses 顺序(`bootstrap_corr`)。
        alpha: 族内单侧 α;method: "maxT"(门槛用同一相关矩阵的零分布模拟)| "holm"。
    模拟:Z ~ N(μ, corr),μ_j = (effect_j + margin_j) / se_j;逐次按族内校正判通过。
    返回 {"per_hypothesis": {id: P(通过)}, "mapping_first": P(映射第一项的全部假设同时通过),
          "selection": {配置名 或 "none": P(映射选中它)}}。
    """
    if method not in METHODS:
        raise ValueError(f"族内校正方法只能是 {METHODS} 之一: {method!r}")
    hyps = family["hypotheses"]
    ids = [h["id"] for h in hyps]
    m = len(ids)
    R = np.asarray(corr, dtype=float)
    if R.shape != (m, m):
        raise ValueError(f"相关矩阵形状应为 ({m}, {m}),实际 {R.shape}")
    mu = np.array([(effects[h["id"]] + h["margin"]) / se_window[h["id"]] for h in hyps])
    rng = np.random.default_rng(seed)
    null = _mvn_draws(rng, R, n_sim)
    Z = mu + _mvn_draws(rng, R, n_sim)
    passed = _maxT_pass(Z, null, alpha) if method == "maxT" else _holm_pass(Z, alpha)
    col = {h: j for j, h in enumerate(ids)}
    first = passed[:, [col[h] for h in family["mapping"][0]["if_all"]]].all(axis=1)
    selection, left = {}, np.ones(n_sim, dtype=bool)
    for item in family["mapping"]:
        if "else" in item:
            selection["none"] = float(left.mean())
            break
        hit = left & passed[:, [col[h] for h in item["if_all"]]].all(axis=1)
        selection[item["adopt"]] = float(hit.mean())
        left &= ~hit
    return {"per_hypothesis": {h: float(passed[:, j].mean()) for j, h in enumerate(ids)},
            "mapping_first": float(first.mean()), "selection": selection}


def forward_check_power(effect: float, se: float, *, delta: float, alpha: float, train_sign: float) -> float:
    """前向窗核对的预期把握:P(非劣效过 且 与训练期同号)。

    非劣效过 = est − z_{1−α}·se ≥ −δ;同号 = sign(est) = train_sign。est ~ N(effect, se²)。"""
    lo = stats.norm.ppf(1 - alpha) * se - delta
    if train_sign > 0:
        return float(stats.norm.sf((max(lo, 0.0) - effect) / se))
    return float(max(0.0, stats.norm.cdf(-effect / se) - stats.norm.cdf((lo - effect) / se)))


# ---------------------------------------------------------------- 幸存者偏差

def distress_symbols(last_close: pd.Series, drawdown_after_train: pd.Series, *, price_floor: float = 1.0,
                     worst_frac: float = 0.10) -> set:
    """日后困境股 = 数据末收盘 < price_floor,或训练窗末到数据末跌得最深的 worst_frac。

    last_close: 按股票代码索引的数据末收盘价。
    drawdown_after_train: 按股票代码索引的涨跌幅 = 数据末收盘 / 训练窗末收盘 − 1(越小跌得越深)。
    跌得最深的只数 = ceil(worst_frac × 有值的股票数),同值按代码排序取前面的。缺失值不进任何一条规则。"""
    lc = last_close.dropna()
    out = set(lc.index[lc < price_floor])
    dd = drawdown_after_train.dropna().sort_index().sort_values(kind="stable")
    out |= set(dd.index[:int(np.ceil(worst_frac * len(dd)))])
    return out


def survivorship_bias(pair_diffs_distress, pair_diffs_rest, *, pi: float = 0.3, bias_pt: float = 0.01) -> dict:
    """往前窗的幸存者偏差敏感性(开窗前在训练窗上算,预注册进清单)。

    往前窗的股票池里没有之后退市的股票。用训练窗里「日后困境」的在池股代理它们:
    H = 困境股配对差均值 − 其余股配对差均值(配对差 = 同一批股票上候选配置与改前配置的首次穿越率差;
    可以传逐股配对差数组,也可以传两组各自的组级估计)。偏差大小 ≲ π·|H|,π = 窗内买点事件中
    属于日后退市股票的比例(预注册取值)。π·|H| > bias_pt(比例口径,0.01 = 1 点)→ flag:
    往前窗的确认降为暂定(按「不显著」读),以前向窗为准。困境股配对差偏高或偏低都可能让往前窗读数失真,
    所以按绝对值判。"""
    d = np.atleast_1d(np.asarray(pair_diffs_distress, dtype=float))
    r = np.atleast_1d(np.asarray(pair_diffs_rest, dtype=float))
    d, r = d[np.isfinite(d)], r[np.isfinite(r)]
    if not len(d) or not len(r):
        raise ValueError("困境股或其余股的配对差为空,算不出幸存者偏差")
    H = float(d.mean() - r.mean())
    bias = pi * abs(H)
    flag = bool(bias > bias_pt)
    head = (f"日后陷入困境的股票和其余股票上,这组改动的效果相差约 {H * 100:+.2f} 点;按往前那段验证数据里约 "
            f"{pi:.0%} 的买点事件可能属于日后退市的股票估算,往前那段的读数可能偏 {bias * 100:.2f} 点")
    tail = (f",超过 {bias_pt * 100:.2f} 点:往前那段的确认只按「暂定」算,以训练期之后的那段为准。" if flag
            else f",不超过 {bias_pt * 100:.2f} 点,不影响往前那段的确认。")
    return {"H": H, "pi": float(pi), "bias": float(bias), "bias_pt": float(bias_pt), "flag": flag,
            "n_distress": int(len(d)), "n_rest": int(len(r)), "text": head + tail}


# ---------------------------------------------------------------- 冻结清单

def _canonical_sha(obj) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, default=str).encode()).hexdigest()


def manifest_hash(manifest: dict) -> str:
    """清单哈希 = sort_keys JSON 的 sha256(与 study_io.canonical_hash 同算法)。"""
    return _canonical_sha(manifest)


def _check_manifest(manifest: dict) -> None:
    lack = [k for k in MANIFEST_KEYS if k not in manifest]
    if lack:
        raise ValueError(f"验证清单缺少 {lack}")
    fam = manifest["family"]
    lack = [k for k in FAMILY_KEYS if k not in fam]
    if lack or FULL not in fam["configs"] or BASE not in fam["configs"]:
        raise ValueError(f"验证清单的确认子族不完整(缺 {lack} 或缺整套 / 改前配置),请用 expand_family 展开")
    ids = [h["id"] for h in fam["hypotheses"]]
    miss = [h for h in ids if not isinstance(manifest["train_est"].get(h), (int, float))
            or not np.isfinite(manifest["train_est"][h])]
    if miss:
        raise ValueError(f"验证清单的训练窗估计缺少或不是有限数: {miss}")
    if not 0 < manifest["alpha"] < 1:
        raise ValueError(f"族内 α 必须在 (0, 1): {manifest['alpha']!r}")
    if manifest["method"] not in METHODS:
        raise ValueError(f"族内校正方法只能是 {METHODS} 之一: {manifest['method']!r}")
    if not (isinstance(manifest["B"], int) and manifest["B"] >= 1 and isinstance(manifest["seed"], int)):
        raise ValueError(f"bootstrap 副本数须为正整数、种子须为整数: B={manifest['B']!r} seed={manifest['seed']!r}")
    ep = manifest["expected_power"]
    if not all(isinstance(ep.get(n), (int, float)) and 0 <= ep[n] <= 1 for n in ledger.CONFIRM_NAMES):
        raise ValueError(f"验证清单的预期把握须给出两段确认窗各一个 [0, 1] 的数: {ep!r}")
    if not isinstance(manifest["survivorship"].get("flag"), bool):
        raise ValueError("验证清单的幸存者偏差须含布尔 flag(用 survivorship_bias 算)")
    if set(manifest["fingerprints"]) != set(ledger.FINGERPRINT_FIELDS):
        raise ValueError(f"验证清单的指纹须恰有 {ledger.FINGERPRINT_FIELDS}")
    try:
        json.dumps(manifest, allow_nan=False)
    except (TypeError, ValueError) as e:
        raise ValueError(f"验证清单含不能写成标准 JSON 的值: {e}") from e


def preregister(app: str, manifest: dict, *, actor: str) -> dict:
    """冻结验证清单:校验后算哈希,写一条 preregister 记录,返回该记录。

    manifest 必需键(可另带附加键,如学习端的闸子族、描述性读数说明):
        family        expand_family 输出
        train_est     {假设 id: 训练窗估计},前向窗「与训练期同号」用
        alpha / method / B / seed   族内单侧 α、校正方法("maxT" | "holm")、bootstrap 副本数与种子
        expected_power {"backward": 映射第一项的预期把握, "forward": 前向核对的预期把握}(可另带明细键)
        survivorship  survivorship_bias 输出
        fingerprints  冻结时的四个指纹(ledger.current_fingerprints)
        round         可选,调参轮次
    记录的 label_horizon / head_buffer 取最新 open 记录(没有则为 null);axes = 各组成改动的参数键。"""
    _check_manifest(manifest)
    op = ledger.latest(app, "open")
    ep = manifest["expected_power"]
    rec = ledger.make_record(
        "preregister", app, actor=actor, round=manifest.get("round"),
        axes=sorted(c["key"] for c in manifest["family"]["changes"]), window=None,
        label_horizon=op["label_horizon"] if op else None, head_buffer=op["head_buffer"] if op else None,
        **manifest["fingerprints"],
        data={"manifest_hash": manifest_hash(manifest), "manifest": manifest,
              "expected_power": {n: float(ep[n]) for n in ledger.CONFIRM_NAMES},
              "survivorship": manifest["survivorship"]})
    return ledger.append(rec)


# ---------------------------------------------------------------- 开窗检验

def _num(x):
    x = float(x)
    return x if np.isfinite(x) else None


def _pt(x) -> str:
    return "算不出" if x is None or not np.isfinite(x) else f"{x * 100:+.2f} 点"


def _config_words(family: dict, name: str) -> str:
    if name == BASE:
        return "改前参数"
    if name == FULL:
        return "整套改动"
    ch = {c["key"]: c for c in family["changes"]}

    def one(k):
        c = ch[k]
        return f"删掉「{k}」这道闸" if c["kind"] == "delete_gate" else f"把「{k}」从 {c['old']} 改成 {c['new']}"

    if name.startswith("K-"):
        return f"整套改动里不做「{name[2:]}」这一项"
    return "只" + one(name)


def _stack(sums: dict, names: list[str]) -> tuple:
    """{配置名: DataFrame(index=股票代码, U/D/N)} → 按股票并集对齐的 (S, K) 三个数组(缺的股记 0)。"""
    lack = [n for n in names if n not in sums]
    if lack:
        raise ValueError(f"窗口数据缺少配置 {lack}")
    symbols = sorted(set().union(*(sums[n].index for n in names)))
    arr = {c: np.column_stack([sums[n][c].reindex(symbols, fill_value=0).to_numpy(dtype=float) for n in names])
           for c in ("U", "D", "N")}
    return arr["U"], arr["D"], arr["N"]


def _backward(U, D, N, family: dict, manifest: dict, window_words: str) -> dict:
    hyps = family["hypotheses"]
    C = family_contrasts(family)
    margins = np.array([h["margin"] for h in hyps])
    rc = [ratio_contrast(U, D, N, C[j]) for j in range(len(hyps))]
    est = np.array([r["est"] for r in rc])
    se = np.array([r["se"] for r in rc])
    with np.errstate(divide="ignore", invalid="ignore"):
        T = (est + margins) / se
    p_raw = stats.norm.sf(T)
    alpha = manifest["alpha"]
    if manifest["method"] == "maxT":
        live = (U != 0).any(axis=1) | (D != 0).any(axis=1)            # 全零股不参与按股重抽
        p_adj = maxT_from_sums(U[live], D[live], C, margins, se, B=manifest["B"], seed=manifest["seed"])["p_adj"]
    else:
        p_adj = holm(np.where(np.isfinite(p_raw), p_raw, 1.0))
    passed = np.isfinite(p_adj) & (p_adj <= alpha)
    selected = select_config(family, {h["id"]: bool(ok) for h, ok in zip(hyps, passed)})
    flag = manifest["survivorship"]["flag"]
    primary = "显著" if selected is not None and not flag else "不显著"

    lines = []
    for h, e, s, ok in zip(hyps, est, se, passed):
        a, b = _config_words(family, h["a"]), _config_words(family, h["b"])
        claim = (f"{a}比{b}好" if h["type"] == "superiority"
                 else f"{a}不比{b}差出 {h['margin'] * 100:.2f} 点以上")
        lines.append(f"  - {claim}:差 {_pt(e)}(误差 {_pt(s).lstrip('+')}),"
                     f"{'校正多重比较后通过' if ok else '没通过'}")
    if selected is None:
        verdict = "按事先定好的顺序,一个配置都没确认下来:往前那段的检验记为「不显著」,前向那段核对整套改动。"
    else:
        verdict = f"按事先定好的顺序选出「{_config_words(family, selected)}」。"
        if flag:
            verdict += "但幸存者偏差可能超出容忍范围,这次确认只按「暂定」算(往前那段的检验记为「不显著」),以前向那段为准。"
    text = f"{window_words}:\n" + "\n".join(lines) + "\n" + verdict
    return {"confirm_window": "backward", "method": manifest["method"], "alpha": alpha,
            "survivorship_flag": flag, "selected": selected, "primary": primary,
            "config_params": family["configs"][selected] if selected is not None else None,
            "hypotheses": [{**h, "est": _num(e), "se": _num(s), "T": _num(t), "p_raw": _num(p), "p_adj": _num(q),
                            "passed": bool(ok), "n_clusters": r["n_clusters"]}
                           for h, e, s, t, p, q, ok, r in zip(hyps, est, se, T, p_raw, p_adj, passed, rc)],
            "text": text}


def _forward(U, D, N, family: dict, manifest: dict, backward: dict | None, window_words: str) -> dict:
    checked = backward["selected"] if backward is not None and backward["selected"] is not None else FULL
    names = list(family["configs"])
    coef = np.zeros(len(names))
    coef[names.index(checked)], coef[names.index(BASE)] = 1.0, -1.0
    rc = ratio_contrast(U, D, N, coef)
    delta, alpha = family["delta"], manifest["alpha"]
    lower = rc["est"] - stats.norm.ppf(1 - alpha) * rc["se"]
    train = manifest["train_est"][_hyp_id(family, checked, BASE)]
    ni_pass = bool(np.isfinite(lower) and lower >= -delta)
    same_sign = bool(np.isfinite(rc["est"]) and train != 0 and np.sign(rc["est"]) == np.sign(train))
    why = ("往前那段还没开,先核对整套改动" if backward is None
           else "往前那段一个都没确认下来,核对整套改动" if backward["selected"] is None
           else "核对往前那段选出的配置")
    text = (f"{window_words}({why}):「{_config_words(family, checked)}」相对改前参数差 {_pt(rc['est'])},"
            f"单侧下界 {_pt(lower)}(容忍到 {-delta * 100:.2f} 点)→ "
            f"{'没有比改前差出容忍范围' if ni_pass else '比改前差出了容忍范围'};"
            f"方向与训练期({_pt(train)}){'一致' if same_sign else '不一致'}。")
    return {"confirm_window": "forward", "checked": checked, "config_params": family["configs"][checked],
            "est": _num(rc["est"]), "se": _num(rc["se"]),
            "lower": _num(lower), "delta": delta, "train_est": train, "ni_pass": ni_pass, "same_sign": same_sign,
            "n_clusters": rc["n_clusters"], "text": text}


def _combine(backward: dict, forward: dict, family: dict) -> tuple[dict | None, str]:
    """两窗齐了才判读。前向核对的配置必须是往前窗该核对的那一个(先开前向窗时它核对的是整套改动)。"""
    should = backward["selected"] if backward["selected"] is not None else FULL
    if forward["checked"] != should:
        return None, (f"前向那段核对的是「{_config_words(family, forward['checked'])}」,而往前那段选出的是"
                      f"「{_config_words(family, should)}」,两段检验的不是同一个配置,给不出合并结论;"
                      "两段数据都已用过,不能重开。")
    res = interpret(backward["primary"], forward["ni_pass"], forward["same_sign"])
    return {**res, "config": should}, f"结论(针对「{_config_words(family, should)}」):{res['text']}"


def _opened(app: str, manifest_hash_: str, window: str) -> dict | None:
    for rec in reversed(ledger.read(app)):
        if (rec["kind"] == "extrapolate" and rec["data"]["manifest_hash"] == manifest_hash_
                and rec["data"]["confirm_window"] == window):
            return rec["data"]["results"]
    return None


def validate(app: str, confirm_window: str, *, manifest_hash: str, load_window_sums, out_dir, actor: str,
             calendar=None) -> dict:
    """在一段确认窗上按冻结清单检验一次;返回结果(含人话 text)。

    1) 过确认窗守卫(`holdout.guard_label_access`,purpose="validate"):清单未冻结、冻结不早于开窗、
       预期把握未告知、把握不足一半且用户未同意、该窗已开过、清单不是最新 → HoldoutLocked,不读任何数据。
    2) load_window_sums(configs, window) → {配置名: DataFrame(index=股票代码, 列 U/D/N)}:该窗每个配置格的
       每股计数和(买点事件口径);window = 该确认窗的买点区间 {start, end}。
    3) 往前窗:每个假设算 est / se / 单侧 T,族内校正(清单冻结的方法)→ 按映射选配置;
       清单里幸存者偏差 flag 为真时主确认按「不显著」读。
       前向窗:只核对映射选出的配置(往前窗没开过或一个都没选出时核对整套改动)相对改前:
       非劣效(单侧下界 ≥ −δ)与和训练期同号。
       另一段已开过时按判读表合并出结论。
    4) 结果先写 out_dir/<清单哈希前 12 位>_<确认窗>.json,再写 extrapolate 记录(ref 带其 sha256)。
    calendar 缺省用数据目录的交易日历(单测传合成日历)。"""
    if confirm_window not in ledger.CONFIRM_NAMES:
        raise ValueError(f"confirm_window 只能是 {ledger.CONFIRM_NAMES} 之一: {confirm_window!r}")
    cal_kw = {} if calendar is None else {"calendar": calendar}
    op = ledger.latest(app, "open")
    if op is None:                                   # 没开局核对:由守卫给出统一的拒绝理由
        holdout.guard_label_access(app, "2000-01-03", "2000-01-03", "validate", manifest_hash=manifest_hash,
                                   confirm_window=confirm_window, **cal_kw)
    seg = op["data"]["confirm"][confirm_window]
    window = {"start": seg["start"], "end": seg["end"]}
    holdout.guard_label_access(app, window["start"], window["end"], "validate", manifest_hash=manifest_hash,
                               confirm_window=confirm_window, **cal_kw)

    pre = next(r for r in reversed(ledger.read(app))
               if r["kind"] == "preregister" and r["data"]["manifest_hash"] == manifest_hash)
    manifest = pre["data"]["manifest"]
    if _canonical_sha(manifest) != manifest_hash:
        raise ValueError("账本里这份验证清单的内容与它的哈希对不上,清单被改动过,不能据此开窗")
    family = manifest["family"]
    U, D, N = _stack(load_window_sums(family["configs"], window), list(family["configs"]))

    words = f"{holdout.WINDOW_WORDS[confirm_window]}({window['start']} 到 {window['end']} 的买点)"
    if confirm_window == "backward":
        res = _backward(U, D, N, family, manifest, words)
        other = _opened(app, manifest_hash, "forward")
        pair = (res, other) if other is not None else None
    else:
        backward = _opened(app, manifest_hash, "backward")
        res = _forward(U, D, N, family, manifest, backward, words)
        pair = (backward, res) if backward is not None else None
    if pair is None:
        res["interpretation"] = None
        res["text"] += "\n另一段验证数据还没开,两段都开完再给最终结论。"
    else:
        res["interpretation"], line = _combine(*pair, family)
        res["text"] += "\n" + line

    out = Path(out_dir) / f"{manifest_hash[:12]}_{confirm_window}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(res, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
    try:
        ref_key = str(out.resolve().relative_to(ledger.REPO))
    except ValueError:
        ref_key = str(out.resolve())
    ledger.append(ledger.make_record(
        "extrapolate", app, actor=actor, round=pre["round"], axes=pre["axes"], window=window,
        label_horizon=op["label_horizon"], head_buffer=op["head_buffer"], n_looks=1,
        **{k: pre[k] for k in ledger.FINGERPRINT_FIELDS},
        ref={ref_key: ledger.sha256_file(out)},
        data={"manifest_hash": manifest_hash, "confirm_window": confirm_window, "results": res}))
    return res
