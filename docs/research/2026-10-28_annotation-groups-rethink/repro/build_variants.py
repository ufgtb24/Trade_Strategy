"""从 mock_v3.html 生成 groups 变体（ui，2026-10-28）。只动买点列表相关的几处，其余逐字照抄，让对比只差这一处：
  - sideSum() 末尾的 groups 一段（换成各变体的列表）；
  - 页头 instances 一行（三个变体都一样：多一行 app:buy 总数；B、C 的数字可点）；
  - features 区的 in k/N 与属性计数（B、C 可点；A 不动）；
  - diffTags 补上 order 签、像但不买的 = 换一句悬停（三个变体都一样）。

    python3 build_variants.py          # 在本目录运行；会覆盖生成出的三个 html
"""
from pathlib import Path

HERE = Path(__file__).parent
SRC = HERE / '../../2026-10-26_annotation-workflow-polish/repro/mock_v3.html'


def sub(s, old, new, n=1):
    assert s.count(old) == n, (old[:80], s.count(old))
    return s.replace(old, new)


CSS_AT = '  .th { position: relative; display: inline-block; }\n'
CSS = """  .vrow { display: grid; gap: 4px 6px; align-items: center; }                            /* groups 变体：表格一行 */
  .vth { display: inline-flex; flex-direction: column; align-items: flex-start; gap: 2px; margin: 0 0 4px 0; vertical-align: top; }   /* 缩略图 + 下面一行股票日期 + 一行签 */
  .vcap { font-size: 11px; }
  button.vdoor { font-family: var(--mono); font-size: 11px; padding: 0 5px; background: transparent; }   /* 可点的计数：点了列出计进它的那几个 */
  button.vdoor.bad { background: var(--bad); color: #fff; border-color: var(--bad); font-weight: 700; }
  button.vdoor[aria-pressed="true"] { background: #111; color: #fff; border-color: #111; }   /* 点开的那个：黑底白字（同全局按下） */
  button.vdoor.bad[aria-pressed="true"] { background: var(--bad); border-color: var(--bad); outline: 2px solid #111; outline-offset: 1px; }
  .kv > .vinline { grid-column: 1 / -1; }                                                    /* 页头里就地展开：占满两栏 */
  .vinline { flex-basis: 100%; }                                                             /* 变体 C：就地展开，占满一行 */
  .vstrip { border-top: 1px dashed #a1a1aa; padding-top: 3px; margin-top: 4px; }
  .vnil { font-family: var(--mono); font-size: 11.5px; color: #a1a1aa; }                   /* 空格子：灰字只给「空」 */
"""

# ── 三个变体共用的辅助，放在 sideSum 前面（features 区渲染时就要用，必须先声明） ──
HELPERS = r"""// ── groups 变体 __V__ 的辅助（到 sideSum 前为止都是新加的）。买点列表不再叫 groups，界面上不出「组」「主组」「偏离组」「by:」 ──
const VAR = '__V__'
const chainOf = x => treeOf(x.ms).map((n, i) => (i ? arrow(null) : '') + roChip(n.b)).join('') || sym('∅')   // 顶层成员按先后（用户的特征名）
const vBy = (xs, key) => { const g = new Map(); for (const x of xs) { const k = key(x); if (!g.has(k)) g.set(k, []); g.get(k).push(x) } return [...g.entries()].sort((p, q) => q[1].length - p[1].length) }
function vInst(p = S.cur) {         // 这个 pattern 的全部买点：按顶栏的图序、再按日期排——顺序稳定，不随阶段变
  const app = PAPP[p]
  return STOCKS.flatMap((st, si) => annOf(st).buys.filter(b => b.pattern === p).sort((a, b) => a.idx - b.idx).map(bp => {
    const ms = membersOf(bp, st), names = [...new Set(ms.map(b => txt(b.name)))]
    return { bp, st, si, ms, names, sig: sigOf(bp, st), d: app ? diffOf(bp, st, names) : null, ap: app ? buyVerdict(bp, st).app : null }
  }))
}
const vDev = x => !!x.d && x.bp.label === 'buy' && !x.d.same        // 和对应表对不上的 buy（讨论里叫偏离，界面上不出这个词）
const vRed = x => !!x.ap && x.ap !== x.bp.label                     // 朱红一刀切：app 的判断和你的 label 不一样就朱红，原因由差那一列说（critic V1，2026-10-28 团队定；取代 X1 的豁免）
const vMissTxt = x => [...x.d.miss.map(t => `缺了「${t}」`), ...x.d.extra.map(t => `有了「${t}」`), ...(x.d.order ? ['先后和 app 不同'] : [])].join('、')
const vNbTip = x => !x.d ? '' : x.d.same ? '；你的框跟正例一样，按现在的对应表分不出它为什么不买——不买的理由要画出来（加一个特征或属性），会话会在单子里问你'
  : `；你的框和正例差在${vMissTxt(x)}，app 没用上这个差（会话按原因分流）`
const vAppTip = x => `app 在这一天${x.ap === 'buy' ? '买了' : '没买'}` + (!vRed(x) ? '' : vDev(x) ? `；和你的 label 对不上。你的框${vMissTxt(x)}，会话下一轮会在单子里问`
  : x.bp.label === 'no_buy' ? '；和你的 label 对不上' + vNbTip(x) : '；和你的 label 对不上。app 不读你的框，补框、改框都改不了它的判断；会话下一轮查原因，你不用动')
const vAppT = (x, pre = true) => seg('app', tag((pre ? 'app:' : '') + x.ap, vRed(x) ? 'bad' : '', vAppTip(x)))
function vDifT(x) {                // 只给 buy（像但不买不挂差签，critic M1）：和对应表比的差，会话浅蓝底
  if (x.bp.label !== 'buy' || !x.d) return ''
  const d = x.d, hint = x.ap === 'buy' ? '；app 买了它：缺的那样往往图上其实有、只是没画（或没收进）' : ''
  if (d.same) return seg('session', tag('=', '', '必须有的都有，必须没有的都没有'))
  return seg('session', [...d.miss.map(t => `<span class="tag"${tip(`必须有「${t}」，成员里没有` + hint)}>−<span class="biz">${esc(t)}</span></span>`),
    ...d.extra.map(t => `<span class="tag"${tip(`「${t}」是必须没有的，成员里有`)}>+<span class="biz">${esc(t)}</span></span>`),
    ...(d.order ? [tag('order', '', '必须有都在，但先后和 app 不同')] : [])].join(' '))
}
const vCap = x => `<span class="biz vcap">${esc(x.st.symbol)} ${esc(dateOf(x.st, x.bp.idx))}</span>`
function vTh(x) {                 // 列表里的缩略图：去掉 ◂（critic V3）；悬停补上虚线框的意思、和这一张朱红的原因（critic U-9）
  const t = thumb(x), take = t.includes('class="take"')
  const more = (take ? '；虚线框 = 可能画了没收：点进去在 instance 页收进' : '') + (vRed(x) ? '。' + vAppTip(x) : '')
  return t.replace(/<button type="button" class="take"[^>]*>◂<\/button>/g, '').replace('</title>', esc(more) + '</title>')
}
const vThumb = (x, marks = true) => `<span class="vth">${vTh(x)}${vCap(x)}${marks && x.ap ? `<span class="row nw" style="gap:3px">${vDifT(x)}${vAppT(x)}</span>` : ''}</span>`
function vFit(xs) {                 // 一下挪过去：每一个都对得上的同一个已有 pattern（按每个买点判，不只看第一个，critic M4）
  return S.patterns.find(p => p !== S.cur && p !== UNSORTED && xs.every(x => PAPP[p] ? fitsApp(x.names, p) : commonSig(p) === x.sig))
}
function vMove(xs, quick = true) {  // 把这几个挪到别的 pattern：只改归类，不切页
  const gid = 'g' + Object.keys(GRP).length; GRP[gid] = xs.map(x => x.bp)
  const to = quick ? vFit(xs) : null
  return `<span class="row nw" style="gap:4px">${to ? `<button type="button" class="biz" style="flex:none" data-act="vmoveto:${gid}§${esc(to)}" title="这 ${xs.length} 个都和「${esc(to)}」对得上：点一下全挪过去（不切页）">→ ${esc(to)}</button>` : ''}<select style="flex:none" data-act="vmove:${gid}" class="sym" title="把这 ${xs.length} 个挪到别的 pattern；只改归类，不切页"><option value="">→ pattern</option>${S.patterns.filter(p => p !== S.cur).map(p => `<option>${esc(p)}</option>`).join('')}<option value="__new">+ new</option></select></span>`
}
// 计数入口：key 说明这个数是怎么数的。A：只有 features 区的 in k/N 可点、就地列出；B：点了在下面的 instances 里只看这几个；C：点了就地列出
const vClick = key => VAR !== 'A' || key.startsWith('feat|')
function vDoor(label, key, tp, cls = '') {
  if (!vClick(key)) return cls ? tag(label, cls, tp) : sym(label, tp)
  return `<button type="button" class="vdoor ${cls}" aria-pressed="${S.vKey === key}" data-act="vkey:${esc(key)}" title="${esc(tp + (VAR === 'B' ? '。点一下：下面 instances 里只看这几个，再点一下看全部' : '。点一下：就地列出这几个，再点一下收起'))}">${esc(label)}</button>`
}
// 一个计数入口背后的几排：k/n 点开 = 算进的一排、没算进的一排（每排都能整排挪走）
function vParts(key) {
  const [kind, a, b] = key.split('|'), xs = vInst(), buys = xs.filter(x => x.bp.label === 'buy')
  if (kind === 'lab') return [{ lab: sym(`${a} ${xs.filter(x => x.bp.label === a).length}`), xs: xs.filter(x => x.bp.label === a) }]
  if (kind === 'app') { const ys = xs.filter(x => x.bp.label === a); return ['buy', 'no_buy'].map(v => ({ lab: seg('app', sym(`app:${v} ${ys.filter(x => x.ap === v).length}`)), xs: ys.filter(x => x.ap === v) })) }
  if (kind === 'feat') {            // 两排都带上像但不买，整排挪时一起走（flow K）；in k/N 的数照旧只数 buy
    const part = (has, w) => { const ys = xs.filter(x => x.names.includes(a) === has).sort((p, q) => (p.bp.label === 'buy' ? 0 : 1) - (q.bp.label === 'buy' ? 0 : 1)), nb = ys.filter(x => x.bp.label === 'no_buy').length
      return { lab: sym(`buy ${w} ${ys.length - nb}` + (nb ? ` · no_buy ${nb}` : ''), `成员中${has ? '有' : '没有'}「${a}」的；上面的 in k/N 只数 buy，这里把 no_buy 也列出来，整排挪时一起走`), xs: ys } }
    return [part(true, 'in'), part(false, 'not_in')]
  }
  if (kind === 'dif') return [...vBy(buys.filter(vDev), x => diffKey(x.d)).map(([, ys]) => ({ lab: `${vDifT(ys[0])}${sym(String(ys.length))}`, xs: ys })),
    { lab: `${seg('session', tag('=', '', '必须有的都有、必须没有的都没有'))}${sym(String(buys.filter(x => !vDev(x)).length))}`, xs: buys.filter(x => !vDev(x)) }]
  if (kind === 'seq') return [{ lab: '', xs: xs.filter(x => x.sig === a) }]
  return []
}
function vStrips(key, marks = true) {
  return vParts(key).filter(p => p.xs.length).map(p => `<div class="vstrip"><div class="row">${p.lab}<span class="grow"></span>${vMove(p.xs)}</div><div class="row" style="margin-top:3px;align-items:flex-start">${p.xs.map(x => vThumb(x, marks)).join('')}</div></div>`).join('')
}
const vInline = key => VAR !== 'B' && vClick(key) && S.vKey === key ? `<div class="vinline">${vStrips(key)}</div>` : ''
// 页头：instances 一行的计数与 app:buy 一行的两个总数（三个变体同；B、C 可点）
function vHead(app) {
  const xs = vInst(), cnt = v => xs.filter(x => x.bp.label === v)
  let inst = `${vDoor('buy ' + cnt('buy').length, 'lab|buy', `${cnt('buy').length} 个标 buy（正例）`)}${sym('·')}${vDoor('no_buy ' + cnt('no_buy').length, 'lab|no_buy', `${cnt('no_buy').length} 个标 no_buy（像但不买）`)}`
  if (!app) return { inst, app: '' }
  const tot = v => { const ys = cnt(v), k = ys.filter(x => x.ap === 'buy').length
    return vDoor(`${v} ${k}/${ys.length}`, 'app|' + v, `你标 ${v} 的 ${ys.length} 个里，app 在那一天买了 ${k} 个` + (ys.some(vRed) ? '（朱红：有 app 和你对不上的）' : ''), ys.some(vRed) ? 'bad' : '') }
  const bs = cnt('buy'), k = bs.filter(vDev).length
  const dif = seg('session', k ? vDoor(`buy ≠ ${k}/${bs.length}`, 'dif|buy', `你标 buy 的 ${bs.length} 个里，有 ${k} 个收的框和对应表对不上（缺了必须有、有了必须没有、或先后和 app 不同）`)
    : sym(`buy ≠ 0/${bs.length}`, '你标 buy 的每一个，收的框都和对应表对得上'))
  return { inst, app: seg('app', `${tot('buy')}${sym('·')}${tot('no_buy')}`), dif }
}
"""

# ── 变体 A：按来源分列，相同的折成一行 ──
VA = r"""  // ── 买点列表（变体 A「按来源分列」）：一行一种组合，每列一个来源，所有列都相同的买点折成一行 ×n、缩略图排在行下 ──
  // 已命名 pattern 页的列始终是 label（你标的）/ must / must_not（你的框和会话写的对应表比，会话浅蓝；只给 buy）/ app（app 判的，琥珀；和 label 不一样就朱红）。
  // 没有 app 时后两列空着，于是只按 label 折成两行；写完 app 只是多出两列的值、行细分，不换折法（critic V4、U-3）。行内缩略图按顶层特征串排，同一种骨架挨着。
  // 未归类页不是 pattern：列是 label / sequence（顶层特征按先后），按特征串排，只差尾巴的挨着——这一页的决定就是「这一批归哪」。
  // 行序（有 app）：和对应表对不上的 buy → app 和 label 不一样的 → 其余；同一档里个数多的在前
  const vi = vInst().sort((p, q) => p.sig.localeCompare(q.sig))   // 稳定排序：同一串里仍按图序、日期
  const rows = vBy(vi, x => uns ? [x.bp.label, x.sig].join('|') : x.bp.label === 'buy' ? ['buy', x.d ? diffKey(x.d) : '', x.ap].join('|') : ['no_buy', x.ap].join('|'))
  const tier = x => vDev(x) ? 0 : vRed(x) ? 1 : 2
  if (uns) rows.sort((p, q) => p[1][0].sig.localeCompare(q[1][0].sig) || (p[1][0].bp.label === 'buy' ? -1 : 1)); else rows.sort((p, q) => (q[1][0].bp.label === 'buy') - (p[1][0].bp.label === 'buy') || tier(p[1][0]) - tier(q[1][0]))
  const G = `grid-template-columns:${uns ? '50px 1fr 24px' : '50px 1fr 64px 24px'}`
  const CT = { label: '你标的：buy = 这一天会买，no_buy = 像但这一天不会买',
    must: '只给 buy：它收的框和会话写的对应表比——= 必须有的都有、必须没有的都没有；−X 缺了必须有的 X；+Y 有了必须没有的 Y；order 必须有都在、先后和 app 不同。不是和 app 跑出来的结果比' + (app ? '' : '。还没有 app，这一列空着'),
    app: 'app 在这一天买没买；和 label 不一样就朱红，原因看那一格或那张缩略图的悬停' + (app ? '' : '。还没有 app，这一列空着'), sequence: '顶层成员的特征按先后排（套在里面的框不算）', n: '这一行几个买点' }
  h += `<div class="hdr">${sym('instances', (uns ? '还没归进 pattern 的买点' : '这个 pattern 的全部买点') + '：每列一样的折成一行；点缩略图在主图打开')}</div>`
  h += `<div class="vrow" style="${G};padding:0 8px">${sym('label', CT.label)}${uns ? sym('sequence', CT.sequence) : (app ? `<span>${seg('session', sym('must / must_not', CT.must))}</span><span>${seg('app', sym('app', CT.app))}</span>` : `<span class="vnil" title="${esc(CT.must)}">must / must_not</span><span class="vnil" title="${esc(CT.app)}">app</span>`)}<span></span></div>`
  for (const [, xs] of rows) {
    const x = xs[0]
    h += `<div class="blk"><div class="vrow" style="${G}">${sym(x.bp.label, CT.label)}${uns ? `<div class="chain">${chainOf(x)}</div>` : `<span>${vDifT(x)}</span><span>${!x.ap ? '' : x.bp.label === 'no_buy' ? seg('app', tag(x.ap, vRed(x) ? 'bad' : '', `app 在这一天${x.ap === 'buy' ? '买了' : '没买'}` + (vRed(x) ? '；和你的 label 对不上；会话下一轮会在单子里问（每一张的情形看它缩略图的悬停）' : ''))) : vAppT(x, false)}</span>`}${sym('×' + xs.length, CT.n)}</div>
      <div class="row" style="margin-top:4px;align-items:flex-end">${xs.map(x => vThumb(x, false)).join('')}<span class="grow"></span>${vMove(xs, uns || vDev(x))}</div></div>`
  }
  return h
}"""

# ── 变体 B：平铺、顺序稳定，数字是筛选 ──
VB = r"""  // ── 买点列表（变体 B「平铺 + 点数字筛」）：已命名 pattern 页不分组也不折叠，每个买点一张缩略图，按图序、日期排，顺序不随阶段变；
  // 缩略图下写股票和日期，有 app 时再挂 diff（会话浅蓝）、app（琥珀）两个签，label 看三角实心 / 空心。
  // 页头的计数、两个 app:buy 总数、features 区的 in k/N 和属性计数都可点：点了这里只看计进它的那几个（k/n 分「算进 / 没算进」两排），每排能整排挪走。
  // 未归类页：按顶层特征串聚一簇（这一页的决定就是「这一批归哪」），簇按特征串排、只差尾巴的挨着
  const vi = vInst()
  if (uns) {
    h += `<div class="hdr">${sym('instances', '还没归进 pattern 的买点：顶层特征串一样的聚一簇，按特征串排；对得上已有 pattern 的整簇一下挪过去')}</div>`
    for (const [, xs] of vBy(vi, x => x.sig).sort((p, q) => p[0].localeCompare(q[0]))) {
      const nb = xs.filter(x => x.bp.label === 'buy').length
      h += `<div class="blk"><div class="chain">${chainOf(xs[0])}</div><div class="row" style="margin-top:3px">${[nb && sym('buy ' + nb), xs.length - nb && sym('no_buy ' + (xs.length - nb))].filter(Boolean).join(' ')}<span class="grow"></span>${vMove(xs)}</div><div class="row" style="margin-top:4px">${xs.map(x => vThumb(x, false)).join('')}</div></div>`
    }
    return h
  }
  const on = S.vKey && vParts(S.vKey).some(p => p.xs.length) ? S.vKey : null
  h += `<div class="hdr" id="vlist">${sym('instances', '这个 pattern 的全部买点，按图序、日期排；点缩略图在主图打开。点上面任何一个数，这里只看计进它的那几个')}${on ? `${sym('·')}${btn('all ✕', false, 'vkey:', 'title="看全部"')}` : ''}</div>`
  h += on ? vStrips(on) : `<div class="row" style="align-items:flex-start">${vi.map(x => vThumb(x)).join('')}</div>`
  return h
}"""

# ── 变体 C：不放列表，数字就是入口 ──
VC = r"""  // ── 买点列表（变体 C「数字就是入口」）：已命名 pattern 页没有单独的列表。页头的计数、两个 app:buy 总数、features 区的 in k/N 和属性计数、
  // 两段之间的签（U35 原有）都可点，点了在那个数底下就地列出计进它的那几个（k/n 分「算进 / 没算进」两排），每排能整排挪走；再点收起，一次只开一个。
  // 未归类页：按顶层特征串一簇一行（这一页的决定就是「这一批归哪」），个数点开才列缩略图，挪走不用点开
  if (uns) {
    h += `<div class="hdr">${sym('instances', '还没归进 pattern 的买点：顶层特征串一样的一行，按特征串排；点个数列出缩略图；对得上已有 pattern 的一下挪过去')}</div>`
    for (const [sig, xs] of vBy(vInst(), x => x.sig).sort((p, q) => p[0].localeCompare(q[0]))) {
      const nb = xs.filter(x => x.bp.label === 'buy').length, key = 'seq|' + sig
      h += `<div class="blk"><div class="chain">${chainOf(xs[0])}</div><div class="row" style="margin-top:3px">${vDoor([nb && 'buy ' + nb, xs.length - nb && 'no_buy ' + (xs.length - nb)].filter(Boolean).join(' · '), key, `${xs.length} 个买点`)}<span class="grow"></span>${vMove(xs)}</div>${S.vKey === key ? vStrips(key, false) : ''}</div>`
    }
  }
  return h
}"""

ACT = """  else if (k === 'vkey') {           // 计数入口：再点一下同一个 = 收起 / 看全部
    S.vKey = !v || S.vKey === v ? null : v
    if (VAR === 'B' && S.vKey) setTimeout(() => { const e = document.getElementById('vlist'); if (e) e.scrollIntoView({ block: 'start' }) })
  }
"""

VARIANTS = {
    'variant_a_columns': ('A', VA, '变体 A「按来源分列」（第三版，按 critic 3.5 的六处改）：买点列表换成一张表，label / must / must_not / app 三列各管一个来源（未归类页是 label / sequence），所有列相同的折成一行 ×n；features 区的 in k/N 点开就地列出——回答「把三个来源分开标、保留折叠，用户要记的规则能少多少」'),
    'variant_b_flat': ('B', VB, '变体 B「平铺 + 点数字筛」：已命名页不分组不折叠，一个买点一张缩略图、顺序稳定、身上挂签；页头和 features 区的数字点了筛这份列表——回答「列表不再有结构、只做索引，找人靠数字，够不够」'),
    'variant_c_doors': ('C', VC, '变体 C「数字就是入口」：已命名页删掉列表，页头和 features 区的每个数字点开就地列出那几个——回答「不常驻列表、用到哪个数就在哪展开，够不够」'),
}

src = SRC.read_text()
G_START = '  // groups：全工具唯一的买点列表、也是 app:buy 唯一的落点，pattern 页总是出现。'
G_END = "  return h + blocks.join('')\n}"
s0, s1 = src.index(G_START), src.index(G_END) + len(G_END)
for name, (v, body, note) in VARIANTS.items():
    out = src[:s0] + body + src[s1:]
    out = sub(out, '<!doctype html>\n', f'<!doctype html>\n<!-- {note}。由 build_variants.py 从 mock_v3.html 复制，只改买点列表相关的几处（见该脚本文件头） -->\n')
    out = sub(out, '<script src="data.js"></script>', '<script src="../../2026-10-26_annotation-workflow-polish/repro/data.js"></script>')
    out = sub(out, '<title>标注界面 mock v3</title>', f'<title>买点列表变体 {v}</title>')
    out = sub(out, CSS_AT, CSS_AT + CSS)
    out = sub(out, "  if (k === 'cur') {\n", "  if (k === 'cur') {\n    S.vKey = null                    // 换 pattern 时收起点开的数（sim 第二轮任务 7：B 的筛选留到了别的 pattern）\n")
    out = sub(out, 'function sideSum() {\n', HELPERS.replace('__V__', v) + 'function sideSum() {\n')
    # 页头：instances 计数换成入口，后面加一行 app:buy 两个总数
    out = sub(out, """<div class="row">${sym('buy ' + buys.length, `${buys.length} 个标 buy（正例）`)}${sym('·')}${sym('no_buy ' + nobuys.length, `${nobuys.length} 个标 no_buy（像但不买）`)}</div>""",
              """<div class="row">${vh.inst}</div>${vInline('lab|buy')}${vInline('lab|no_buy')}${app ? `${kk('app:buy', 'app 在你标的买点那一天买没买，按你的 label 分开数；app 这一侧的结果（琥珀）')}<div class="row">${vh.app}</div>${vInline('app|buy')}${vInline('app|no_buy')}${VAR === 'A' ? '' : `${kk('diff', '你标 buy 的买点收的框，和会话写的对应表（必须有 / 必须没有）比；不是和 app 跑出来的结果比')}<div class="row">${vh.dif}</div>${vInline('dif|buy')}`}` : ''}""")
    out = sub(out, "    const NT = { answer:", "    const vh = vHead(app)\n    const NT = { answer:")
    # features 区：in k/N 与属性计数（B、C 可点，A 照旧）
    out = sub(out, "const inTxt = (k, n, t) => n && k < n ? sym(`in ${k}/${n}`, `${n} 个 buy 里有 ${k} 个的成员中有「${t}」（no_buy 不算）`) : ''",
              "const inTxt = (k, n, t) => n && k < n ? vDoor(`in ${k}/${n}`, 'feat|' + t, `${n} 个 buy 里有 ${k} 个的成员中有「${t}」（no_buy 不算）`) : ''")
    # diffTags 补 order（mock 原先只画 −X / +Y，order 的组头是空的，model 第 0 节第 8 条）
    # features 区点开的两排放到那个特征块的末尾（子内容之后），免得像是挨着的那个买点的东西（critic U-5）
    out = sub(out, "${inTxt(k(id), buys.length, txt(id))}</div>${attrs ? `<div class=\"l2\">${attrs}</div>` : ''}${kids}</div>`",
              "${inTxt(k(id), buys.length, txt(id))}</div>${attrs ? `<div class=\"l2\">${attrs}</div>` : ''}${kids}${vInline('feat|' + txt(id))}</div>`")
    out = sub(out, "${inTxt(k(c), buys.length, txt(c))}</div></div>`", "${inTxt(k(c), buys.length, txt(c))}</div>${vInline('feat|' + txt(c))}</div>`")
    out = sub(out, "${seg('app', run)}</div>${attrs ? `<div class=\"l2\">${attrs}</div>` : ''}${hang}</div>`", "${seg('app', run)}</div>${attrs ? `<div class=\"l2\">${attrs}</div>` : ''}${hang}${vInline('feat|' + t)}</div>`")
    out = sub(out, "${wi ? flagOf(wi) : ''}`)}</div></div>`", "${wi ? flagOf(wi) : ''}`)}</div>${vInline('feat|' + w)}</div>`")
    out = sub(out, "+<span class=\"biz\">${esc(t)}</span></span>`)].join(' ')",
              "+<span class=\"biz\">${esc(t)}</span></span>`), ...(d.order ? [tag('order', '', '必须有都在，但先后和 app 不同')] : [])].join(' ')")
    out = sub(out, "  else return\n  render()\n})\ndocument.addEventListener('mouseover'", ACT + "  else return\n  render()\n})\ndocument.addEventListener('mouseover'")
    (HERE / f'{name}.html').write_text(out)
    print(name, len(out.splitlines()))
