"""R7: (a) 单流 detector 上 run() 与 run_bundle()[None] 是否逐事件等价 + 校验强度是否变;
     (b) engine.py:171 的 `produces_stream not in bundle` 是否可达(NodeSpec 构造期已挡)。"""
from dataclasses import dataclass
from typing import ClassVar
from path2 import config
from path2.core import Event
from path2.dag.nodes import NodeSpec
from path2.runner import run, run_bundle

config.set_runtime_checks(True)

@dataclass(frozen=True)
class E1(Event):
    is_point: ClassVar[bool] = True

class Single:
    event_cls = E1
    def detect(self, df):
        for i in (1, 2, 3):
            yield E1(start_idx=i, end_idx=i, confirm_idx=i)

class BadOrder:
    event_cls = E1
    def detect(self, df):
        yield E1(start_idx=5, end_idx=5, confirm_idx=5)
        yield E1(start_idx=1, end_idx=1, confirm_idx=1)

class DupObj:
    event_cls = E1
    def detect(self, df):
        e = E1(start_idx=1, end_idx=1, confirm_idx=1)
        yield e
        yield E1(start_idx=1, end_idx=1, confirm_idx=1)

d = Single()
a = [(e.start_idx, e.end_idx) for e in run(d, None)]
b = [(e.start_idx, e.end_idx) for e in run_bundle(d, None)[None]]
print("(a) 单流逐事件等价:", a == b, a)
for cls in (BadOrder, DupObj):
    for fn, nm in ((lambda x: list(run(x, None)), "run"), (lambda x: run_bundle(x, None), "run_bundle")):
        try:
            fn(cls()); print(f"    {cls.__name__}/{nm}: 未抛 ← 校验缺失")
        except Exception as e:
            print(f"    {cls.__name__}/{nm}: {type(e).__name__}: {str(e)[:60]}")

# (b) NodeSpec 构造期是否已挡住未声明流名
class Two:
    produces: ClassVar[dict] = {"a": E1, "b": E1}
    def detect(self, df):
        yield ("a", E1(start_idx=1, end_idx=1, confirm_idx=1))
try:
    NodeSpec("x", Two(), produces_stream="zzz")
    print("(b) NodeSpec 接受未声明流名 ← engine:171 可达")
except ValueError as e:
    print("(b) NodeSpec 构造期拒绝:", str(e)[:70], "→ engine:171 在正常契约下不可达")

# (b') 唯一漏洞:produces 在 NodeSpec 构造后被改
t = Two()
n = NodeSpec("x", t, produces_stream="b")
t.produces = {"a": E1}          # 实例属性遮蔽 ClassVar
print("(b') 构造后改 produces → run_bundle 键集:", set(run_bundle(t, None)),
      "| node 要的流:", n.produces_stream, "→ engine:171 此时可达")
