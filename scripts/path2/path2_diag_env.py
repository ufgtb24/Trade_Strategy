"""path2 event 诊断环境探测脚本。

输入 symbol + event_id(+可选 scan 路径),自动从 scan 推断诊断环境:
worktree / 最新 scan / 目标 pattern(非 bo_only 的 xxx) / params(params_snapshot 重建) / 窗口,
并打印声明(scan_ts + provenance + 关键阈值)让用户核对、一句纠正。

用法(诊断时,推荐 import 调用,不改脚本):
    import sys; sys.path.insert(0, "scripts/path2")
    from path2_diag_env import diagnose_env, format_declaration
    env = diagnose_env("DVLT", "tb_257_258")
    print(format_declaration(env))

或改本文件 __main__ 顶部变量跑(CLAUDE.md: 入口脚本无 argparse)。
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path


def resolve_target_pattern(pattern_ids: list[str], event_id: str) -> str:
    """诊断目标 pattern = pattern_ids 中非 bo_only 的那个(xxx,真正诊断的)。
    bo_only 是 xxx 的漏检参照系,非诊断目标。
    event_id 的 class_id 前缀辅助:tb_*/burst_* 必属 xxx;bo_* 共有,默认归 xxx。
    多个非 bo_only 且无法消歧 → 报错(需用户指定)。
    """
    candidates = [p for p in pattern_ids if p != "bo_only"]
    if not candidates:
        raise ValueError("scan 无非 bo_only pattern(无诊断目标)")
    if len(candidates) == 1:
        return candidates[0]
    # 多个 xxx:event_id 前缀无法可靠消歧(bo_* 共有;tb/burst 需查 pattern 拓扑),报错让用户指定
    raise ValueError(f"多个非 bo_only pattern {candidates},event_id={event_id} 无法消歧,请指定目标 pattern")


def extract_window(scan: dict) -> dict:
    """scan.scan 的窗口字段(slice_window 切窗用 win_start/win_end)。"""
    s = scan["scan"]
    return {"win_start": s["win_start"], "win_end": s["win_end"],
            "start_date": s["start_date"], "end_date": s["end_date"]}


def extract_provenance(scan: dict, pid: str) -> str:
    """scan.per_pattern[pid].params_provenance(scan 用的参数来源,如 file:p2.yaml)。
    老 scan 无此字段 → 标"未知"。
    """
    return scan.get("per_pattern", {}).get(pid, {}).get("params_provenance") or "未知(老 scan 无 provenance)"


def params_summary(params) -> str:
    """关键阈值摘要(burst/tb/bo),供声明让用户核对 params 是否符合预期。"""
    b, t, bo = params.burst, params.tb, params.bo
    return (f"burst(min_bos={b.min_bos}/first_drought_min={b.first_drought_min}/"
            f"distinct_pk_min={b.distinct_pk_min}/vol_spike_min={b.vol_spike_min}) "
            f"tb(stop_confirm_bars={t.stop_confirm_bars}/big_rise_k={t.big_rise_k}/max_start_gap={t.max_start_gap}) "
            f"bo(breakout_measure={bo.breakout_measure})")


def format_declaration(env: dict) -> str:
    """格式化环境声明(打印让用户核对,不符一句纠正)。硬性步骤——防默认错。"""
    w = env["window"]
    return "\n".join([
        "=== 诊断环境声明(核对,不符请纠正) ===",
        f"worktree: {env['worktree']}  (branch={env['branch']})",
        f"scan: {env['scan_ts']}  ({env['scan_path']})",
        f"目标 pattern(xxx): {env['pattern']}   (bo_only=漏检参照系,不诊断)",
        f"params provenance: {env['provenance']}",
        f"params 重建: {env['params_summary']}",
        f"窗口: win={w['win_start']}~{w['win_end']}  label={w['start_date']}~{w['end_date']}",
        f"诊断目标: {env['symbol']} 的 {env['event_id']}",
        "========================================",
    ])


def find_latest_scan(outputs_dir: str) -> Path | None:
    """scans/ 下 scan_ts(=文件名,YYYYMMDDTHHMMSS)字典序最大的 json = 最新 scan。"""
    files = sorted(Path(outputs_dir).glob("*.json"))
    return files[-1] if files else None


def resolve_worktree() -> tuple[str, str]:
    """session cwd 所在 worktree 的 root + branch(git rev-parse)。"""
    root = subprocess.check_output(["git", "rev-parse", "--show-toplevel"], text=True).strip()
    branch = subprocess.check_output(["git", "branch", "--show-current"], text=True).strip()
    return root, branch


def rebuild_params(snapshot: dict):
    """scan 的 params_snapshot → Params 重建(from_dict strict=False 容忍探索态改坏/老 snapshot 缺字段)。"""
    from path2_apps.bottom_breakout_burst.params import Params
    return Params.from_dict(snapshot, strict=False)


def load_explore_wc(worktree_root: str, target_pid: str) -> dict | None:
    """探索态:读 outputs/path2_web/wc.json(Write Copy 镜像,单一覆盖文件)。
    存在 + pid 匹配 + enabled=true 才用(防切 pattern 滞后 + 休眠态误用);否则 None(回退 scan snapshot)。
    wc.json schema: {pid, scan_ts, win_start, win_end, start_date, end_date, wc(currentDict), enabled, written_at}。
    """
    p = Path(worktree_root) / "outputs/path2_web/wc.json"
    if not p.exists():
        return None
    wc = json.loads(p.read_text())
    if wc.get("pid") != target_pid:
        return None  # 滞后(上一个 pattern 的),不用
    if not wc.get("enabled", False):
        return None  # 休眠态(enabled=false),回退 scan snapshot
    return wc


def diagnose_env(symbol: str, event_id: str, scan_path: str | None = None) -> dict:
    """环境探测主入口:推 worktree/scan/pattern/params/窗口 + 声明 dict。"""
    worktree_root, branch = resolve_worktree()
    outputs_dir = Path(worktree_root) / "outputs/path2_web/scans"
    sp = Path(scan_path) if scan_path else find_latest_scan(str(outputs_dir))
    if sp is None:
        raise FileNotFoundError(f"未找到 scan 文件(在 {outputs_dir})")
    scan = json.loads(sp.read_text())
    pid = resolve_target_pattern(scan["pattern_ids"], event_id)

    # 探索态优先:wc.json 存在 + pid 匹配 + enabled → 用 WC dict;否则 scan snapshot
    wc = load_explore_wc(worktree_root, pid)
    if wc is not None:
        # 用 wc.scan_ts 定位 scan(保证 events 索引跟用户探索时一致,而非最新 scan)
        wc_scan_ts = wc.get("scan_ts")
        if wc_scan_ts and wc_scan_ts != scan["scan"]["scan_ts"]:
            wc_sp = outputs_dir / f"{wc_scan_ts}.json"
            if wc_sp.exists():
                sp = wc_sp
                scan = json.loads(sp.read_text())   # 重读探索时那个 scan
        snapshot = wc["wc"]
        win = {"win_start": wc["win_start"], "win_end": wc["win_end"],
               "start_date": wc.get("start_date", "?"), "end_date": wc.get("end_date", "?")}
        provenance = f"working_copy(wc.json @ {wc.get('written_at','?')})"
    else:
        snapshot = scan["per_pattern"][pid]["params_snapshot"]
        win = extract_window(scan)
        provenance = extract_provenance(scan, pid)

    params = rebuild_params(snapshot)
    return {
        "symbol": symbol, "event_id": event_id,
        "worktree": worktree_root, "branch": branch,
        "scan_path": str(sp), "scan_ts": scan["scan"]["scan_ts"],
        "pattern": pid, "provenance": provenance,
        "params": params, "params_summary": params_summary(params),
        "window": win,
    }


if __name__ == "__main__":
    # CLAUDE.md: 入口脚本无 argparse,参数作顶部变量。诊断时优先 import diagnose_env 调用(不改脚本)。
    SYMBOL = "DVLT"
    EVENT_ID = "tb_257_258"
    SCAN_PATH: str | None = None   # None=最新 scan;或给绝对路径

    env = diagnose_env(SYMBOL, EVENT_ID, SCAN_PATH)
    print(format_declaration(env))
