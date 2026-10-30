import numpy as np
import pytest
from lottery.experiments import probability_vectors, weighted_tickets
from lottery.predict import generate_tickets
from lottery.domain import validate_ticket

@pytest.mark.parametrize('strategy',['forest_all','boost_all','neural_all','ensemble_all'])
@pytest.mark.parametrize('game',['ssq','dlt'])
def test_nonlinear_candidates_valid_reproducible_and_registered(strategy,game):
    from lottery.indicators import STRATEGIES
    from lottery.prospective import versions
    assert STRATEGIES[strategy]==STRATEGIES['freq_all']
    assert strategy in versions()
    history=[generate_tickets(game,i,1)[0] for i in range(160)]
    p=probability_vectors(game,history,strategy)
    again=probability_vectors(game,history,strategy)
    for key,count in [('front',6 if game=='ssq' else 5),('back',1 if game=='ssq' else 2)]:
        assert np.allclose(p[key],again[key])
        assert all(0<v<1 for v in p[key])
        assert sum(p[key])==pytest.approx(count)
    tickets=weighted_tickets(game,p,31)
    assert len(tickets)==len({str(t) for t in tickets})==5
    for t in tickets:validate_ticket(game,**t)


def test_forest_fit_calibration_and_target_are_chronologically_separate(monkeypatch):
    import lottery.model_training as module
    from lottery.indicators import feature_sequence, STRATEGIES
    fits=[]; predictions=[]
    class Recorder:
        def __init__(self,**kwargs):
            assert kwargs['n_jobs']==1 and kwargs['max_depth']==4
            self.kwargs=kwargs
        def get_params(self,deep=False): return self.kwargs
        def fit(self,x,y):
            fits.append((x.copy(),y.copy()))
        def predict_proba(self,x):
            predictions.append(x.copy())
            return np.tile([.8,.2],(len(x),1))
    monkeypatch.setattr(module,'RandomForestClassifier',Recorder)
    rows=[generate_tickets('ssq',i,1)[0] for i in range(160)]
    probability_vectors('ssq',rows,'forest_all')
    for index,key in enumerate(('front','back')):
        size=33 if key=='front' else 16
        from lottery.experiments import encoded
        matrix=encoded(rows,key,size)
        sequence=feature_sequence(matrix,STRATEGIES['freq_all'])
        assert np.array_equal(fits[index][0],np.concatenate(sequence[:100]))
        assert np.array_equal(fits[index][1],matrix[30:130].reshape(-1))
        assert np.array_equal(predictions[index],np.concatenate(sequence[100:-1]))
        assert np.array_equal(predictions[index+2],sequence[-1])


def test_nonconverged_neural_candidate_does_not_block_other_forecasts(session,monkeypatch):
    import warnings
    from datetime import datetime
    from sqlalchemy import select
    import lottery.model_training as module
    from lottery.models import CandidateForecast
    from lottery.workflow import persist_prediction
    from lottery.domain import TZ
    from test_prospective import seed_history
    seed_history(session)
    def fail(*args,**kwargs):
        warnings.warn('test convergence failure',module.ConvergenceWarning)
    monkeypatch.setattr(module.MLPClassifier,'fit',fail)
    p=persist_prediction(session,'ssq',datetime(2026,10,23,8,tzinfo=TZ))
    candidates=list(session.scalars(select(CandidateForecast)))
    assert len(candidates)==16
    assert [f.model for f in candidates if f.error]==['neural_all']
    assert all(len(f.tickets)==5 for f in candidates if not f.error)
    assert p.strategy=='uniform-v1' and len(p.tickets)==5

# Reuse the isolated SQLite/artifact fixture, never the application database.
from test_prospective import session
