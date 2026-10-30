import pytest
from lottery.jobs import JobConfig, create_job, catalog, execute_job
from test_prospective import session


def test_config_rejects_unbounded_or_unknown_inputs():
    for value in ({'model':'shell'},{'window':10000},{'periods':21},{'budget':1000},{'code':'print(1)'},{'window':True}):
        with pytest.raises(ValueError):JobConfig(game='ssq',issue_to='2026121',**value)
    assert catalog()['max_active']==1


def test_submission_freezes_snapshot_and_rejects_active(session):
    from lottery.ingestion import ingest
    from test_workflow import draw
    for i in range(1,162):ingest(session,draw(f'2025{i:03d}','2025-10-01'),None,'cwl')
    config=JobConfig(game='ssq',issue_to='2025161',model='frequency',window=160,periods=1,budget=10)
    job=create_job(session,config,'operator');assert job.status=='queued'
    assert len(job.snapshot)==161 and job.config['window']==160
    with pytest.raises(ValueError,match='active'):create_job(session,config,'operator')
    from lottery.models import Draw
    from sqlalchemy import select
    row=session.scalar(select(Draw));row.data={**row.data,'back':[2]};session.flush()
    assert job.snapshot[0]['back']==[1]


def test_run_failure_releases_slot(session,monkeypatch):
    from lottery.models import ResearchJob
    import lottery.jobs as jobs
    job=ResearchJob(status='running',active_slot=1,config={},snapshot=[],snapshot_hash='x',submitted_by='operator')
    session.add(job);session.commit()
    def fail(*args):raise RuntimeError('secret-in-error')
    monkeypatch.setattr(jobs,'compute',fail)
    execute_job(session,job)
    assert job.status=='failed' and job.active_slot is None
    assert 'secret-in-error' not in job.error


def test_synthetic_backtest_artifact_and_protocol_restore(session,monkeypatch,tmp_path):
    import lottery.config as settings
    from lottery.experiments import PROTOCOL
    from lottery.ingestion import ingest
    from test_workflow import draw
    monkeypatch.setattr(settings,'RUNTIME',tmp_path)
    for i in range(1,162):ingest(session,draw(f'2025{i:03d}','2025-10-01'),None,'cwl')
    job=create_job(session,JobConfig(game='ssq',issue_to='2025161',window=160,periods=1,budget=10),'operator')
    original=dict(PROTOCOL);job.status='running';session.commit();execute_job(session,job)
    assert job.status=='succeeded' and job.active_slot is None
    assert PROTOCOL==original
    assert job.result['records'][0]['cutoff_issue']=='2025160'
    assert job.result['records'][0]['issue']=='2025161'
    assert len(job.result['records'])==2 and len(job.result['artifacts'])==1
    artifact=job.result['artifacts'][0]
    assert artifact['metadata']['history_count']==160
    assert (tmp_path/'research-models'/(artifact['id']+'.pkl')).exists()


def test_job_api_authorization_and_submission(api,configured):
    from test_auth import login,ORIGIN
    from sqlalchemy.orm import Session
    from lottery.ingestion import ingest
    from test_workflow import draw
    client,engine=api
    body={'game':'ssq','issue_to':'2025161','window':160,'periods':1,'budget':10}
    assert client.post('/api/research/jobs',json=body,headers=ORIGIN).status_code==401
    with Session(engine) as s:
        for i in range(1,162):ingest(s,draw(f'2025{i:03d}','2025-10-01'),None,'cwl')
        s.commit()
    csrf=login(client).json()['csrf_token'];headers={**ORIGIN,'X-CSRF-Token':csrf}
    first=client.post('/api/research/jobs',json=body,headers=headers)
    assert first.status_code==202 and first.json()['status']=='queued'
    assert client.post('/api/research/jobs',json=body,headers=headers).status_code==409
    assert client.get('/api/research/jobs').json()['total']==1
    assert len(client.get('/api/research/jobs/'+str(first.json()['id'])).json()['snapshot'])==161

from test_api import api
from test_auth import configured


def test_worker_recovers_interrupt_and_is_exclusive(session,monkeypatch,tmp_path):
    import fcntl
    import lottery.config as settings
    import lottery.db as db
    import lottery.jobs as jobs
    from sqlalchemy.orm import sessionmaker
    from lottery.models import ResearchJob
    monkeypatch.setattr(settings,'RUNTIME',tmp_path)
    monkeypatch.setattr(db,'session_factory',lambda:sessionmaker(session.bind,expire_on_commit=False))
    interrupted=ResearchJob(status='running',active_slot=1,config={},snapshot=[],snapshot_hash='x',submitted_by='operator')
    session.add(interrupted);session.commit()
    with (tmp_path/'research-worker.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        with pytest.raises(SystemExit,match='already running'):jobs.worker(once=True)
    jobs.worker(once=True);session.refresh(interrupted)
    assert interrupted.status=='failed' and interrupted.active_slot is None
    queued=ResearchJob(status='queued',active_slot=1,config={},snapshot=[],snapshot_hash='x',submitted_by='operator')
    session.add(queued);session.commit()
    monkeypatch.setattr(jobs,'compute',lambda job:{'synthetic':True})
    jobs.worker(once=True);session.refresh(queued)
    assert queued.status=='succeeded' and queued.started_at and queued.finished_at


def test_keyboard_interrupt_marks_task_failed(session,monkeypatch):
    from lottery.models import ResearchJob
    import lottery.jobs as jobs
    job=ResearchJob(status='running',active_slot=1,config={},snapshot=[],snapshot_hash='x',submitted_by='operator')
    session.add(job);session.commit()
    def interrupt(*args):raise KeyboardInterrupt()
    monkeypatch.setattr(jobs,'compute',interrupt)
    with pytest.raises(KeyboardInterrupt):execute_job(session,job)
    assert job.status=='failed' and job.active_slot is None


def test_job_migration_adds_table_without_touching_history(tmp_path,monkeypatch):
    from pathlib import Path
    from sqlalchemy import create_engine,inspect,select,func
    from sqlalchemy.orm import Session
    from alembic import command
    from alembic.config import Config
    from lottery.models import Base,Draw
    from lottery.ingestion import ingest
    from test_workflow import draw
    import lottery.db as db
    engine=create_engine('sqlite:///'+str(tmp_path/'jobs.db'))
    Base.metadata.create_all(engine,tables=[t for t in Base.metadata.sorted_tables if t.name!='research_jobs'])
    with Session(engine) as s:ingest(s,draw(),None,'cwl');s.commit()
    monkeypatch.setattr(db,'engine',lambda:engine)
    cfg=Config(str(Path(__file__).resolve().parents[1]/'alembic.ini'))
    command.stamp(cfg,'006');command.upgrade(cfg,'head');command.upgrade(cfg,'head')
    assert 'research_jobs' in inspect(engine).get_table_names()
    with Session(engine) as s:assert s.scalar(select(func.count()).select_from(Draw))==1


def test_compute_integrity_version_and_exception_restore(monkeypatch):
    from lottery.models import ResearchJob
    from lottery.jobs import compute,digest
    from lottery.experiments import PROTOCOL
    import lottery.experiment_registry as registry
    import lottery.model_training as training
    from test_workflow import draw
    rows=[draw(f'2025{i:03d}','2025-10-01') for i in range(1,161)]
    config=JobConfig(game='ssq',kind='train',issue_to='2025160',window=160,periods=1,budget=10).model_dump()
    monkeypatch.setattr(registry,'fingerprint',lambda model:'recipe')
    job=ResearchJob(config=config,snapshot=rows,snapshot_hash='broken',recipe_hash='recipe')
    with pytest.raises(ValueError,match='integrity'):compute(job)
    job.snapshot_hash=digest(rows);job.recipe_hash='changed'
    with pytest.raises(ValueError,match='Recipe changed'):compute(job)
    job.recipe_hash='recipe';original=dict(PROTOCOL)
    def fail(*args):
        assert PROTOCOL['training_window']==160
        raise RuntimeError('synthetic failure')
    monkeypatch.setattr(training,'fit_model',fail)
    with pytest.raises(RuntimeError):compute(job)
    assert PROTOCOL==original
