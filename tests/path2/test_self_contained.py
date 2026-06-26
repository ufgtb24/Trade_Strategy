"""CI 检查:path2/ 包零 import BreakoutStrategy。"""
from __future__ import annotations

import subprocess
from pathlib import Path


def test_no_breakoutstrategy_imports_in_path2():
    repo_root = Path(__file__).resolve().parents[2]
    path2_dir = repo_root / "path2"
    assert path2_dir.is_dir(), f"path2/ not found at {path2_dir}"

    result = subprocess.run(
        ["grep", "-r", "-l", "BreakoutStrategy", str(path2_dir)],
        capture_output=True, text=True
    )
    # grep 找到匹配返回 0;未找到返回 1
    assert result.returncode != 0, \
        f"path2/ contains BreakoutStrategy references:\n{result.stdout}"


def test_no_breakoutstrategy_imports_in_path2_apps():
    repo_root = Path(__file__).resolve().parents[2]
    apps_dir = repo_root / "path2_apps"
    if not apps_dir.is_dir():
        return  # apps 可选
    result = subprocess.run(
        ["grep", "-r", "-l", "BreakoutStrategy", str(apps_dir)],
        capture_output=True, text=True
    )
    assert result.returncode != 0, \
        f"path2_apps/ contains BreakoutStrategy references:\n{result.stdout}"
