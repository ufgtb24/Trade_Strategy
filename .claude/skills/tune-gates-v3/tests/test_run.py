"""合成逐日结果联通真实 Optuna、方向评分和使用记录；不访问市场文件。"""
from pathlib import Path
import json
import sys
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import run


def test_same_direction_objective_selects_even_when_upside_declines():
    def result(raw, score):
        return {'statistics': {'raw_median_upside': raw}, 'score': score, 'feasible': True}
    reference = result(.20, .05)
    stable_but_worse = result(.15, .14)
    improving = result(.25, .10)
    chosen = reference
    for proposal in [stable_but_worse, improving]:
        if run.prefer_candidate(proposal, chosen, reference):
            chosen = proposal
    assert chosen is stable_but_worse


@pytest.fixture
def setup(tmp_path, monkeypatch):
    class Params:
        def __init__(self, d):
            self.d = d

        @classmethod
        def from_dict(cls, d, strict=False):
            assert strict
            return cls(d)

        def to_dict(self):
            return self.d

    initial = {'gate': {'cutoff': 0.0, 'untouched': 73}}
    app = SimpleNamespace(Params=Params, load_params=lambda: Params(initial), build_pattern=lambda p: p)
    monkeypatch.setitem(sys.modules, 'path2_apps.synthetic_v3', app)
    monkeypatch.setenv('TUNE_LEDGER_DIR', str(tmp_path / 'usage'))
    days = pd.bdate_range('2018-01-01', '2022-01-01')
    cfg = {'app': 'synthetic_v3', 'symbols': [f'S{i}' for i in range(8)],
           'data_dir': str(tmp_path / 'never-open'),
           'train': {'start': '2019-01-01', 'end': '2019-10-01', 'label_end': '2019-10-10'},
           'final': {'start': '2020-01-01', 'end': '2020-05-01', 'label_end': '2020-05-10'},
           'review': {'start': '2021-01-01', 'end': '2021-05-01', 'label_end': '2021-05-10'},
           'calendar': [d.date().isoformat() for d in days],
           'evaluation': {'horizon': 2, 'k': 5.0},
           'space': {'gate.cutoff': {'type': 'float', 'low': 0.0, 'high': 0.9}},
           'parameter_notes': {'gate.cutoff': '合成测试：提高数值只保留标记较高的买点'},
           'causality_note': '测试装置直接提供已知逐日结果，不声称是真实走势的时序证明',
           'search': {'trials': 8, 'seed': 9}}
    calls = []

    class Evaluator:
        def __init__(self, config, stage):
            calls.append(stage)
            self.stage = stage
            window = config[stage]
            dates = pd.bdate_range(window['start'], window['end'])
            self.baseline = pd.DataFrame([
                dict(symbol=s, date=d.date().isoformat(), upside=(.02 if i < 4 else .12),
                     up=int(i >= 4), down=int(i < 4), both=0, none=0, M=.01, drawdown=-.03)
                for d in dates for i, s in enumerate(config['symbols'])])

        def evaluate(self, params):
            assert params['gate']['untouched'] == 73
            frame = self.baseline
            if params['gate']['cutoff'] > 0.05:
                frame = frame.loc[frame.symbol.isin(['S4', 'S5', 'S6', 'S7'])]
            result = frame.copy()
            result.attrs = {'detected_count': len(result), 'eligible_count': len(result), 'unavailable_count': 0}
            return result

        def evaluate_control(self, app_module, params):
            assert app_module == 'path2_apps.bo_only'
            return self.baseline.copy()

    monkeypatch.setattr(run, 'evaluator', lambda config, stage, source: Evaluator(config, stage))
    config_path = tmp_path / 'input.json'
    config_path.write_text(json.dumps(cfg))
    return cfg, config_path, tmp_path / 'run', calls, app


def test_real_optuna_search_freezes_then_one_validation(setup):
    cfg, path, out, calls, app = setup
    result = run.run_search(path, out)
    assert result['ready_for_final']
    assert result['candidate_params']['gate']['cutoff'] > .05
    assert calls == ['train']  # 搜索没有实例化最后验证数据。
    assert result['training_comparison']['score_difference'] == pytest.approx(1.0)
    final = run.run_check(out, 'final')
    # 当前没有经过校准的确认规则，不能把高方向分冒充改善已确认。
    assert final['decision']['status'] == 'provisional'
    assert final['live_params_written'] is False
    assert app.load_params().to_dict()['gate']['cutoff'] == 0.0
    assert calls == ['train', 'final']
    assert run.run_check(out, 'final') == final
    assert calls == ['train', 'final']  # 再调用只读保存结果。
    review = run.run_check(out, 'review')
    assert review['decision']['status'] == 'rollback'
    assert calls == ['train', 'final', 'review']
    assert run.run_check(out, 'review') == review
    records = [json.loads(line) for line in (out.parent / 'usage/synthetic_v3.v3.jsonl').read_text().splitlines()]
    assert sum(r['kind'] == 'claim' and r['stage'] == 'final' for r in records) == 1


def test_no_improvement_preserves_unused_final_for_next_run(setup):
    cfg, path, out, calls, _ = setup
    cfg['space']['gate.cutoff']['high'] = .01
    path.write_text(json.dumps(cfg))
    result = run.run_search(path, out)
    assert result['ready_for_final'] is False
    with pytest.raises(ValueError, match='没有值得'):
        run.run_check(out, 'final')
    assert calls == ['train']
    run.run_search(path, out.parent / 'another-run')
    assert calls == ['train', 'train']


def test_manifest_tamper_refused_before_evaluation(setup):
    _, path, out, calls, _ = setup
    run.run_search(path, out)
    manifest_path = out / 'manifest.json'
    record = json.loads(manifest_path.read_text())
    record['payload']['candidate_params']['gate']['cutoff'] = .1
    manifest_path.write_text(json.dumps(record))
    with pytest.raises(ValueError, match='已改变'):
        run.run_check(out, 'final')
    assert calls == ['train']


def test_guard_refuses_used_final_before_evaluator(setup):
    _, path, out, calls, _ = setup
    run.run_search(path, out)
    run.run_check(out, 'final')
    with pytest.raises(ValueError):
        run.run_search(path, out.parent / 'next-run')
    assert calls == ['train', 'final']


@pytest.mark.parametrize('mutation', [
    lambda c: c['policy'].update(min_buy_days=float('nan')),
    lambda c: c['train'].update(label_end=c['final']['start']),
    lambda c: c.update(causality_note=''),
    lambda c: c.update(baseline_params={'gate': {'cutoff': 0.0}}),
    lambda c: c['space']['gate.cutoff'].update(low=.1),
])
def test_invalid_config_refused_before_any_labels(setup, mutation):
    cfg, path, out, calls, _ = setup
    cfg['policy'] = {}
    mutation(cfg)
    path.write_text(json.dumps(cfg))
    with pytest.raises((ValueError, KeyError)):
        run.run_search(path, out)
    assert not calls


def test_empty_final_saves_rejection_after_consuming_once(setup, monkeypatch):
    _, path, out, calls, _ = setup
    run.run_search(path, out)
    original = run.evaluator

    def no_data(config, stage, source):
        ev = original(config, stage, source)
        ev.baseline = ev.baseline.iloc[:0]
        return ev

    monkeypatch.setattr(run, 'evaluator', no_data)
    result = run.run_check(out, 'final')
    assert result['decision']['status'] == 'reject'
    assert result['metrics']['score_difference'] is None
    assert run.run_check(out, 'final') == result
    assert calls == ['train', 'final']


def test_empty_training_releases_reserved_data(setup, monkeypatch):
    _, path, out, calls, _ = setup
    original = run.evaluator

    def no_data(config, stage, source):
        ev = original(config, stage, source)
        ev.baseline = ev.baseline.iloc[:0]
        return ev

    monkeypatch.setattr(run, 'evaluator', no_data)
    result = run.run_search(path, out)
    assert not result['ready_for_final']
    assert result['trials_completed'] == 0
    monkeypatch.setattr(run, 'evaluator', original)
    assert run.run_search(path, out.parent / 'later')['ready_for_final']


def test_history_input_is_part_of_exposure_and_frozen_config(setup):
    cfg, path, out, calls, _ = setup
    cfg['train']['history_start'] = '2018-10-01'
    path.write_text(json.dumps(cfg))
    run.run_search(path, out)
    records = [json.loads(line) for line in (out.parent / 'usage/synthetic_v3.v3.jsonl').read_text().splitlines()]
    training = next(r for r in records if r['kind'] == 'claim')
    assert training['start'] == '2018-10-01'
    frozen = run.read_sealed(out / 'config.json')['config']
    assert frozen['train']['start'] == '2019-01-01'
    assert frozen['train']['history_start'] == '2018-10-01'


def test_final_history_must_not_reuse_training_suffix(setup):
    cfg, path, out, calls, _ = setup
    cfg['final']['history_start'] = '2019-10-10'
    path.write_text(json.dumps(cfg))
    with pytest.raises(ValueError, match='回看及前瞻'):
        run.run_search(path, out)
    assert not calls


def test_machine_rounding_is_not_an_improvement():
    old = {'feasible': True, 'score': 0.5}
    rounded = {'feasible': True, 'score': 0.5 + 1e-15}
    assert not run.prefer_candidate(rounded, old, old)


@pytest.mark.parametrize('settings', [{'enabled': 1}, {'tau': 0}, {'bandwidth': -1}, {'typo': True}])
def test_shrinkage_config_rejected_before_any_labels(setup, settings):
    cfg, path, out, calls, _ = setup
    cfg['shrinkage'] = settings
    path.write_text(json.dumps(cfg))
    with pytest.raises(ValueError):
        run.run_search(path, out)
    assert calls == []


def test_enabled_shrinkage_is_frozen_across_optuna_validation_and_review(setup, monkeypatch):
    cfg, path, out, calls, _ = setup
    cfg['shrinkage'] = {'enabled': True, 'tau': .1, 'bandwidth': 2}
    cfg['search']['trials'] = 4
    original = run.evaluator

    def variable_data(config, stage, source):
        ev = original(config, stage, source)
        frame = ev.baseline
        # 周期不与21日窗口重合，确保窗口差值本身有可识别的时间变化。
        date_id = pd.factorize(frame.date, sort=True)[0]
        reverse = frame.symbol.isin(['S4', 'S5', 'S6', 'S7']) & (date_id % 29 < 5)
        frame.loc[reverse, ['up', 'down']] = [0, 1]
        return ev

    monkeypatch.setattr(run, 'evaluator', variable_data)
    path.write_text(json.dumps(cfg))
    result = run.run_search(path, out)
    assert result['ready_for_final']
    assert result['score_mode'] == 'direction_window_shrinkage_experimental'
    stats = result['assessment']['statistics']
    assert 0 < stats['shrinkage']['factor'] < 1
    assert stats['score'] < stats['raw_direction_score']
    frozen = run.read_sealed(out / 'config.json')['config']
    assert frozen['shrinkage'] == cfg['shrinkage']
    # 改外部输入不影响已冻结轮次；最终评价不能静默切回基础分。
    cfg['shrinkage']['enabled'] = False
    path.write_text(json.dumps(cfg))
    final = run.run_check(out, 'final')
    assert final['metrics']['score_mode'] == result['score_mode']
    assert final['metrics']['shrinkage']['candidate']['enabled'] is True
    assert final['decision']['status'] == 'provisional'
    assert run.run_check(out, 'final') == final
    review = run.run_check(out, 'review')
    assert review['metrics']['score_mode'] == result['score_mode']
    assert review['decision']['status'] == 'rollback'
    assert calls == ['train', 'final', 'review']
