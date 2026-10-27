from datetime import datetime, timedelta
import math
import pytest
from sqlalchemy import create_engine, select, func
from sqlalchemy.orm import Session
from lottery.models import Base, CandidateForecast, CandidateScore, StrategyDecision
from lottery.prospective import evidence, choose, freeze_candidates, score_candidates, status, versions
from lottery.workflow import persist_prediction
from lottery.domain import TZ
from lottery.ingestion import ingest
from test_workflow import draw

@pytest.fixture
def session(tmp_path, monkeypatch):
    import lottery.workflow as w
    monkeypatch.setattr(w,'ARTIFACTS',tmp_path)
    engine=create_engine('sqlite://')
    Base.metadata.create_all(engine)
    with Session(engine) as s: yield s

def test_gate_requires_samples_and_sequential_evidence():
    positive=[{'baseline':.2,'brier':.1,'normalized_gain':.8}]*100
    assert not evidence(positive[:59],40)['eligible']
    assert evidence(positive,40)['eligible']
    weak=[{'baseline':.2,'brier':.199,'normalized_gain':.01}]*100
    assert not evidence(weak,40)['eligible']
    assert evidence([],40)['e_value']==1

def test_choose_promotes_and_reverts_without_chasing_small_samples():
    good={'strategy':'frequency-v1','eligible':True,'brier':.1,'recent_degraded':False}
    assert choose('uniform-v1',[good],{'frequency-v1'})[0]=='frequency-v1'
    bad=dict(good,eligible=False,recent_degraded=True)
    assert choose('frequency-v1',[bad],{'frequency-v1'})[0]=='uniform-v1'
    assert choose('old-version',[],{'frequency-v1'})[0]=='uniform-v1'

def test_shadow_freeze_and_scoring_are_idempotent_and_revision_aware(session):
    now=datetime(2026,10,23,8,tzinfo=TZ)
    ingest(session,draw(),None,'cwl')
    p=persist_prediction(session,'ssq',now)
    forecasts=list(session.scalars(select(CandidateForecast)))
    # Insufficient training history is recorded as failures, not fabricated evidence.
    assert len(forecasts)==len(versions()) and all(f.error for f in forecasts)
    freeze_candidates(session,p,now)
    assert session.scalar(select(func.count()).select_from(CandidateForecast))==len(versions())
    f=forecasts[0]
    f.error=None; f.probabilities=p.probabilities; f.tickets=p.tickets
    actual=ingest(session,draw('2026122','2026-10-25'),None,'cwl')
    score_candidates(session,'ssq')
    score_candidates(session,'ssq')
    assert session.scalar(select(func.count()).select_from(CandidateScore))==1
    changed=draw('2026122','2026-10-25'); changed['back']=[2]
    ingest(session,changed,None,'cwl')
    score_candidates(session,'ssq')
    assert session.scalar(select(func.count()).select_from(CandidateScore))==2
    assert status(session,'ssq')['candidates'][0]['samples']==1
    actual.conflict=True;session.flush()
    assert status(session,'ssq')['candidates'][0]['samples']==0

def test_late_forecasts_never_count_as_forward_evidence(session):
    ingest(session,draw(),None,'cwl')
    p=persist_prediction(session,'ssq',datetime(2026,10,23,8,tzinfo=TZ))
    for f in session.scalars(select(CandidateForecast)): session.delete(f)
    session.flush()
    freeze_candidates(session,p,datetime(2026,10,25,21,tzinfo=TZ))
    assert session.scalar(select(func.count()).select_from(CandidateForecast))==0
    ingest(session,draw('2026122','2026-10-25'),None,'cwl')
    freeze_candidates(session,p,datetime(2026,10,23,8,tzinfo=TZ))
    assert session.scalar(select(func.count()).select_from(CandidateForecast))==0

def seed_history(session):
    from lottery.predict import generate_tickets
    for i in range(160):
        row=draw(f'2025{i+1:03d}','2025-01-01')
        row.update(generate_tickets('ssq',i,1)[0]);ingest(session,row,None,'cwl')
    ingest(session,draw(),None,'cwl')

def test_real_candidates_freeze_once_and_only_new_prediction_can_switch(session,monkeypatch):
    import lottery.prospective as module
    seed_history(session)
    now=datetime(2026,10,23,8,tzinfo=TZ)
    monkeypatch.setattr(module,'select_strategy',lambda *args:(module.versions()['frequency'],'test passed gate'))
    p=persist_prediction(session,'ssq',now)
    assert p.strategy==module.versions()['frequency']
    assert len(p.tickets)==5 and len({str(t) for t in p.tickets})==5
    assert all(not f.error for f in session.scalars(select(CandidateForecast)))
    original=json_copy(p.tickets)
    monkeypatch.setattr(module,'select_strategy',lambda *args:('uniform-v1','fallback'))
    assert persist_prediction(session,'ssq',now).tickets==original
    from lottery.experiments import weighted_tickets
    assert weighted_tickets('ssq',p.probabilities,int(p.seed))==p.tickets

def json_copy(value):
    import json
    return json.loads(json.dumps(value))

def test_model_exception_does_not_block_uniform_prediction(session,monkeypatch):
    import lottery.model_training as training
    seed_history(session)
    monkeypatch.setattr(training,'fit_model',lambda *args:(_ for _ in ()).throw(RuntimeError('failure')))
    p=persist_prediction(session,'ssq',datetime(2026,10,23,8,tzinfo=TZ))
    assert p.strategy=='uniform-v1' and len(p.tickets)==5
    assert all(f.error for f in session.scalars(select(CandidateForecast)))

def test_new_versions_get_separate_budget_and_no_reused_scores(session,monkeypatch):
    import lottery.prospective as module
    seed_history(session)
    p=persist_prediction(session,'ssq',datetime(2026,10,23,8,tzinfo=TZ))
    first=status(session,'ssq')['candidates']
    count=len(versions())
    assert [c['threshold'] for c in first]==[i*(i+1)/.05 for i in range(1,count+1)]
    monkeypatch.setattr(module,'versions',lambda:{'frequency':'frequency-new','logistic':'logistic-new'})
    module.freeze_candidates(session,p,datetime(2026,10,23,9,tzinfo=TZ))
    current=[c for c in status(session,'ssq')['candidates'] if c['current_version']]
    assert [c['threshold'] for c in current]==[i*(i+1)/.05 for i in (count+1,count+2)]
    assert all(c['samples']==0 for c in current)

def test_migration_adds_tables_without_losing_existing_history(tmp_path,monkeypatch):
    from alembic import command
    from alembic.config import Config
    from sqlalchemy import inspect
    from pathlib import Path
    import lottery.db as db
    engine=create_engine('sqlite:///'+str(tmp_path/'migration.db'))
    added={'candidate_forecasts','candidate_scores','strategy_decisions'}
    Base.metadata.create_all(engine,tables=[t for t in Base.metadata.sorted_tables if t.name not in added])
    with Session(engine) as s:
        ingest(s,draw(),None,'cwl');s.commit()
    monkeypatch.setattr(db,'engine',lambda:engine)
    config=Config(str(Path(__file__).resolve().parents[1]/'alembic.ini'))
    command.stamp(config,'001');command.upgrade(config,'head');command.upgrade(config,'head')
    assert added.issubset(inspect(engine).get_table_names())
    from lottery.models import Draw
    with Session(engine) as s: assert s.scalar(select(func.count()).select_from(Draw))==1

def test_invalidated_evidence_forces_rollback():
    candidate={'strategy':'frequency-v1','eligible':False,'samples':0,'brier':None,'recent_degraded':False}
    assert choose('frequency-v1',[candidate],{'frequency-v1'})[0]=='uniform-v1'

def test_evaluate_only_never_creates_formal_predictions(session):
    from lottery.prospective import evaluate_existing
    from lottery.models import Prediction
    ingest(session,draw(),None,'cwl')
    evaluate_existing(session,'ssq')
    assert session.scalar(select(func.count()).select_from(Prediction))==0
