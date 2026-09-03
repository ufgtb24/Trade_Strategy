"""worker 数上限实测：对 `tune.scan` 与 `tune.compare` 扫 WORKERS，
同时记录 wall 时间与进程树峰值内存，找出「加核不再变快」与「内存吃不消」两条边界。

**跑法**：`uv run python .claude/skills/tune-gates/bench_workers.py`。每个 WORKERS 值起一个
子进程，以 `-c` 代码串直接调 `tune.scan(APP, window='bench', workers=W, ...)` /
`tune.compare(...)`，不复制脚本、不改写源码——旧版靠正则改写常量行,唯一存在理由是
「参数只能写死在 main() 里」，该前提已不成立。

**内存口径 = PSS（Proportional Set Size）而不是 RSS**：进程池是 fork 出来的，父子之间
大量页是写时复制共享的，把每个进程的 RSS 直接相加会把共享页重复计数、严重高估。PSS 把
每个共享页按共享它的进程数均摊，进程树的 PSS 之和才是这棵树真实占用的物理内存。
读 `/proc/<pid>/smaps_rollup`，不可用时退回 `VmRSS`（会高估，输出里标注）。

**输出落点**：`SCRATCH` 只装内存采样这一份 bench 自身的记录（当前仅供人肉观察 stdout，
不落盘）；`tune.scan(window='bench')` 的扫描产物（parquet 分片 + run_meta.json）写进
`outputs/tune_gates/<app>/bench/`，**不进 scratchpad**——这是 `tune.out_dir_of` 的全局
目录约定，本文件不改它。scan 轮之间要清的正是这个真实输出目录（断点续跑：残留分片会让
下一轮「已完成」而秒退），因此每轮 scan 前清理的是它，不是 SCRATCH。
"""
import os
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

REPO = Path(subprocess.check_output(["git", "rev-parse", "--show-toplevel"], text=True).strip())


def _proc_kb(pid: int) -> tuple[int, bool]:
    """返回 (该进程内存 KB, 是否为 PSS 口径)。smaps_rollup 不可读时退回 VmRSS。"""
    try:
        with open(f"/proc/{pid}/smaps_rollup") as f:
            for line in f:
                if line.startswith("Pss:"):
                    return int(line.split()[1]), True
    except (OSError, ValueError):
        pass
    try:
        with open(f"/proc/{pid}/status") as f:
            for line in f:
                if line.startswith("VmRSS:"):
                    return int(line.split()[1]), False
    except (OSError, ValueError):
        pass
    return 0, True


def _tree_pids(root: int) -> list[int]:
    """root 及其全部后代 pid（读 /proc/<pid>/stat 的 ppid 字段自底向上聚合）。"""
    kids: dict[int, list[int]] = {}
    for entry in os.listdir("/proc"):
        if not entry.isdigit():
            continue
        try:
            with open(f"/proc/{entry}/stat") as f:
                data = f.read()
            ppid = int(data[data.rindex(")") + 2:].split()[1])
        except (OSError, ValueError, IndexError):
            continue
        kids.setdefault(ppid, []).append(int(entry))
    out, stack = [], [root]
    while stack:
        pid = stack.pop()
        out.append(pid)
        stack.extend(kids.get(pid, []))
    return out


class PeakSampler(threading.Thread):
    """后台采样进程树内存峰值。"""

    def __init__(self, root_pid: int, interval: float):
        super().__init__(daemon=True)
        self.root, self.interval = root_pid, interval
        self.peak_kb, self.pss_ok, self.n_peak_proc = 0, True, 0
        self._halt = threading.Event()   # 不能叫 _stop:Thread 基类已有同名方法

    def run(self):
        while not self._halt.is_set():
            total, ok, n = 0, True, 0
            for pid in _tree_pids(self.root):
                kb, is_pss = _proc_kb(pid)
                if kb:
                    total += kb
                    n += 1
                ok &= is_pss
            if total > self.peak_kb:
                self.peak_kb, self.n_peak_proc = total, n
            self.pss_ok &= ok
            self._halt.wait(self.interval)

    def stop(self):
        self._halt.set()
        self.join(timeout=5)


def _run_one_code(code: str, workers: int, interval: float) -> dict:
    """跑一次并采样。返回 wall / 峰值内存 / 脚本自报的末行。"""
    t0 = time.time()
    proc = subprocess.Popen([sys.executable, "-c", code], cwd=REPO,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    sampler = PeakSampler(proc.pid, interval)
    sampler.start()
    out, _ = proc.communicate()
    sampler.stop()
    wall = time.time() - t0
    tail = [ln for ln in out.strip().splitlines() if ln.strip()]
    return dict(workers=workers, wall=wall, peak_mb=sampler.peak_kb / 1024, pss=sampler.pss_ok,
                n_proc=sampler.n_peak_proc, rc=proc.returncode, last=tail[-1] if tail else "(无输出)",
                out=out)


def main():
    # ---- 实验参数 ----
    APP = "bb_v1"                      # 定标用哪个 app 的真实数据
    WORKER_GRID = [4, 8, 12, 16, 20, 24, 26]
    SAMPLE_SEC = 0.4
    TICKER_REGEX = r"^A[A-C]"          # 108 只：W=26 时每 worker 仍有 ~4 个任务，避免尾部效应主导
    SCRATCH = Path(os.environ.get("CLAUDE_SCRATCH", "/tmp")) / "bench_workers"
    # ──────────────────
    SCRATCH.mkdir(parents=True, exist_ok=True)
    scan_out_dir = REPO / "outputs" / "tune_gates" / APP / "bench"   # 与 tune.out_dir_of(APP, "bench") 等价
    print(f"scratch={SCRATCH}\nscan 输出目录(每轮清理)={scan_out_dir}\n"
          f"股票正则={TICKER_REGEX} · WORKERS 网格={WORKER_GRID} · 采样间隔={SAMPLE_SEC}s\n", flush=True)

    # 不再复制脚本、不再改写源码:直接起子进程调 tune 的函数,参数走命令行传给 -c。
    # 那套正则改写的唯一存在理由是「参数只能写死在 main() 里」,该前提已不成立。
    def _cmd(call: str) -> str:
        return (f"import sys; sys.path.insert(0, {str(REPO / '.claude/skills/tune-gates')!r}); "
                f"import tune; {call}")

    for name in ("scan", "compare"):
        print(f"===== {name} =====", flush=True)
        rows = []
        for w in WORKER_GRID:
            if name == "scan":
                # 每轮重来：扫描是断点续跑的，残留分片会让后续轮次「已完成」而秒退。
                # compare 轮不删——它读的是 scan 轮最后一次留下的扫描结果(含 run_meta.json)
                shutil.rmtree(scan_out_dir, ignore_errors=True)
                call = (f"tune.scan({APP!r}, window='bench', workers={w}, "
                        f"ticker_regex={TICKER_REGEX!r})")
            else:
                call = (f"tune.compare({APP!r}, window='bench', workers={w}, "
                        f"cmp_ticker_regex={TICKER_REGEX!r})")
            r = _run_one_code(_cmd(call), w, SAMPLE_SEC)
            rows.append(r)
            flag = "" if r["rc"] == 0 else f"  ⚠ rc={r['rc']}"
            print(f"  W={w:>2}  wall {r['wall']:7.1f}s  峰值 {r['peak_mb']:7.0f} MB"
                  f"({'PSS' if r['pss'] else 'RSS,高估'}, {r['n_proc']} 进程){flag}", flush=True)
            if r["rc"] != 0:
                print("    " + "\n    ".join(r["out"].strip().splitlines()[-6:]), flush=True)

        ok = [r for r in rows if r["rc"] == 0]
        if not ok:
            print("  (全部失败,跳过汇总)\n", flush=True)
            continue
        base = min(ok, key=lambda r: r["workers"])
        print(f"\n  相对 W={base['workers']} 的加速比与内存:")
        for r in ok:
            dw = r["workers"] - base["workers"]
            per_w = (r["peak_mb"] - base["peak_mb"]) / dw if dw else float("nan")
            print(f"    W={r['workers']:>2}  {base['wall'] / r['wall']:5.2f}×  "
                  f"峰值 {r['peak_mb']:6.0f} MB  每多一 worker 约 {per_w:6.1f} MB", flush=True)
        best = min(ok, key=lambda r: r["wall"])
        print(f"  最快 = W={best['workers']}（{best['wall']:.1f}s，峰值 {best['peak_mb']:.0f} MB）\n", flush=True)


if __name__ == "__main__":
    main()
