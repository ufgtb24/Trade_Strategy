"""同时启动 path2_web 前后端(开发态)。

    uv run python scripts/run_path2_web.py

- 后端: uvicorn(path2_web.app),默认 127.0.0.1:8000
- 前端: vite dev server(path2_web_ui),默认 127.0.0.1:5173(--strictPort 禁止自动换端口)

端口可在 configs/path2_web.yaml 的 backend_port / frontend_port 修改;
多 worktree 并行开发时,各 worktree 在工作树里改 yaml(不 commit)即可不互杀。
前端调后端的 VITE_API_BASE 由本脚本据 backend_port 自动派生并注入 vite 子进程。

启动前会"清场":若目标端口已被占用(通常是本工具的残留实例),直接终止
占用者(连其进程组),不换端口、不复用,确保每次都是干净的重启。

两个进程并行运行,任一退出或按 Ctrl+C 时一并优雅关停。
参数在 main() 顶部声明(无 argparse,遵循入口规范)。
"""
from __future__ import annotations

import os
import re
import shutil
import signal
import subprocess
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
MIN_NODE_MAJOR = 18  # vite 要求 node >=18(见 path2_web_ui/node_modules/vite engines)


def _node_major(node_bin: str) -> int | None:
    """返回 node 二进制的主版本号,失败返回 None。"""
    try:
        out = subprocess.run([node_bin, "-v"], capture_output=True, text=True, timeout=5)
    except (OSError, subprocess.SubprocessError):
        return None
    m = re.match(r"v(\d+)\.", out.stdout.strip())
    return int(m.group(1)) if m else None


def _frontend_env() -> dict[str, str]:
    """返回前端子进程的环境:确保 PATH 里有一个 >=MIN_NODE_MAJOR 的 node。

    从 IDE 启动时通常没加载 nvm 初始化,PATH 只剩系统老 node;此处主动
    探测当前 PATH,不满足则回退到 nvm 已安装的最高合格版本并 prepend。
    """
    env = os.environ.copy()
    cur = shutil.which("node")
    if cur and (_node_major(cur) or 0) >= MIN_NODE_MAJOR:
        return env  # 当前 PATH 已够新,直接用

    candidates: list[tuple[int, Path]] = []
    for bin_dir in sorted((Path.home() / ".nvm" / "versions" / "node").glob("*/bin")):
        major = _node_major(str(bin_dir / "node"))
        if major and major >= MIN_NODE_MAJOR:
            candidates.append((major, bin_dir))
    if not candidates:
        raise SystemExit(
            f"[run_path2_web] 未找到 node >= v{MIN_NODE_MAJOR};"
            f"当前 node={cur or '无'}。请安装/激活合适的 node(如 nvm use 22)。"
        )
    best = max(candidates)[1]
    print(f"[run_path2_web] 当前 PATH 的 node 过旧,改用 {best}")
    env["PATH"] = f"{best}{os.pathsep}{env.get('PATH', '')}"
    return env


def _ensure_frontend_deps(frontend_dir: Path) -> None:
    """sentinel = node_modules/.bin/vite 是否存在;缺失则 npm ci 装一遍。

    新 worktree 首次启动场景:git worktree add 不复制 node_modules(.gitignore 排除)。
    简单版:只看 vite 二进制是否存在,不查 package-lock.json 是否变。
    """
    sentinel = frontend_dir / "node_modules" / ".bin" / "vite"
    if sentinel.exists():
        return
    print(f"[run_path2_web] 未检测到 {sentinel},跑 npm ci 装依赖(首次或新 worktree)...")
    subprocess.run(["npm", "ci"], cwd=str(frontend_dir), env=_frontend_env(), check=True)


def _pids_on_port(port: int) -> set[int]:
    """返回正在 <port> 上 LISTEN 的进程 PID 集合(本机可见者)。"""
    try:
        out = subprocess.run(["ss", "-ltnp"], capture_output=True, text=True, timeout=5)
    except (OSError, subprocess.SubprocessError):
        return set()
    pids: set[int] = set()
    for line in out.stdout.splitlines():
        parts = line.split()
        # 列: State Recv-Q Send-Q Local-Address:Port Peer-Address:Port Process
        if len(parts) >= 4 and parts[3].rsplit(":", 1)[-1] == str(port):
            pids |= {int(m) for m in re.findall(r"pid=(\d+)", line)}
    return pids


def _signal_pids(pids: set[int], sig: int) -> None:
    """给一组 PID 发信号:优先按进程组(连带其 fork 的子进程),失败回退单进程。"""
    my_pgid = os.getpgrp()
    handled_pgids: set[int] = set()
    for pid in sorted(pids):
        try:
            pgid = os.getpgid(pid)
        except ProcessLookupError:
            continue
        if pgid == my_pgid:
            # 与本进程同组:避免 killpg 误伤自己,只杀该 pid
            try:
                os.kill(pid, sig)
            except ProcessLookupError:
                pass
            continue
        if pgid in handled_pgids:
            continue
        handled_pgids.add(pgid)
        try:
            os.killpg(pgid, sig)
        except ProcessLookupError:
            pass
        except PermissionError:  # 无权杀整组(非己进程),退回单进程
            try:
                os.kill(pid, sig)
            except OSError:
                pass


def _free_port(port: int, label: str) -> None:
    """启动前清场:若 <port> 被占用,终止占用者(连进程组)并等待端口释放。

    符合"检测到已在运行就统统关闭、不绕开、再重启"的预期:不换端口、不复用。
    先 SIGTERM 优雅终止,超时再 SIGKILL;仍无法释放则报错退出而非静默继续。
    """
    pids = _pids_on_port(port)
    if not pids:
        return
    print(f"[run_path2_web] {label} 端口 {port} 已被占用(pid={sorted(pids)}),终止占用者...")
    _signal_pids(pids, signal.SIGTERM)
    for _ in range(16):  # 最多约 8s 等待优雅退出
        time.sleep(0.5)
        if not _pids_on_port(port):
            print(f"[run_path2_web] 端口 {port} 已释放。")
            return
    remaining = _pids_on_port(port)
    if remaining:
        print(f"[run_path2_web] 端口 {port} 仍被占(pid={sorted(remaining)}),强制 SIGKILL。")
        _signal_pids(remaining, signal.SIGKILL)
        time.sleep(1.0)
    if _pids_on_port(port):
        raise SystemExit(f"[run_path2_web] 无法释放端口 {port},请手动检查后重试。")


def _spawn(cmd: list[str], cwd: Path, env: dict[str, str] | None = None) -> subprocess.Popen:
    """在独立进程组中启动子进程,便于整组终止(vite 会再 fork 子进程)。"""
    return subprocess.Popen(cmd, cwd=str(cwd), start_new_session=True, env=env)


def _terminate(proc: subprocess.Popen) -> None:
    """向整个进程组发 SIGTERM,超时则 SIGKILL。"""
    if proc.poll() is not None:
        return
    try:
        os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
    except ProcessLookupError:
        return
    try:
        proc.wait(timeout=8)
    except subprocess.TimeoutExpired:
        os.killpg(os.getpgid(proc.pid), signal.SIGKILL)


def main() -> None:
    # ===== 参数(在此处直接改) =====
    from path2_web.config import load_config
    cfg = load_config()
    BACKEND_PORT = int(cfg["backend_port"])   # 改端口请改 configs/path2_web.yaml
    FRONTEND_PORT = int(cfg["frontend_port"])  # 通过 --port 传给 vite,--strictPort 禁止自动换端口
    BACKEND_CMD = ["uv", "run", "python", "-m", "path2_web.main"]
    FRONTEND_CMD = ["npm", "run", "dev", "--", "--port", str(FRONTEND_PORT), "--strictPort"]
    FRONTEND_DIR = REPO / "path2_web_ui"
    # ================================

    # 启动前清场:检测到端口已被占用(通常是本工具的残留实例)就统统关闭,不绕开
    _free_port(BACKEND_PORT, "backend")
    _free_port(FRONTEND_PORT, "frontend")

    _ensure_frontend_deps(FRONTEND_DIR)

    procs: list[tuple[str, subprocess.Popen]] = []
    print(f"[run_path2_web] 启动后端: {' '.join(BACKEND_CMD)}")
    procs.append(("backend", _spawn(BACKEND_CMD, REPO)))
    print(f"[run_path2_web] 启动前端: {' '.join(FRONTEND_CMD)} (cwd={FRONTEND_DIR})")
    frontend_env = _frontend_env()
    frontend_env["VITE_API_BASE"] = f"http://localhost:{BACKEND_PORT}"
    procs.append(("frontend", _spawn(FRONTEND_CMD, FRONTEND_DIR, env=frontend_env)))

    # 统一接管 SIGINT(Ctrl+C)/SIGTERM(kill、timeout):首次触发即把两者都
    # 设为忽略,确保随后的清理段不会被第二次信号(PyCharm 停止键常连发)打断。
    def _on_signal(*_args) -> None:
        signal.signal(signal.SIGINT, signal.SIG_IGN)
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
        raise KeyboardInterrupt
    signal.signal(signal.SIGINT, _on_signal)
    signal.signal(signal.SIGTERM, _on_signal)

    print("[run_path2_web] 前后端已启动,按 Ctrl+C 退出。")
    try:
        while True:
            for name, proc in procs:
                code = proc.poll()
                if code is not None:
                    print(f"[run_path2_web] {name} 进程已退出(code={code}),关停其余进程。")
                    return
            time.sleep(0.5)
    except KeyboardInterrupt:
        print("\n[run_path2_web] 收到中断信号,正在关停...")
    finally:
        # 进入清理前再次确保信号被忽略(覆盖 return 路径与竞态窗口)
        signal.signal(signal.SIGINT, signal.SIG_IGN)
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
        for name, proc in procs:
            _terminate(proc)
        print("[run_path2_web] 已全部关停。")


if __name__ == "__main__":
    main()
