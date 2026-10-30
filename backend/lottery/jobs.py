"""Bounded, single-host research worker; never invoked inside the API process."""
import hashlib
import json
import time
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from .models import Draw, ResearchJob, utcnow
from .indicators import STRATEGIES

MODELS=('frequency','logistic',*STRATEGIES)

class JobConfig(BaseModel):
    model_config=ConfigDict(extra='forbid')
    game:Literal['ssq','dlt']
    kind:Literal['train','backtest']='backtest'
    model:str='frequency'
    window:int=Field(default=300,strict=True)
    periods:int=Field(default=5,ge=1,le=20,strict=True)
    budget:int=Field(default=50,ge=10,le=200,strict=True)
    seed:int=Field(default=20261023,ge=0,le=2**32-1,strict=True)
    issue_to:str=Field(pattern=r'^[0-9]{7}$')

    @field_validator('model')
    @classmethod
    def valid_model(cls,value):
        if value not in MODELS:raise ValueError('Unsupported model')
        return value

    @field_validator('window')
    @classmethod
    def valid_window(cls,value):
        if value not in (160,300,500):raise ValueError('Unsupported training window')
        return value

    @model_validator(mode='after')
    def valid_budget(self):
        if self.kind=='train' and self.periods!=1:raise ValueError('Training requires periods=1')
        if self.periods*10>self.budget:raise ValueError('Budget below planned model cost')
        return self


def catalog():
    return {'models':[{'id':m,'features':list(STRATEGIES.get(m,()))} for m in MODELS],
            'windows':[160,300,500],'max_periods':20,'max_budget':200,'max_active':1,
            'note':'研究任务独立于正式策略；特征方案随模型固定。回测使用当前修订快照，不作为前瞻晋升证据。每期模型和随机基线各5注，模型成本10元/期。训练不产生购买建议。'}


def digest(value):return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()


def create_job(session,config,username):
    from .experiment_registry import fingerprint
    if session.scalar(select(ResearchJob.id).where(ResearchJob.active_slot==1)):
        raise ValueError('active task exists')
    needed=config.window+(config.periods if config.kind=='backtest' else 0)
    rows=list(session.scalars(select(Draw).where(Draw.game==config.game,Draw.issue<=config.issue_to).order_by(Draw.issue.desc()).limit(needed)))
    if len(rows)!=needed or rows[0].issue!=config.issue_to:raise ValueError('Insufficient history or missing cutoff issue')
    if any(r.conflict for r in rows):raise ValueError('Snapshot contains conflicted draws')
    snapshot=json.loads(json.dumps([r.data for r in reversed(rows)]))
    job=ResearchJob(active_slot=1,status='queued',submitted_by=username,config=config.model_dump(),
                    snapshot=snapshot,snapshot_hash=digest(snapshot),recipe_hash=fingerprint(config.model))
    session.add(job)
    try:session.commit()
    except IntegrityError as exc:
        session.rollback();raise ValueError('active task exists') from exc
    return job


def compute(job):
    from .experiments import PROTOCOL, encoded
    from .experiment_registry import fingerprint
    from .model_training import fit_model, predict_model
    from .model_artifacts import save_model
    from .config import RUNTIME
    from .selection import select_tickets, WEIGHTED
    from .settlement import settle_ticket
    from .evaluation import evaluation_record, compare_records
    from .domain import GAMES
    import numpy as np
    c=JobConfig.model_validate(job.config)
    if digest(job.snapshot)!=job.snapshot_hash:raise ValueError('Snapshot integrity failure')
    if fingerprint(c.model)!=job.recipe_hash:raise ValueError('Recipe changed; submit a new task')
    original=dict(PROTOCOL)
    try:
        PROTOCOL.update(training_window=c.window,seed=c.seed)
        rows=job.snapshot
        if c.kind=='train':
            model=fit_model(c.game,rows,c.model)
            artifact=save_model(model,RUNTIME/'research-models')
            return {'kind':'train','artifact':artifact,'probabilities':predict_model(model),
                    'note':'离线研究产物，不注册正式候选，不改变预测。'}
        records=[];scores=[];artifacts=[]
        for index in range(c.window,len(rows)):
            actual=rows[index];past=rows[index-c.window:index]
            model=fit_model(c.game,past,c.model);prob=predict_model(model)
            artifacts.append({'issue':actual['issue'],**save_model(model,RUNTIME/'research-models')})
            target=np.concatenate([encoded([actual],z,GAMES[c.game][z][0])[0] for z in ('front','back')])
            baseline=np.concatenate([np.full(GAMES[c.game][z][0],GAMES[c.game][z][1]/GAMES[c.game][z][0]) for z in ('front','back')])
            scores.append({'issue':actual['issue'],'model_brier':float(np.mean((np.array(prob['front']+prob['back'])-target)**2)),
                           'uniform_brier':float(np.mean((baseline-target)**2))})
            for name in (c.model,'uniform'):
                tickets=select_tickets(c.game,c.seed+index) if name=='uniform' else select_tickets(c.game,c.seed+index,protocol=WEIGHTED,probabilities=prob)
                results=[settle_ticket(c.game,t,actual) for t in tickets]
                records.append(evaluation_record(mode='historical',game=c.game,strategy=name,issue=actual['issue'],
                    cutoff_issue=past[-1]['issue'],tickets=tickets,results=results,rule_version=actual['rule_version']))
        return {'kind':'backtest','records':records,'scores':scores,'artifacts':artifacts,
                'comparison':compare_records(records,[c.model,'uniform']),
                'note':'当前修订数据的探索性滚动回测，随机基线仅一条轨迹；不是前瞻证据，不作显著性或优势声明。'}
    finally:
        PROTOCOL.clear();PROTOCOL.update(original)


def execute_job(session,job):
    try:
        job.result=compute(job);job.status='succeeded'
    except (KeyboardInterrupt,SystemExit):
        job.status='failed';job.error='Worker interrupted; submit a new task'
        raise
    except Exception as exc:
        job.status='failed';job.error=f'{type(exc).__name__}: 研究执行失败，请核对快照、版本和运行环境后新建任务'
    finally:
        job.finished_at=utcnow();job.active_slot=None
        session.commit()


def job_view(job,detail=False):
    stamp=lambda v:v.isoformat()+'Z' if v else None
    result={'id':job.id,'status':job.status,'config':job.config,'created_at':stamp(job.created_at),
            'started_at':stamp(job.started_at),'finished_at':stamp(job.finished_at),
            'duration_seconds':max(0,((job.finished_at or utcnow())-job.started_at).total_seconds()) if job.started_at else None,
            'snapshot_hash':job.snapshot_hash,'recipe_hash':job.recipe_hash,'error':job.error}
    if detail:result.update(snapshot=job.snapshot,result=job.result)
    return result


def worker(once=False):
    import fcntl
    from .config import RUNTIME
    from .db import session_factory
    with (RUNTIME/'research-worker.lock').open('a') as lock:
        try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:raise SystemExit('Research worker already running')
        with session_factory()() as session:
            for job in session.scalars(select(ResearchJob).where(ResearchJob.status=='running')):
                job.status='failed';job.active_slot=None;job.finished_at=utcnow();job.error='Worker interrupted; submit a new task'
            session.commit()
        while True:
            with session_factory()() as session:
                job=session.scalar(select(ResearchJob).where(ResearchJob.status=='queued',ResearchJob.active_slot==1).order_by(ResearchJob.id).limit(1))
                if job:
                    job.status='running';job.started_at=utcnow();session.commit()
                    execute_job(session,job)
            if once:return
            time.sleep(5)
