"""两个启动脚本给前后端子进程的模式:正式脚本不管 shell 里留着什么,后端都按正式模式起;调试脚本按调试模式起。
前端也拿到启动时的模式(VITE_CHART_WORKFLOW_MODE),和后端报的对不上就在页顶报警。不真起进程。"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

from chart_workflow import debugroot, mode

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts" / "path2"
sys.path.insert(0, str(SCRIPTS))
import run_path2_web  # noqa: E402
import run_path2_web_debug  # noqa: E402


class _Done:
    """假子进程:一启动就已退出,serve 的等待循环立刻返回、关停时什么都不用做。"""
    pid = 0

    def poll(self):
        return 0


@pytest.fixture
def spawned(monkeypatch):
    calls: dict[str, dict] = {}

    def spawn(cmd, cwd, env=None):
        calls["frontend" if "npm" in cmd else "backend"] = dict(env)
        return _Done()
    monkeypatch.setattr(run_path2_web, "_spawn", spawn)
    monkeypatch.setattr(run_path2_web, "_free_port", lambda *a: None)
    monkeypatch.setattr(run_path2_web, "_ensure_frontend_deps", lambda *a: None)
    monkeypatch.setattr(run_path2_web, "_frontend_env", lambda: dict(os.environ))
    monkeypatch.setattr(run_path2_web.signal, "signal", lambda *a: None)    # 别改测试进程自己的信号处理
    return calls


@pytest.mark.parametrize("leftover", [mode.DEBUG, "garbage", None])
def test_formal_launcher_starts_formal_whatever_shell_says(spawned, monkeypatch, leftover):
    """shell 里留着 CHART_WORKFLOW_MODE=debug(或乱值、或没有):正式脚本起的后端一律是正式模式,前端也被告知正式模式。"""
    if leftover is None:
        monkeypatch.delenv(mode.ENV_VAR, raising=False)
    else:
        monkeypatch.setenv(mode.ENV_VAR, leftover)
    monkeypatch.setenv("VITE_CHART_WORKFLOW_MODE", mode.DEBUG)            # shell 里也留着前端的
    run_path2_web.main()
    assert spawned["backend"][mode.ENV_VAR] == "formal"
    assert spawned["frontend"]["VITE_CHART_WORKFLOW_MODE"] == "formal"
    assert spawned["frontend"]["VITE_API_BASE"].startswith("http://localhost:")
    monkeypatch.setenv(mode.ENV_VAR, "formal")
    assert mode.current() == mode.FORMAL                                   # 后端拿到的值就是正式模式


def test_debug_launcher_starts_debug(spawned, monkeypatch, tmp_path):
    monkeypatch.setenv(mode.ENV_VAR, mode.FORMAL)      # 先登记原值:脚本会改本进程的环境变量,测完要还原
    monkeypatch.setattr(debugroot, "ensure", lambda: tmp_path)             # 不建真调试账
    run_path2_web_debug.main()
    assert spawned["backend"][mode.ENV_VAR] == mode.DEBUG
    assert spawned["frontend"]["VITE_CHART_WORKFLOW_MODE"] == mode.DEBUG
