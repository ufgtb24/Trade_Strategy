# -*- coding: utf-8 -*-
"""多维稳健区 v2 · app 接入端:apps/<APP>/study.py → apps/<APP>/classification.json。

本模块只提供 app 接入端的**模块级函数**,不再有 main()/MODE——调用面统一在 tune.py:
  tune.setup(app)   生成 classification.json(原 MODE="build")
  tune.status(app)  报告分类表是否过期(原 MODE="check")
  tune.retire(app)  退役清理(原 MODE="delete")
"""
from __future__ import annotations

import subprocess, sys
from pathlib import Path

REPO = Path(subprocess.check_output(["git", "rev-parse", "--show-toplevel"], text=True).strip())
sys.path.insert(0, str(REPO)); sys.path.insert(0, str(REPO / ".claude/skills/tune-gates"))
import study_io as S  # noqa: E402


def plan_delete(app: str, apps_dir, repo, delete_notes: bool = False,
                delete_exposure: bool = False) -> dict:
    """构造删除清单。**只走精确路径,绝不按 app 名 glob。**

    为什么不 glob:实测按名字模糊匹配会误伤 6 项、同时漏 3 项——真实存在的
    2026-08-20_tune-bb-v1 用连字符命名会被漏掉,而误伤最重的一项是把整个
    2026-08-25_multivar-bb_v1 研究目录连报告一起删。全 repo grep -rIl bb_v1
    命中 161 个文件,绝大多数是包名与历史文档。

    分组(误删=数据永久丢失、误留=多几个文件,代价不对称,所以默认偏保留):
      must    —— study.py / run.py / classification.json / __pycache__:纯配置与派生物,进 git 可找回
      confirm —— notes.md / exposure.jsonl(仅在显式开关打开时进这里):跨轮沉淀,默认保留
      keep    —— 默认保留的那些,列出来让人看见放弃了什么
      blocked —— 不可再生的重产物:只报不删

    **已知后果(有意的保守侧行为,不是 bug)**:重产物要不要落 confirm 走的是
    `check_regenerable`(见其链 5),而链 5 需要 `import_app` 成功。app 本身已经坏掉时
    (底座 yaml 缺失、拓扑改崩等)import 会失败,`_regenerable` 把这类异常也判成不可再生,
    于是该 app 名下**全部**重产物都落进 blocked——"app 坏了也要能清理"这句话因此只兑现
    了一半:配置(study.py/run.py/classification.json,must 组不依赖 import_app)能清,
    但真正占磁盘的重产物一份都清不掉。要清重产物,得先让 app 能正常 import(或接受
    blocked 里报的原因、手动确认后再删)。

    本函数**不删任何东西**,只返回清单。
    """
    apps_dir, repo = Path(apps_dir), Path(repo)
    app_dir = apps_dir / app
    must, confirm, keep, blocked = [], [], [], []

    if not app_dir.is_dir():
        raise SystemExit(f"{app_dir} 不存在:没有这个 app 可退役")

    for name, why in (("study.py", "app 的搜索空间声明,app 退役即无意义;进 git 可 git checkout 找回"),
                      ("run.py", "run 级常量,app 退役即无意义;进 git 可 git checkout 找回"),
                      ("classification.json", "study.py 的派生物;进 git 可找回"),
                      ("__pycache__", "字节码缓存")):
        p = app_dir / name
        if p.exists():
            must.append({"path": str(p), "why": why})

    for name, flag, why in (
            ("notes.md", delete_notes,
             "跨轮实测沉淀(踩过的坑/校准记录),意义不随 app 消失;通用区仍有多处'案例见'指向它"),
            ("exposure.jsonl", delete_exposure,
             "识别端运行审计日志,记的是对这批数据看过几次;同名 app 重建后底层数据仍是同一批")):
        p = app_dir / name
        if not p.exists():
            continue
        entry = {"path": str(p), "why": why}
        if name == "exposure.jsonl":
            entry["why"] += f"(当前 {sum(1 for _ in p.open(encoding='utf-8'))} 条记录,删除后不可恢复)"
        (confirm if flag else keep).append(entry)

    out_root = repo / "outputs" / "tune_gates" / app
    if out_root.is_dir():
        for sub in sorted(p for p in out_root.iterdir() if p.is_dir()):
            # 删除单元是整个 sub(一次 run 的产物目录),不是只 longtable/:同级的
            # random_baseline.csv / filtered_symbols.csv 是 multivar_scan 断点续跑 done 集
            # 的一部分(见 multivar_scan.py 的 done 集三来源),只删 longtable/ 会让重跑时
            # 这批股票仍被判"已完成"、产出空长表——"删了要重跑"这句话本身就要求删除单元
            # 与"重跑"的 resume 状态是一致的一整份。可再生性判定仍然对含 run_meta.json 的
            # 那一层做(longtable/ 存在则查它,否则查 sub 本身),但删除目标固定是 sub。
            lt = sub / "longtable"
            check_target = lt if lt.is_dir() else sub
            ok, why = _regenerable(check_target, apps_dir)
            if ok:
                confirm.append({"path": str(sub), "why": "重产物,当前代码可再生;删了要重跑"})
            else:
                blocked.append({"path": str(sub), "why": "不可再生,只报不删:" + "; ".join(why)})

    return {"must": must, "confirm": confirm, "keep": keep, "blocked": blocked}


def _regenerable(target, apps_dir):
    """薄封装:目录里没有 run_meta.json 时一律判不可再生(归属不明,只报不删)。

    apps_dir 必须显式透传——测试在 tmp_path 假树上跑,用默认 APPS_DIR 会去核对真实的
    apps/ 目录,让测试结果依赖真实仓库状态。
    """
    try:
        return S.check_regenerable(target, apps_dir=apps_dir)
    except Exception as e:                      # noqa: BLE001 —— 检测本身失败也归入"不可再生"侧
        return False, [f"可再生性检测异常({e.__class__.__name__}: {e}),按不可再生处理"]


def _worktree_dirty(app_dir: Path) -> str:
    """查 app_dir 下有没有未提交改动(含未跟踪文件)。返回 `git status --porcelain -uall .`
    的原始输出——空字符串即干净。这是 delete 分支唯一的安全闸,从 main() 抽出来是为了让它
    能被单独测试(评审 I-4:这段逻辑经历过三轮修复,每一轮都是评审读代码读出来的,没有回归钉)。

    锚点必须是"即将被删的那些文件所在的位置"(app_dir),不能是 S.REPO:S.REPO 由**进程
    cwd** 推(study_io.py 里 git rev-parse --show-toplevel 没有任何 chdir),cwd=S.REPO
    查的其实还是 cwd 所在的那个仓库,和不传 cwd 是同一件事——真正的错配来自 S.APPS_DIR
    由 __file__ 推,它可能根本不在 cwd 所在的仓库里(多 worktree 下常见:从主仓库目录去跑
    某个 worktree 里的这份脚本)。用 `git -C app_dir` 让 git 自己从 app 目录出发去发现
    它属于哪个仓库,查的就是真正要删的那批文件,不受调用者 cwd 影响。

    -uall 必须显式给:这道闸就是靠未跟踪文件的 `??` 兜底的(新建未 commit 的 app、
    exposure.jsonl 这类文件全是未跟踪状态),而 `status.showUntrackedFiles=no` 这个
    git config(用户级/全局/系统级都可能被设上)会让默认的 status --porcelain 对着一整
    目录的未跟踪内容空输出+rc=0,和"干净"完全分不出来——实测过:不加 -uall 时该 config
    下确实是空输出;加了 -uall 后同一目录正确报出 `??`。这不是可选优化,删掉这个 flag
    会让 must 组"进 git 可找回"的前提在这类 config 下失效。

    returncode 也必须检查:git 查不出来(非 0)绝不能被当成"没有改动",
    那与"判不了 ≠ 可再生"是同一条安全原则,故直接 SystemExit,不返回一个"看似干净"的值。
    """
    import subprocess as sp
    r = sp.run(["git", "-C", str(app_dir), "status", "--porcelain", "-uall", "."],
               capture_output=True, text=True)
    if r.returncode != 0:
        raise SystemExit(f"git status 失败,拒绝删除(查不了 ≠ 干净):{r.stderr.strip()}")
    return r.stdout.strip()


def _execute_delete(plan: dict, app_dir: Path, confirm: bool) -> None:
    """delete 分支的执行段:dirty 闸 → CONFIRM dry-run → 真删 → 清空目录。从 main() 抽出来
    是为了让唯一会毁数据的这条路径可测(评审 I-4);逐字保留原 main() 里的行为与打印文案,
    只是把 `S.APPS_DIR / APP` 换成参数 `app_dir`(同一个值,main() 里算一次传进来)。
    """
    dirty = _worktree_dirty(app_dir)
    if dirty:
        print(f"\n⚠ {app_dir} 下有未提交改动——这是 app 目录里 git 唯一兜不住的部分:\n{dirty}")
    if not confirm:
        print("\nCONFIRM=False:以上为 dry-run,未删除任何文件。确认无误后把 CONFIRM 改成 True 再跑。")
        return
    if dirty:
        raise SystemExit(f"拒绝删除:{app_dir} 下有未提交改动,先提交或还原后再删")
    import shutil
    to_delete = plan["must"] + plan["confirm"]
    done = []
    try:
        for x in to_delete:
            p = Path(x["path"])
            if p.is_dir():
                shutil.rmtree(p)
            else:
                p.unlink()
            done.append(x["path"]); print(f"已删除 {p}")
    except Exception:
        # 中途失败:已删的回不去,但至少把"删到哪儿了"报清楚——不告诉人删到哪是最难收拾的情况
        remaining = [x["path"] for x in to_delete if x["path"] not in done]
        print(f"\n⚠ 删除中途失败:已删除 {len(done)} 项,以下 {len(remaining)} 项未删:")
        for pth in remaining:
            print(f"  {pth}")
        raise
    left = list(app_dir.iterdir()) if app_dir.is_dir() else []
    if not left:
        app_dir.rmdir(); print(f"已删除空目录 {app_dir}")
