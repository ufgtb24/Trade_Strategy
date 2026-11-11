"""compare 对照的判法与容差(`.scratch/annotation-path2/spec.md` 第 10 节「match 容差」「认出」、6.13「状态判法」)。

容差(共用常数,只在这里设定一处):
- POS_TOL / NEG_TOL:sample 与 hit 比较时,hit 的买点离样本日几根以内算 matched;
- SUB_TOL:认出时子框对子段,子段终点离子框终点几根以内算对上(框本身按框终点那天精确取,不用容差)。
界面(`path2_web_ui/src/annotate/compareRead.ts` 的 matchOf、pairOn)读的是标注路由带出的同一组值
(GET /annotations 的 match)。

反馈状态(feedback_status、is_red):唯一实现在这里。后端的反馈状态接口与会话的改版报告都调它,界面只照接口给的
状态与朱红与否画、排,不另写一套判法。页面上只显示 matched / unmatched 两种(shown_status 把 lost 并进
unmatched),原因标签挂不挂由 shown_tag 判;三态只留给会话。

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


def feedback_status(fb: Mapping, buys: "AppBuys") -> str:
    """一条反馈在当前 app 下的状态:'matched'(app 仍在买,朱红)/ 'unmatched'(常色)/ 'lost'(第三态)。

    参数:fb 是重放出的反馈记录(用到 target、start、end,family 另用 family_start);buys 是这只股票上
    当前 app 的买点(path2_web/app_run.py 的 AppBuys)。

    - point / range:[start, end] 内有买点日 → matched,否则 unmatched;
    - family:[start, end] 内有买点日,或起于 family_start 的那一族 hit 还有买点日(买点日不论在哪)→ matched;
      两样都没有、而且参与求解的 node 连一个起于 family_start 的事件(不论档位)都没有 → lost(起点认不出:
      改好了,或认法变了,由会话逐条交代);其余 unmatched。
    只看日期,不看是哪一族的买点。target 不认得、family 缺 family_start → ValueError。
    """
    target = fb["target"]
    if target not in FEEDBACK_TARGETS:
        raise ValueError(f"反馈 target 不认得: {target!r}")
    start, end = fb["start"], fb["end"]
    if any(start <= d <= end for d in buys.buy_days):
        return "matched"
    if target != "family":
        return "unmatched"
    fs = fb.get("family_start")
    if not fs:
        raise ValueError(f"family 反馈缺 family_start: {fb.get('id')!r}")
    if buys.families.get(fs):
        return "matched"
    return "unmatched" if fs in buys.event_starts else "lost"


def shown_status(status: Optional[str]) -> Optional[str]:
    """页面上显示的反馈状态:只有 matched(app 还在这里买)/ unmatched(不买了)/ None(读不到行情)。
    lost 并进 unmatched:「起点认不出」要懂机制才看得懂,对用户来说就是不买了;它是真改好了还是认法变了,
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
