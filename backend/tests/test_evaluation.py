import pytest
from lottery.evaluation import evaluation_record, compare_records


def record(strategy='a',issue='2026001',**overrides):
    args=dict(mode='historical',game='ssq',strategy=strategy,issue=issue,cutoff_issue='2025150',tickets=[{'front':[1,2,3,4,5,6],'back':[1]}],results=[{'level':None,'amount':'0'}],rule_version='ssq-classic')
    args.update(overrides)
    return evaluation_record(**args)


def test_record_keeps_unknown_amount_and_failure_distinct_from_loss():
    unknown=record(results=[{'level':1,'amount':None}])
    assert unknown['status']=='amount_pending' and unknown['metrics']['net'] is None
    assert unknown['cost']==2 and unknown['mode']=='historical'
    failed=record(tickets=[],results=None,error='training failed')
    assert failed['status']=='failed' and failed['metrics'] is None and failed['cost'] is None
    assert record()['metrics']['net']=='-2'
    with pytest.raises(ValueError): record(mode='invented')


def test_common_comparison_requires_same_mode_rule_budget_and_all_tracks():
    rows=[record(s) for s in ['a','b']]
    rows += [record('a','2026002'),record('b','2026002',tickets=[],results=None,error='failed')]
    rows += [record('a','2026003'),record('b','2026003',tickets=[{'front':[1,2,3,4,5,6],'back':[1]}]*2,results=[{'level':None,'amount':'0'}]*2)]
    rows += [record('a','2026004'),record('b','2026004',rule_version='different')]
    rows += [record('a','2026005'),record('b','2026005',mode='prospective')]
    rows += [record('a','2026006'),record('b','2026006',results=[{'level':1,'amount':None}])]
    report=compare_records(rows,['a','b'])
    assert report['issues']==['2026001','2026006']
    assert report['money_issues']==['2026001']
    assert len(report['excluded'])==4
    assert report['strategies']['b']['pending_tickets']==1
    assert report['strategies']['b']['net'] is None
    with pytest.raises(ValueError,match='Duplicate'): compare_records(rows+[rows[0]],['a','b'])


def test_historical_training_failure_is_retained_and_pairing_is_common(monkeypatch):
    import lottery.experiments as e
    from test_experiments import history
    original=e.probability_vectors
    def probability(game,past,strategy):
        if strategy=='frequency' and len(past)==160: raise ValueError('deliberate failure')
        return original(game,past,'uniform')
    monkeypatch.setattr(e,'probability_vectors',probability)
    report=e.evaluate_history('ssq',history(162),test_count=2,simulations=1)
    first=report['forecast_audit'][0]['forecasts']['frequency']['evaluation']
    assert first['status']=='failed' and first['mode']=='historical'
    assert first['cutoff_issue']<first['issue'] and first['metrics'] is None
    assert report['comparison']['issues']==['2025162']
    assert all(m['evaluated_periods']==1 for m in report['strategies'])
    assert next(m for m in report['strategies'] if m['strategy']=='frequency')['failed_periods']==1


from test_prospective import session


def test_prospective_projection_retains_failure_waiting_conflict_and_revision(session):
    from datetime import datetime
    from lottery.models import CandidateForecast, CandidateScore
    from lottery.evaluation import prospective_records
    from lottery.ingestion import ingest
    from test_workflow import draw
    f=CandidateForecast(game='ssq',issue='2026122',strategy='test-v1',model='frequency',
        created_at=datetime(2026,10,23),cutoff_at=datetime(2026,10,25,12),cutoff_issue='2026121',
        seed='1',tickets=[{'front':[1,2,3,4,5,6],'back':[1]}],probabilities={},
        snapshot_path='none',dataset_hash='a'*64,provenance={},error='training failed')
    session.add(f);session.flush()
    assert prospective_records(session,'ssq')[0]['status']=='failed'
    f.error=None;session.flush()
    assert prospective_records(session,'ssq')[0]['status']=='waiting'
    d=ingest(session,draw('2026122','2026-10-25'),None,'cwl')
    assert prospective_records(session,'ssq')[0]['status']=='unscored'
    session.add(CandidateScore(forecast_id=f.id,draw_fingerprint=d.fingerprint,metrics={'results':[{'level':1,'amount':None}],'cost':2}));session.flush()
    r=prospective_records(session,'ssq')[0]
    assert r['status']=='amount_pending' and r['mode']=='prospective'
    assert r['dataset_hash']=='a'*64 and r['cutoff_at'].endswith('Z')
    d.fingerprint='corrected';session.flush()
    assert prospective_records(session,'ssq')[0]['status']=='unscored'
    d.conflict=True;session.flush()
    assert prospective_records(session,'ssq')[0]['status']=='draw_conflict'
    f.created_at=f.cutoff_at;session.flush()
    assert prospective_records(session,'ssq')[0]['status']=='invalid_cutoff'


from test_api import api


def test_evaluations_api_is_read_only_and_has_explicit_mode(api):
    client,engine=api
    r=client.get('/api/evaluations?game=ssq')
    assert r.status_code==200 and r.json()['mode']=='prospective'
    assert r.json()['records']==[]
    assert client.get('/api/evaluations?limit=10000').status_code==422


def test_empty_intersection_is_not_reported_as_zero_profit():
    report=compare_records([record(tickets=[],results=None,error='failure')],['a','b'])
    assert report['issues']==[]
    assert report['strategies']['a']['net'] is None
    assert report['strategies']['b']['roi'] is None


def test_control_comparison_rejects_unequal_budgets_and_rules():
    from lottery.portfolio import comparison,group_result
    normal=group_result([{'level':None,'amount':'0'}],'a',10)
    cheap=group_result([{'level':None,'amount':'0'}],'a',2)
    other=group_result([{'level':None,'amount':'0'}],'b',10)
    report=comparison([('1',normal),('2',normal)],{'1':[cheap]*100,'2':[other]*100})
    assert report['periods']==0
    assert len(report['excluded'])==2


def test_all_model_failures_remain_in_audit_without_nan_or_zero_profit(monkeypatch):
    import json
    import lottery.experiments as e
    from test_experiments import history
    def fail(*args): raise RuntimeError('model unavailable')
    monkeypatch.setattr(e,'probability_vectors',fail)
    report=e.evaluate_history('ssq',history(161),test_count=1,simulations=1)
    assert report['comparison']['issues']==[] and report['random_hit_interval'] is None
    assert all(r['failed_periods']==1 and r['brier'] is None and r['net'] is None for r in report['strategies'])
    assert len(report['forecast_audit'][0]['forecasts'])==15
    json.dumps(report,allow_nan=False)


def test_formal_projection_and_backtest_do_not_create_candidate_evidence(session,monkeypatch,tmp_path):
    import lottery.experiments as e
    import lottery.config as config
    from sqlalchemy import select,func
    from datetime import datetime
    from lottery.domain import TZ
    from lottery.ingestion import ingest
    from lottery.workflow import persist_prediction,settle
    from lottery.evaluation import prospective_records
    from lottery.models import CandidateForecast,CandidateScore,Experiment
    from test_workflow import draw
    from test_experiments import history
    ingest(session,draw(),None,'cwl')
    p=persist_prediction(session,'ssq',datetime(2026,10,23,8,tzinfo=TZ))
    # Persisted created_at uses the wall clock; this fixture simulates an earlier freeze.
    p.created_at=datetime(2026,10,23);session.flush()
    actual=draw('2026122','2026-10-25');ingest(session,actual,None,'cwl')
    settle(session)
    formal=next(r for r in prospective_records(session,'ssq') if r['kind']=='formal')
    assert formal['issue']==p.issue and formal['cost']==10
    assert formal['status'] in ('settled','amount_pending') and len(formal['results'])==5
    before=session.scalar(select(func.count()).select_from(CandidateForecast))
    before_scores=session.scalar(select(func.count()).select_from(CandidateScore))
    monkeypatch.setattr(config,'RUNTIME',tmp_path)
    original=e.evaluate_history
    monkeypatch.setattr(e,'evaluate_history',lambda *a,**k:original('ssq',history(161),test_count=1,simulations=1))
    report=e.backtest(session,'ssq',test_count=1)
    import json
    artifact=json.loads((tmp_path/'artifacts'/report['artifact']).read_text())
    assert artifact['report']['forecast_audit'][0]['forecasts']['uniform']['evaluation']['mode']=='historical'
    assert session.scalar(select(func.count()).select_from(Experiment))==1
    assert session.scalar(select(func.count()).select_from(CandidateForecast))==before
    assert session.scalar(select(func.count()).select_from(CandidateScore))==before_scores


@pytest.mark.parametrize('metrics',[{'brier':.1,'cost':2},{'results':[],'cost':2}])
def test_malformed_persisted_scores_do_not_break_paginated_api(api,metrics):
    from datetime import datetime
    from sqlalchemy.orm import Session
    from lottery.models import CandidateForecast,CandidateScore
    from lottery.ingestion import ingest
    from test_workflow import draw
    client,engine=api
    with Session(engine) as session:
        d=ingest(session,draw('2026122','2026-10-25'),None,'cwl')
        f=CandidateForecast(game='ssq',issue=d.issue,strategy='test',model='frequency',created_at=datetime(2026,10,23),
            cutoff_at=datetime(2026,10,25,12),cutoff_issue='2026121',seed='1',
            tickets=[{'front':[1,2,3,4,5,6],'back':[1]}],probabilities={},snapshot_path='none',dataset_hash='x',provenance={})
        session.add(f);session.flush()
        session.add(CandidateScore(forecast_id=f.id,draw_fingerprint=d.fingerprint,metrics=metrics));session.commit()
    response=client.get('/api/evaluations?game=ssq&limit=1')
    assert response.status_code==200
    row=response.json()['records'][0]
    assert row['status']=='invalid_score' and row['metrics'] is None
    assert response.json()['comparison']['issues']==[]
    with Session(engine) as session:
        assert session.query(CandidateScore).one().metrics==metrics
