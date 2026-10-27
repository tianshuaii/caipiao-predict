from datetime import datetime
from sqlalchemy import select, func
from test_prospective import session
from test_workflow import draw
from lottery.domain import TZ
from lottery.ingestion import ingest
from lottery.workflow import persist_prediction
from lottery.portfolio import group_result, aggregate, freeze_controls, score_controls, portfolio_status
from lottery.models import RandomControl, ControlScore


def test_group_objectives_and_unknown_money():
    result=group_result([{'level':1,'amount':None},{'level':6,'amount':'5'}], 'ssq-classic', cost=4)
    assert result['any_prize'] and result['first_prize']
    assert result['net'] is None and result['known_return']=='5'
    report=aggregate([result])
    assert report['periods']==1 and report['first_prize_rate']==1
    assert report['net'] is None and report['roi'] is None


def test_controls_frozen_before_draw_idempotent_and_revision_aware(session):
    ingest(session,draw(),None,'cwl')
    now=datetime(2026,10,23,8,tzinfo=TZ)
    p=persist_prediction(session,'ssq',now)
    batch=freeze_controls(session,p,now)
    assert len(batch.groups)==100 and all(len(g)==5 for g in batch.groups)
    assert all(len({str(t) for t in g})==5 for g in batch.groups)
    assert freeze_controls(session,p,now).groups==batch.groups
    assert session.scalar(select(func.count()).select_from(RandomControl))==1
    actual=ingest(session,draw('2026122','2026-10-25'),None,'cwl')
    score_controls(session,'ssq');score_controls(session,'ssq')
    assert session.scalar(select(func.count()).select_from(ControlScore))==1
    actual.fingerprint='changed';session.flush()
    score_controls(session,'ssq')
    assert session.scalar(select(func.count()).select_from(ControlScore))==2
    actual.conflict=True;session.flush()
    assert portfolio_status(session,'ssq')['rows']==[]


def test_no_retrospective_controls(session):
    ingest(session,draw(),None,'cwl')
    p=persist_prediction(session,'ssq',datetime(2026,10,23,8,tzinfo=TZ))
    for b in session.scalars(select(RandomControl)): session.delete(b)
    session.flush()
    assert freeze_controls(session,p,datetime(2026,10,25,20,tzinfo=TZ)) is None
    ingest(session,draw('2026122','2026-10-25'),None,'cwl')
    assert freeze_controls(session,p,datetime(2026,10,23,8,tzinfo=TZ)) is None


def test_matched_comparison_uses_periods_not_control_count_and_excludes_unknown_money():
    from lottery.portfolio import comparison
    win=group_result([{'level':6,'amount':'5'}], 'a')
    loss=group_result([{'level':None,'amount':'0'}], 'a')
    pending=group_result([{'level':1,'amount':None}], 'a')
    entries=[('1',win),('2',loss),('3',win)]
    controls={'1':[loss]*100,'2':[pending]*100}
    result=comparison(entries,controls)
    assert result['periods']==2 and result['strategy']['any_prize_rate']==.5
    assert result['random_any_prize_rate']==[.5,.5,.5]
    assert result['money_periods']==1
    assert result['money_strategy']['net']=='-5'
    assert result['random_net']==[-10,-10,-10]
    assert comparison(entries,{})['random_any_prize_rate'] is None


def test_summary_splits_rule_versions_and_uses_current_revision(session):
    from lottery.models import CandidateForecast, CandidateScore
    ingest(session,draw(),None,'cwl')
    p=persist_prediction(session,'ssq',datetime(2026,10,23,8,tzinfo=TZ))
    f=session.scalar(select(CandidateForecast));f.error=None
    actual=ingest(session,draw('2026122','2026-10-25'),None,'cwl')
    results=[{'level':None,'amount':'0'}]*5
    session.add(CandidateScore(forecast_id=f.id,draw_fingerprint=actual.fingerprint,metrics={'results':results,'cost':10}))
    session.flush()
    report=portfolio_status(session,'ssq')
    assert len(report['rows'])==1 and report['rows'][0]['metrics']['periods']==1
    assert report['rows'][0]['comparison']['periods']==0  # no control score yet
    score_controls(session,'ssq')
    assert portfolio_status(session,'ssq')['rows'][0]['comparison']['periods']==1
    second=draw('2026123','2026-10-27');second['rule_version']='another-rule'
    d2=ingest(session,second,None,'cwl')
    f2=CandidateForecast(game='ssq',issue=d2.issue,strategy=f.strategy,model=f.model,created_at=f.created_at,
        cutoff_at=f.cutoff_at,cutoff_issue=f.cutoff_issue,seed=f.seed,probabilities={},tickets=[],
        snapshot_path=f.snapshot_path,dataset_hash=f.dataset_hash,provenance={})
    session.add(f2);session.flush()
    session.add(CandidateScore(forecast_id=f2.id,draw_fingerprint=d2.fingerprint,metrics={'results':results,'cost':10}))
    session.flush()
    assert len(portfolio_status(session,'ssq')['rows'])==2
    actual.fingerprint='corrected';session.flush()
    rows=portfolio_status(session,'ssq')['rows']
    assert len(rows)==1 and rows[0]['rule_version']=='another-rule'


def test_control_migration_preserves_existing_data(tmp_path,monkeypatch):
    from alembic import command
    from alembic.config import Config
    from sqlalchemy import create_engine, inspect
    from sqlalchemy.orm import Session
    from pathlib import Path
    from lottery.models import Base, Draw
    import lottery.db as db
    engine=create_engine('sqlite:///'+str(tmp_path/'controls.db'))
    Base.metadata.create_all(engine,tables=[t for t in Base.metadata.sorted_tables if t.name not in {'random_controls','control_scores'}])
    with Session(engine) as s:
        ingest(s,draw(),None,'cwl');s.commit()
    monkeypatch.setattr(db,'engine',lambda:engine)
    config=Config(str(Path(__file__).resolve().parents[1]/'alembic.ini'))
    command.stamp(config,'002');command.upgrade(config,'head');command.upgrade(config,'head')
    assert {'random_controls','control_scores'}.issubset(inspect(engine).get_table_names())
    with Session(engine) as s: assert s.scalar(select(func.count()).select_from(Draw))==1
