# -*- coding: utf-8 -*-
"""调参预算计算器:功效线、噪声地板上界、分辨力(能分辨的最小改进)、联合调参可行性。

δ(最小关心改进)与 n_pl、floor_upper 的输入输出一律用比例(0.02 = 2 点)。
se_flip / x_screen / x_single / delta_needed_for_joint 是线性量,传入什么单位就返回什么单位,
与 joint_feasible 比较的 delta 须与 se_flip 同单位。

设计效应 deff、定向占比 s_dec 没有默认值:调用方必须传本窗优势检查的实测值,没有实测就不算。
标定示例(bb_v1,仅供对照量级):p = 0.5、deff = 5、s_dec = 0.62 时 n_pl ≈ 3.29/δ²,δ = 2 点约每折 8233 个 bar。
"""
from __future__ import annotations

import numpy as np

from inference import z_bh_first

POWER_Z = 0.84          # 80% 功效对应的 z
SINGLE_MULT = 2.8       # 单个预写改动:双侧 5% + 80% 功效 ≈ 1.96 + 0.84
JOINT_MULT = 1.7        # 两个及以上参数同改时分辨力放大倍数

# 检测参数改动的买点保留比例先验。只在 bb_v1 上标定过:
# 只许用于筛选扫描之前的估算,由此算出的分辨力 / 可行性结果必须标「估计」;筛选之后改用实测保留比例。
R_BAR_DETECT_PRIOR: float = 0.85


def n_pl(delta, *, deff, s_dec, p=0.5) -> float:
    """功效线:每折所需的全部 bar 数 n_pl = 1.96·p(1−p)·deff / (1.2·s_dec·δ²)。

    deff = 设计效应,s_dec = 定向 bar / 全部 bar,均取本窗优势检查实测值。
    """
    return 1.96 * p * (1 - p) * deff / (1.2 * s_dec * delta ** 2)


def floor_upper(n_pl, *, deff, s_dec, p=0.5) -> float:
    """噪声地板上界:floor = 1.4·√(p(1−p)·deff / (1.2·n_pl·s_dec))。

    恰在功效线上(n_pl = n_pl(δ))时 floor = δ;floor ≥ δ 的网格拒绝扫。deff、s_dec 同 n_pl。
    """
    return 1.4 * float(np.sqrt(p * (1 - p) * deff / (1.2 * n_pl * s_dec)))


def se_flip(se_level, r_bar) -> float:
    """一次改动(翻转)的差值 SE:SE_flip ≈ SE_level·√((1−r̄)/r̄)。

    SE_level = 工作点格两年合并的按股线性化 SE;r̄ = 改动后的买点保留比例。
    闸类改动直接数 bar;检测参数在筛选之前只能取 R_BAR_DETECT_PRIOR 估算(结果标「估计」),筛选之后用实测值。
    """
    return se_level * float(np.sqrt((1 - r_bar) / r_bar))


def x_screen(se_flip, m, q) -> float:
    """筛选阶段能分辨的最小改进:x = (z_BH(m, q) + 0.84)·SE_flip,m 为实际对比族大小、q 为 BH 阈值。"""
    return (z_bh_first(m, q) + POWER_Z) * se_flip


def x_single(se_flip) -> float:
    """单个预写改动能分辨的最小改进:x = 2.8·SE_flip。"""
    return SINGLE_MULT * se_flip


def delta_needed_for_joint(se_flip, n_params) -> float:
    """联合调参要求的最小 δ:x_single·(1.7 若 n_params ≥ 2,否则 1)。"""
    return x_single(se_flip) * (JOINT_MULT if n_params >= 2 else 1.0)


def joint_feasible(se_flip, delta, n_params) -> bool:
    """联合调参是否可行:delta_needed_for_joint(se_flip, n_params) ≤ δ。"""
    return bool(delta_needed_for_joint(se_flip, n_params) <= delta)
