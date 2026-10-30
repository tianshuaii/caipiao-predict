from decimal import Decimal
from datetime import date, datetime, timezone
import json
from typing import Annotated, Literal
from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import func, select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from apscheduler.triggers.cron import CronTrigger
from .config import RUNTIME
from .domain import GAMES, TZ
from .ingestion import coverage
from .models import Draw, Experiment, Notification, Observation, Prediction, Run, Settlement

from .auth import access_control, database, router as auth_router

app=FastAPI(title='拾数 · Lottery Lab',version='0.1.0',dependencies=[Depends(access_control)])
app.include_router(auth_router)
app.add_middleware(CORSMiddleware,allow_origins=['http://127.0.0.1:9998','http://localhost:9998'],allow_methods=['GET'],allow_headers=['Accept','Content-Type'])

DB=Annotated[Session,Depends(database)]
Game=Literal['dlt','ssq']

@app.exception_handler(SQLAlchemyError)
async def database_error(request, exc):
    return JSONResponse(status_code=503,content={'detail':'数据库暂不可用，请检查本地 MySQL 服务。'})

def timestamp(value):
    return value.isoformat()+'Z' if value else None

def draw_view(row):
    return {**row.data,'id':row.id,'revision':row.revision,'source':row.source,'sources':row.sources,'conflict':row.conflict,'updated_at':timestamp(row.updated_at)}

def prediction_view(session,p):
    draw=session.scalar(select(Draw).where(Draw.game==p.game,Draw.issue==p.issue))
    settlement=session.scalar(select(Settlement).where(Settlement.prediction_id==p.id,Settlement.draw_fingerprint==draw.fingerprint).order_by(Settlement.id.desc()).limit(1)) if draw and not draw.conflict else None
    return {'id':p.id,'game':p.game,'issue':p.issue,'draw_date':p.draw_date.isoformat(),'created_at':timestamp(p.created_at),'cutoff_issue':p.cutoff_issue,'strategy':p.strategy,'tickets':p.tickets,'seed':p.seed,'dataset_hash':p.dataset_hash,'provenance':p.provenance,'probabilities':p.probabilities,'actual':draw_view(draw) if draw else None,'settlement':{'results':settlement.results,'summary':settlement.summary,'created_at':timestamp(settlement.created_at)} if settlement else None}

def schedule_view():
    next_run=CronTrigger(day_of_week='mon,wed,fri',hour=8,minute=0,timezone=TZ).get_next_fire_time(None,datetime.now(TZ))
    heartbeat=RUNTIME/'scheduler.json'
    status={'running':False}
    if heartbeat.exists():
        try:
            status=json.loads(heartbeat.read_text())
            status['running']=(datetime.now(timezone.utc)-datetime.fromisoformat(status['heartbeat'])).total_seconds()<120
        except (ValueError,KeyError): status={'running':False}
    return {'timezone':'Asia/Shanghai','label':'每天22:30分析，未齐则重试至00:00；周一、三、五08:00推送','next_run':next_run.isoformat(),'scheduler':status}

@app.get('/api/health')
def health(db:DB):
    db.execute(text('SELECT 1'))
    return {'status':'ok','database':'connected'}

@app.get('/api/overview')
def overview(db:DB):
    games={}
    for game,definition in GAMES.items():
        latest=db.scalar(select(Draw).where(Draw.game==game).order_by(Draw.issue.desc()).limit(1))
        recent=list(db.scalars(select(Draw).where(Draw.game==game).order_by(Draw.issue.desc()).limit(20)))
        predictions=list(db.scalars(select(Prediction).where(Prediction.game==game).order_by(Prediction.issue.desc())))
        views=[prediction_view(db,p) for p in predictions]
        settled=[v['settlement']['summary'] for v in views if v['settlement'] and v['settlement']['summary']['pending']==0]
        last_prediction=next((v for v in views if not v['actual'] and v['draw_date'] >= datetime.now(TZ).date().isoformat() and (not latest or v['issue'] > latest.issue)),None)
        frequency=[{'number':i,'count':sum(i in r.data['front'] for r in recent)} for i in range(1,definition['front'][0]+1)]
        games[game]={'name':definition['name'],'latest':draw_view(latest) if latest else None,'prediction':last_prediction,'coverage':coverage(db,game),'recent':[draw_view(r) for r in recent], 'frequency':frequency,
            'stats':{'predictions':len(predictions),'settled_periods':len(settled),'committed_cost':len(predictions)*10,'settled_cost':sum(float(s['cost']) for s in settled),'return':sum(float(s['amount']) for s in settled),'net':sum(float(s['net']) for s in settled),'winning_tickets':sum(s['winning_tickets'] for s in settled)}}
    return {'games':games,'schedule':schedule_view(),'generated_at':datetime.now(TZ).isoformat()}

@app.get('/api/draws')
def draws(db:DB,game:Game='dlt',limit:Annotated[int,Query(ge=1,le=100)]=20,offset:Annotated[int,Query(ge=0)]=0,
          issue_from:Annotated[str | None,Query(pattern=r'^[0-9]{7}$')]=None,
          issue_to:Annotated[str | None,Query(pattern=r'^[0-9]{7}$')]=None,
          date_from:date | None=None,date_to:date | None=None,conflict:bool | None=None):
    if issue_from and issue_to and issue_from>issue_to:
        raise HTTPException(422,'起始期号不能晚于结束期号')
    if date_from and date_to and date_from>date_to:
        raise HTTPException(422,'起始日期不能晚于结束日期')
    filters=[Draw.game==game]
    if issue_from: filters.append(Draw.issue>=issue_from)
    if issue_to: filters.append(Draw.issue<=issue_to)
    if date_from: filters.append(Draw.draw_date>=date_from)
    if date_to: filters.append(Draw.draw_date<=date_to)
    if conflict is not None: filters.append(Draw.conflict.is_(conflict))
    rows=list(db.scalars(select(Draw).where(*filters).order_by(Draw.issue.desc()).limit(limit).offset(offset)))
    total=db.scalar(select(func.count()).select_from(Draw).where(*filters))
    return {'items':[draw_view(r) for r in rows],'total':total,'limit':limit,'offset':offset}

@app.get('/api/draws/{game}/{issue}')
def draw_details(game:Game,issue:str,db:DB):
    row=db.scalar(select(Draw).where(Draw.game==game,Draw.issue==issue))
    if not row: raise HTTPException(404,'没有找到该期数据')
    obs=list(db.scalars(select(Observation).where(Observation.draw_id==row.id).order_by(Observation.id)))
    return {**draw_view(row),'observations':[{'source':r.source,'raw_id':r.raw_id,'conflict':r.conflict,'created_at':timestamp(r.created_at),'data':r.data} for r in obs]}

@app.get('/api/predictions')
def predictions(db:DB,game:Game='dlt',limit:Annotated[int,Query(ge=1,le=100)]=20,offset:Annotated[int,Query(ge=0)]=0):
    rows=list(db.scalars(select(Prediction).where(Prediction.game==game).order_by(Prediction.issue.desc()).limit(limit).offset(offset)))
    return {'items':[prediction_view(db,p) for p in rows],'total':db.scalar(select(func.count()).select_from(Prediction).where(Prediction.game==game))}

@app.get('/api/experiments')
def experiments(db:DB,game:Game='dlt'):
    rows=list(db.scalars(select(Experiment).where(Experiment.game==game).order_by(Experiment.id.desc()).limit(10)))
    return {'items':[{'id':r.id,'created_at':timestamp(r.created_at),**r.result} for r in rows]}

@app.get('/api/tasks')
def tasks(db:DB):
    runs=list(db.scalars(select(Run).order_by(Run.id.desc()).limit(30)))
    notices=list(db.scalars(select(Notification).order_by(Notification.id.desc()).limit(20)))
    return {'runs':[{'id':r.id,'kind':r.kind,'status':r.status,'started_at':timestamp(r.started_at),'finished_at':timestamp(r.finished_at),'details':({k:v for k,v in r.details.items() if k != 'issues'} if r.kind=='inventory' else r.details)} for r in runs], 'notifications':[{'id':n.id,'title':n.title,'status':n.status,'attempts':n.attempts,'detail':n.detail,'created_at':timestamp(n.created_at)} for n in notices],'schedule':schedule_view()}

@app.get("/api/strategies")
def strategies(db:DB,game:Game="dlt"):
    from .prospective import status
    result=status(db,game)
    from .models import CandidateForecast, CandidateScore
    forecasts=list(db.scalars(select(CandidateForecast).where(CandidateForecast.game==game).order_by(CandidateForecast.id.desc()).limit(30)))
    items=[]
    for f in forecasts:
        draw=db.scalar(select(Draw).where(Draw.game==game,Draw.issue==f.issue))
        score=db.scalar(select(CandidateScore).where(CandidateScore.forecast_id==f.id,CandidateScore.draw_fingerprint==draw.fingerprint)) if draw and not draw.conflict else None
        items.append({'id':f.id,'issue':f.issue,'strategy':f.strategy,'tickets':f.tickets,'error':f.error,'created_at':timestamp(f.created_at),'metrics':score.metrics if score else None})
    result['forecasts']=items
    from .portfolio import portfolio_status
    result['portfolio']=portfolio_status(db,game)
    return result

@app.get('/api/winner-cases')
def winner_cases(db:DB,game:Game='dlt',ticket_type:Literal['all','single','multiple','banker','mixed','unknown']='all',limit:Annotated[int,Query(ge=1,le=50)]=20,offset:Annotated[int,Query(ge=0)]=0):
    from .models import WinnerCase
    from .winner_cases import NOTICE
    filters=[WinnerCase.game==game,WinnerCase.active.is_(True)]
    if ticket_type!='all': filters.append(WinnerCase.ticket_type==ticket_type)
    rows=db.scalars(select(WinnerCase).where(*filters).order_by(WinnerCase.issue.desc(),WinnerCase.id.desc()).offset(offset).limit(limit))
    return {'items':[{'id':r.id,'game':r.game,'issue':r.issue,'ticket_type':r.ticket_type,'title':r.title,
                      'article_url':r.article_url,'source':r.source,'published_date':r.published_date.isoformat() if r.published_date else None,
                      'fetched_at':timestamp(r.fetched_at),'evidence':r.evidence,'details':r.details,'images':r.images,
                      'status':r.status,'parser_version':r.parser_version,'raw_id':r.raw_id} for r in rows],
            'total':db.scalar(select(func.count()).select_from(WinnerCase).where(*filters)),
            'limit':limit,'offset':offset,'notice':NOTICE}

@app.get('/api/data-quality')
def data_quality(db:DB,game:Game='dlt'):
    from .data_history import quality_view
    return quality_view(db,game)

@app.get('/api/history-as-of')
def history_as_of_view(db:DB,as_of:datetime,game:Game='dlt',limit:Annotated[int,Query(ge=1,le=100)]=20,offset:Annotated[int,Query(ge=0)]=0):
    from .data_history import history_as_of
    if as_of.tzinfo is None:
        raise HTTPException(422,'as_of必须包含时区，例如2026-10-26T08:00:00+08:00')
    result=history_as_of(db,game,as_of)
    result['items']=result['items'][offset:offset+limit]
    return {**result,'limit':limit,'offset':offset}

@app.get('/api/features/catalog')
def features_catalog():
    from .feature_service import feature_catalog
    return feature_catalog()

@app.get('/api/features')
def features(db:DB,as_of:datetime,cutoff_issue:str,game:Game='dlt',
             zone:Literal['front','back']='front',window:Literal['10','20','30','50','100','500','all']='20'):
    from .data_history import history_as_of
    from .domain import canonical_issue
    from .feature_service import analyze_features
    if as_of.tzinfo is None:
        raise HTTPException(422,'as_of 必须包含时区')
    try: cutoff=canonical_issue(cutoff_issue)
    except ValueError as exc: raise HTTPException(422,str(exc)) from exc
    snapshot=history_as_of(db,game,as_of,before_issue=str(int(cutoff)+1))
    if snapshot['conflicts'] or snapshot['unavailable_count']:
        raise HTTPException(409,{'message':'截止范围存在冲突或缺少当时观测，不能计算完整统计。',
                                 'conflicts':snapshot['conflicts'],'unavailable_count':snapshot['unavailable_count']})
    result=analyze_features(snapshot['items'],game,zone,cutoff,int(window) if window!='all' else 'all')
    return {**result,'as_of':snapshot['as_of'],'data_mode':snapshot['mode']}

@app.get('/api/research/selection')
def research_selection_api(config:Annotated[str,Query(max_length=2000)]):
    from .research import research_selection
    try: return research_selection(json.loads(config))
    except ValueError as exc: raise HTTPException(422,str(exc)) from exc


@app.get('/api/evaluations')
def evaluations(db:DB,game:Game='dlt',limit:Annotated[int,Query(ge=1,le=200)]=50,
                offset:Annotated[int,Query(ge=0)]=0,
                strategies:Annotated[str,Query(max_length=2000)]='',
                initial_capital:Annotated[Decimal,Query(ge=0,le=1000000000,max_digits=12,decimal_places=2)]=Decimal('1000')):
    from .evaluation import prospective_records,compare_records,VERSION
    from .performance import performance_report
    records=prospective_records(db,game)
    candidates=[r for r in records if r['kind']=='candidate']
    selected=strategies.split(',') if strategies else sorted({r['strategy'] for r in candidates})
    try:
        comparison=compare_records(candidates,selected) if selected else None
    except ValueError as exc: raise HTTPException(422,str(exc)) from exc
    return {'version':VERSION,'mode':'prospective','game':game,'total':len(records),
            'records':list(reversed(records))[offset:offset+limit],'comparison':comparison,
            'performance':performance_report(records,initial_capital),
            'note':'比较基于所选候选版本的共同有效期、同预算和同规则；失败与缺失明确列出。历史回测不计入前瞻样本。'}


@app.get('/api/statistics')
def statistics_reports(limit:Annotated[int,Query(ge=1,le=100)]=20,offset:Annotated[int,Query(ge=0)]=0):
    from .statistics import read_report
    files=sorted((RUNTIME/'statistics').glob('*.json'),key=lambda p:p.stat().st_mtime,reverse=True)
    items=[]
    for file in files[offset:offset+limit]:
        try:
            report=read_report(file.stem,RUNTIME/'statistics')['report']
            items.append({'id':file.stem,'version':report['version'],'dataset_sha256':report['dataset_sha256'],
                          'post_hoc':report['post_hoc'],'total_tests':report['total_tests'],
                          'significant_count':len(report['significant']),'groups':report['groups'],'skipped':report['skipped']})
        except (ValueError,KeyError,OSError): items.append({'id':file.stem,'status':'integrity_error'})
    return {'items':items,'total':len(files)}


@app.get('/api/statistics/{report_id}')
def statistics_report(report_id:str):
    from .statistics import read_report
    import re
    if not re.fullmatch(r'[0-9a-f]{64}',report_id):raise HTTPException(422,'Invalid report id')
    try:return {'id':report_id,**read_report(report_id,RUNTIME/'statistics')}
    except FileNotFoundError as exc:raise HTTPException(404,'Report not found') from exc
    except (ValueError,KeyError) as exc:raise HTTPException(409,'Report integrity failure') from exc

@app.get('/api/rankings')
def rankings(db:DB,game:Game='dlt',objective:Literal['brier','any_prize','first_prize','roi']='brier'):
    from .ranking import ranking_status
    return ranking_status(db,game,objective)

from .jobs import JobConfig

@app.get('/api/research/models')
def research_models():
    from .jobs import catalog
    return catalog()

@app.post('/api/research/jobs',status_code=202)
def submit_research_job(config:JobConfig,db:DB):
    from .jobs import create_job,job_view
    from .auth import settings
    try:return job_view(create_job(db,config,settings()[0]))
    except ValueError as exc:
        raise HTTPException(409 if 'active' in str(exc) else 422,str(exc)) from exc

@app.get('/api/research/jobs')
def research_jobs(db:DB,limit:Annotated[int,Query(ge=1,le=50)]=20,offset:Annotated[int,Query(ge=0)]=0):
    from .models import ResearchJob
    from .jobs import job_view
    rows=db.scalars(select(ResearchJob).order_by(ResearchJob.id.desc()).limit(limit).offset(offset))
    return {'items':[job_view(r) for r in rows],'total':db.scalar(select(func.count()).select_from(ResearchJob))}

@app.get('/api/research/jobs/{job_id}')
def research_job(job_id:int,db:DB):
    from .models import ResearchJob
    from .jobs import job_view
    row=db.get(ResearchJob,job_id)
    if not row:raise HTTPException(404,'任务不存在')
    return job_view(row,True)

@app.get('/api/visualizations')
def visualizations(db:DB,source:Literal['experiment','job'],id:Annotated[int,Query(ge=1)],strategy:str=''):
    from .models import ResearchJob,Experiment
    from .visualization import visual_records
    row=db.get(Experiment if source=='experiment' else ResearchJob,id)
    if row is None:raise HTTPException(404,'研究记录不存在')
    result=row.result or {}
    if source=='job':
        records=result.get('records',[]) if row.status=='succeeded' and row.config.get('kind')=='backtest' else []
    else:
        records=[f['evaluation'] for a in result.get('forecast_audit',[]) for f in a.get('forecasts',{}).values() if 'evaluation' in f]
    choices=sorted({r['strategy'] for r in records}-{'uniform'})
    if strategy and strategy not in choices:raise HTTPException(422,'策略不在此研究记录中')
    selected=strategy or next(iter(choices),'')
    try:projection=visual_records(records,selected) if selected else {'available':False,'groups':[],'note':'尚无可用的逐期评估记录；不会补造历史数据。'}
    except ValueError as exc:raise HTTPException(422,str(exc)) from exc
    return {'source':source,'id':id,'strategies':choices,**projection}

@app.get('/api/research/combinations')
def research_combinations(db:DB,config:Annotated[str,Query(max_length=2000)],issue:Annotated[str,Query(pattern=r'^[0-9]{7}$')]|None=None):
    from .combinations import expand,simulate
    try:
        value=json.loads(config)
        preview=expand(value)
    except (ValueError,TypeError) as exc:raise HTTPException(422,str(exc)) from exc
    if issue is None:return preview
    row=db.scalar(select(Draw).where(Draw.game==preview['config']['game'],Draw.issue==issue))
    if row is None:raise HTTPException(404,'未找到该期开奖数据')
    if row.conflict:raise HTTPException(409,'该期开奖存在来源冲突，暂不结算')
    try:return {**simulate(value,row.data),'draw_fingerprint':row.fingerprint}
    except ValueError as exc:raise HTTPException(422,str(exc)) from exc

from .simulation import SimulationConfig

@app.post('/api/simulations',status_code=201)
def submit_simulation(config:SimulationConfig,db:DB):
    from .simulation import create_simulation,view
    try:return view(create_simulation(db,config),True)
    except ValueError as exc:raise HTTPException(422,str(exc)) from exc

@app.get('/api/simulations')
def simulations(db:DB,limit:Annotated[int,Query(ge=1,le=50)]=20,offset:Annotated[int,Query(ge=0)]=0):
    from .models import SimulationRun
    from .simulation import view
    return {'items':[view(r) for r in db.scalars(select(SimulationRun).order_by(SimulationRun.id.desc()).limit(limit).offset(offset))],
            'total':db.scalar(select(func.count()).select_from(SimulationRun))}

@app.get('/api/simulations/{run_id}')
def simulation_detail(run_id:int,db:DB,replay:bool=False):
    from .models import SimulationRun
    from .simulation import view,replay as replay_run
    row=db.get(SimulationRun,run_id)
    if not row:raise HTTPException(404,'模拟不存在')
    try:return replay_run(row) if replay else view(row,True)
    except ValueError as exc:raise HTTPException(409,str(exc)) from exc

@app.get('/api/monitoring')
def monitoring_status():
    from .monitoring import read_state
    try:
        state=read_state(RUNTIME)
        stamp=state.get('checked_at')
        age=(datetime.now(timezone.utc)-datetime.fromisoformat(stamp)).total_seconds() if stamp else None
        return {**state,'monitor_fresh':age is not None and 0<=age<180}
    except (OSError,ValueError,TypeError):raise HTTPException(503,'监控状态不可读，请检查监控进程及状态文件')

@app.get('/api/research/export')
def research_export(db:DB,game:Game='dlt'):
    from .exports import build_export,encode
    # SQLite's legacy driver does not begin a read snapshot on SELECT alone.
    connection=db.connection()
    if connection.dialect.name=='sqlite':connection.exec_driver_sql('BEGIN')
    return JSONResponse(encode(build_export(db,game,RUNTIME/'statistics')),headers={'Cache-Control':'no-store'})
