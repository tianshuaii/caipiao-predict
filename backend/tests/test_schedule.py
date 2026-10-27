from datetime import datetime,date
from lottery.domain import TZ
from lottery.scheduler import collection_slot, build_scheduler

def test_collection_slots_end_at_midnight():
    assert collection_slot(datetime(2026,10,26,22,30,tzinfo=TZ))==(date(2026,10,26),0)
    assert collection_slot(datetime(2026,10,26,23,0,tzinfo=TZ))==(date(2026,10,26),1)
    assert collection_slot(datetime(2026,10,26,23,30,tzinfo=TZ))==(date(2026,10,26),2)
    assert collection_slot(datetime(2026,10,27,0,0,tzinfo=TZ))==(date(2026,10,26),3)
    assert collection_slot(datetime(2026,10,27,0,6,tzinfo=TZ)) is None
    assert collection_slot(datetime(2026,10,26,8,tzinfo=TZ)) is None

def test_schedule_separates_collect_and_send():
    jobs={j.id:j for j in build_scheduler().get_jobs()}
    assert 'notification-retry' not in jobs
    now=datetime(2026,10,26,7,tzinfo=TZ)
    assert jobs['morning-report'].trigger.get_next_fire_time(None,now).hour==8
    assert jobs['nightly-analysis'].trigger.get_next_fire_time(None,now).hour==22

import pytest
from sqlalchemy import create_engine,select,func
from sqlalchemy.orm import Session,sessionmaker
from lottery.models import Base,Run,Notification,Prediction
from lottery.ingestion import ingest
from lottery.workflow import persist_prediction,run_workflow,data_pending
from lottery.reporting import send_morning_report
from test_workflow import draw

@pytest.fixture
def db(tmp_path,monkeypatch):
    import lottery.workflow as w
    import lottery.db as database
    monkeypatch.setattr(w,'ARTIFACTS',tmp_path)
    engine=create_engine('sqlite://')
    Base.metadata.create_all(engine)
    factory=sessionmaker(bind=engine,expire_on_commit=False)
    monkeypatch.setattr(database,'session_factory',lambda:factory)
    import lottery.scheduler as scheduler
    monkeypatch.setattr(scheduler,'session_factory',lambda:factory)
    with factory() as s: yield s

def test_evening_prediction_uses_todays_draw_and_is_frozen(db):
    ingest(db,draw(),None,'cwl')
    p=persist_prediction(db,'ssq',datetime(2026,10,22,22,30,tzinfo=TZ))
    assert p.issue=='2026122'
    assert persist_prediction(db,'ssq',datetime(2026,10,23,0,0,tzinfo=TZ)).tickets==p.tickets

def test_night_analysis_never_enqueues_or_sends(db,monkeypatch):
    import lottery.collectors as collectors
    import lottery.workflow as workflow
    import lottery.notify as notify
    monkeypatch.setattr(collectors,'collect',lambda *a,**k:{})
    monkeypatch.setattr(workflow,'coverage',lambda *a:{'complete':True})
    monkeypatch.setattr(notify,'deliver',lambda *a:pytest.fail('night sent a notification'))
    ingest(db,draw(),None,'cwl');db.commit()
    result=run_workflow(notify=True,now=datetime(2026,10,22,22,30,tzinfo=TZ))
    assert result['notification']=='not_queued'
    assert db.scalar(select(func.count()).select_from(Notification))==0

def test_retry_stops_after_success_and_midnight_is_final(db,monkeypatch):
    import lottery.scheduler as scheduler
    from datetime import timezone
    calls=[]
    monkeypatch.setattr(scheduler,'run_workflow',lambda **kw:calls.append(kw) or {})
    start=datetime(2026,10,26,22,30,tzinfo=TZ).astimezone(timezone.utc).replace(tzinfo=None)
    run=Run(kind='nightly',status='success',started_at=start,details={'dlt':{'pending':False},'ssq':{'pending':False}})
    db.add(run);db.commit()
    scheduler.scheduled_run(datetime(2026,10,26,23,tzinfo=TZ));assert not calls
    run.details={'dlt':{'pending':True}};db.commit()
    scheduler.scheduled_run(datetime(2026,10,27,0,tzinfo=TZ));assert len(calls)==1
    scheduler.scheduled_run(datetime(2026,10,27,0,30,tzinfo=TZ));assert len(calls)==1

def test_missing_expected_draw_or_prizes_is_pending(db):
    ingest(db,draw(),None,'cwl')
    assert data_pending(db,'ssq',datetime(2026,10,25,22,30,tzinfo=TZ))
    latest=draw('2026122','2026-10-25');latest['prizes']={}
    ingest(db,latest,None,'cwl')
    assert data_pending(db,'ssq',datetime(2026,10,26,0,0,tzinfo=TZ))
    latest['prizes']={str(i):{'amount':'5','count':1} for i in range(1,7)}
    ingest(db,latest,None,'cwl')
    assert not data_pending(db,'ssq',datetime(2026,10,26,0,0,tzinfo=TZ))

def test_morning_reads_saved_predictions_without_fetch_or_regeneration(db,monkeypatch):
    import lottery.collectors as collectors
    import lottery.notify as notify
    monkeypatch.setattr(collectors,'collect',lambda *a,**kw:pytest.fail('morning fetched'))
    delivered=[]
    def deliver(s,n):
        if n.status!='sent': delivered.append(n.body);n.status='sent';s.commit()
    monkeypatch.setattr(notify,'deliver',deliver)
    # Friday morning both next forecasts are already stored from Thursday night.
    ingest(db,draw(),None,'cwl')
    from lottery.predict import generate_tickets
    dlt={'game':'dlt','issue':'2026120','draw_date':'2026-10-21',**generate_tickets('dlt',1,1)[0], 'prizes':{},'source_url':'https://www.lottery.gov.cn/','sales':None,'pool':None,'rule_version':'dlt-2026014'}
    ingest(db,dlt,None,'sporttery')
    for game in ('dlt','ssq'): persist_prediction(db,game,datetime(2026,10,22,22,30,tzinfo=TZ))
    db.commit()
    for _ in range(2): send_morning_report(datetime(2026,10,23,8,tzinfo=TZ))
    assert len(delivered)==1
    assert delivered[0].count('5 注单式')==2
    assert db.scalar(select(func.count()).select_from(Prediction))==2
    assert send_morning_report(datetime(2026,10,23,22,30,tzinfo=TZ))['status']=='outside_send_window'
    # A later morning without fresh results must not send these stale numbers.
    send_morning_report(datetime(2026,10,26,8,tzinfo=TZ))
    assert '5 注单式' not in delivered[-1]
