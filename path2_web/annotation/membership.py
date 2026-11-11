"""框套框、成员框、骨架的参照实现:同一张图上的框和样本,算出框的归属、样本的成员框、骨架和成员链上的空槽。

这份参照的用处
--------------
会话读标注时用这里算出的结果,它必须和用户在界面上看到的一致。任何另写的实现(比如为了交互流畅在前端本地算)
都要逐例通过同一组带答案的例子 `tests/path2_web/fixtures/membership_examples.json`;那份文件是唯一的事实
来源,格式写在它的 about 里。
- Python:`tests/path2_web/test_annotation_membership.py` 逐例调用本模块;
- vitest:用 node 的 fs 读同一个文件(从 `path2_web_ui/tests/` 下是
  `../../tests/path2_web/fixtures/membership_examples.json`),照 about 里的约定把序号换成日期再逐例调用。

输入
----
- 框:状态里 `charts[].boxes` 的元素 {id, feature, start, end, attrs?, note?, detach?, attach?},只用到
  id、feature、start、end、detach、attach;
- 样本:状态里 `charts[].samples` 的元素 {id, date, pattern, judgment, members[], ...};
- days:这只股票的交易日,YYYY-MM-DD 升序,要覆盖用到的全部日期。它决定「隔了几根 K 线」。会话可以取
  `path2_web.data.read_bars(view_dataset_dir(cfg), symbol)` 的日期。

怎么比
------
- 一个日期在 days 里的序号 = days 里比它早的交易日有几个(在 days 里就是它的下标)。先后、包住、交叠、长短、
  GAP、NEAR 都按序号比:「隔 20 根」是 20 根 K 线,不是 20 天。
- 因果(框在样本日当天或之前结束)按日期字符串比 `end <= date`,与存储保存时的校验是同一条。
- 框的长度 = 终点序号 − 起点序号。框的先后:起点早的在前;同起点的,长的在前;再按编号(字符串比)。

框套框(归属)
--------------
在一组框里给每个框找它属于谁(一个样本的成员框;一张图上显示用的归属,组怎么取见「一张图上的框套框」):
1. 有 detach:不属于任何框;
2. 有 attach,且那个框在这组里、比它长、和它交叠(至少共用一根 K 线):属于那个框。
   attach 的框不在这组里,或拖框以后已经不比它长、不再交叠,这条 attach 不算数,照第 3 条;
3. 否则属于包住它的框里最短的那个;一样短取起点早的,再一样取编号小的;没有框包住它就不属于任何框。
「o 包住 b」= b 的起止都落在 o 里,且 o 比 b 长(没有容差,一样长的两个框互不包住)。
detach 和 attach 互斥,同一个框两个都有时报 MembershipInputError(code 为 attach_and_detach)。
所属的框一定更长,所以不会绕成环。

一张图上的框套框(chart_parents)
--------------------------------
界面上选中框时的 parent 一行、副图的子框轨标题、compare 里子框对子段,用的是整张图上的归属。它不是把全部
框当一组来找,而是按样本分范围:
- 一个框「被样本收着」= 它在某个样本存下的成员框里、还在这张图上、且在那个样本的样本日当天或之前结束
  (与读存下的成员框是同一条);
- 被样本收着的框:只在和它至少同被一个样本收着的框里找(照「框套框」的三条;attach 的框不在这个范围里,
  这条 attach 不算数);
- 没被任何样本收着的框:在整张图的全部框里找。
理由:同一张图上常有两个样本各画一个同特征的框(晚的那个样本需要更长的一段,另画一个到它的样本日为止),
短的在日期上必然被长的包住,但它们是两个样本各自的依据,不是「小的属于大的」。这样分范围,显示出来的归属
与成员框树(只在一个样本的成员框之间找)一致。被收着的框不到没被收着的框里找,是因为长的那个框在第二个
样本放下之前就已经画好了(待验证:用下来不顺再调)。

成员框推断(放下样本时的默认成员框)
------------------------------------
1. 候选只取在样本日当天或之前结束的框(因果);
2. 边界从样本日开始往前扩:候选框的终点序号 ≥ 边界 − GAP 就并进来,边界随之更新为成员框里最早的起点,
   循环到没有新增;
3. 再带上被成员框包住的框、attach 到成员框上的框。这一步不用单独做:这样的框和某个成员框交叠,终点不早于
   那个成员框的起点,也就不早于边界,第 2 步停下时已经收进来了。attach 照「框套框」第 2 条,不算数的
   attach 不带进来;detach 只管属不属于外框,不管是不是成员框。

成员框随后怎么变(sample_members)
----------------------------------
- 新放的样本(还没有存下的成员框):成员框 = 推断结果;
- 已有成员框的样本:存下的成员框就是冻结的那份。它是「当前样本」期间新画的框(new_boxes),推断会收的
  就并进来,只加不踢;不是当前样本时 new_boxes 为空,成员框不变;
- 手动点进点出(manual:框编号 → true 收进 / false 拿掉)最后生效,永远算数;
- 最后只留在这张图上、且在样本日当天或之前结束的框:跨过样本日的框手动也收不进。
存下的成员框也照最后这条读(两台机器的修改合在一起,可能让存下的成员框越过样本日):空槽用的就是这样读出的
成员框。

骨架与 dup
----------
成员框按上面的归属排成树,顶层是不属于任何其他成员框的框;骨架 = 顶层框的特征编号按先后排,子框和属性
不进骨架;还没标特征的框(feature 为 null)记 None。顶层有两段以上是同一特征时,这个特征记进 dup
(没标特征的不算)。

成员链上的空槽(empty_slots)
----------------------------
满足这三条的框在样本的成员链上留一个空槽:在这只股票上;它的特征在同一 pattern 的样本(unsorted 的样本
自成一组)的成员框里出现过;既不是这个样本的成员框,也不是同一张图上同一 pattern 别的样本的成员框。
按原因分两种:
- unclaimed(画了没收):在样本日当天或之前结束,终点序号 ≥ 样本范围起点 − NEAR。样本范围起点 = 样本日
  和成员框起点里最早的那个。这种框可以收进;
- crosses_sample_date(跨过样本日收不进):起点不晚于样本日、终点晚于样本日。
整段在样本日之后的框、离得比 NEAR 远的框不留空槽。

GAP、NEAR 的默认值只在本模块设定;界面本地推断时读的是标注路由带出的同一对值(GET /annotations 的 membership)。
例子文件自带它算答案用的值,改默认值不用改例子。
本模块不读行情、不读写标注文件,只做纯计算。
"""
from __future__ import annotations

from bisect import bisect_left
from collections.abc import Iterable, Sequence
from dataclasses import dataclass

GAP = 20    # 暂定值,待验证:从样本日往前,前后两段之间空几根 K 线以内仍算连着(样本到第一个框、框到框同一个数)
NEAR = 40   # 暂定值,待验证:样本范围起点往前几根以内没收进的框,算「画了没收」

UNCLAIMED = "unclaimed"
CROSSES_SAMPLE_DATE = "crosses_sample_date"


class MembershipInputError(ValueError):
    """输入不合规。code:attach_and_detach(同一个框既 detach 又 attach)、unknown_chart、unknown_sample。"""

    def __init__(self, code: str, message: str):
        self.code = code
        super().__init__(message)


@dataclass(frozen=True)
class _Box:
    """换算好序号的框。start / end 是日期(比因果),s / e 是起点、终点的序号(比先后、长短、间隔)。"""
    id: str
    feature: str | None
    start: str
    end: str
    s: int
    e: int
    attach: str | None
    detach: bool

    @property
    def length(self) -> int:
        """长度:终点序号 − 起点序号。"""
        return self.e - self.s

    @property
    def order(self) -> tuple:
        """框的先后:起点早的在前,同起点长的在前,再按编号。"""
        return self.s, -self.e, self.id

    def overlaps(self, other: _Box) -> bool:
        """和 other 至少共用一根 K 线。"""
        return self.s <= other.e and other.s <= self.e

    def contains(self, other: _Box) -> bool:
        """包住 other:other 的起止都落在自己里面,且自己更长。"""
        return self.s <= other.s and other.e <= self.e and self.length > other.length


# ---------------------------------------------------------------- 公开函数

def parents(boxes: Sequence[dict], days: Sequence[str]) -> dict[str, str | None]:
    """框套框:每个框属于这组框里的哪个框(框编号 → 所属框编号,不属于任何框为 None)。规则见模块说明「框套框」。"""
    pool = _pool(boxes, days)
    return {bid: _parent(b, pool) for bid, b in pool.items()}


def chart_parents(boxes: Sequence[dict], samples: Sequence[dict], days: Sequence[str]) -> dict[str, str | None]:
    """一张图上显示用的框套框(框编号 → 所属框编号或 None):被样本收着的框只在和它同被一个样本收着的框里找,
    没被任何样本收着的框在整张图的框里找。规则见模块说明「一张图上的框套框」。"""
    pool = _pool(boxes, days)
    held: dict[str, set[int]] = {}
    for i, s in enumerate(samples):
        for b in _current_member_boxes(s, boxes):
            held.setdefault(b["id"], set()).add(i)
    out: dict[str, str | None] = {}
    for bid, b in pool.items():
        mine = held.get(bid)
        scope = pool if not mine else {oid: o for oid, o in pool.items() if oid == bid or held.get(oid, set()) & mine}
        out[bid] = _parent(b, scope)
    return out


def sample_members(date: str, boxes: Sequence[dict], days: Sequence[str], *,
                   stored: Sequence[str] | None = None, new_boxes: Iterable[str] = (),
                   manual: dict[str, bool] | None = None, gap: int = GAP) -> list[str]:
    """一个样本现在的成员框编号,按框的先后排。规则见模块说明「成员框推断」「成员框随后怎么变」。

    date:样本日;boxes:这只股票上的全部框;stored:存下的成员框(None 表示新放的样本);
    new_boxes:它是当前样本期间新画的框;manual:手动点进点出,框编号 → true / false;gap:默认读 GAP。
    """
    pool = _pool(boxes, days)
    auto = _infer(date, pool, days, gap)
    chosen = set(auto) if stored is None else set(stored) | (auto & set(new_boxes))
    for bid, keep in (manual or {}).items():
        if keep:
            chosen.add(bid)
        else:
            chosen.discard(bid)
    return [b.id for b in _ordered(pool.values()) if b.id in chosen and b.end <= date]


def member_tree(members: Iterable[str], boxes: Sequence[dict], days: Sequence[str]) -> list[dict]:
    """成员框按框套框排成树:[{box: 框编号, kids: [同样的结点]}],顶层和每层子框都按框的先后排。
    归属只在成员框之间找;不在 boxes 里的编号不计。"""
    wanted = set(members)
    pool = _pool([b for b in boxes if b["id"] in wanted], days)
    kids: dict[str | None, list[_Box]] = {}
    for b in _ordered(pool.values()):
        kids.setdefault(_parent(b, pool), []).append(b)

    def node(b: _Box) -> dict:
        return {"box": b.id, "kids": [node(k) for k in kids.get(b.id, [])]}

    return [node(b) for b in kids.get(None, [])]


def skeleton(members: Iterable[str], boxes: Sequence[dict], days: Sequence[str]) -> list[str | None]:
    """骨架:成员框树顶层框的特征编号按先后排(还没标特征的为 None);子框和属性不进骨架。"""
    feature = _features(boxes)
    return [feature[n["box"]] for n in member_tree(members, boxes, days)]


def dup_features(members: Iterable[str], boxes: Sequence[dict], days: Sequence[str]) -> list[str]:
    """成员框树顶层出现两次以上的特征编号,按第一次出现的先后排;还没标特征的不算。"""
    tops = skeleton(members, boxes, days)
    return [f for i, f in enumerate(tops) if f is not None and tops.index(f) == i and tops.count(f) > 1]


def empty_slots(charts: Sequence[dict], symbol: str, sample_id: str, days: Sequence[str],
                near: int = NEAR) -> list[dict]:
    """一个样本成员链上的空槽:[{box, feature, reason}],reason 为 unclaimed 或 crosses_sample_date,按框的先后排。
    规则见模块说明「成员链上的空槽」。

    charts:状态里的 charts(要看全部图,才知道特征在这个 pattern 里出现过没有);symbol、sample_id:哪张图的
    哪个样本;days:这张图的交易日;near:默认读 NEAR。成员框取样本存下的 members(照「成员框随后怎么变」
    最后一条读),不重算推断。找不到这张图或这个样本 → MembershipInputError(unknown_chart / unknown_sample)。
    """
    chart = next((c for c in charts if c["symbol"] == symbol), None)
    if chart is None:
        raise MembershipInputError("unknown_chart", f"没有 {symbol} 这张图")
    sample = next((s for s in chart["samples"] if s["id"] == sample_id), None)
    if sample is None:
        raise MembershipInputError("unknown_sample", f"{symbol} 上没有样本 {sample_id}")
    pattern, date = sample["pattern"], sample["date"]
    used = {b["feature"] for c in charts for s in c["samples"] if s["pattern"] == pattern
            for b in _current_member_boxes(s, c["boxes"])} - {None}
    others = {b["id"] for s in chart["samples"] if s["id"] != sample_id and s["pattern"] == pattern
              for b in _current_member_boxes(s, chart["boxes"])}
    mine = {b["id"] for b in _current_member_boxes(sample, chart["boxes"])}
    pool = _pool(chart["boxes"], days)
    range_start = min([_rank(days, date)] + [pool[bid].s for bid in mine])
    out = []
    for b in _ordered(pool.values()):
        if b.id in mine or b.id in others or b.feature not in used:
            continue
        if b.end > date:
            if b.start > date:
                continue
            reason = CROSSES_SAMPLE_DATE
        elif b.e >= range_start - near:
            reason = UNCLAIMED
        else:
            continue
        out.append({"box": b.id, "feature": b.feature, "reason": reason})
    return out


# ---------------------------------------------------------------- 内部

def _rank(days: Sequence[str], date: str) -> int:
    """日期的序号:days 里比它早的交易日有几个。"""
    return bisect_left(days, date)


def _features(boxes: Sequence[dict]) -> dict[str, str | None]:
    """框编号 → 特征编号。"""
    return {b["id"]: b["feature"] for b in boxes}


def _current_member_boxes(sample: dict, boxes: Sequence[dict]) -> list[dict]:
    """样本存下的成员框里,还在这张图上、且在样本日当天或之前结束的那些框。"""
    by_id = {b["id"]: b for b in boxes}
    return [by_id[m] for m in sample["members"] if m in by_id and by_id[m]["end"] <= sample["date"]]


def _pool(boxes: Sequence[dict], days: Sequence[str]) -> dict[str, _Box]:
    """框编号 → 换算好序号的框;同一个框既 detach 又 attach → MembershipInputError。"""
    out = {}
    for b in boxes:
        if b.get("detach") and b.get("attach") is not None:
            raise MembershipInputError("attach_and_detach", f"框 {b['id']} 既 detach 又 attach,两者互斥")
        out[b["id"]] = _Box(b["id"], b["feature"], b["start"], b["end"], _rank(days, b["start"]),
                            _rank(days, b["end"]), b.get("attach"), bool(b.get("detach")))
    return out


def _ordered(boxes: Iterable[_Box]) -> list[_Box]:
    """按框的先后排。"""
    return sorted(boxes, key=lambda b: b.order)


def _parent(b: _Box, pool: dict[str, _Box]) -> str | None:
    """b 在 pool 里属于哪个框(模块说明「框套框」的三条)。"""
    if b.detach:
        return None
    o = pool.get(b.attach) if b.attach is not None else None
    if o is not None and o.length > b.length and o.overlaps(b):
        return o.id
    containers = [o for o in pool.values() if o.contains(b)]
    return min(containers, key=lambda o: (o.length, o.s, o.id)).id if containers else None


def _infer(date: str, pool: dict[str, _Box], days: Sequence[str], gap: int) -> set[str]:
    """成员框推断(模块说明「成员框推断」):返回推断出的成员框编号。"""
    candidates = [b for b in pool.values() if b.end <= date]
    members: set[str] = set()
    edge = _rank(days, date)
    while True:
        joined = [b for b in candidates if b.id not in members and b.e >= edge - gap]
        if not joined:
            return members
        members.update(b.id for b in joined)
        edge = min(b.s for b in candidates if b.id in members)
