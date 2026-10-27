import argparse
import hashlib
import json
from pathlib import Path
from .db import session_factory

def main():
    parser=argparse.ArgumentParser(description='Lottery Lab operations')
    sub=parser.add_subparsers(dest='command',required=True)
    sub.add_parser('init-db')
    sync=sub.add_parser('sync');sync.add_argument('--game',choices=['dlt','ssq','all'],default='all');sync.add_argument('--full',action='store_true')
    sub.add_parser('archive')
    cases=sub.add_parser('cases',help='采集官方一等奖票型报道，不参与预测')
    cases.add_argument('--url',action='append',help='官方报道URL，可多次指定')
    cases.add_argument('--limit',type=int,default=20)
    run=sub.add_parser('run',help='同步、复盘、预测；不生成或发送通知');run.add_argument('--no-notify',action='store_true',help='兼容旧命令；run 已默认不发通知')
    backtest=sub.add_parser('backtest');backtest.add_argument('--game',choices=['dlt','ssq','all'],default='all');backtest.add_argument('--periods',type=int,default=60)
    backtest.add_argument('--data-mode',choices=['current-revised','retained-as-of'],default='current-revised')
    sub.add_parser('scheduler')
    sub.add_parser('status')
    sub.add_parser('evaluate')
    replay=sub.add_parser('replay');replay.add_argument('id',type=int)
    notify=sub.add_parser('notify');notify.add_argument('id',type=int)
    args=parser.parse_args()
    if args.command=='init-db':
        from alembic.config import Config
        from alembic import command
        command.upgrade(Config(str(Path(__file__).resolve().parents[1]/'alembic.ini')),'head')
        print('Database migrations applied.');return
    if args.command=='run':
        from .workflow import run_workflow
        print(json.dumps(run_workflow(),ensure_ascii=False));return
    if args.command=='scheduler':
        from .scheduler import serve
        serve();return
    with session_factory()() as session:
        if args.command=='cases':
            from .winner_cases import sync_cases
            from .workflow import workflow_lock
            with workflow_lock():
                print(json.dumps(sync_cases(session,args.url,args.limit),ensure_ascii=False))
        elif args.command=='evaluate':
            from .prospective import evaluate_existing, status
            from .workflow import workflow_lock
            with workflow_lock():
                for game in ['dlt','ssq']:
                    evaluate_existing(session,game)
                    session.commit()
                    print(json.dumps(status(session,game),ensure_ascii=False))
        elif args.command=='sync':
            from .collectors import collect,collect_archive
            from .ingestion import coverage
            for game in (['dlt','ssq'] if args.game=='all' else [args.game]):
                result=collect(session,game,args.full)
                if args.full and game=='ssq': result['archive']=collect_archive(session)
                print(json.dumps({**result,'coverage':coverage(session,game)},ensure_ascii=False))
        elif args.command=='archive':
            from .collectors import collect_archive
            print(json.dumps(collect_archive(session),ensure_ascii=False))
        elif args.command=='backtest':
            from .experiments import backtest
            for game in (['dlt','ssq'] if args.game=='all' else [args.game]):
                print(json.dumps(backtest(session,game,args.periods,args.data_mode),ensure_ascii=False),flush=True)
        elif args.command=='status':
            from .ingestion import coverage
            from .config import sendkey
            from .api import schedule_view
            print(json.dumps({'coverage':{g:coverage(session,g) for g in ['dlt','ssq']},'schedule':schedule_view(),'serverchan_configured':bool(sendkey())},ensure_ascii=False))
        elif args.command=='replay':
            from .models import Prediction
            from .selection import replay_tickets
            from .workflow import ARTIFACTS
            p=session.get(Prediction,args.id)
            if not p: raise SystemExit('Prediction not found')
            protocol=p.provenance.get('selection',{}).get('protocol') or ('legacy-uniform-v1' if p.strategy=='uniform-v1' else 'legacy-weighted-v1')
            replayed=replay_tickets(p.game,int(p.seed),p.probabilities,protocol,len(p.tickets))
            matched=replayed==p.tickets
            intact=hashlib.sha256((ARTIFACTS/p.snapshot_path).read_bytes()).hexdigest()==p.dataset_hash
            print(json.dumps({'id':p.id,'tickets_match':matched,'snapshot_hash_matches':intact}))
            if not matched or not intact: raise SystemExit(1)
        elif args.command=='notify':
            from .models import Notification
            from .notify import deliver
            row=session.get(Notification,args.id)
            if not row: raise SystemExit('Notification not found')
            print(deliver(session,row))

if __name__=='__main__':main()
