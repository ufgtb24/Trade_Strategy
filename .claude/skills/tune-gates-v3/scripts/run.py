"""v3 编排入口：冻结训练规则、Optuna 搜索、一次验证与暂用复核。

从仓库根运行本脚本；辅助模块只放在本 skill 内，不改 path2 引擎。
每次搜索新建运行目录。中断可查已写的试验记录，但不伪装成精确续跑。
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import importlib
import json
import math
import os
from pathlib import Path
import re
import sys
from datetime import date, datetime
from zoneinfo import ZoneInfo
import uuid

# 脚本在 .agents/skills 或临时测试目录均可从仓库根运行。
ROOT = Path.cwd().resolve()
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import optuna
import pandas as pd

from daily import DailyEvaluator
from governance import UsageLedger, adoption, canonical_hash, SCORE_EPSILON
from scoring import WindowPlan, assess, comparison, normalize_policy, normalize_shrinkage, summary


def write_json(path: Path, payload: dict) -> None:
    """同目录原子替换，拒绝 NaN，保留真实小数与非 ASCII 文本。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + '.tmp')
    with tmp.open('w', encoding='utf-8') as f:
        json.dump(payload, f, ensure_ascii=False, indent=2, allow_nan=False)
        f.write('\n')
        f.flush()
        os.fsync(f.fileno())
    tmp.replace(path)


def seal(payload: dict) -> dict:
    """防止保存后的规则或候选被无意改动；不是抵御恶意篡改的签名。"""
    return {'sha256': canonical_hash(payload), 'payload': payload}


def read_sealed(path: Path) -> dict:
    obj = json.loads(path.read_text(encoding='utf-8'))
    if obj['sha256'] != canonical_hash(obj['payload']):
        raise ValueError(f'{path.name} 已改变，不能沿用本轮验证机会')
    return obj['payload']


def source_hash(root: Path = ROOT) -> str:
    """包含引擎、所有 app 与本 skill 的 Python 代码，排除运行产物。"""
    digest = hashlib.sha256()
    groups = [(root / 'path2', 'path2'), (root / 'path2_apps', 'path2_apps'),
              (Path(__file__).parent, 'skill')]
    for folder, name in groups:
        for path in sorted(folder.rglob('*.py')):
            digest.update((name + '/' + str(path.relative_to(folder))).encode())
            digest.update(path.read_bytes())
    return digest.hexdigest()


def get_value(params: dict, dotted: str):
    result = params
    for part in dotted.split('.'):
        result = result[part]
    return result


def with_values(base: dict, values: dict) -> dict:
    """严格叠加在整份现役快照上，未调字段不回到代码默认值。"""
    result = copy.deepcopy(base)
    for dotted, value in values.items():
        get_value(base, dotted)
        parts = dotted.split('.')
        parent = result
        for part in parts[:-1]:
            parent = parent[part]
        parent[parts[-1]] = value
    return result


def legal_relations(params: dict, relations: list[dict]) -> bool:
    """预先声明的跨参数合法关系；真实程序错误不当作正常低分吞掉。"""
    ops = {'<': lambda a, b: a < b, '<=': lambda a, b: a <= b,
           '>': lambda a, b: a > b, '>=': lambda a, b: a >= b,
           '==': lambda a, b: a == b, '!=': lambda a, b: a != b}
    return all(ops[r['op']](get_value(params, r['left']),
                           get_value(params, r['right']) if 'right' in r else r['value'])
               for r in relations)


def _positive_int(value, name: str) -> int:
    if type(value) is not int or value < 1:
        raise ValueError(f'{name} 必须为正整数')
    return value


def normalize_config(raw: dict, root: Path = ROOT) -> dict:
    """在看成绩前固定全部选择；使用纯交易日历核对前瞻间隔。"""
    cfg = copy.deepcopy(raw)
    allowed = {'app', 'symbols', 'data_dir', 'train', 'windows', 'final', 'review',
               'calendar', 'evaluation', 'space', 'relations', 'search', 'policy',
               'adoption', 'baseline_params', 'causality_note', 'parameter_notes', 'bo_params', 'shrinkage'}
    if set(cfg) - allowed:
        raise ValueError(f'未知配置字段：{sorted(set(cfg) - allowed)}')
    if not re.fullmatch(r'[a-z][a-z0-9_]*', cfg['app']):
        raise ValueError('app 必须是 path2_apps 下的包名')
    mod = importlib.import_module('path2_apps.' + cfg['app'])
    live = mod.load_params().to_dict()
    cfg.setdefault('baseline_params', live)
    # 显式传基准时也必须是完整字段，不能靠 Params.from_dict 默认补缺。
    def keys(obj, prefix=''):
        return {prefix + k for k, v in obj.items() if not isinstance(v, dict)} | {
            p for k, v in obj.items() if isinstance(v, dict) for p in keys(v, prefix + k + '.')}
    if keys(cfg['baseline_params']) != keys(live):
        raise ValueError('baseline_params 必须是完整现役快照')
    if cfg['baseline_params'] != live:
        raise ValueError('初始 baseline_params 与当前正式参数不一致；重新核对后开新一轮')
    mod.build_pattern(mod.Params.from_dict(cfg['baseline_params'], strict=True))
    control = importlib.import_module('path2_apps.bo_only')
    # 有 bo 节点时冻结原参数的简单突破，搜索时不随候选 bo 改动。
    cfg.setdefault('bo_params', {'bo': copy.deepcopy(cfg['baseline_params']['bo'])}
                   if 'bo' in cfg['baseline_params'] else control.load_params().to_dict())
    control_params = control.Params.from_dict(cfg['bo_params'], strict=True)
    control.build_pattern(control_params)
    cfg['bo_params'] = control_params.to_dict()
    symbols = cfg['symbols']
    if (not symbols or len(symbols) != len(set(symbols)) or
            any(not isinstance(s, str) or not re.fullmatch(r'[A-Za-z0-9^][A-Za-z0-9.^_-]*', s)
                for s in symbols)):
        raise ValueError('symbols 必须是无重复的股票名列表，不能包含路径')
    cfg['symbols'] = sorted(symbols)
    cfg['data_dir'] = str(Path(cfg.get('data_dir',
        '/home/yu/PycharmProjects/Trade_Strategy/datasets/pkls')).expanduser().resolve())
    if not cfg.get('causality_note', '').strip():
        raise ValueError('须先核对买点当天能否知道全部成立条件，填写 causality_note')
    ev = cfg.setdefault('evaluation', {})
    if set(ev) - {'horizon', 'k'}:
        raise ValueError('evaluation 只允许 horizon/k')
    ev.setdefault('horizon', 20)
    ev.setdefault('k', 5.0)
    _positive_int(ev['horizon'], 'horizon')
    if type(ev['k']) not in (int, float) or not math.isfinite(ev['k']) or ev['k'] <= 0:
        raise ValueError('k 必须是有限正数')
    cfg.setdefault('relations', [])
    for rel in cfg['relations']:
        if (set(rel) not in ({'left', 'op', 'right'}, {'left', 'op', 'value'}) or
                rel['op'] not in {'<', '<=', '>', '>=', '==', '!='}):
            raise ValueError('关系必须是 left/op/right 或 left/op/value')
    if not legal_relations(cfg['baseline_params'], cfg['relations']):
        raise ValueError('现役参数不满足声明的合法关系')
    if not cfg.get('space'):
        raise ValueError('必须声明至少一个待调参数')
    for key, spec in cfg['space'].items():
        current = get_value(cfg['baseline_params'], key)
        if isinstance(current, dict):
            raise ValueError('搜索路径必须指向单个参数')
        if not cfg.get('parameter_notes', {}).get(key, '').strip():
            raise ValueError(f'{key} 缺少参数含义与范围依据')
        kind = spec['type']
        if kind == 'categorical':
            if set(spec) != {'type', 'choices'} or not spec['choices']:
                raise ValueError('categorical 只接受非空 choices')
            if current not in spec['choices']:
                raise ValueError(f'{key} 的选项须包含现役值')
        elif kind in {'int', 'float'}:
            if type(current) not in (int, float) or (kind == 'int' and type(current) is not int):
                raise ValueError(f'{key} 搜索类型与现役参数类型不一致')
            if set(spec) - {'type', 'low', 'high', 'step', 'log'}:
                raise ValueError(f'{key} 存在未知分布字段')
            for bound in ['low', 'high']:
                if type(spec[bound]) not in (int, float) or not math.isfinite(spec[bound]):
                    raise ValueError(f'{key} 边界必须是有限数')
                if kind == 'int' and type(spec[bound]) is not int:
                    raise ValueError(f'{key} 整数分布须用整数边界')
            if not spec['low'] <= current <= spec['high']:
                raise ValueError(f'{key} 范围须包含现役值')
            if 'log' in spec and type(spec['log']) is not bool:
                raise ValueError(f'{key} log 必须是布尔值')
            if 'step' in spec and (type(spec['step']) not in (int, float) or
                                  not math.isfinite(spec['step']) or spec['step'] <= 0 or
                                  (kind == 'int' and type(spec['step']) is not int)):
                raise ValueError(f'{key} step 非法')
            if spec.get('log', False) and (spec['low'] <= 0 or
                    (kind == 'float' and 'step' in spec) or
                    (kind == 'int' and spec.get('step', 1) != 1)):
                raise ValueError(f'{key} log 与边界/step 不兼容')
        else:
            raise ValueError(f'不支持的参数类型：{kind}')
    sr = cfg.setdefault('search', {})
    if set(sr) - {'trials', 'seed'}:
        raise ValueError('search 只允许 trials/seed；方向评分枚举完整窗口，不再配置重抽次数')
    for key, default in [('trials', 80)]:
        sr.setdefault(key, default)
        _positive_int(sr[key], key)
    sr.setdefault('seed', 42)
    if type(sr['seed']) is not int or not 0 <= sr['seed'] < 2**32:
        raise ValueError('seed 必须是 0..2**32-1 整数')
    windows = cfg.setdefault('windows', {})
    if set(windows) - {'window_days', 'half_life_days', 'recent_days'}:
        raise ValueError('未知 windows 字段')
    for key, default in [('window_days', 21), ('half_life_days', 252), ('recent_days', 126)]:
        windows.setdefault(key, default)
        _positive_int(windows[key], key)
    cfg['policy'] = normalize_policy(cfg.get('policy', {}))
    cfg['shrinkage'] = normalize_shrinkage(cfg.get('shrinkage'))
    cfg.setdefault('adoption', {'allow_provisional': True, 'review_inconclusive': 'rollback'})
    if cfg['adoption'] != {'allow_provisional': True, 'review_inconclusive': 'rollback'}:
        raise ValueError('本版采用规则固定为允许暂用；预定复核仍不足则恢复原参数')
    for key in ['train', 'final', 'review']:
        window = cfg[key]
        if set(window) - {'history_start', 'start', 'end', 'label_end'} or not {'start', 'end', 'label_end'} <= set(window):
            raise ValueError(f'{key} 必须指定 start/end/label_end，可显式指定 history_start')
        window.setdefault('history_start', window['start'])
        for value in window.values():
            if date.fromisoformat(value).isoformat() != value:
                raise ValueError('日期须为 YYYY-MM-DD')
        if not window['history_start'] <= window['start'] <= window['end'] < window['label_end']:
            raise ValueError(f'{key} 日期顺序不正确')
    if not (cfg['train']['label_end'] < cfg['final']['history_start'] and
            cfg['final']['label_end'] < cfg['review']['history_start']):
        raise ValueError('训练、最后验证、复核的全部回看及前瞻数据不能重叠')
    if 'calendar' not in cfg:
        import pandas_market_calendars as mcal
        # 纯日期安排，不从行情推断哪天的结果值得留下。
        dates = mcal.get_calendar('NYSE').valid_days(
            start_date='1950-01-01', end_date=cfg['review']['label_end'])
        cfg['calendar'] = [d.date().isoformat() for d in dates]
    calendar = cfg['calendar']
    if calendar != sorted(set(calendar)):
        raise ValueError('calendar 必须有序且无重复')
    for d in calendar:
        date.fromisoformat(d)
    for stage in ['train', 'final', 'review']:
        w = cfg[stage]
        if sum(w['start'] <= d <= w['end'] for d in calendar) < windows['window_days']:
            raise ValueError(f'{stage} 的买入日历少于完整评分窗口长度')
        if sum(w['end'] < d <= w['label_end'] for d in calendar) < ev['horizon']:
            raise ValueError(f'{stage} 的 label_end 未覆盖完整后续交易日数')
    return cfg


def ledger_for(cfg: dict, root: Path = ROOT) -> UsageLedger:
    directory = Path(os.environ.get('TUNE_LEDGER_DIR', str(root / 'docs/sample_usage')))
    return UsageLedger(directory / f"{cfg['app']}.v3.jsonl",
                       legacy_path=directory / f"{cfg['app']}.jsonl", calendar=cfg['calendar'])


def evaluator(cfg: dict, stage: str, source: str) -> DailyEvaluator:
    required_end = max(day for day in cfg['calendar'] if day <= cfg[stage]['label_end'])
    return DailyEvaluator('path2_apps.' + cfg['app'], cfg['baseline_params'],
                          Path(cfg['data_dir']), cfg['symbols'], **cfg[stage],
                          **cfg['evaluation'], code_token=source,
                          required_price_end=required_end)


def usage_window(cfg: dict, stage: str) -> dict:
    """账本包括回看输入，不只登记产出买点的日期。"""
    window = cfg[stage]
    return {'start': window['history_start'], 'end': window['end'],
            'label_end': window['label_end']}


def make_plan(cfg: dict, baseline: pd.DataFrame) -> WindowPlan:
    return WindowPlan(baseline, horizon=cfg['evaluation']['horizon'], **cfg['windows'],
                      shrinkage=cfg['shrinkage'])


def propose(trial, space: dict) -> dict:
    values = {}
    for name, spec in space.items():
        kw = {k: v for k, v in spec.items() if k != 'type'}
        values[name] = getattr(trial, 'suggest_' + spec['type'])(name, **kw)
    return values


def prefer_candidate(result: dict, current: dict, reference: dict) -> bool:
    """在同一合格集合按唯一方向主分排名；平分保留先出现的原参数。"""
    return bool(result['feasible'] and
                (not current['feasible'] or result['score'] > current['score'] + SCORE_EPSILON))


def run_search(config_path: Path, run_dir: Path, root: Path = ROOT) -> dict:
    cfg = normalize_config(json.loads(config_path.read_text()), root)
    run_dir.mkdir(parents=True, exist_ok=False)
    run_id = uuid.uuid4().hex
    cfg_hash = canonical_hash(cfg)
    code = source_hash(root)
    usage = ledger_for(cfg, root)
    usage.reserve(cfg['app'], run_id, [dict(stage=s, **usage_window(cfg, s)) for s in ['final', 'review']], cfg_hash)
    frozen = {'config': cfg, 'config_hash': cfg_hash, 'run_id': run_id, 'source_hash': code}
    write_json(run_dir / 'config.json', seal(frozen))
    usage.claim(cfg['app'], run_id, 'training', **usage_window(cfg, 'train'), config_hash=cfg_hash)
    ev = evaluator(cfg, 'train', code)
    baseline = ev.baseline
    ref_all = ev.evaluate(cfg['baseline_params'])
    ref = ref_all
    if baseline.empty:
        payload = {'run_id': run_id, 'config_hash': cfg_hash, 'source_hash': code,
                   'candidate_params': cfg['baseline_params'], 'baseline_params': cfg['baseline_params'],
                   'ready_for_final': False, 'trials_completed': 0,
                   'reason': '训练范围没有可评估日，维持原参数并释放未消费的验证数据'}
        write_json(run_dir / 'manifest.json', seal(payload))
        usage.abandon(cfg['app'], run_id, cfg_hash)
        return payload
    plan = make_plan(cfg, baseline)
    bo = ev.evaluate_control('path2_apps.bo_only', cfg['bo_params'])
    bo_assess = assess(bo, bo, baseline, plan, cfg['policy'])
    write_json(run_dir / 'bo.json', bo_assess)
    bo.to_csv(run_dir / 'bo-days.csv', index=False)
    ref_assess = assess(ref, ref, baseline, plan, cfg['policy'])
    write_json(run_dir / 'reference.json', ref_assess)
    ref_all.to_csv(run_dir / 'reference-days.csv', index=False)
    chosen = {'params': cfg['baseline_params'], 'assessment': ref_assess, 'trial': None}
    # constraints_func 只使用已经写入的约束，未完成 trial 不会被当成合格。
    sampler = optuna.samplers.TPESampler(seed=cfg['search']['seed'],
        constraints_func=lambda t: t.user_attrs['constraints'])
    study = optuna.create_study(direction='maximize', sampler=sampler,
        storage='sqlite:///' + str((run_dir / 'study.sqlite3').resolve()), study_name=run_id)
    def objective(trial):
        nonlocal chosen
        params = with_values(cfg['baseline_params'], propose(trial, cfg['space']))
        if not legal_relations(params, cfg['relations']):
            trial.set_user_attr('constraints', [1.0] * len(ref_assess['constraints']))
            trial.set_user_attr('reason', '预先声明的参数合法关系不满足')
            return -1e100
        rows = ev.evaluate(params)
        result = assess(rows, ref, baseline, plan, cfg['policy'])
        trial.set_user_attr('constraints', result['constraints'])
        trial.set_user_attr('assessment', result)
        # 机会等要求达标后仅按统一方向主分；相同分数保留先出现者。
        if prefer_candidate(result, chosen['assessment'], ref_assess):
            chosen = {'params': params, 'assessment': result, 'trial': trial.number}
        return result['score']
    study.enqueue_trial({key: get_value(cfg['baseline_params'], key) for key in cfg['space']})
    study.optimize(objective, n_trials=cfg['search']['trials'], n_jobs=1)
    selected_all = ev.evaluate(chosen['params'])
    selected = selected_all
    train_compare = comparison(selected, ref, baseline, plan, cfg['policy'])
    changed = chosen['params'] != cfg['baseline_params']
    worth = bool(changed and chosen['assessment']['feasible'] and
                 train_compare['score_difference'] is not None and train_compare['score_difference'] > SCORE_EPSILON)
    payload = {'run_id': run_id, 'config_hash': cfg_hash, 'source_hash': code,
               'candidate_params': chosen['params'], 'baseline_params': cfg['baseline_params'],
               'trial': chosen['trial'], 'trials_completed': len(study.trials),
               'assessment': chosen['assessment'], 'training_comparison': train_compare,
               'score_version': 'close-direction-window-v2', 'score_mode': plan.score_mode,
               'bo_control': bo_assess,
               'all_training_counts': {'reference': ref_all.attrs, 'candidate': selected_all.attrs},
               'ready_for_final': worth,
               'reason': '固定一个候选，最后验证仅判断是否采用' if worth else '维持原参数，不打开最后验证数据'}
    selected_all.to_csv(run_dir / 'candidate-days.csv', index=False)
    write_json(run_dir / 'manifest.json', seal(payload))
    if not worth:
        usage.abandon(cfg['app'], run_id, cfg_hash)
    return payload


def run_check(run_dir: Path, stage: str, root: Path = ROOT) -> dict:
    if stage not in {'final', 'review'}:
        raise ValueError('只允许 final/review')
    frozen = read_sealed(run_dir / 'config.json')
    manifest = read_sealed(run_dir / 'manifest.json')
    cfg = frozen['config']
    if canonical_hash(cfg) != frozen['config_hash'] or any(
            manifest[k] != frozen[k] for k in ['run_id', 'config_hash', 'source_hash']):
        raise ValueError('参数、规则与冻结记录不一致')
    if not manifest['ready_for_final']:
        raise ValueError('本轮没有值得最后验证的候选')
    result_path = run_dir / f'{stage}.json'
    if result_path.exists():
        # 只读已保存结果，不再读取数据；同一窗口不能拿来另挑参数。
        result = read_sealed(result_path)
        if result['manifest_hash'] != canonical_hash(manifest):
            raise ValueError('结果对应另一份候选')
        return result
    if source_hash(root) != frozen['source_hash']:
        raise ValueError('检测或评价代码已变化，不能沿用冻结结果')
    previous = None
    if stage == 'review':
        previous = read_sealed(run_dir / 'final.json')['decision']
        if previous['status'] != 'provisional':
            raise ValueError('本入口只复核本轮的暂用结论')
    today = datetime.now(ZoneInfo('America/New_York')).date().isoformat()
    if today <= cfg[stage]['label_end']:
        raise ValueError('尚未到预定复核/验证时点；等待完整数据，不提前反复查看')
    usage = ledger_for(cfg, root)
    usage.claim(cfg['app'], frozen['run_id'], stage, **usage_window(cfg, stage), config_hash=frozen['config_hash'])
    ev = evaluator(cfg, stage, frozen['source_hash'])
    ref = ev.evaluate(manifest['baseline_params'])
    candidate = ev.evaluate(manifest['candidate_params'])
    if ev.baseline.empty:
        metrics = {'hard_constraints_passed': False, 'score_difference': None,
                   'improvement_lower': None, 'improvement_upper': None,
                   'evidence_sufficient': False,
                   'summaries': {'candidate': summary(candidate), 'reference': summary(ref),
                                 'baseline': summary(ev.baseline)},
                   'reason': '整个预定范围没有可评估日，不能作表现比较'}
    else:
        baseline = ev.baseline
        plan = make_plan(cfg, baseline)
        metrics = comparison(candidate, ref, baseline, plan, cfg['policy'])
        bo = ev.evaluate_control('path2_apps.bo_only', cfg['bo_params'])
        metrics['bo_control'] = assess(bo, bo, baseline, plan, cfg['policy'])
        bo.to_csv(run_dir / f'{stage}-bo-days.csv', index=False)
    decision = adoption(metrics, cfg['adoption'], stage=stage, previous_status=previous)
    result = {'manifest_hash': canonical_hash(manifest), 'stage': stage,
              'window': cfg[stage], 'metrics': metrics, 'decision': decision,
              'counts': {'reference': ref.attrs, 'candidate': candidate.attrs},
              'candidate_params': manifest['candidate_params'], 'baseline_params': manifest['baseline_params'],
              'review_window': cfg['review'], 'live_params_written': False}
    candidate.to_csv(run_dir / f'{stage}-candidate-days.csv', index=False)
    ref.to_csv(run_dir / f'{stage}-reference-days.csv', index=False)
    write_json(result_path, seal(result))
    if decision['status'] != 'provisional':
        usage.abandon(cfg['app'], frozen['run_id'], frozen['config_hash'])
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    search = sub.add_parser('search')
    search.add_argument('--config', type=Path, required=True)
    search.add_argument('--run-dir', type=Path, required=True)
    for name in ['validate', 'review', 'status', 'abandon']:
        p = sub.add_parser(name)
        p.add_argument('--run-dir', type=Path, required=True)
    args = parser.parse_args()
    if args.command == 'search':
        result = run_search(args.config, args.run_dir)
        result = {k: result[k] for k in ['run_id', 'ready_for_final', 'reason', 'trials_completed']}
    elif args.command in {'validate', 'review'}:
        full = run_check(args.run_dir, 'final' if args.command == 'validate' else 'review')
        result = {'stage': full['stage'], 'decision': full['decision'], 'live_params_written': False}
    elif args.command == 'abandon':
        frozen = read_sealed(args.run_dir / 'config.json')
        ledger_for(frozen['config']).abandon(frozen['config']['app'], frozen['run_id'], frozen['config_hash'])
        result = {'status': 'closed', 'reason': '本轮已终止；未读取的预留区间已释放，已读取记录仍保留'}
    else:
        result = {path.stem: read_sealed(path) for path in [args.run_dir / (name + '.json')
                  for name in ['manifest', 'final', 'review']] if path.exists()}
    print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))


if __name__ == '__main__':
    main()
