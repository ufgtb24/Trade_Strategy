"""票 03：e2e spec 不进 vue-tsc（tsconfig 只含 src、tests），有些 spec 又没实跑。这里静态核对它们用到的名字都还在：
window.__e2e.view 上取的 store 成员、locator 里的类名。只读。用法（worktree 根目录）：python e2e_static_check.py"""
import re
from pathlib import Path

ui = Path("path2_web_ui")
view = (ui / "src/stores/view.ts").read_text(encoding="utf-8")
ret = view[view.rindex("return {"):]
members = set(re.findall(r"[A-Za-z_]\w*", ret))
src_text = "\n".join(p.read_text(encoding="utf-8") for p in (ui / "src").rglob("*") if p.suffix in {".vue", ".ts", ".css"})
bad = 0
for spec in sorted((ui / "e2e").glob("*.spec.ts")):
    text = spec.read_text(encoding="utf-8")
    names = set(re.findall(r"\b(?:view\??|v)\.([A-Za-z_]\w*)", text))
    gone = sorted(n for n in names if n not in members)
    classes = set(re.findall(r"locator\(['\"`][^'\"`]*?\.((?:hit|level|funnel|attr)[\w-]*)", text))
    gone_cls = sorted(c for c in classes if c not in src_text)
    print(f"{spec.name}: store 成员 {len(names)}，类名 {len(classes)}" + (f"；不在 store 里：{gone}" if gone else "") + (f"；不在 src 里：{gone_cls}" if gone_cls else ""))
    bad += len(gone) + len(gone_cls)
print("未找到的名字合计", bad)
