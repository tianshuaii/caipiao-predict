from datetime import date, datetime
import pytest
from sqlalchemy import create_engine, select, func
from sqlalchemy.orm import Session
from lottery.models import Base, Prediction, Draw, Settlement
from lottery.domain import next_target, TZ
from lottery.ingestion import ingest
from lottery.workflow import persist_prediction, settle

@pytest.fixture
def session(tmp_path, monkeypatch):
    import lottery.workflow as workflow
    monkeypatch.setattr(workflow, 'ARTIFACTS', tmp_path)
    engine = create_engine('sqlite://')
    Base.metadata.create_all(engine)
    with Session(engine) as session: yield session

def draw(issue='2026121', day='2026-10-22'):
    return {'game':'ssq','issue':issue,'draw_date':day,'front':[1,2,3,4,5,6],'back':[1],'prizes':{'1':{'amount':'5000000','count':1},'6':{'amount':'5','count':10}},'source_url':'https://www.cwl.gov.cn/','sales':None,'pool':None,'rule_version':'ssq-2026014'}

def test_calendar_friday_targets_and_stale_draw_guard():
    now = datetime(2026,10,23,8,tzinfo=TZ)
    assert next_target('dlt','2026120',date(2026,10,21),now)[:2] == ('2026121',date(2026,10,24))
    assert next_target('ssq','2026121',date(2026,10,22),now)[:2] == ('2026122',date(2026,10,25))
    with pytest.raises(ValueError): next_target('ssq','2026120',date(2026,10,20),now)
    with pytest.raises(ValueError): next_target('dlt','2026120',date(2026,10,21),datetime(2026,10,24,21,tzinfo=TZ))

def test_calendar_closure_and_year_boundary():
    result = next_target('ssq','2025151',date(2025,12,30),datetime(2025,12,31,8,tzinfo=TZ))
    assert result[:2] == ('2026001',date(2026,1,1))
    result = next_target('ssq','2026113',date(2026,9,29),datetime(2026,10,2,8,tzinfo=TZ), ['2026-10-01','2026-10-04'])
    assert result[1] == date(2026,10,6)

def test_prediction_is_immutable_across_retries(session):
    ingest(session, draw(), None, 'cwl')
    now = datetime(2026,10,23,8,tzinfo=TZ)
    first = persist_prediction(session, 'ssq', now)
    second = persist_prediction(session, 'ssq', now)
    assert first.id == second.id and first.tickets == second.tickets
    assert session.scalar(select(func.count()).select_from(Prediction)) == 1
    assert first.cutoff_issue == '2026121' and len(first.tickets) == 5

def test_conflicting_data_blocks_prediction(session):
    row=ingest(session,draw(),None,'cwl')
    row.conflict=True
    with pytest.raises(ValueError): persist_prediction(session,'ssq',datetime(2026,10,23,8,tzinfo=TZ))

def test_settlement_matches_actual_numbers_and_does_not_duplicate(session):
    ingest(session, draw(), None, 'cwl')
    p = persist_prediction(session,'ssq',datetime(2026,10,23,8,tzinfo=TZ))
    winning = dict(draw('2026122','2026-10-25'), **p.tickets[0])
    ingest(session, winning, None, 'cwl')
    settle(session)
    settle(session)
    rows = list(session.scalars(select(Settlement)))
    assert len(rows) == 1
    assert rows[0].results[0]['level'] == 1
    assert rows[0].results[0]['amount'] == '5000000'

def test_missing_prize_is_pending_not_zero(session):
    ingest(session, draw(), None, 'cwl')
    p = persist_prediction(session,'ssq',datetime(2026,10,23,8,tzinfo=TZ))
    winning = dict(draw('2026122','2026-10-25'), **p.tickets[0], prizes={})
    ingest(session, winning, None, 'cwl')
    settle(session)
    s=session.scalar(select(Settlement))
    assert s.results[0]['amount'] is None and s.summary['pending'] > 0

def test_report_rejects_conflicted_settlement(session):
    from lottery.models import Run
    from lottery.reporting import build_report
    ingest(session, draw(), None, 'cwl')
    p=persist_prediction(session,'ssq',datetime(2026,10,23,8,tzinfo=TZ))
    actual=ingest(session,dict(draw('2026122','2026-10-25'), **p.tickets[0]),None,'cwl')
    settle(session)
    actual.conflict=True
    run=Run(kind='scheduled',details={'ssq':{'error':'conflict'}})
    session.add(run);session.flush()
    _,body,_=build_report(session,run)
    assert '5000000 元' not in body
    assert '冲突' in body

def test_workflow_commits_settlement_when_next_prediction_blocked(session, monkeypatch):
    import lottery.workflow as workflow
    import lottery.collectors as collectors
    import lottery.db as database
    from sqlalchemy.orm import sessionmaker
    ingest(session,draw(),None,'cwl')
    p=persist_prediction(session,'ssq',datetime(2026,10,23,8,tzinfo=TZ))
    ingest(session,dict(draw('2026122','2026-10-25'), **p.tickets[0]),None,'cwl')
    session.commit()
    monkeypatch.setattr(database,'session_factory',lambda:sessionmaker(bind=session.get_bind()))
    monkeypatch.setattr(collectors,'collect',lambda *args,**kwargs:{})
    monkeypatch.setattr(workflow,'coverage',lambda *args:{'complete':False})
    report=workflow.run_workflow(notify=False)
    assert report['status']=='partial'
    assert session.scalar(select(func.count()).select_from(Settlement))==1
