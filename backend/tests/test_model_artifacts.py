import json
from pathlib import Path
import numpy as np
import pytest
from lottery.model_training import fit_model, predict_model
from lottery.model_artifacts import save_model, load_model
from lottery.predict import generate_tickets


def history(game,n):
    return [dict(generate_tickets(game,i,1)[0],issue=f'2025{i+1:03}') for i in range(n)]


@pytest.mark.parametrize('case',json.loads((Path(__file__).parent/'fixtures/probabilities-pre-t09.json').read_text()))
def test_all_legacy_probabilities_reproduced(case):
    from lottery.experiments import probability_vectors
    rows=history(case['game'],case['n'])
    for strategy,expected in case['probabilities'].items():
        actual=probability_vectors(case['game'],rows,strategy)
        for zone in ('front','back'):
            np.testing.assert_allclose(actual[zone],expected[zone],rtol=0,atol=1e-14)


@pytest.mark.parametrize('strategy',['uniform','frequency','logistic','forest_all','neural_all'])
def test_artifact_round_trip_and_training_metadata(strategy,tmp_path):
    model=fit_model('ssq',history('ssq',160),strategy)
    ref=save_model(model,tmp_path)
    restored=load_model(ref['id'],tmp_path)
    assert predict_model(restored)==predict_model(model)
    assert restored.metadata['cutoff_issue']=='2025160'
    assert restored.metadata['training_window']==300
    assert restored.metadata['environment']['sklearn']
    assert restored.metadata['feature_version'] and restored.metadata['dataset_hash']
    assert restored.metadata['seed']==20261023
    assert ref['id']==save_model(model,tmp_path)['id']
    if strategy not in ('uniform','frequency'):
        assert restored.metadata['fit_issues']==[f'2025{i:03}' for i in range(31,131)]
        assert restored.metadata['calibration_issues']==[f'2025{i:03}' for i in range(131,161)]
        assert restored.zones['front']['estimator'] is not None
        assert restored.zones['front']['calibrator'] is not None
        assert restored.metadata['parameters']['front']


def test_artifact_integrity_checked_before_unpickle(tmp_path,monkeypatch):
    import lottery.model_artifacts as storage
    ref=save_model(fit_model('ssq',history('ssq',160),'frequency'),tmp_path)
    (tmp_path/(ref['id']+'.pkl')).write_bytes(b'corrupt')
    monkeypatch.setattr(storage.pickle,'loads',lambda raw:pytest.fail('must verify hash before loading'))
    with pytest.raises(ValueError,match='hash'): load_model(ref['id'],tmp_path)
    with pytest.raises(ValueError): load_model('../model',tmp_path)


def test_environment_mismatch_rejected_before_unpickle(tmp_path,monkeypatch):
    import lottery.model_artifacts as storage
    ref=save_model(fit_model('ssq',history('ssq',160),'frequency'),tmp_path)
    monkeypatch.setattr(storage,'environment',lambda:{'python':'different'})
    monkeypatch.setattr(storage.pickle,'loads',lambda raw:pytest.fail('must check environment first'))
    with pytest.raises(ValueError,match='environment'): load_model(ref['id'],tmp_path)


def test_cutoff_data_ownership_and_unknown_model():
    rows=history('ssq',310)
    model=fit_model('ssq',rows,'frequency')
    before=predict_model(model)
    rows[-1]['front']=[28,29,30,31,32,33]
    assert predict_model(model)==before
    assert model.metadata['history_issues'][0]=='2025011'
    with pytest.raises(ValueError): fit_model('ssq',rows,'bad-model')


def test_forecasts_retain_replayable_models(session):
    from datetime import datetime
    from sqlalchemy import select
    from lottery.models import CandidateForecast
    from lottery.workflow import persist_prediction, ARTIFACTS
    from lottery.domain import TZ
    from test_prospective import seed_history
    seed_history(session)
    persist_prediction(session,'ssq',datetime(2026,10,23,8,tzinfo=TZ))
    forecasts=list(session.scalars(select(CandidateForecast)))
    assert len(forecasts)==14
    for forecast in forecasts:
        assert forecast.error is None
        ref=forecast.provenance['model_artifact']
        trained=load_model(ref['id'],ARTIFACTS/'models')
        assert predict_model(trained)==forecast.probabilities
        assert trained.metadata['cutoff_issue']==forecast.cutoff_issue


def test_artifact_write_failure_is_recorded_without_promoting_candidate(session,monkeypatch):
    from datetime import datetime
    from sqlalchemy import select
    from lottery.models import CandidateForecast
    from lottery.workflow import persist_prediction
    from lottery.domain import TZ
    import lottery.model_artifacts as storage
    from test_prospective import seed_history
    seed_history(session)
    monkeypatch.setattr(storage,'save_model',lambda *args:(_ for _ in ()).throw(OSError('disk full')))
    prediction=persist_prediction(session,'ssq',datetime(2026,10,23,8,tzinfo=TZ))
    assert prediction.strategy=='uniform-v1'
    assert all(f.error.startswith('OSError:') for f in session.scalars(select(CandidateForecast)))


from test_prospective import session


def test_implementation_mismatch_rejected_before_unpickle(tmp_path,monkeypatch):
    import lottery.model_artifacts as storage
    ref=save_model(fit_model('ssq',history('ssq',160),'frequency'),tmp_path)
    monkeypatch.setattr(storage,'fingerprint',lambda *args:'different')
    monkeypatch.setattr(storage.pickle,'loads',lambda raw:pytest.fail('must check implementation first'))
    with pytest.raises(ValueError,match='implementation'): load_model(ref['id'],tmp_path)


def test_partial_issue_labels_rejected():
    rows=history('ssq',160);rows[0].pop('issue')
    with pytest.raises(ValueError,match='issue'): fit_model('ssq',rows,'frequency')
