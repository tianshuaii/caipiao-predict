from decimal import Decimal
from datetime import datetime, timezone
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
from .db import session_factory
from .domain import GAMES, TZ
from .ingestion import coverage
from .models import Draw, Experiment, Notification, Observation, Prediction, Run, Settlement

app=FastAPI(title='拾数 · Lottery Lab',version='0.1.0')
app.add_middleware(CORSMiddleware,allow_origins=['http://127.0.0.1:9998','http://localhost:9998'],allow_methods=['GET'],allow_headers=['Accept','Content-Type'])

def database():
    with session_factory()() as session: yield session

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
def draws(db:DB,game:Game='dlt',limit:Annotated[int,Query(ge=1,le=100)]=20,offset:Annotated[int,Query(ge=0)]=0):
    query=select(Draw).where(Draw.game==game)
    rows=list(db.scalars(query.order_by(Draw.issue.desc()).limit(limit).offset(offset)))
    total=db.scalar(select(func.count()).select_from(Draw).where(Draw.game==game))
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
