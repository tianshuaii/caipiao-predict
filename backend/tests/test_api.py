import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
from lottery.api import app, database
from lottery.models import Base
from lottery.ingestion import ingest

@pytest.fixture
def api():
    engine=create_engine('sqlite://',connect_args={'check_same_thread':False},poolclass=StaticPool)
    Base.metadata.create_all(engine)
    def db():
        with Session(engine) as s: yield s
    app.dependency_overrides[database]=db
    with TestClient(app) as client: yield client,engine
    app.dependency_overrides.clear()

def test_empty_dashboard_and_secrets_not_exposed(api):
    client,_=api
    result=client.get('/api/overview')
    assert result.status_code==200
    assert result.json()['games']['ssq']['latest'] is None
    assert 'SENDKEY' not in result.text and 'DATABASE_URL' not in result.text

def test_invalid_game_and_pagination(api):
    client,_=api
    assert client.get('/api/draws?game=wrong').status_code==422
    assert client.get('/api/draws?game=ssq&limit=10000').status_code==422
    assert client.get('/api/draws?game=ssq&offset=-1').status_code==422

def test_draws_filter_and_source_provenance(api):
    client,engine=api
    from test_workflow import draw
    with Session(engine) as session:
        ingest(session,draw(),None,'cwl');session.commit()
    response=client.get('/api/draws?game=ssq').json()
    assert response['total']==1 and response['items'][0]['issue']=='2026121'
    assert response['items'][0]['sources']==['cwl']
    assert client.get('/api/draws?game=dlt').json()['items']==[]

def test_drawn_prediction_is_not_displayed_as_next(api,tmp_path,monkeypatch):
    from datetime import datetime
    import lottery.workflow as workflow
    from lottery.domain import TZ
    from test_workflow import draw
    monkeypatch.setattr(workflow,'ARTIFACTS',tmp_path)
    client,engine=api
    with Session(engine) as session:
        ingest(session,draw(),None,'cwl')
        p=workflow.persist_prediction(session,'ssq',datetime(2026,10,23,8,tzinfo=TZ))
        ingest(session,dict(draw('2026122','2026-10-25'),**p.tickets[0]),None,'cwl')
        session.commit()
    assert client.get('/api/overview').json()['games']['ssq']['prediction'] is None

def test_strategy_status_is_read_only_and_starts_with_no_evidence(api):
    client,_=api
    result=client.get('/api/strategies?game=ssq')
    assert result.status_code==200
    assert result.json()['active']=='uniform-v1'
    assert result.json()['candidates']==[]
    assert client.get('/api/strategies?game=unknown').status_code==422
    assert client.post('/api/strategies?game=ssq').status_code==405
