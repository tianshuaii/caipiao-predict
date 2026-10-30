"""Independent watchdog with local durable events; no raw exception disclosure."""
import fcntl
import json
import shutil
import time
from datetime import datetime,timezone,timedelta
from .config import RUNTIME

LABELS={'database':'数据库连接','disk':'磁盘余量','scheduler':'调度心跳','nightly':'夜间任务',
        'research':'研究任务','candidates':'候选模型','history_dlt':'大乐透历史完整性',
        'history_ssq':'双色球历史完整性','sources':'开奖来源','latest':'最新开奖数据'}
DB_KEYS=('nightly','research','candidates','history_dlt','history_ssq','sources','latest')


def transition(state,checks,stamp):
    statuses=state.setdefault('checks',{});events=state.setdefault('events',[])
    for key,healthy in checks.items():
        if key not in LABELS:continue
        old=statuses.get(key,{}).get('healthy')
        if healthy is not None and healthy!=old and (healthy is False or old is False):
            state['sequence']=state.get('sequence',0)+1
            events.append({'id':state['sequence'],'key':key,'label':LABELS[key],
                           'kind':'recovery' if healthy else 'fault','at':stamp,'delivery':'disabled'})
        statuses[key]={'healthy':old if healthy is None else healthy,'observed':healthy,'checked_at':stamp}
    state['events']=events[-200:];state['checked_at']=stamp


def database_checks(session,now):
    from sqlalchemy import select,text
    from sqlalchemy.orm import load_only
    from .models import Run,ResearchJob,CandidateForecast
    from .ingestion import coverage
    session.execute(text('SELECT 1'))
    checks={}
    nightly=session.scalar(select(Run).where(Run.kind=='nightly').order_by(Run.id.desc()).limit(1))
    checks['nightly']=bool(nightly and now-nightly.started_at<timedelta(hours=26) and
        (nightly.status=='success' or nightly.status=='running' and now-nightly.started_at<timedelta(hours=1)))
    checks['sources']=None if not nightly or nightly.status=='running' else nightly.status=='success' and all(not v.get('sync',{}).get('crosscheck',{}).get('error') for v in nightly.details.values() if isinstance(v,dict) and v.get('sync',{}).get('crosscheck'))
    checks['latest']=None if not nightly or nightly.status=='running' else nightly.status=='success' and all(not v.get('pending',True) for v in nightly.details.values())
    # Latest task per model: a successful replacement clears the model's failure.
    jobs=list(session.scalars(select(ResearchJob).options(load_only(ResearchJob.id,ResearchJob.config,ResearchJob.status,ResearchJob.started_at,ResearchJob.created_at)).order_by(ResearchJob.id.desc())))
    seen=set();checks['research']=True
    for job in jobs:
        key=(job.config.get('game'),job.config.get('model'),job.config.get('kind'))
        if key in seen:continue
        seen.add(key)
        age=now-(job.started_at or job.created_at)
        if job.status=='failed' or job.status in ('queued','running') and age>timedelta(hours=1):checks['research']=False
    forecasts=list(session.scalars(select(CandidateForecast).options(load_only(CandidateForecast.id,CandidateForecast.game,CandidateForecast.issue,CandidateForecast.strategy,CandidateForecast.error)).order_by(CandidateForecast.id.desc())))
    latest={game:max((f.issue for f in forecasts if f.game==game),default=None) for game in ('dlt','ssq')}
    checks['candidates']=not any(f.error for f in forecasts if f.issue==latest[f.game])
    for game in ('dlt','ssq'):checks['history_'+game]=coverage(session,game)['complete']
    return checks


def probe_health(path=RUNTIME):
    now=datetime.now(timezone.utc)
    checks={k:None for k in DB_KEYS}
    checks['disk']=shutil.disk_usage(path).free>=1024**3
    try:
        heartbeat=json.loads((path/'scheduler.json').read_text())['heartbeat']
        age=(now-datetime.fromisoformat(heartbeat)).total_seconds()
        checks['scheduler']=0<=age<120
    except (OSError,ValueError,KeyError,TypeError):checks['scheduler']=False
    engine=None
    try:
        from sqlalchemy import create_engine
        from sqlalchemy.engine import make_url
        from sqlalchemy.orm import Session
        from .config import database_url
        url=make_url(database_url())
        args={'connect_timeout':5,'read_timeout':5,'write_timeout':5} if 'pymysql' in url.drivername else {'timeout':5} if url.drivername.startswith('sqlite') else {}
        engine=create_engine(url,connect_args=args)
        with Session(engine) as session:checks.update(database_checks(session,now.replace(tzinfo=None)))
        checks['database']=True
    except Exception:checks['database']=False
    finally:
        if engine is not None:engine.dispose()
    return checks


def send_alert(event):
    from .config import sendkey
    import httpx
    key=sendkey()
    if not key or not key.startswith('SCT'):return 'not_configured'
    title='彩票平台监控：'+('恢复' if event['kind']=='recovery' else '故障')+' · '+LABELS[event['key']]
    with httpx.Client(timeout=10) as client:
        response=client.post('https://sctapi.ftqq.com/'+key+'.send',data={'title':title,'desp':f"事件 #{event['id']} · UTC {event['at']}\n请检查平台运行记录。"})
    if response.status_code>=500:return 'uncertain'
    if response.status_code!=200:return 'failed'
    return 'sent' if response.json().get('code')==0 else 'failed'


def read_state(path=RUNTIME):
    file=path/'monitor.json'
    if not file.exists():return {'checks':{},'events':[],'checked_at':None}
    return json.loads(file.read_text())


def save_state(path,state):
    temp=path/'monitor.tmp'
    temp.write_text(json.dumps(state,ensure_ascii=False));temp.replace(path/'monitor.json')


def check_once(path=RUNTIME,*,probe=None,sender=None,send=False):
    path.mkdir(parents=True,exist_ok=True)
    with (path/'monitor.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        state=read_state(path);previous=state.get('sequence',0)
        checks=(probe or (lambda:probe_health(path)))()
        transition(state,checks,datetime.now(timezone.utc).isoformat())
        save_state(path,state)
        for event in state['events']:
            if not send or event['id']<=previous:continue
            event['delivery']='sending';save_state(path,state)
            try:event['delivery']=(sender or send_alert)(event)
            except Exception:event['delivery']='uncertain'
            save_state(path,state)
        return state


def monitor(watch=False,send=False):
    while True:
        try:check_once(send=send)
        except Exception:print('Monitor check failed; inspect local state and permissions',flush=True)
        if not watch:return
        time.sleep(60)
