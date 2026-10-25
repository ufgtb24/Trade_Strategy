"""flow.md 用的小样本算术：盲看一份多大能看出什么、均匀抽能不能抽到某次改动新增的 match。
纯组合计算，不读任何行情数据。"""
from math import comb, sqrt

def wilson(k, n, z=1.96):
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return max(0, c - h), min(1, c + h)

def p_at_least(k, n, p):
    return sum(comb(n, i) * p**i * (1 - p)**(n - i) for i in range(k, n + 1))

def hyper_at_least1(M, D, n):
    # 从 M 个 match 里不放回均匀抽 n 张，至少抽到 1 张「本次改动新增」的概率（新增 D 个）
    return 1 - comb(M - D, n) / comb(M, n)

print("== 盲看 n 张里 k 张「不是」，真实「不是」比例的 95% 区间 ==")
for n in (20, 30):
    for k in range(0, 7):
        lo, hi = wilson(k, n)
        print(f"n={n} k={k}: {k/n:.0%}  区间 {lo:.0%}~{hi:.0%}")

print("\n== 某类毛病真实占比 p，n 张里至少出现 2 次（会话能认出它是反复出现的同一类）的概率 ==")
for n in (20, 30):
    for p in (0.05, 0.10, 0.15, 0.20):
        print(f"n={n} p={p:.0%}: {p_at_least(2, n, p):.0%}")

print("\n== 全池 M 个 match，本次改动新增 D 个，均匀抽 20 张至少碰到 1 张新增的概率 ==")
for M in (300, 1000, 3000):
    for D in (5, 20, 50, 150):
        if D < M:
            print(f"M={M} D={D}: {hyper_at_least1(M, D, 20):.0%}")

print("\n== 新标注 m 张，app 真实认出率 r，认出张数 ≤ m/2 的概率（看不出 app 是否偏窄的风险）==")
for m in (5, 8, 12):
    for r in (0.5, 0.7, 0.9):
        # 认出数 X~Bin(m,r)，P(X <= floor(m/2))
        pr = sum(comb(m, i) * r**i * (1 - r)**(m - i) for i in range(0, m // 2 + 1))
        print(f"m={m} r={r:.0%}: P(认出≤一半)={pr:.0%}")

print("\n== 同时有 k 类小毛病、各占 p，n 张里至少有一类出现 ≥2 次的概率（多项分布精确枚举）==")
from functools import lru_cache

def p_any_ge2(n, k, p):
    # 每张图：落入第 i 类（i=1..k）概率 p，其余 1-k*p。求所有类计数都 ≤1 的概率，再取补。
    # 所有类都 ≤1：选 j 张分别落在 j 个不同类里，其余落在「其他」。
    q = 1 - k * p
    tot = 0.0
    for j in range(0, min(k, n) + 1):
        # 选 j 个类各出现一次：C(k,j) * 排列 n!/(n-j)! * p^j * q^(n-j)
        perm = 1
        for t in range(j):
            perm *= (n - t)
        tot += comb(k, j) * perm * p**j * q**(n - j)
    return 1 - tot

for n in (20, 30):
    for k in (2, 3, 4):
        for p in (0.05, 0.10):
            print(f"n={n} k={k} p={p:.0%}: {p_any_ge2(n, k, p):.0%}")

print("\n== 某类毛病真实占比 p，n 张里至少出现 3 次的概率；以及同时 3 类各 5% 时至少一类 ≥3 次 ==")
for n in (20, 40, 60):
    row = ", ".join(f"p={p:.0%}: {p_at_least(3, n, p):.0%}" for p in (0.05, 0.10, 0.15, 0.20))
    print(f"n={n}: {row}")

def p_any_ge3_mc(n, k, p, trials=200000, seed=1):
    import random
    rng = random.Random(seed)
    hit = 0
    for _ in range(trials):
        cnt = [0] * k
        for _ in range(n):
            u = rng.random()
            i = int(u / p)
            if i < k:
                cnt[i] += 1
        hit += max(cnt) >= 3
    return hit / trials

for n in (20, 40):
    for k in (3,):
        for p in (0.05,):
            print(f"n={n} k={k} p={p:.0%}: 至少一类≥3 次 ≈ {p_any_ge3_mc(n, k, p):.0%}（模拟）")

print("\n== 改动新增 / 去掉的 match 抽 5 张，真实「不是」比例 r 时，至少 4 张「不是」的概率 ==")
for r in (0.2, 0.4, 0.6, 0.8):
    print(f"r={r:.0%}: {p_at_least(4, 5, r):.0%}")

print("\n== 均匀部分只有 15 / 10 张时的区间与「某类出现 ≥2 次」的概率 ==")
for n in (10, 15):
    print(f"n={n}: " + ", ".join(f"k={k}: {wilson(k, n)[0]:.0%}~{wilson(k, n)[1]:.0%}" for k in range(0, 6)))
    print(f"n={n}: " + ", ".join(f"p={p:.0%} ≥2 次 {p_at_least(2, n, p):.0%}" for p in (0.05, 0.10, 0.15, 0.20)))
