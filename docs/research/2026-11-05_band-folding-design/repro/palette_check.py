"""研究用临时脚本:评估 path2_web 默认调色板(serialize._PALETTE)对色盲用户的可分性,并在候选色里搜一组新的。

量什么(每个颜色 / 每对颜色):
- L*:CIELAB 明度(0 黑 ~ 100 白)。
- 对白底的对比度:WCAG 2 相对亮度对比度(图形元素建议 ≥ 3:1)。
- ΔE:CIE76 色差,分别在正常视觉、红色盲(protanopia)、绿色盲(deuteranopia)模拟下算,取三者最小值
  (模拟矩阵:Machado, Oliveira & Fernandes 2009,严重度 1.0,作用在线性 RGB 上)。
- 冷暖:蓝、紫算冷,红、橘、黄、绿算暖(用户的配色规则)。

用法: uv run python docs/research/2026-11-05_band-folding-design/repro/palette_check.py
"""
from __future__ import annotations

import itertools

import numpy as np

CURRENT = ["#16f943", "#2563eb", "#FF1500", "#14b24e", "#7c3aed", "#0891b2", "#ca8a04"]
GRAYS = {"qualified": "#9ca3af", "detected": "#d1d5db"}
BG = {"white": "#ffffff", "band_line": "#e0e6f1"}

PROTAN = np.array([[0.152286, 1.052583, -0.204868],
                   [0.114503, 0.786281, 0.099216],
                   [-0.003882, -0.048116, 1.051998]])
DEUTAN = np.array([[0.367322, 0.860646, -0.227968],
                   [0.280085, 0.672501, 0.047413],
                   [-0.011820, 0.042940, 0.968881]])

COOL = ["#1a80ba", "#2563eb", "#1f5fa8", "#3949ab", "#4157c4", "#2f6fd0", "#3a7bd5", "#4a90c8", "#5b8fd9",
        "#6a5acd", "#5b4fc4", "#7c3aed", "#4062bb", "#2b6cb0", "#3182ce", "#4c72b0", "#5677c8", "#1e5a96",
        "#355c9c", "#6d5bd0", "#2a4d8f"]
WARM = ["#d46a00", "#e07b00", "#c2410c", "#b45309", "#c0392b", "#b91c1c", "#a83232", "#d9534f", "#c75d2c",
        "#2e8540", "#3a8f3a", "#4d9a2a", "#5a8f00", "#9a7d0a", "#b8860b", "#a16207", "#c08a00", "#d97706",
        "#8a6a00", "#a0522d"]


def hex2rgb(h):
    h = h.lstrip("#")
    return np.array([int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)])


def lin(c):
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


def delin(c):
    c = np.clip(c, 0, 1)
    return np.where(c <= 0.0031308, 12.92 * c, 1.055 * c ** (1 / 2.4) - 0.055)


def lab_of_lin(rl):
    m = np.array([[0.4124, 0.3576, 0.1805], [0.2126, 0.7152, 0.0722], [0.0193, 0.1192, 0.9505]])
    xyz = m @ rl / np.array([0.95047, 1.0, 1.08883])
    f = np.where(xyz > 0.008856, np.cbrt(xyz), 7.787 * xyz + 16 / 116)
    return np.array([116 * f[1] - 16, 500 * (f[0] - f[1]), 200 * (f[1] - f[2])])


def lab(h, sim=None):
    rl = lin(hex2rgb(h))
    if sim is not None:
        rl = lin(delin(sim @ rl))   # 模拟在线性空间做,回 sRGB 截断后再线性化,保持和显示一致
    return lab_of_lin(rl)


def lum(h):
    rl = lin(hex2rgb(h))
    return float(0.2126 * rl[0] + 0.7152 * rl[1] + 0.0722 * rl[2])


def contrast(a, b):
    la, lb = sorted([lum(a), lum(b)], reverse=True)
    return (la + 0.05) / (lb + 0.05)


def de_min(a, b):
    """三种视觉下 ΔE 的最小值(最难分的那种)。"""
    return float(min(np.linalg.norm(lab(a, s) - lab(b, s)) for s in (None, PROTAN, DEUTAN)))


def warmth(h):
    return "cool" if h in COOL or h.lower() in ("#2563eb", "#7c3aed", "#0891b2") else "warm"


def report(name, pal):
    print(f"\n## {name}: {pal}")
    print("颜色  L*  对白底  对#e0e6f1  ΔE(对 qualified 灰)  ΔE(对 detected 灰)")
    for c in pal:
        print(f"{c}  {lab(c)[0]:5.1f}  {contrast(c, '#ffffff'):4.2f}  {contrast(c, BG['band_line']):4.2f}  "
              f"{de_min(c, GRAYS['qualified']):5.1f}  {de_min(c, GRAYS['detected']):5.1f}")
    print("相邻两色(含首尾相接):ΔE 三种视觉最小值 / ΔL* / 冷暖")
    n = len(pal)
    for i in range(n):
        a, b = pal[i], pal[(i + 1) % n]
        print(f"  [{i}]{a} - [{(i + 1) % n}]{b}: ΔE {de_min(a, b):5.1f}  ΔL {abs(lab(a)[0] - lab(b)[0]):4.1f}")
    print("隔一个的两色:")
    for i in range(n):
        a, b = pal[i], pal[(i + 2) % n]
        print(f"  [{i}]{a} - [{(i + 2) % n}]{b}: ΔE {de_min(a, b):5.1f}  ΔL {abs(lab(a)[0] - lab(b)[0]):4.1f}")


def ok_single(c):
    L = lab(c)[0]
    return (contrast(c, "#ffffff") >= 3.0 and L >= 33
            and de_min(c, GRAYS["qualified"]) >= 15 and de_min(c, GRAYS["detected"]) >= 30)


def search():
    cool = [c for c in COOL if ok_single(c)]
    warm = [c for c in WARM if ok_single(c)]
    allc = list(dict.fromkeys(cool + warm))
    D = {(a, b): de_min(a, b) for a in allc for b in allc}
    best = None
    c0 = "#1a80ba"
    for w1, c2, w3, c4, w5 in itertools.product(warm, cool, warm, cool, warm):
        pal = [c0, w1, c2, w3, c4, w5]
        if len(set(pal)) < 6:
            continue
        d1 = min(D[(pal[i], pal[(i + 1) % 6])] for i in range(6))
        d2 = min(D[(pal[i], pal[(i + 2) % 6])] for i in range(6))
        score = (min(d1, d2), d1 + d2)
        if best is None or score > best[0]:
            best = (score, pal)
    return best


if __name__ == "__main__":
    report("现色板", CURRENT)
    best = search()
    print("\n搜索结果(首色固定中蓝 #1a80ba,冷暖交替 6 色,目标:相邻与隔一个两色在三种视觉下的最小 ΔE 最大):", best)
    report("新色板", best[1])


def search5():
    """5 色、冷暖交替(冷 暖 冷 暖 冷)。约束:L* 在 [36, 62]、对白底 ≥ 3:1、
    对两档灰 ΔE 够大;相邻两色三种视觉最小 ΔE ≥ 40;同冷暖的每一对(三个冷色两两、两个暖色)ΔL* ≥ 10。
    目标:先让隔一个的两色 ΔL* 最小值最大,再让相邻两色 ΔE 最小值最大。返回前 5 名。"""
    extra_cool = ["#4d8fe0", "#5599dd", "#3a8fd9", "#4a90c8", "#5b8fd9", "#2f5fb3", "#4157c4", "#6a5acd", "#7c3aed",
                  "#5b6fd6", "#4f6bd8", "#3d6fc4"]
    extra_warm = ["#c0392b", "#b91c1c", "#a83232", "#d46a00", "#d97706", "#c08a00", "#b8860b", "#e07b00", "#2e8540",
                  "#3a8f3a", "#c2410c", "#b45309"]
    Lc = {}

    def ok(c):
        Lc[c] = lab(c)[0]
        return 36 <= Lc[c] <= 62 and ok_single(c)
    cool = [c for c in dict.fromkeys(COOL + extra_cool) if ok(c)]
    warm = [c for c in dict.fromkeys(WARM + extra_warm) if ok(c)]
    allc = cool + warm
    D = {(a, b): de_min(a, b) for a in allc for b in allc}
    res = []
    for c0, w1, c2, w3, c4 in itertools.product(cool, warm, cool, warm, cool):
        pal = [c0, w1, c2, w3, c4]
        if len(set(pal)) < 5:
            continue
        d1 = min(D[(pal[i], pal[i + 1])] for i in range(4))
        if d1 < 40:
            continue
        same = [(0, 2), (2, 4), (0, 4), (1, 3)]   # 同冷暖的每一对(含首尾两个冷色)
        dl2 = min(abs(Lc[pal[i]] - Lc[pal[j]]) for i, j in same)
        if dl2 < 10:
            continue
        de2 = min(D[(pal[i], pal[j])] for i, j in same)
        res.append(((round(float(dl2), 1), round(float(min(d1, 2 * de2)), 1)), pal))
    res.sort(reverse=True)
    return res[:5]


if __name__ == "__main__":
    top = search5()
    print("\n5 色搜索前 5 名:", *top, sep="\n  ")
    if top:
        report("新色板(5 色)", top[0][1])


if __name__ == "__main__":
    # 手调:把用户配色规则里举例的中蓝 #1a80ba 放进首位,其余沿用搜索结果的冷暖与明度梯度
    report("手调候选 A(首色 #1a80ba)", ["#1a80ba", "#d97706", "#1e5a96", "#c0392b", "#5599dd"])


def search5_v2():
    """skeptic-2 审后的第二版约束:更看重「离浅底远、离两档灰远」,放宽同冷暖的明度差。
    - 冷暖按 CIELAB b*(黄-蓝轴,红绿色盲也保留):b* ≤ -20 算冷、≥ +20 算暖,中间判不合格(界线待验证)。
    - 每色 L* 在 [40, 55](低于 40 就是用户说的深靛、深褐,压掉形状);对副图浅灰底 #f3f4f6 对比度 ≥ 3.5;对 qualified 灰 #9ca3af 对比度 ≥ 1.6。
    - 相邻两色冷暖相反,三种视觉最小 ΔE ≥ 40。
    目标:同冷暖每一对(三个冷两两、两个暖)的三种视觉最小 ΔE 的最小值最大,再看相邻 ΔE 最小值。"""
    cool_pool = ["#1a80ba", "#2563eb", "#1f5fa8", "#3949ab", "#4157c4", "#2f6fd0", "#3a7bd5", "#5b6fd6", "#4c51bf",
                 "#5a67d8", "#3182ce", "#2b6cb0", "#2c5282", "#434190", "#6b46c1", "#805ad5", "#1e5a96", "#355c9c",
                 "#7c3aed", "#6d5bd0", "#2a4d8f", "#4062bb"]
    warm_pool = ["#c2410c", "#b45309", "#a16207", "#c05621", "#dd6b20", "#9c4221", "#b7791f", "#975a16", "#c0392b",
                 "#b91c1c", "#a83232", "#d9534f", "#c75d2c", "#d97706", "#a0522d", "#8a6a00"]
    def bstar(c):
        return lab(c)[2]
    def ok(c, sign):
        L = lab(c)[0]
        return (40 <= L <= 55 and contrast(c, "#f3f4f6") >= 3.5 and contrast(c, GRAYS["qualified"]) >= 1.6
                and (bstar(c) <= -20 if sign < 0 else bstar(c) >= 20))
    cool = [c for c in dict.fromkeys(cool_pool) if ok(c, -1)]
    warm = [c for c in dict.fromkeys(warm_pool) if ok(c, +1)]
    allc = cool + warm
    D = {(a, b): de_min(a, b) for a in allc for b in allc}
    res = []
    for c0, w1, c2, w3, c4 in itertools.product(cool, warm, cool, warm, cool):
        pal = [c0, w1, c2, w3, c4]
        if len(set(pal)) < 5:
            continue
        d1 = min(D[(pal[i], pal[i + 1])] for i in range(4))
        if d1 < 40:
            continue
        same = min(D[(pal[i], pal[j])] for i, j in [(0, 2), (2, 4), (0, 4), (1, 3)])
        res.append(((round(float(same), 1), round(float(d1), 1)), pal))
    res.sort(reverse=True)
    return res[:5], cool, warm


def report2(name, pal):
    print(f"\n## {name}: {pal}")
    print("颜色  L*  b*  对白底  对#f3f4f6  对qualified灰  对detected灰")
    for c in pal:
        L = lab(c)
        print(f"{c}  {L[0]:5.1f}  {L[2]:6.1f}  {contrast(c, '#ffffff'):4.2f}  {contrast(c, '#f3f4f6'):4.2f}  "
              f"{contrast(c, GRAYS['qualified']):4.2f}  {contrast(c, GRAYS['detected']):4.2f}")
    for i in range(len(pal) - 1):
        print(f"  相邻 [{i}]-[{i + 1}] ΔE {de_min(pal[i], pal[i + 1]):5.1f}")
    for i, j in [(0, 2), (2, 4), (0, 4), (1, 3)]:
        if j < len(pal):
            print(f"  同冷暖 [{i}]-[{j}] ΔE {de_min(pal[i], pal[j]):5.1f}  ΔL {abs(lab(pal[i])[0] - lab(pal[j])[0]):4.1f}")


if __name__ == "__main__":
    top2, cool2, warm2 = search5_v2()
    print("\n第二版候选池通过单色约束的: 冷", cool2, "暖", warm2)
    print("第二版前 5 名:", *top2, sep="\n  ")
    report2("第一版色板(已落代码)", ["#5b6fd6", "#d97706", "#5599dd", "#c0392b", "#1e5a96"])
    if top2:
        report2("第二版色板", top2[0][1])
