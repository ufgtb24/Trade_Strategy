"""designer：画淡的对比度（WCAG 相对亮度）。记号按不透明度 a 叠在它实际所在的底上，再和同一块底比、和没画淡的自己比。
运行：python3 docs/research/2026-11-12_selection-highlight-rules/repro/designer_contrast.py"""
def hx(h): h = h.lstrip('#'); return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))
def lin(c): c /= 255; return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
def L(rgb): r, g, b = (lin(x) for x in rgb); return 0.2126 * r + 0.7152 * g + 0.0722 * b
def cr(a, b): la, lb = L(a), L(b); return (max(la, lb) + 0.05) / (min(la, lb) + 0.05)
def blend(fg, bg, a): return tuple(a * f + (1 - a) * b for f, b in zip(fg, bg))
WHITE, STRIPE, HITS = hx('#ffffff'), hx('#ebebeb'), hx('#fffbdb')
marks = [('天蓝 node #1e9be0', '#1e9be0', [WHITE, STRIPE]), ('中蓝 node #1a80ba', '#1a80ba', [WHITE, STRIPE]),
         ('红 node #d7000f', '#d7000f', [WHITE, STRIPE]), ('qualified 灰 #9ca3af', '#9ca3af', [WHITE, STRIPE]),
         ('detected 灰 #b4bac2', '#b4bac2', [WHITE, STRIPE]), ('hits 琥珀格 #fbbf24', '#fbbf24', [HITS]),
         ('族底线 #6b7280', '#6b7280', [WHITE, STRIPE, HITS])]
bgname = {WHITE: '白底', STRIPE: '隔行底', HITS: 'hits 浅黄底'}
alphas = [1.0, 0.6, 0.5, 0.45, 0.4, 0.28]
print('记号 | 底 | ' + ' | '.join(f'a={a}: 对底 / 照常对淡' for a in alphas))
for name, c, bgs in marks:
    for bg in bgs:
        cells = []
        for a in alphas:
            d = blend(hx(c), bg, a)
            cells.append(f'{cr(d, bg):.2f} / {cr(hx(c), d) if a < 1 else 1:.2f}')
        print(f'{name} | {bgname[bg]} | ' + ' | '.join(cells))
# ▼：黑三角压在琥珀格上，两者一起画淡（各自按 a 叠到下面）
amber = hx('#fbbf24'); tri = hx('#111111')
for a in alphas:
    cell = blend(amber, HITS, a); t = blend(tri, cell, a)
    print(f'▼ 叠在画淡的琥珀格上 a={a}: ▼ 对格 {cr(t, cell):.2f}，▼ 对 hits 底 {cr(t, HITS):.2f}，照常 ▼ 对淡 ▼ {cr(tri, t):.2f}')
