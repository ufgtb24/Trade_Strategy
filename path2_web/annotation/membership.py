"""框套框、样本成员、骨架的参照实现:同一张图上的框、样本,算出界面上看到的归属、成员、骨架和空槽。

为什么有这份参照
----------------
界面(前端)为了交互流畅在本地算这些量,会话读标注时用这里的 Python 版。两边必须给出同一个答案:用户在界面上
看到的成员、归属、骨架,就是会话读到的。所以两边过同一组带答案的例子,例子是唯一的事实来源:
`tests/path2_web/fixtures/membership_examples.json`(格式写在它的 about 里)。
- Python:`tests/path2_web/test_annotation_membership.py` 逐例调用本模块;
- vitest:用 node 的 fs 读同一个文件(从 `path2_web_ui/tests/` 下是 `../../tests/path2_web/fixtures/membership_examples.json`),
  照 about 里的约定把序号换成日期,逐例调前端的实现。

输入
----
- 框:状态里 `charts[].boxes` 的元素 {id, feature, start, end, attrs?, note?, detach?, attach?},只用到
  id、feature、start、end、detach、attach;
- 样本:状态里 `charts[].samples` 的元素 {id, date, pattern, judgment, members[], ...};
- days:这只股票的交易日,YYYY-MM-DD 升序。它决定「隔了几根 K 线」。界面用图上那份 K 线的日期;会话用
  `path2_web.data.read_bars(view_dataset_dir(cfg), symbol)` 的日期。必须覆盖用到的全部日期。

怎么比
------
- 一个日期在 days 里的序号 = days 里比它早的交易日有几个(在 days 里就是它的下标)。先后、包住、交叠、长短、
  GAP、NEAR 都按序号比:「隔 20 根」是 20 根 K 线,不是 20 天。
- 因果(框在样本日当天或之前结束)按日期字符串比 `end <= date`,与存储保存时的校验是同一条。
- 框的长度 = 终点序号 − 起点序号。框的先后:起点早的在前;同起点的,长的在前;再按编号(字符串比)。

框套框(归属)
--------------
在一组框里给每个框找它属于谁(全图的框用来分子框轨;一个样本的成员用来排成员链、算骨架):
1. 有 detach:不属于任何框;
2. 有 attach,且那个框在这组里、比它长、和它有交叠(至少共用一根 K 线):属于那个框。
   attach 的框不在这组里,或拖框以后已经不比它长、不再交叠,这条 attach 不算数,照第 3 条;
3. 否则属于包住它的框里最短的那个;一样短取起点早的,再一样取编号小的;没有框包住它就不属于任何框。
「o 包住 b」= b 的起止都落在 o 里,且 o 比 b 长(没有容差,一样长的两个框互不包住)。
detach 和 attach 互斥,同一个框两个都有时报 MembershipInputError(code 为 attach_and_detach)。
所属的框一定更长,所以不会绕成环。

成员推断(放下样本时的默认成员)
--------------------------------
1. 候选只取在样本日当天或之前结束的框(因果);
2. 边界从样本日开始往前扩:候选框的终点序号 ≥ 边界 − GAP 就并进来,边界随之更新为成员里最早的起点,
   循环到没有新增;
3. spec 的第 3 步(带上被成员包住的框、attach 到成员上的框)在第 2 步停下时已经满足:这样的框和某个成员
   交叠,终点不早于那个成员的起点,也就不早于边界,第 2 步已经收进来了。detach 只管属不属于外框,
   不管是不是成员。

成员随后怎么变(sample_members)
--------------------------------
- 新放的样本(还没有存下的成员):成员 = 推断结果;
- 已有成员的样本:存下的成员就是冻结的那份。它是「当前样本」期间新画的框(new_boxes),推断会收的就并进来,
  只加不踢;不是当前样本时 new_boxes 为空,成员不变;
- 手动点进点出(manual:框编号 → true 收进 / false 拿掉)最后生效,永远算数;
- 最后滤掉不在这张图上的框和跨过样本日的框:跨过样本日的框手动也收不进。

骨架与 dup
----------
成员按上面的归属排成树,顶层是不属于任何其他成员的框;骨架 = 顶层框的特征编号按先后排,子框和属性不进骨架;
没起名的框记 None。顶层有两段以上同一特征时,这个特征记进 dup(没起名的不算)。

空槽(empty_slots)
------------------
样本的成员链上留空槽的框:这只股票上、特征在同一 pattern(unsorted 自成一组)的样本成员里用过、
不是这个样本的成员、也不是同一张图上同一 pattern 别的样本的成员的框,按原因分两种:
- unclaimed(画了没收):在样本日当天或之前结束,终点序号 ≥ 样本范围起点 − NEAR。
  样本范围起点 = 样本日和成员起点里最早的那个。界面上挂 ◂,点一下收进;
- crosses_sample_date(跨过样本日收不进):起点不晚于样本日、终点晚于样本日。界面上悬停写明原因。

GAP、NEAR 只在本模块设定,别处都读这两个常数;例子文件自带它算答案用的值,改默认值不用改例子。
本模块不读行情、不读写标注文件,只做纯计算。
"""
from __future__ import annotations

from bisect import bisect_left
from collections.abc import Iterable, Sequence
from dataclasses import dataclass

GAP = 20    # 待验证(V-01-1):从样本日往前,前后两段之间空几根 K 线以内仍算连着(样本到第一个框、框到框同一个数)
NEAR = 40   # 待验证(V-01-1):样本范围起点往前几根以内没收进的框,算「画了没收」

UNCLAIMED = "unclaimed"
CROSSES_SAMPLE_DATE = "crosses_sample_date"


class MembershipInputError(ValueError):
    """输入不合规。code:attach_and_detach(同一个框既 detach 又 attach)、unknown_chart、unknown_sample。"""

    def __init__(self, code: str, message: str):
        self.code = code
        super().__init__(message)


@dataclass(frozen=True)
class _Box:
    """换算好序号的框。start / end 是日期(比因果),s / e 是序号(比先后、长短、间隔)。"""
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
        return self.e - self.s

    @property
    def order(self) -> tuple:
        """框的先后:起点早的在前,同起点长的在前,再按编号。"""
        return self.s, -self.e, self.id


# ---------------------------------------------------------------- 公开函数

def parents(boxes: Sequence[dict], days: Sequence[str]) -> dict[str, str | None]:
    """框套框:每个框属于这组框里的哪个框(框编号 → 所属框编号,不属于任何框为 None)。规则见模块说明「框套框」。"""
    pool = _pool(boxes, days)
    return {bid: _parent(b, pool) for bid, b in pool.items()}


def sample_members(date: str, boxes: Sequence[dict], days: Sequence[str], *,
                   stored: Sequence[str] | None = None, new_boxes: Iterable[str] = (),
                   manual: dict[str, bool] | None = None, gap: int = GAP) -> list[str]:
    """一个样本现在的成员框编号,按框的先后排。规则见模块说明「成员推断」「成员随后怎么变」。

    date:样本日;boxes:这只股票上的全部框;stored:存下的成员(None 表示新放的样本);
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
    """成员按框套框排成树:[{box: 框编号, kids: [同样的结点]}],顶层和每层子框都按框的先后排。
    归属只在成员之间找;不在 boxes 里的成员编号不计。"""
    wanted = set(members)
    pool = _pool([b for b in boxes if b["id"] in wanted], days)
    kids: dict[str | None, list[_Box]] = {}
    for b in _ordered(pool.values()):
        kids.setdefault(_parent(b, pool), []).append(b)

    def node(b: _Box) -> dict:
        return {"box": b.id, "kids": [node(k) for k in kids.get(b.id, [])]}

    return [node(b) for b in kids.get(None, [])]


def skeleton(members: Iterable[str], boxes: Sequence[dict], days: Sequence[str]) -> list[str | None]:
    """骨架:成员树顶层框的特征编号按先后排(没起名的为 None);子框和属性不进骨架。"""
    feature = {b["id"]: b["feature"] for b in boxes}
    return [feature[n["box"]] for n in member_tree(members, boxes, days)]


def dup_features(members: Iterable[str], boxes: Sequence[dict], days: Sequence[str]) -> list[str]:
    """成员树顶层出现两次以上的特征编号,按第一次出现的先后排;没起名的不算。"""
    tops = skeleton(members, boxes, days)
    return [f for i, f in enumerate(tops) if f is not None and tops.index(f) == i and tops.count(f) > 1]


def empty_slots(charts: Sequence[dict], symbol: str, sample_id: str, days: Sequence[str],
                near: int = NEAR) -> list[dict]:
    """一个样本成员链上的空槽:[{box, feature, reason}],reason 为 unclaimed 或 crosses_sample_date,按框的先后排。
    规则见模块说明「空槽」。

    charts:状态里的 charts(要看全部图,才知道特征在这个 pattern 里用过没有);symbol、sample_id:哪张图的
    哪个样本;days:这张图的交易日;near:默认读 NEAR。成员用样本存下的 members,不重算推断。
    找不到这张图或这个样本 → MembershipInputError(unknown_chart / unknown_sample)。
    """
    chart = next((c for c in charts if c["symbol"] == symbol), None)
    if chart is None:
        raise MembershipInputError("unknown_chart", f"没有 {symbol} 这张图")
    sample = next((x for x in chart["samples"] if x["id"] == sample_id), None)
    if sample is None:
        raise MembershipInputError("unknown_sample", f"{symbol} 上没有样本 {sample_id}")
    pattern, date = sample["pattern"], sample["date"]
    used = set()
    for c in charts:
        feature = {b["id"]: b["feature"] for b in c["boxes"]}
        for x in c["samples"]:
            if x["pattern"] == pattern:
                used |= {feature.get(m) for m in x["members"]}
    used.discard(None)
    others = {m for x in chart["samples"] if x["id"] != sample_id and x["pattern"] == pattern for m in x["members"]}
    mine = set(sample["members"])
    pool = _pool(chart["boxes"], days)
    start = min([_rank(days, date)] + [b.s for b in pool.values() if b.id in mine])
    out = []
    for b in _ordered(pool.values()):
        if b.id in mine or b.id in others or b.feature not in used:
            continue
        if b.end > date:
            if b.start > date:
                continue
            reason = CROSSES_SAMPLE_DATE
        elif b.e >= start - near:
            reason = UNCLAIMED
        else:
            continue
        out.append({"box": b.id, "feature": b.feature, "reason": reason})
    return out


# ---------------------------------------------------------------- 内部

def _rank(days: Sequence[str], date: str) -> int:
    """日期的序号:days 里比它早的交易日有几个。"""
    return bisect_left(days, date)


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


def _contains(o: _Box, b: _Box) -> bool:
    """o 包住 b:b 的起止都落在 o 里,且 o 更长。"""
    return o.s <= b.s and b.e <= o.e and o.length > b.length


def _parent(b: _Box, pool: dict[str, _Box]) -> str | None:
    """b 在 pool 里属于哪个框(模块说明「框套框」的三条)。"""
    if b.detach:
        return None
    o = pool.get(b.attach) if b.attach is not None else None
    if o is not None and o.length > b.length and o.s <= b.e and b.s <= o.e:
        return o.id
    containers = [o for o in pool.values() if _contains(o, b)]
    return min(containers, key=lambda o: (o.length, o.s, o.id)).id if containers else None


def _infer(date: str, pool: dict[str, _Box], days: Sequence[str], gap: int) -> set[str]:
    """成员推断(模块说明「成员推断」):返回推断出的成员框编号。"""
    candidates = [b for b in pool.values() if b.end <= date]
    members: set[str] = set()
    edge = _rank(days, date)
    while True:
        joined = [b for b in candidates if b.id not in members and b.e >= edge - gap]
        if not joined:
            return members
        members.update(b.id for b in joined)
        edge = min(b.s for b in candidates if b.id in members)
