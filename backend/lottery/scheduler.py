from datetime import datetime, timedelta, timezone
import fcntl
import json
import os
from apscheduler.schedulers.blocking import BlockingScheduler
from sqlalchemy import select
from .config import RUNTIME
from .db import session_factory
from .domain import TZ
from .models import Run, utcnow
from .workflow import run_workflow


def heartbeat():
    path=RUNTIME/'scheduler.json'
    temporary=path.with_suffix('.tmp')
    temporary.write_text(json.dumps({'pid':os.getpid(),'heartbeat':datetime.now(timezone.utc).isoformat()}))
    temporary.replace(path)


def collection_slot(now):
    now=now.astimezone(TZ)
    if now.hour==0 and now.minute<5: return now.date()-timedelta(days=1),3
    minute=now.hour*60+now.minute
    if 22*60+30<=minute<24*60:
        return now.date(),(minute-(22*60+30))//30
    return None


def scheduled_run(now=None):
    now=now or datetime.now(TZ)
    slot=collection_slot(now)
    if slot is None: return
    day,index=slot
    start=datetime.combine(day,datetime.min.time(),TZ)+timedelta(hours=22,minutes=30)
    slot_start=start+timedelta(minutes=30*index)
    with session_factory()() as s:
        last=s.scalar(select(Run).where(Run.kind=='nightly',Run.started_at>=start.astimezone(timezone.utc).replace(tzinfo=None)).order_by(Run.id.desc()).limit(1))
        if last and (last.started_at>=slot_start.astimezone(timezone.utc).replace(tzinfo=None) or (last.status=='success' and all(not v.get('pending',True) for v in last.details.values()))): return
    try:
        print(json.dumps(run_workflow(now=now),ensure_ascii=False),flush=True)
    except Exception as exc:
        with session_factory()() as s:
            s.add(Run(kind='nightly',status='failed',finished_at=utcnow(),details={'error':{'pending':True,'message':type(exc).__name__}}));s.commit()


def morning_report(now=None):
    from .reporting import send_morning_report
    now=now or datetime.now(TZ)
    if now.weekday() not in (0,2,4) or now.hour!=8 or now.minute>=5: return
    print(json.dumps(send_morning_report(now),ensure_ascii=False),flush=True)


def monthly_evaluation():
    from .experiments import backtest
    with session_factory()() as s:
        for game in ['dlt','ssq']: backtest(s,game)


def build_scheduler():
    scheduler=BlockingScheduler(timezone=TZ,job_defaults={'coalesce':True,'max_instances':1,'misfire_grace_time':240})
    scheduler.add_job(scheduled_run,'cron',hour=22,minute=30,id='nightly-analysis')
    scheduler.add_job(scheduled_run,'cron',hour=23,minute='0,30',id='nightly-retry')
    scheduler.add_job(scheduled_run,'cron',hour=0,minute=0,id='midnight-final-retry')
    scheduler.add_job(morning_report,'cron',day_of_week='mon,wed,fri',hour=8,minute=0,id='morning-report')
    scheduler.add_job(heartbeat,'interval',seconds=30,id='heartbeat')
    scheduler.add_job(monthly_evaluation,'cron',day=1,hour=6,minute=0,id='monthly-evaluation')
    return scheduler


def serve():
    with (RUNTIME/'scheduler.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        scheduler=build_scheduler()
        heartbeat()
        scheduled_run()  # Catch up only inside the bounded collection window.
        morning_report()  # Morning report is idempotent and never fetches data.
        print('Scheduler: daily 22:30 analysis; retries until 00:00; M/W/F 08:00 report',flush=True)
        try: scheduler.start()
        finally: (RUNTIME/'scheduler.json').unlink(missing_ok=True)
