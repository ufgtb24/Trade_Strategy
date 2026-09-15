# -*- coding: utf-8 -*-
"""tune-gates · 优势检查:这个走势的买点比同一天、同样波动水平的随机买入日好不好,手上的样本能分辨多小的改进。

流程(run):
  1. scan:单配置扫描,只许训练窗。检测参数取正式值(params.yaml),闸按放开值(wide_overrides)构造;
     每只股票跑一次 pattern(engine.analyze,不走反转循环)。每个过了窗口与价格过滤的 match、它的每个
     样本 bar t 写一行(bars,t 须落在买点区间内、前瞻窗完整、M 有效),同一 (symbol, seg_id, t) 可因
     前缀不同出现多行;另写与 multivar_scan 同口径的逐日基线(baseline)。断点续跑、分片提交、done 集
     规则与 multivar_scan 相同。
  2. points:两个比较点。宽进点 = 全部行按 (symbol, seg_id, t) 去重;工作点 = 过全部正式闸的行再去重
     (同一买点日的多行里任一行过全部正式闸即算过,同一段买点只计一次)。
  3. 两个点各自逐年 + 合并做层匹配比较(edge_core.edge_by_year)与三分支判读;宽进点不是有边际、
     工作点是有边际 → 底子来自现役的闸(edge_core.edge_source_note)。
  4. 分辨力:工作点每股计数(全部年份合并)按股去簇;改动后买点保留比例用标定先验
     budget.R_BAR_DETECT_PRIOR(由它算出的量都是估计),样本离散程度与定向占比取本次实测;
     对比族大小 m 由调用方预估。
  5. 写 edge_report.md(人话),最后往账本追加 edge 记录(ref 带报告 sha256,n_looks = 1)。

输出目录 outputs/tune_gates/<app>/edge/:bars/、baseline/(分片号一致)、run_meta.json、shards_committed.csv、
filtered_symbols.csv、empty_symbols.csv、edge_report.md。
"""
from __future__ import annotations

import importlib
import json
import math
import shutil
import sys
import time
import traceback
from pathlib import Path

import numpy as np
import pandas as pd

SKILL_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SKILL_DIR))

import ledger  # noqa: E402

REPO = ledger.REPO
sys.path.insert(0, str(REPO))

import budget  # noqa: E402
import edge_core  # noqa: E402
import holdout  # noqa: E402
import multivar_scan as MS  # noqa: E402
from multivar_core import STATES, apply_overrides, check_predicate_axes, classify, seg_id_of, stock_scales  # noqa: E402

WINDOW = "edge"
ACTOR = "tune.edge"
SHARD_DIRS = ("bars", "baseline")
BAR_COLS = ["symbol", "t", "date", "M", "c0_atr_pct", *STATES, "seg_id"]
ROW_KEY = ["symbol", "seg_id", "t"]
# run_meta 里这些项变了,已扫的样本就不是同一回事,不能续跑。ticker_regex(本次股票范围)不在其列:
# 先用小正则试跑、再放开全宇宙续跑是支持的用法,每次运行按本次值重写
CALIBER = ("app", "start_date", "end_date", "head_buffer", "label_horizon", "first_passage_k", "price_min",
           "price_max", "volume_min", "wide_overrides", "source_fingerprint", "base_fingerprint", "ruler_fingerprint")
VERDICT_WORDS = {"有边际": "有底子", "未证实": "还不能确定", "没有": "没有"}
POINT_WORDS = {"wide": "闸全部放开", "working": "按现在的正式参数"}
LOW_COVERAGE = 0.8


# ---------------------------------------------------------------- 闸
def _app_module(app: str) -> str:
    """app 名 → 走势模块路径,沿用 path2_web 的 pattern 发现约定:path2_apps/<app>/dag_spec.py。"""
    return f"path2_apps.{app}.dag_spec"


def _probe_alternatives(v) -> list:
    """放开值与正式值相同时,判断参数类型需要另一个取值来试:数值取相邻值,其余类型给不出。"""
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        return []
    if isinstance(v, int):
        return [v + 1, v - 1]
    return [v * 2, v / 2] if v else [1.0, -1.0]


def _classify_gate(mod, base: dict, dim: tuple, levels: list) -> tuple:
    """(kind, (node, field, op) 或 None, 失败原因或 None)。先当 where 阈值试,再当过滤型 / 检测参数试。"""
    errors = []
    try:
        cls = classify(mod, base, {}, {dim: levels})
        return "W", cls.where_fields[dim], None
    except Exception as e:  # noqa: BLE001 —— app 用什么异常表达"这组参数不合法"是它的自由
        errors.append(f"{type(e).__name__}: {e}")
    try:
        cls = classify(mod, base, {dim: levels}, {})
    except Exception as e:  # noqa: BLE001
        errors.append(f"{type(e).__name__}: {e}")
        return None, None, " | ".join(errors)
    return cls.kinds[dim], cls.filter_fields.get(dim), None


def gate_specs(mod, base_yaml: dict, wide_overrides: dict) -> list[dict]:
    """放开的每个参数逐个探针,必须是 where 阈值或过滤型(闸),否则 ValueError(人话)。

    参数:base_yaml = 正式参数(params.yaml 解析结果);wide_overrides = {section: {field: 放开值}}。
    探针在「正式参数 ⊕ 全部放开值」上做,用放开值与正式值两档;两者相同(正式值本来就是放开的)时改用
    相邻取值来试。闸所在的 node 必须参与求解(match 里取得到它的字段),且不能是否定边的目标(否定边
    目标上的闸收紧反而会多出 match,不能事后按行切)。
    返回 [{"param", "kind"("W"|"F"), "node", "field", "op", "production", "wide"}],production = 正式值。
    """
    from path2.dag._solve import compile_plan
    base = apply_overrides(base_yaml, wide_overrides, {})
    out, fields = [], {}
    for sec, kv in wide_overrides.items():
        for field, wide in kv.items():
            dim, key = (sec, field), f"{sec}.{field}"
            if field not in base_yaml.get(sec, {}):
                raise ValueError(f"放开的参数 {key} 不在正式参数里")
            prod = base_yaml[sec][field]
            alts = [prod] if prod != wide else _probe_alternatives(wide)
            kind, fld, errors = None, None, []
            for alt in alts:
                kind, fld, err = _classify_gate(mod, base, dim, [wide, alt])
                if kind in ("W", "F"):
                    break
                errors.append(err or f"判成 {kind}")
            if kind in ("D", "E"):
                raise ValueError(f"{key} 不是闸:改它会重新检测买点或改变买点之间的关系。优势检查的检测参数一律取"
                                 "正式值,放开的只能是闸")
            if kind not in ("W", "F"):
                why = ("正式值与放开值相同,又找不到别的取值来试" if not alts else ";".join(e for e in errors if e))
                raise ValueError(f"{key} 判断不了是不是闸:{why}")
            fields[dim] = fld
            out.append({"param": key, "kind": kind, "node": fld[0], "field": fld[1], "op": fld[2],
                        "production": prod, "wide": wide})
    spec = mod.build_pattern(mod.Params.from_dict(base, strict=True))
    check_predicate_axes(spec, fields)
    bound = {nid for w in compile_plan(spec).wcc_plans for nid in w.comp}
    loose = [g["param"] for g in out if g["node"] not in bound]
    if loose:
        raise ValueError(f"{loose} 所在的 node 不参与求解,match 里取不到它们的字段,不能当闸事后切")
    return out


def _gate_col(g: dict) -> str:
    return f"{g['node']}.{g['field']}"


# ---------------------------------------------------------------- 扫描
def _fingerprints(mod, spec, params: dict) -> dict:
    """底座(正式参数 ⊕ 放开值)、检测源码、标签尺子三个指纹 + git 版本;算法与 study_io / ledger 同源,
    所以与 ledger.current_fingerprints 在同一份代码下相等。"""
    import study_io as S
    return {"git_head": S._git_head(), "base_fingerprint": S.canonical_hash(params),
            "source_fingerprint": S.source_fingerprint(S.source_files(mod, spec))["hash"],
            "ruler_fingerprint": ledger.ruler_fingerprint()}


def _write_meta(out: Path, meta: dict) -> None:
    p = out / "run_meta.json"
    if p.exists():
        old = json.loads(p.read_text(encoding="utf-8"))
        bad = [k for k in CALIBER if old.get(k) != meta.get(k)]
        if bad:
            raise SystemExit(f"上一次优势检查的扫描是在不同的设置或代码下做的(变了:{bad}),样本不能接着用;"
                             "要重做请传 restart=True(会先清掉上一次的扫描结果)")
    p.write_text(json.dumps(meta, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


def _worker(pkl_path, app_module, params, end_node, gate_cols, buf_start, buf_end, start_date, end_date,
            horizon, k, price_min, price_max, volume_min):
    """一只股票:切窗 → 股票级过滤 → 单配置 analyze → 样本 bar 行 + 逐日基线。

    返回 (symbol, 被过滤, bars | None, baseline | None, err)。样本 bar = 买点 node 事件的 sample_bar_indices
    落在买点区间 [lo, hi] 内、且是合格日(daily_first_passage 有这一天:前瞻窗完整、M 有效)的 t;
    一个 match 内同一 t 只写一行。窗口与价格过滤与 multivar_core.scan_one_stock 相同。"""
    from path2 import config
    from path2.dag.engine import analyze
    from path2.eval import _resolve_end_events, daily_first_passage
    symbol = Path(pkl_path).stem
    try:
        config.set_runtime_checks(True)
        win = MS.load_stock(pkl_path, buf_start, buf_end, start_date, end_date, volume_min)
        if win is None:
            return (symbol, True, None, None, None)
        s, e = pd.to_datetime(start_date), pd.to_datetime(end_date)
        lo = int(win["date"].searchsorted(s, "left"))
        hi = int(win["date"].searchsorted(e, "right")) - 1
        mod = importlib.import_module(app_module)
        p = mod.Params.from_dict(params, strict=True)
        res = analyze(mod.build_pattern(p), win, p)
        M, c0 = stock_scales(win)
        daily = daily_first_passage(win, s, e, horizon, k, M=M)
        pos = np.full(len(win), -1)
        pos[daily["idx"].to_numpy()] = np.arange(len(daily))
        closes = win["close"].to_numpy()
        ts, sids, vals = [], [], [[] for _ in gate_cols]
        for m in res.matches:
            events = _resolve_end_events(m, end_node)
            if not any(lo <= ev.start_idx <= hi for ev in events):
                continue
            if not any((price_min is None or closes[ev.start_idx] >= price_min)
                       and (price_max is None or closes[ev.start_idx] <= price_max) for ev in events):
                continue
            bars_t = sorted({t for ev in events for t in ev.sample_bar_indices() if lo <= t <= hi and pos[t] >= 0})
            if not bars_t:
                continue
            sid = seg_id_of(tuple((ev.start_idx, ev.end_idx) for ev in events))
            ts += bars_t; sids += [sid] * len(bars_t)
            for j, (n, f) in enumerate(gate_cols):
                vals[j] += [getattr(m.node_index[n], f)] * len(bars_t)
        bars = None
        if ts:
            t = np.asarray(ts, dtype=np.int64)
            st = daily[list(STATES)].to_numpy()[pos[t]]
            bars = pd.DataFrame({"symbol": [symbol] * len(t), "t": t.astype(np.int32), "date": win["date"].to_numpy()[t],
                                 "M": M[t], "c0_atr_pct": c0[t], **{x: st[:, i] for i, x in enumerate(STATES)},
                                 "seg_id": np.asarray(sids, dtype=np.int64),
                                 **{f"{n}.{f}": v for (n, f), v in zip(gate_cols, vals)}})
        base = MS.daily_baseline(symbol, daily, c0, price_min, price_max)
        return (symbol, False, bars, base, None)
    except Exception as ex:  # noqa: BLE001
        tb_tail = "".join(traceback.format_exc().splitlines(keepends=True)[-6:]).rstrip("\n")
        return (symbol, False, None, None, f"{type(ex).__name__}: {ex}\n{tb_tail}")


def scan(app: str, cfg, *, wide_overrides: dict, restart: bool = False) -> Path:
    """优势检查的单配置扫描(断点续跑),返回输出目录。只许训练窗:先过确认窗守卫,任何拒绝原样抛。

    cfg 是 tune.Settings(用到数据目录、买点区间、首部缓冲、标签窗长、首次穿越阈值、价格 / 成交量过滤、
    股票正则、每片股数、并行数)。restart=True 先清掉上一次的扫描结果再扫;否则设置或代码与上一次不同时拒绝续跑。
    """
    holdout.guard_label_access(app, cfg.start_date, cfg.end_date, "edge")
    import study_io as S
    from path2_web.scan import _list_pkls
    app_module = _app_module(app)
    mod = importlib.import_module(app_module)
    production = mod.Params.from_yaml(S.app_dir(mod) / "params.yaml").to_dict()
    gates = gate_specs(mod, production, wide_overrides)
    params = apply_overrides(production, wide_overrides, {})
    p = mod.Params.from_dict(params, strict=True)
    spec = mod.build_pattern(p)
    end_node = mod.eval_meta(params=p)["end_node"]

    out = REPO / "outputs" / "tune_gates" / app / WINDOW
    if restart and out.exists():
        shutil.rmtree(out)
    for d in SHARD_DIRS:
        (out / d).mkdir(parents=True, exist_ok=True)
    _write_meta(out, {"app": app, "start_date": cfg.start_date, "end_date": cfg.end_date,
                      "head_buffer": cfg.head_buffer, "label_horizon": cfg.label_horizon,
                      "first_passage_k": cfg.first_passage_k, "price_min": cfg.price_min, "price_max": cfg.price_max,
                      "volume_min": cfg.volume_min, "ticker_regex": cfg.ticker_regex,
                      "wide_overrides": wide_overrides, "gates": gates,
                      "end_node": end_node, **_fingerprints(mod, spec, params),
                      "written_at": pd.Timestamp.now().isoformat(timespec="seconds")})
    done, _parts, n_shard = MS.prepare_resume(out, SHARD_DIRS, SHARD_DIRS)
    filtered, empty = _parts["filtered"], _parts["empty"]
    _, _, buf_start, buf_end = MS._window_bounds(cfg.start_date, cfg.end_date, cfg.head_buffer, cfg.label_horizon)
    pkls = [str(x) for x in _list_pkls(str(REPO / cfg.data_dir), cfg.ticker_regex) if x.stem not in done]
    print(f"[优势检查] {app}:股票 {len(pkls)} 待扫(已完成 {len(done)}),买点区间 {cfg.start_date}..{cfg.end_date}")

    t0 = time.time()
    bar_buf, base_buf = [], []
    n_done = n_det = n_hit = n_bars = n_base = n_err = 0

    def flush():
        nonlocal n_shard
        if bar_buf or base_buf:
            tables = {}
            for sub, buf in (("bars", bar_buf), ("baseline", base_buf)):
                if buf:
                    df = pd.concat(buf, ignore_index=True)
                    df["symbol"] = df["symbol"].astype("category")
                    tables[sub] = df
            MS.write_shard(out, n_shard, tables)
            n_shard += 1; bar_buf.clear(); base_buf.clear()
        if filtered:
            pd.DataFrame({"symbol": filtered}).to_csv(out / "filtered_symbols.csv", index=False)
        if empty:
            pd.DataFrame({"symbol": empty}).to_csv(out / "empty_symbols.csv", index=False)

    def on_result(res):
        nonlocal n_done, n_det, n_hit, n_bars, n_base, n_err
        symbol, was_filtered, bars, base, err = res
        n_done += 1
        if err:
            n_err += 1; print("ERR", symbol, err)          # 不计入 done,下次自动重试
        elif was_filtered:
            filtered.append(symbol)
        else:
            n_det += 1
            if bars is not None:
                n_hit += 1; n_bars += len(bars); bar_buf.append(bars)
            if len(base):
                n_base += len(base); base_buf.append(base)
            elif bars is None:
                empty.append(symbol)
        if n_done % cfg.shard_stocks == 0 or n_done == len(pkls):
            flush()

    gate_cols = [(g["node"], g["field"]) for g in gates]
    MS._scan_pool(pkls, _worker, (app_module, params, end_node, gate_cols, buf_start, buf_end, cfg.start_date,
                                  cfg.end_date, cfg.label_horizon, cfg.first_passage_k, cfg.price_min, cfg.price_max,
                                  cfg.volume_min), cfg.workers, on_result)
    flush()
    print(f"[优势检查] 本轮:进 detector {n_det} / 过滤 {len(pkls) - n_det - n_err} / 有买点 {n_hit} / 异常 {n_err};"
          f"样本行 {n_bars},逐日基线行 {n_base},{time.time() - t0:.0f}s")
    return out


# ---------------------------------------------------------------- 比较点与报告
def points(bars: pd.DataFrame, gates: list[dict]) -> dict:
    """{"wide": 全部行按 (symbol, seg_id, t) 去重, "working": 过全部正式闸的行再按同键去重}。

    闸的判定:正式值 None = 不设闸(恒过);否则 `字段值 op 正式值`,字段值缺失算不过。"""
    import study_io as S
    ok = np.ones(len(bars), dtype=bool)
    for g in gates:
        if g["production"] is None:
            continue
        col = pd.to_numeric(bars[_gate_col(g)], errors="coerce")
        ok &= S._cmp(col, g["production"], g["op"]).to_numpy(dtype=bool)
    return {"wide": bars.drop_duplicates(ROW_KEY).reset_index(drop=True),
            "working": bars[ok].drop_duplicates(ROW_KEY).reset_index(drop=True)}


def _read_committed(out: Path, sub: str, columns: list) -> pd.DataFrame:
    committed = MS.committed_shards(out) or set()
    frames = [pd.read_parquet(p, columns=columns) for p in sorted((out / sub).glob("part-*.parquet"))
              if p.name in committed]
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=columns)


def _jsonable(x):
    """账本只收标准 JSON:numpy 标量转 Python,NaN / inf 转 null,元组转列表。"""
    if isinstance(x, dict):
        return {str(k): _jsonable(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [_jsonable(v) for v in x]
    if isinstance(x, (bool, np.bool_)):
        return bool(x)
    if isinstance(x, np.integer):
        return int(x)
    if isinstance(x, (float, np.floating)):
        return float(x) if math.isfinite(float(x)) else None
    return x


def _artifact_path(path: Path) -> str:
    p = Path(path).resolve()
    try:
        return str(p.relative_to(REPO))
    except ValueError:
        return str(p)


def _fin(x) -> bool:
    return x is not None and math.isfinite(float(x))


def _pt(x, sign=True) -> str:
    return "—" if not _fin(x) else (f"{x * 100:+.1f}" if sign else f"{x * 100:.1f}")


def _pct(x) -> str:
    return "—" if not _fin(x) else f"{x * 100:.1f}%"


def render_report(app: str, meta: dict, gates: list, res: dict, verdicts: dict, note, resol: dict,
                  delta: float, m: int) -> str:
    """优势检查报告(给用户读):只讲业务含义,不出现内部名字。"""
    d_pt = f"{delta * 100:.1f}"
    L = [f"# 优势检查 · {app}", "",
         "这份检查回答两件事:", "",
         "1. 这个走势的买点,比**同一天、同样波动水平的随机买入日**好不好;",
         "2. 手上这些样本,能分辨出多小的改进。", "",
         f"「好」用首次穿越率衡量:买入后 {meta['label_horizon']} 个交易日内,先涨到上轨、而不是先跌到下轨的比例"
         "(上下轨按这只股票近期的波动幅度定)。比较时,每个买点日只和同一天、波动水平落在同一档(当天全部股票按"
         "波动高低分三档)的随机买入日比,所以差值读到的是走势本身,而不是它碰巧落在哪段行情、多高波动的股票上。"
         "同一段买点的同一天只算一次。", "",
         f"- 训练数据:{meta['start_date']} 到 {meta['end_date']} 的买点",
         f"- 最小关心改进:{d_pt} 个百分点",
         "- 两种比较口径:「闸全部放开」只看走势检测本身;「按现在的正式参数」闸按现在的值。", ""]
    if gates:
        L += ["| 闸 | 现在的值 | 放开时的值 |", "|---|---|---|"]
        L += [f"| {g['param']} | {g['production']!r} | {g['wide']!r}"
              f"{'(现在本来就是放开的)' if g['production'] == g['wide'] else ''} |" for g in gates]
        L.append("")

    def word(k, y):
        return "比不了" if res[k][y]["n_layers"] == 0 else VERDICT_WORDS[verdicts[k][y]]

    L += ["## 结论", ""]
    for k in ("wide", "working"):
        if res[k]["pooled"]["n_layers"] == 0:
            L.append(f"- {POINT_WORDS[k]}:**比不了**——同一天找不到足够多同样波动水平的随机买入日来比"
                     "(通常是只扫了一小部分股票),这一口径没有结论")
            continue
        years = [y for y in res[k] if y != "pooled"]
        per_year = ",".join(f"{y} 年{word(k, y)}" for y in years)
        L.append(f"- {POINT_WORDS[k]}:合并看**{word(k, 'pooled')}**"
                 f"(差值 {_pt(res[k]['pooled']['est'])} 点;逐年:{per_year})")
    L.append("")
    if note is not None:
        where = [("全部年份合并" if y == "pooled" else f"{y} 年") for y in res["working"]
                 if y in verdicts["wide"] and verdicts["wide"][y] != "有边际" and verdicts["working"][y] == "有边际"]
        L += [f"{'、'.join(where)}:闸全部放开时看不出底子、按现在的正式参数有——这点底子来自现在开着的闸,"
              "不是走势检测本身带来的。", ""]
    v = verdicts["working"]["pooled"]
    if res["working"]["pooled"]["n_layers"] == 0:
        pass
    elif v == "没有":
        L += [f"按现在的正式参数,买点比同一天、同样波动水平的随机买入日没有值得关心的优势(差值区间的上沿不到 {d_pt} 点)。"
              "继续调参之前,先想清楚这个走势值不值得调。", ""]
    elif v == "未证实":
        L += [f"按现在的正式参数,还不能确定有没有底子:差值区间里既有 0 以下的值,也有 {d_pt} 点以上的值。", ""]
    else:
        L += ["按现在的正式参数,买点稳定地好于同一天、同样波动水平的随机买入日(差值区间整体在 0 以上)。", ""]
    for k in ("wide", "working"):
        low = [f"{'全部年份合并' if y == 'pooled' else y + ' 年'} {1 - r['coverage']:.0%}" for y, r in res[k].items()
               if r["n_layers"] > 0 and _fin(r["coverage"]) and r["coverage"] < LOW_COVERAGE]
        if low:
            L.append(f"- 提醒:{POINT_WORDS[k]}时,有一部分买点日在同一天找不到足够多同样波动水平的随机买入日来比"
                     f"({'、'.join(low)}),这些栏的结论只代表比得上的那部分买点。")
    L += ["", f"三种结论的意思:有底子 = 差值的 95% 区间整体在 0 以上;没有 = 区间上沿不到 {d_pt} 点;还不能确定 = 其余情况。", ""]

    L += ["## 明细", ""]
    for k in ("wide", "working"):
        L += [f"### {POINT_WORDS[k]}", "",
              "| 年份 | 结论 | 差值(点) | 95% 区间(点) | 买点首次穿越率 | 同一天、同样波动水平的随机买入日 | 比得上的买点日占比 | 分出涨跌的买点日 | 股票数 |",
              "|---|---|---|---|---|---|---|---|---|"]
        for y, r in res[k].items():
            label = "全部合并" if y == "pooled" else y
            L.append(f"| {label} | {word(k, y)} | {_pt(r['est'])} | {_pt(r['ci_lo'])} ~ {_pt(r['ci_hi'])} "
                     f"| {_pct(r['pattern_rate'])} | {_pct(r['matched_base_rate'])} | {_pct(r['coverage'])} "
                     f"| {r['n_pattern_dir']:,} | {r['n_pattern_symbols']:,} |")
        L.append("")

    n_years = len([y for y in res["working"] if y != "pooled"])
    enough = resol["n_bars_per_fold"] >= resol["n_pl"] if _fin(resol["n_pl"]) else False
    L += ["## 样本能分辨多小的改进(估计)", "",
          f"按现在的正式参数:分出涨跌的买点日 {resol['n_dir']:,} 个(连同没分出涨跌的共 {resol['n_bars']:,} 个,{n_years} 年合计),"
          f"首次穿越率按股票算的误差约 ±{_pt(resol['se_level'], sign=False)} 点。", "",
          f"- 事先写好的单个改动:能分辨出约 {_pt(resol['x_single'], sign=False)} 点以上的改进;",
          f"- 筛选阶段(预估一共要比 {m} 组改动):约 {_pt(resol['x_screen'], sign=False)} 点以上;",
          f"- 两个参数一起调:{'能' if resol['joint_feasible_2'] else '不能'}分辨出 {d_pt} 点这么大的改进;",
          f"- 要分辨 {d_pt} 点的改进,每年大约需要 {resol['n_pl']:,.0f} 个买点日;现在每年约 {resol['n_bars_per_fold']:,.0f} 个,"
          f"{'够' if enough else '不够'};",
          f"- 按现在每年的样本量,噪声本身就可能造出最多约 {_pt(resol['floor_upper'], sign=False)} 点的假差值。", "",
          f"这一节标「估计」的原因:改一个参数之后大约还保留多少买点,这里用的是事先标定的经验比例(约 {resol['r_bar']:.0%}),"
          f"不是这次实测的,真正筛选之后会换成实测比例重算;{m} 组也是预估数,以筛选时实际要比的为准。"
          "样本本身的离散程度、分出涨跌的买点日占比是这次实测的。", ""]
    return "\n".join(L)


def run(app: str, cfg, *, wide_overrides: dict, delta: float, m: int, B: int = 300, seed: int = 0,
        restart: bool = False) -> dict:
    """优势检查全流程:扫描(续跑)→ 两个比较点 → 逐年 + 合并判读 → 分辨力 → 报告 → 账本 edge 记录。

    参数:delta = 最小关心改进(比例,0.02 = 2 点);m = 调用方预估的筛选对比族大小;B、seed = bootstrap
    副本数与种子;cfg 另用到 screen_fdr_q(筛选的 BH 阈值)。账本记录最后写,ref 带报告哈希。
    返回 {"out_dir", "report", "verdicts", "source_note", "record"}。
    """
    out = scan(app, cfg, wide_overrides=wide_overrides, restart=restart)
    meta = json.loads((out / "run_meta.json").read_text(encoding="utf-8"))
    gates = meta["gates"]
    bars = _read_committed(out, "bars", BAR_COLS + [_gate_col(g) for g in gates])
    if bars.empty:
        raise SystemExit(f"「{app}」在训练数据上一个买点都没扫到,做不了优势检查。")
    pts = points(bars, gates)
    del bars
    if pts["working"].empty:
        raise SystemExit(f"「{app}」按现在的正式参数,训练数据上一个买点都没有,做不了优势检查。")
    base = _read_committed(out, "baseline", ["symbol", "date", "M", *STATES])
    res = {k: edge_core.edge_by_year(pts[k], base, B=B, seed=seed) for k in ("wide", "working")}
    verdicts = {k: {y: edge_core.edge_verdict(r, delta) for y, r in res[k].items()} for k in res}
    note = edge_core.edge_source_note(verdicts["wide"], verdicts["working"])
    w = pts["working"]
    sums = w.groupby(w["symbol"].astype(str))[list(STATES)].sum()
    D = (sums["up"] + sums["down"] + sums["both"]).to_numpy(dtype=float)
    resol = edge_core.resolution(sums["up"].to_numpy(dtype=float), D, D + sums["none"].to_numpy(dtype=float),
                                 delta=delta, m=m, q=cfg.screen_fdr_q, r_bar=budget.R_BAR_DETECT_PRIOR,
                                 r_bar_source="标定先验", n_folds=len([y for y in res["working"] if y != "pooled"]))

    report = out / "edge_report.md"
    report.write_text(render_report(app, meta, gates, res, verdicts, note, resol, delta, m), encoding="utf-8")
    data = _jsonable({"points": res, "verdicts": verdicts, "verdict": verdicts["working"]["pooled"],
                      "source_note": note, "delta": delta, "resolution": resol,
                      "m_note": "预估族大小(调用方按设计预估,筛选时以实际对比族为准)",
                      "resolution_note": "改动后买点保留比例取标定先验,分辨力各量为估计",
                      "gates": gates, "wide_overrides": wide_overrides,
                      "n_rows": {k: len(v) for k, v in pts.items()}})
    rec = ledger.make_record(
        "edge", app, actor=ACTOR, round=None, axes=[g["param"] for g in gates],
        window={"start": str(meta["start_date"]), "end": str(meta["end_date"])},
        label_horizon=int(meta["label_horizon"]), head_buffer=int(meta["head_buffer"]),
        **{k: meta[k] for k in ledger.FINGERPRINT_FIELDS},
        n_looks=1, ref={_artifact_path(report): ledger.sha256_file(report)}, data=data)
    ledger.append(rec)
    return {"out_dir": str(out), "report": str(report), "verdicts": verdicts, "source_note": note, "record": rec}
