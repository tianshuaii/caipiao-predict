import json
from pathlib import Path
import numpy as np
import pytest
from lottery.selection import select_tickets, selection_metadata, EXACT, UNIFORM, WEIGHTED, replay_tickets
from lottery.domain import validate_ticket

BASELINE=json.loads((Path(__file__).parent/'fixtures/selection-pre-t11.json').read_text())


def test_checked_engine_matches_old_tickets_on_valid_inputs():
    for case in BASELINE['weighted']:
        actual=select_tickets(case['game'],case['seed'],protocol=WEIGHTED,probabilities=case['probabilities'])
        assert actual==case['tickets']
        assert replay_tickets(case['game'],case['seed'],case['probabilities'],'legacy-weighted-v1')==case['tickets']
    for case in BASELINE['uniform']:
        assert select_tickets(case['game'],case['seed'])==case['tickets']


@pytest.mark.parametrize('count',[0,11,True,1.5])
def test_invalid_counts(count):
    with pytest.raises(ValueError): select_tickets('ssq',42,count=count)


@pytest.mark.parametrize('seed',[True,-1,1.5,'42'])
def test_invalid_seeds(seed):
    with pytest.raises(ValueError): select_tickets('ssq',seed)


def test_invalid_weights_and_impossible_unique_batch():
    p={'front':[1.]*33,'back':[1.]*16}
    for value in [float('nan'),float('inf'),-1]:
        bad={**p,'front':[value]+p['front'][1:]}
        with pytest.raises(ValueError): select_tickets('ssq',42,probabilities=bad,protocol=WEIGHTED)
    for bad in [{'front':[1.],'back':[1.]*16},{'front':[0.]*33,'back':[1.]*16}]:
        with pytest.raises(ValueError): select_tickets('ssq',42,probabilities=bad,protocol=WEIGHTED)
    only={'front':[1.]*6+[0.]*27,'back':[1.]+[0.]*15}
    with pytest.raises(ValueError,match='support'):select_tickets('ssq',42,probabilities=only,protocol=WEIGHTED)
    assert len(select_tickets('ssq',42,count=1,probabilities=only,protocol=WEIGHTED))==1


def test_bounded_retries_for_concentrated_distribution():
    p={'front':[1.]*6+[1e-300]*27,'back':[1.]+[1e-300]*15}
    with pytest.raises(ValueError,match='retry'):select_tickets('ssq',42,probabilities=p,protocol=WEIGHTED)


@pytest.mark.parametrize('game',['ssq','dlt'])
@pytest.mark.parametrize('protocol',[UNIFORM,WEIGHTED])
def test_reproducible_legal_unique(game,protocol):
    from lottery.domain import GAMES
    p={zone:[1.]*GAMES[game][zone][0] for zone in ('front','back')}
    tickets=select_tickets(game,42,count=10,protocol=protocol,probabilities=p if protocol==WEIGHTED else None)
    assert tickets==select_tickets(game,42,count=10,protocol=protocol,probabilities=p if protocol==WEIGHTED else None)
    assert len(tickets)==len({str(t) for t in tickets})==10
    for ticket in tickets:validate_ticket(game,**ticket)


def test_exact_single_ticket_empirical_marginals():
    p={'front':[.9,.8,.7,.6,.5,.4,.3,.2,.2,.2,.2]+[0.]*24,'back':[.8,.7,.5]+[0.]*9}
    observed={zone:np.zeros(len(values)) for zone,values in p.items()}
    for seed in range(4000):
        ticket=select_tickets('dlt',seed,count=1,probabilities=p,protocol=EXACT)[0]
        validate_ticket('dlt',**ticket)
        for zone in observed:observed[zone][np.array(ticket[zone])-1]+=1
    for zone in p: np.testing.assert_allclose(observed[zone]/4000,p[zone],atol=.035,rtol=0)
    with pytest.raises(ValueError):select_tickets('dlt',42,count=5,probabilities=p,protocol=EXACT)
    assert selection_metadata(EXACT)['input_semantics']=='inclusion-marginals'
    assert selection_metadata(WEIGHTED)['input_semantics']=='sampling-weights'


def test_candidate_protocol_and_replay_are_recorded(session,monkeypatch):
    from datetime import datetime
    from sqlalchemy import select
    from lottery.domain import TZ
    from lottery.models import CandidateForecast
    from lottery.workflow import persist_prediction
    from test_prospective import seed_history
    import lottery.prospective as prospective
    seed_history(session)
    monkeypatch.setattr(prospective,'select_strategy',lambda *args:(prospective.versions()['frequency'],'test'))
    prediction=persist_prediction(session,'ssq',datetime(2026,10,23,8,tzinfo=TZ))
    assert prediction.provenance['selection']['protocol']==WEIGHTED
    assert replay_tickets(prediction.game,int(prediction.seed),prediction.probabilities,WEIGHTED)==prediction.tickets
    for candidate in session.scalars(select(CandidateForecast)):
        assert candidate.provenance['selection']['input_semantics']=='sampling-weights'
        assert candidate.provenance['experiment']['selection_protocol']==WEIGHTED


def test_legacy_model_recipe_can_still_load(tmp_path):
    from lottery.model_training import fit_model,predict_model
    from lottery.model_artifacts import save_model,load_model
    from lottery.experiment_registry import LEGACY_SELECTION,describe,fingerprint
    model=fit_model('ssq',[{**BASELINE['uniform'][0]['tickets'][0],'issue':f'2025{i+1:03}'} for i in range(160)],'frequency')
    model.metadata['experiment']=describe('frequency',LEGACY_SELECTION)
    model.metadata['experiment_hash']=fingerprint('frequency',LEGACY_SELECTION)
    ref=save_model(model,tmp_path)
    assert predict_model(load_model(ref['id'],tmp_path))==predict_model(model)
    # T10 envelopes have the experiment hash but no selection_protocol field.
    import hashlib
    raw=(tmp_path/(ref['id']+'.pkl')).read_bytes()
    header,payload=raw.split(b'\n',1)
    manifest=json.loads(header);manifest.pop('selection_protocol')
    raw=json.dumps(manifest,sort_keys=True).encode()+b'\n'+payload
    old_id=hashlib.sha256(raw).hexdigest()
    (tmp_path/(old_id+'.pkl')).write_bytes(raw)
    assert predict_model(load_model(old_id,tmp_path))==predict_model(model)


from test_prospective import session


def test_weighted_sampling_inclusion_is_not_input_marginal():
    p={'front':[1.]*35,'back':[.8,.7,.5]+[0.]*9}
    included=0
    for seed in range(3000):
        ticket=select_tickets('dlt',seed,count=1,probabilities=p,protocol=WEIGHTED)[0]
        included+=1 in ticket['back']
    expected=.8/2+(.7/2)*(.8/1.3)+(.5/2)*(.8/1.5)
    assert included/3000==pytest.approx(expected,abs=.025)
    assert abs(included/3000-.8)>.03


def test_exact_boundaries_and_invalid_marginals():
    p={'front':[1.]*5+[0.]*30,'back':[1.,1.]+[0.]*10}
    assert select_tickets('dlt',42,count=1,protocol=EXACT,probabilities=p)==[{'front':[1,2,3,4,5],'back':[1,2]}]
    for values in ([1.]*6+[0.]*29,[1.1,.9,1.,1.,1.]+[0.]*30):
        with pytest.raises(ValueError):select_tickets('dlt',42,count=1,protocol=EXACT,probabilities={**p,'front':values})


def test_backtest_forecasts_replay_using_recorded_protocol():
    from lottery.experiments import evaluate_history
    from test_experiments import history
    report=evaluate_history('ssq',history(161),test_count=1,simulations=1)
    assert report['selection_protocols']=={'uniform':UNIFORM,'candidate':WEIGHTED,'random_controls':UNIFORM}
    for name,forecast in report['forecast_audit'][0]['forecasts'].items():
        protocol=forecast['selection']['protocol']
        assert protocol==(UNIFORM if name=='uniform' else WEIGHTED)
        assert replay_tickets('ssq',forecast['seed'],forecast['probabilities'],protocol)==forecast['tickets']
