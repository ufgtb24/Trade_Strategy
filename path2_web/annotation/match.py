"""compare 对照的判法与容差(`.scratch/annotation-path2/spec.md` 第 10 节「match 容差」「认出」、6.13「状态判法」)。

容差(共用常数,只在这里设定一处):
- POS_TOL / NEG_TOL:sample 与 hit 比较时,hit 的买点离样本日几根以内算 matched;
- SUB_TOL:认出时子框对子段,子段终点离子框终点几根以内算对上(框本身按框终点那天精确取,不用容差)。
界面(`path2_web_ui/src/annotate/compareRead.ts` 的 matchOf、pairOn)读的是标注路由带出的同一组值
(GET /annotations 的 match)。

反馈状态(feedback_status、is_red):唯一实现在这里。后端的反馈状态接口与会话的改版报告都调它,界面只照接口给的
状态与朱红与否画、排,不另写一套判法。页面上只显示 matched / unmatched 两种(shown_status 把 lost 并进
unmatched),原因标签挂不挂由 shown_tag 判;三态只留给会话。一条反馈收进来的 hit(feedback_hits)和记号变朱红
同一口径;前端选中一条反馈时牵出的 hit(path2_web_ui/src/annotate/feedback.ts 的 feedbackHits)照它写,两边逐例
通过同一份例子文件 `tests/path2_web/fixtures/reference_examples.json`。

整族反馈按基准 node 认「同一次形状」(spec 6.13「状态判法」;词条见 path2/GLOSSARY.md 的 reference node):
反馈记录的 reference = {node, spans} 是写反馈时这一族各 hit 的基准 event 起止;当前 app 的基准 event 与其中一段
共用至少一根 K 线,就是同一次形状。日期都是交易日,两段日期有交集即共用 K 线。只比日期,不认是哪种走势。

样本 match(sample_match):有两份实现——前端 compareRead.ts 的 matchOf(画图用)和这里(给会话的改版报告用),
两份逐例通过同一份例子文件 `tests/path2_web/fixtures/match_examples.json`,答案只写在那份文件里。

三者的买点日都按 app 的 eval_meta 声明的买点 node 取(每个买点事件跨度里的每一根,见 path2_web/app_run.py 的
app_buys、前端 render/fold.ts 的 buyDaysOf),所以「样本日落在买点 node 那段事件里」已包含在「离样本日 0 根」里。
只比日期,不认任何具体 node 名或事件类型。
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Mapping, Optional, Sequence

# 会话账本里「定义改过」的原因标签:挂了它的 matched 反馈不再算朱红(spec 6.14)。标签取值只在
# path2_web/mapping.py(mapping 会话段的格式)写一处,这里引用同一个常量。
from path2_web.mapping import TAG_REDEFINED

if TYPE_CHECKING:
    from path2_web.app_run import AppBuys

POS_TOL = 3   # 暂定值,待用户在第一批真实标注后定:正样本,买点离样本日几根以内算 matched
NEG_TOL = 1   # 暂定值,同上:负样本
SUB_TOL = 2   # 暂定值,同上:子框终点与子段终点相差几根以内算对上

FEEDBACK_TARGETS = ("point", "family", "range")


def _overlaps(a: Sequence, b: Sequence) -> bool:
    """两段日期 (start, end) 有没有共用的 K 线(两端都含;日期都是交易日)。"""
    return a[0] <= b[1] and b[0] <= a[1]


def _stored_spans(fb: Mapping, buys: "AppBuys") -> Optional[list]:
    """整族反馈存下的基准 event 起止;认不了时为 None:不是 family、没存 reference、或它存的基准 node 不是
    取 buys 时用的那个(mapping 现在声明的;没声明时 buys.reference 为 None,一样认不了)。"""
    ref = fb.get("reference") if fb.get("target") == "family" else None
    if not ref or buys.reference is None or ref.get("node") != buys.reference:
        return None
    return list(ref.get("spans") or ())


def same_shape_hits(fb: Mapping, buys: "AppBuys") -> list[int]:
    """整族反馈的同一次形状上还在买的 hit(buys.hits 里的下标):基准 event 与存下的某一段共用 K 线、而且在买
    (买点日不论在哪)。逐个 hit 判,不按族合并起止;认不了存下的起止时(_stored_spans 为 None)为空。"""
    spans = _stored_spans(fb, buys)
    if not spans:
        return []
    return [i for i, h in enumerate(buys.hits)
            if h.buy_days and any(_overlaps(a, b) for a in h.spans for b in spans)]


def feedback_hits(fb: Mapping, buys: "AppBuys") -> list[int]:
    """一条反馈收进来的 hit(buys.hits 里的下标,即 res.hits 的先后;选中这条反馈时它牵出的 hit):
    买点日落在 [start, end] 里的 hit,不论哪一族;整族反馈另加同一次形状上还在买的 hit(same_shape_hits)。
    旧 round 文件读出的 buys 没有 hits,结果为空。"""
    start, end = fb["start"], fb["end"]
    shape = set(same_shape_hits(fb, buys))
    return [i for i, h in enumerate(buys.hits) if i in shape or any(start <= d <= end for d in h.buy_days)]


def feedback_status(fb: Mapping, buys: "AppBuys") -> str:
    """一条反馈在当前 app 下的状态:'matched'(app 仍在买,朱红)/ 'unmatched'(常色)/ 'lost'(第三态)。

    参数:fb 是重放出的反馈记录(用到 target、start、end,family 另用 reference);buys 是这只股票上
    当前 app 的买点(path2_web/app_run.py 的 AppBuys,带着取它时 mapping 声明的基准 node)。

    - point / range:[start, end] 内有买点日 → matched,否则 unmatched;
    - family(逐个 hit 判,不按族合并起止):
      1. [start, end] 内有买点日 → matched(不看基准);
      2. 认不了存下的起止(没存 reference、或存的基准 node 不是 mapping 现在声明的)→ lost;
      3. 有 hit 的基准 event 与存下的某一段共用 K 线、而且这个 hit 在买(买点日不论在哪)→ matched;
      4. 存下的至少一段,当前 app 有与它共用 K 线的基准 event(不论档位、不论在不在 hit 里)→ unmatched;
      5. 其余(每一段都没有共用 K 线的基准 event)→ lost。
      lost = 基准 node 对不上:可能真改好了,也可能同一次形状挪远了还在买,由会话在改版报告里逐条交代;
      不退回按 family_start 对。
    target 不认得 → ValueError。
    """
    target = fb["target"]
    if target not in FEEDBACK_TARGETS:
        raise ValueError(f"反馈 target 不认得: {target!r}")
    start, end = fb["start"], fb["end"]
    if any(start <= d <= end for d in buys.buy_days):
        return "matched"
    if target != "family":
        return "unmatched"
    spans = _stored_spans(fb, buys)
    if not spans:
        return "lost"
    if same_shape_hits(fb, buys):
        return "matched"
    if any(_overlaps(a, b) for a in buys.ref_spans for b in spans):
        return "unmatched"
    return "lost"


def shown_status(status: Optional[str]) -> Optional[str]:
    """页面上显示的反馈状态:只有 matched(app 还在这里买)/ unmatched(不买了)/ None(读不到行情)。
    lost 并进 unmatched:「基准 node 对不上」要懂机制才看得懂,对用户来说就是不买了;它是真改好了还是认法变了,
    由会话在改版报告里逐条交代。会话这边(改版报告、摘要)照旧用 feedback_status 的三态。"""
    return "unmatched" if status == "lost" else status


def shown_tag(status: Optional[str], tag: Optional[str]) -> Optional[str]:
    """页面上这条反馈挂不挂会话写的原因标签:状态是 matched 或 lost 才挂(status 是 feedback_status 的三态,
    不是 shown_status 的结果)。lost 而会话挂了标签的,是「认法变了、原来的毛病还在」:页面上显示成 unmatched
    加原因标签,看得出还没改好。挂不挂只在这里判一次,页面三处(面板、侧栏、图上记号的悬停)照着写。"""
    return tag if status in ("matched", "lost") else None


def is_red(status: Optional[str], tag: Optional[str]) -> bool:
    """这条反馈画不画朱红:状态 matched,且会话没给它挂「定义改过」的原因标签。朱红与否只在这里判一次。"""
    return status == "matched" and tag != TAG_REDEFINED


def sample_match(date: str, judgment: str, buy_days: Sequence[str], dates: Sequence[str],
                 tol: Optional[Mapping[str, int]] = None) -> str:
    """一个样本在一组买点日下的 match:'matched' / 'unmatched'(前端 compareRead.ts 的 matchOf 的 Python 版)。

    参数:date 是样本日;judgment 是 'pos' / 'neg';buy_days 是这只股票上 app 的全部买点日;dates 是窗口内全部
    交易日(升序,距离按 K 线根数算,不按自然日);tol 是 {pos, neg} 容差,省略时取本模块的 POS_TOL / NEG_TOL。
    有一个买点日离样本日不超过容差根数 → matched。样本日不是 dates 里的交易日 → unmatched(界面上那天也
    画不出样本);不在 dates 里的买点日不算。
    """
    if judgment not in ("pos", "neg"):
        raise ValueError(f"样本 judgment 不认得: {judgment!r}")
    t = tol if tol is not None else {"pos": POS_TOL, "neg": NEG_TOL}
    lim = t[judgment]
    idx = {d: i for i, d in enumerate(dates)}
    day = idx.get(date)
    if day is None:
        return "unmatched"
    for b in buy_days:
        i = idx.get(b)
        if i is not None and abs(i - day) <= lim:
            return "matched"
    return "unmatched"
