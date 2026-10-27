import numpy as np
from lottery.experiments import probability_vectors, evaluate_history
from lottery.predict import generate_tickets

def history(n):
    return [dict(generate_tickets('ssq', i, 1)[0], issue=f'2025{i+1:03d}', prizes={}, rule_version='ssq-classic') for i in range(n)]

def test_uniform_baseline_matches_combinatorics():
    p=probability_vectors('ssq', history(160), 'uniform')
    assert np.allclose(p['front'], 6/33)
    assert np.allclose(p['back'], 1/16)

def test_frequency_probabilities_use_only_given_past():
    rows=history(170)
    original=probability_vectors('ssq',rows[:160],'frequency')
    rows[169]['front']=[28,29,30,31,32,33]
    updated=probability_vectors('ssq',rows[:160],'frequency')
    assert np.allclose(original['front'],updated['front'])

def test_regularized_calibrated_model_returns_valid_marginals():
    p=probability_vectors('ssq', history(160), 'logistic')
    assert all(0 < x < 1 for x in p['front'])
    assert abs(sum(p['front'])-6) < 1e-6
    assert abs(sum(p['back'])-1) < 1e-6

def test_walk_forward_marks_cutoffs_and_equal_budgets():
    report=evaluate_history('ssq',history(165),test_count=3,simulations=10)
    assert report['evaluation_periods']==3
    assert all(row['cost']==30 for row in report['strategies'])
    assert all(row['cutoff_issue'] < row['target_issue'] for row in report['forecast_audit'])
    assert report['production_strategy']=='uniform-v1'


def test_point_in_time_backtest_never_falls_back_to_current_history():
    import pytest
    with pytest.raises(ValueError,match='visible history'):
        evaluate_history('ssq',history(161),test_count=1,simulations=1,history_provider=lambda actual:[])


def test_point_in_time_backtest_rejects_target_leakage():
    import pytest
    rows=history(161)
    with pytest.raises(ValueError,match='visible history'):
        evaluate_history('ssq',rows,test_count=1,simulations=1,history_provider=lambda actual:rows)


def test_point_in_time_mode_retains_training_snapshot_and_matches_visible_data():
    rows=history(161)
    report=evaluate_history('ssq',rows,test_count=1,simulations=1,history_provider=lambda actual:rows[:160])
    assert report['data_mode']=='retained-as-of'
    assert report['forecast_audit'][0]['training_snapshot']==rows[:160]
    assert len(report['strategies'])==15  # uniform plus fourteen candidates
    assert all(r['cost']==10 for r in report['strategies'])
