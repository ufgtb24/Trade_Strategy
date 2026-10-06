"""simplicity 红队的三处行为复现（合成数据、临时账本，不读真实行情）。

运行：从仓库根
    uv run python -m pytest -q docs/research/2026-10-05_tune-gates-v3-design-review/repro/simplicity_repro.py

R1 复核必撤回：即使新参数在复核段完美改善，复核结论也恒为 rollback。
R2 行情未更新就跑最后验证：失败但使用记录已写，第二次再跑被拒，本轮最后验证永久作废。
R3 搜索后任一 path2/ 或 path2_apps/ 的 .py 变动，最后验证即被拒；冻结记录里没有 git 提交号可回退。
"""
from pathlib import Path
import json
import sys
from types import SimpleNamespace

import pandas as pd
import pytest

SKILL = Path(__file__).resolve().parents[4] / '.claude/skills/tune-gates-v3/scripts'
sys.path.insert(0, str(SKILL))
import run  # noqa: E402
from governance import adoption, UsageError  # noqa: E402


@pytest.fixture
def setup(tmp_path, monkeypatch):
    """与 tests/test_run.py 的装置同构：S4~S7 全部先上，S0~S3 全部先下。"""
    class Params:
        def __init__(self, d):
            self.d = d

        @classmethod
        def from_dict(cls, d, strict=False):
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
           'parameter_notes': {'gate.cutoff': '合成'},
           'causality_note': '合成',
           'search': {'trials': 8, 'seed': 9}}
    state = {'stale_final_once': False}

    class Evaluator:
        def __init__(self, config, stage):
            if stage == 'final' and state['stale_final_once']:
                state['stale_final_once'] = False
                # 与 daily.DailyEvaluator._prepare 的真实报错同文
                raise ValueError('S0 行情尚未到齐：最新日 2020-04-30，要求至少到 2020-05-08')
            window = config[stage]
            dates = pd.bdate_range(window['start'], window['end'])
            self.baseline = pd.DataFrame([
                dict(symbol=s, date=d.date().isoformat(), upside=(.02 if i < 4 else .12),
                     up=int(i >= 4), down=int(i < 4), both=0, none=0, M=.01, drawdown=-.03)
                for d in dates for i, s in enumerate(config['symbols'])])

        def evaluate(self, params):
            frame = self.baseline
            if params['gate']['cutoff'] > 0.05:
                frame = frame.loc[frame.symbol.isin(['S4', 'S5', 'S6', 'S7'])]
            result = frame.copy()
            result.attrs = {'detected_count': len(result), 'eligible_count': len(result),
                            'unavailable_count': 0}
            return result

        def evaluate_control(self, app_module, params):
            return self.baseline.copy()

    monkeypatch.setattr(run, 'evaluator', lambda config, stage, source: Evaluator(config, stage))
    path = tmp_path / 'input.json'
    path.write_text(json.dumps(cfg))
    return path, tmp_path / 'run', state


def test_R1_review_always_rolls_back_even_for_perfect_improvement(setup):
    path, out, _ = setup
    assert run.run_search(path, out)['ready_for_final']
    final = run.run_check(out, 'final')
    assert final['decision']['status'] == 'provisional'
    review = run.run_check(out, 'review')
    m = review['metrics']
    # 复核段：新参数方向分 1.0（全部先上），原参数 0.0，所有要求通过……
    assert m['new_direction_score'] == pytest.approx(1.0)
    assert m['hard_constraints_passed'] is True
    # ……结论仍是恢复原参数：确认分支不可达，因为评分层恒给 evidence_sufficient=False。
    assert m['evidence_sufficient'] is False
    assert review['decision']['status'] == 'rollback'


def test_R1b_adoption_review_branch_has_no_keep_outcome():
    """直接枚举：评分层给出的任何 metrics 在复核时都只能 rollback。"""
    for diff in [-0.5, 0.0, 1e-6, 0.3, 1.0]:
        for passed in [True, False]:
            metrics = {'hard_constraints_passed': passed, 'evidence_sufficient': False,
                       'score_difference': diff, 'improvement_lower': None, 'improvement_upper': None}
            out = adoption(metrics, {'allow_provisional': True, 'review_inconclusive': 'rollback'},
                           stage='review', previous_status='provisional')
            assert out['status'] == 'rollback'


def test_R2_stale_price_files_burn_final_window_permanently(setup):
    path, out, state = setup
    assert run.run_search(path, out)['ready_for_final']
    state['stale_final_once'] = True
    with pytest.raises(ValueError, match='尚未到齐'):
        run.run_check(out, 'final')          # 第一次：行情文件没更新，失败
    assert not (out / 'final.json').exists()  # 没有任何结果被看到
    with pytest.raises(UsageError, match='已经消耗'):
        run.run_check(out, 'final')          # 补齐行情后第二次：被拒，本轮最后验证作废


def test_R3_any_code_change_blocks_validation_without_recovery_handle(setup, monkeypatch):
    path, out, _ = setup
    run.run_search(path, out)
    frozen = json.loads((out / 'config.json').read_text())['payload']
    assert set(frozen) == {'config', 'config_hash', 'run_id', 'source_hash'}  # 没有 git 提交号
    monkeypatch.setattr(run, 'source_hash', lambda root=None: '0' * 64)
    with pytest.raises(ValueError, match='代码已变化'):
        run.run_check(out, 'final')
