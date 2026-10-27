from datetime import datetime, timedelta, timezone
from sqlalchemy.orm import Session
from lottery.ingestion import ingest
from lottery.models import Observation
from sqlalchemy import select
from test_api import api
from test_workflow import session,draw


def test_asof_uses_observation_time_not_draw_date(session):
    from lottery.data_history import history_as_of
    t=datetime(2026,10,23,0)
    ingest(session,draw(),None,'cwl')
    first=session.scalar(select(Observation));first.created_at=t
    changed=draw();changed['back']=[2]
    ingest(session,changed,None,'cwl')
    observations=list(session.scalars(select(Observation).order_by(Observation.id)))
    observations[-1].created_at=t+timedelta(days=1)
    session.flush()
    assert history_as_of(session,'ssq',t-timedelta(seconds=1))['items']==[]
    old=history_as_of(session,'ssq',t)
    assert old['items'][0]['back']==[1]
    assert old['items'][0]['observed_at']==t.isoformat()+'Z'
    assert history_as_of(session,'ssq',t+timedelta(days=1))['items'][0]['back']==[2]
    assert history_as_of(session,'ssq',t-timedelta(seconds=1))['unavailable_count']==1


def test_asof_conflict_does_not_leak_backward(session):
    from lottery.data_history import history_as_of
    t=datetime(2026,10,23)
    ingest(session,draw(),None,'cwl')
    session.scalar(select(Observation)).created_at=t
    changed=draw();changed['back']=[2]
    ingest(session,changed,None,'secondary')
    obs=list(session.scalars(select(Observation).order_by(Observation.id)))
    obs[-1].created_at=t+timedelta(hours=1);session.flush()
    assert history_as_of(session,'ssq',t)['items'][0]['conflict'] is False
    later=history_as_of(session,'ssq',t+timedelta(hours=2))
    assert later['items']==[] and later['conflicts']==1


def test_quality_and_asof_api_require_explicit_timezone(api):
    client,engine=api
    with Session(engine) as s:
        ingest(s,draw(),None,'cwl');s.commit()
    quality=client.get('/api/data-quality?game=ssq').json()
    assert quality['draw_count']==1
    assert quality['prize_complete_count']==0
    assert quality['prize_complete_rate']==0
    assert quality['latest_draw_date']=='2026-10-22'
    assert client.get('/api/history-as-of?game=ssq&as_of=2026-10-23T00:00:00').status_code==422
    result=client.get('/api/history-as-of',params={'game':'ssq','as_of':'2000-01-01T00:00:00Z'}).json()
    assert result['items']==[] and result['unavailable_count']==0


def test_reverting_to_an_old_value_is_a_new_observation(session):
    original=draw()
    ingest(session,original,None,'cwl')
    changed=draw();changed['back']=[2]
    ingest(session,changed,None,'cwl')
    ingest(session,original,None,'cwl')
    observations=list(session.scalars(select(Observation).order_by(Observation.id)))
    assert len(observations)==3
    assert observations[0].fingerprint==observations[2].fingerprint


def test_asof_date_correction_does_not_hide_old_observation(session):
    from lottery.data_history import history_as_of
    t=datetime(2026,10,23)
    ingest(session,draw(),None,'cwl')
    session.scalar(select(Observation)).created_at=t
    changed=draw();changed['draw_date']='2026-10-24'
    ingest(session,changed,None,'cwl')
    obs=list(session.scalars(select(Observation).order_by(Observation.id)))
    obs[-1].created_at=t+timedelta(days=2);session.flush()
    assert history_as_of(session,'ssq',t)['items'][0]['draw_date']=='2026-10-22'


def test_repeated_secondary_value_records_new_conflict_state(session):
    from lottery.data_history import history_as_of
    t=datetime(2026,10,23)
    a=draw();b=draw();b['back']=[2]
    for index,(value,source) in enumerate([(a,'cwl'),(a,'secondary'),(b,'cwl'),(a,'secondary')]):
        ingest(session,value,None,source)
        last=session.scalar(select(Observation).order_by(Observation.id.desc()))
        last.created_at=t+timedelta(minutes=index)
        session.flush()
    result=history_as_of(session,'ssq',t+timedelta(minutes=4))
    assert result['conflicts']==1 and result['items']==[]
    assert len(list(session.scalars(select(Observation))))==4
    ingest(session,a,None,'secondary')
    assert len(list(session.scalars(select(Observation))))==4
