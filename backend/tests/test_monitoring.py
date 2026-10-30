from lottery.monitoring import transition,check_once


def test_dedup_recovery_and_unknown():
    state={}
    transition(state,{'database':False,'scheduler':False},'now')
    assert len(state['events'])==2
    transition(state,{'database':False,'scheduler':None},'later')
    assert len(state['events'])==2
    transition(state,{'database':True,'scheduler':True},'last')
    assert len(state['events'])==4
    assert all(e['kind']=='recovery' for e in state['events'][2:])


def test_persist_and_send_once(tmp_path):
    calls=[]
    for _ in range(2):check_once(tmp_path,probe=lambda:{'database':False},sender=lambda e:calls.append(e) or 'sent',send=True)
    assert len(calls)==1
    check_once(tmp_path,probe=lambda:{'database':True},sender=lambda e:calls.append(e) or 'sent',send=True)
    assert len(calls)==2


def test_unknown_delivery_not_retried(tmp_path):
    def broken(e):raise RuntimeError('secret-sendkey')
    state=check_once(tmp_path,probe=lambda:{'database':False},sender=broken,send=True)
    assert state['events'][0]['delivery']=='uncertain'
    assert 'secret' not in (tmp_path/'monitor.json').read_text()
    calls=[]
    check_once(tmp_path,probe=lambda:{'database':False},sender=lambda e:calls.append(e),send=True)
    assert not calls

from test_api import api
from sqlalchemy.orm import Session
from datetime import datetime,timedelta,timezone


def test_database_fault_signals_and_recovery(api):
    from lottery.monitoring import database_checks
    from lottery.models import Run,ResearchJob
    _,engine=api;now=datetime.now(timezone.utc).replace(tzinfo=None)
    with Session(engine) as s:
        run=Run(kind='nightly',status='partial',started_at=now,details={'ssq':{'error':'SECRET'}})
        job=ResearchJob(status='running',config={'model':'frequency'},snapshot=[],snapshot_hash='x',submitted_by='test',created_at=now,started_at=now-timedelta(hours=2))
        s.add_all([run,job]);s.commit()
        checks=database_checks(s,now)
        assert not checks['nightly'] and not checks['research'] and not checks['sources']
        run.status='success';run.details={'ssq':{'pending':False}};job.status='succeeded';s.commit()
        checks=database_checks(s,now)
        assert checks['nightly'] and checks['research'] and checks['sources'] and checks['latest']


def test_db_outage_keeps_dependency_unknown(tmp_path,monkeypatch):
    import lottery.config as config
    from lottery.monitoring import probe_health
    monkeypatch.setattr(config,'database_url',lambda:'invalid-driver://SECRET')
    state=probe_health(tmp_path)
    assert state['database'] is False and state['nightly'] is None and state['scheduler'] is False
    (tmp_path/'scheduler.json').write_text(__import__('json').dumps({'heartbeat':datetime.now(timezone.utc).isoformat()}))
    assert probe_health(tmp_path)['scheduler'] is True


def test_state_api_without_business_database(api,tmp_path,monkeypatch):
    import lottery.api as routes
    monkeypatch.setattr(routes,'RUNTIME',tmp_path)
    client,_=api
    assert not client.get('/api/monitoring').json()['monitor_fresh']
    check_once(tmp_path,probe=lambda:{'disk':False})
    assert client.get('/api/monitoring').json()['monitor_fresh']
    (tmp_path/'monitor.json').write_text('invalid')
    assert client.get('/api/monitoring').status_code==503


def test_default_no_send_and_event_retention(tmp_path):
    calls=[]
    check_once(tmp_path,probe=lambda:{'disk':False},sender=lambda e:calls.append(e))
    assert not calls
    state={}
    for i in range(220):transition(state,{'disk':i%2==1},str(i))
    assert len(state['events'])==200 and state['sequence']==220


def test_retired_candidate_failure_does_not_latch_current_health(api):
    from lottery.models import CandidateForecast
    from lottery.monitoring import database_checks
    _,engine=api;now=datetime.now(timezone.utc).replace(tzinfo=None)
    with Session(engine) as s:
        for issue,strategy,error in [('2025001','old','failure'),('2025002','new',None)]:
            s.add(CandidateForecast(game='ssq',issue=issue,strategy=strategy,model='frequency',cutoff_at=now,cutoff_issue='2024001',seed='1',snapshot_path='x',dataset_hash='x',provenance={},error=error))
        s.commit()
        assert database_checks(s,now)['candidates']


def test_running_collection_does_not_claim_source_or_latest_failure(api):
    from lottery.monitoring import database_checks
    from lottery.models import Run
    _,engine=api;now=datetime.now(timezone.utc).replace(tzinfo=None)
    with Session(engine) as s:
        s.add(Run(kind='nightly',status='running',started_at=now,details={}));s.commit()
        checks=database_checks(s,now)
        assert checks['nightly'] and checks['sources'] is None and checks['latest'] is None
