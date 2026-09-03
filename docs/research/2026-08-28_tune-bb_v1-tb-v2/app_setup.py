# -*- coding: utf-8 -*-
"""多维稳健区 v2 · app 接入端:apps/<APP>/study.py → apps/<APP>/classification.json。
用法:复制到研究目录、填 APP、选 MODE 后 `uv run python <路径>/app_setup.py`(无 argparse)。

MODE="build":跑 classify + 全部静态守卫 + 推导 + 三指纹 → 写 classification.json,打印分类表。幂等。
MODE="check":只算指纹不写文件,打印三行报告(source / base / study 各一行)+ 上次生成时间。
             报告是给用户看的证据;要不要重生成由用户裁定(协议见 SKILL.md「入口协议」),本脚本不替用户决定。
"""
from __future__ import annotations

import subprocess, sys
from pathlib import Path

REPO = Path(subprocess.check_output(["git", "rev-parse", "--show-toplevel"], text=True).strip())
sys.path.insert(0, str(REPO)); sys.path.insert(0, str(REPO / ".claude/skills/tune-gates"))
import study_io as S  # noqa: E402


def main() -> None:
    APP = "bb_v1"
    MODE = "check"        # "build" | "check"

    S.require(APP, "APP")
    study_path = S.APPS_DIR / APP / "study.py"
    if not study_path.exists():
        raise SystemExit(f"{study_path} 不存在:cp -r {S.APPS_DIR / '_template'} {S.APPS_DIR / APP} 后填 8 项声明")
    study = S.load_study(study_path); mod = S.import_app(study)
    from path2 import config
    config.set_runtime_checks(True)
    if MODE == "build":
        cl = S.build_classification(APP, study, mod, study_path)
        p = S.write_classification(APP, cl)
        print(f"写入 {p}")
        print("参数分类:"); [print(f"  {d:32s} {k}") for d, k in cl["kinds"].items()]
        print("过滤型字段:", cl["filter_fields"]); print("where 字段:", cl["where_fields"])
        print(f"end_node={cl['end_node']} bound_nodes={cl['bound_nodes']} 检测组合数={cl['detection_combos']}")
        print("源码指纹范围:", cl["fingerprints"]["source"]["files"])
    elif MODE == "check":
        print(S.check_report(APP, study, mod, S.load_classification(APP), study_path))
    else:
        raise SystemExit(f"MODE 只能是 build/check,得到 {MODE!r}")


if __name__ == "__main__":
    main()
