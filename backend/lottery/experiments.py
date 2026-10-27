"""Chronological experiments; historical experiments cannot promote production strategies."""
import hashlib
import json
import numpy as np
from scipy.stats import ttest_rel
from .domain import GAMES
from .models import Experiment
from .selection import weighted_tickets, select_tickets, selection_metadata, WEIGHTED, UNIFORM
from .settlement import settle_ticket
from .indicators import STRATEGIES
from .feature_service import feature_sequence

PROTOCOL = {'version': 'walk-forward-nonlinear-v3', 'warmup': 160, 'training_window': 300, 'calibration_draws': 30, 'seed': 20261023, 'tickets_per_draw': 5, 'primary_metric': 'mean-marginal-brier', 'multiple_testing': 'Holm, alpha=0.05', 'promotion': 'historical-backtests-cannot-promote; independent-prospective-gate'}

def encoded(history, key, maximum):
    result = np.zeros((len(history), maximum))
    for i, row in enumerate(history): result[i, np.array(row[key])-1] = 1
    return result

def features(matrix, stop):
    return np.stack([matrix[max(0,stop-30):stop].mean(axis=0), matrix[max(0,stop-100):stop].mean(axis=0), matrix[stop-1]], axis=1)

def probability_vectors(game, history, strategy):
    from .model_training import fit_model, predict_model
    return predict_model(fit_model(game,history,strategy))

def hits(ticket, actual):
    return len(set(ticket['front'])&set(actual['front'])) + len(set(ticket['back'])&set(actual['back']))

def evaluate_history(game, rows, test_count=60, simulations=200, history_provider=None):
    if test_count < 1 or simulations < 1:
        raise ValueError('Evaluation periods and simulations must be positive')
    if len(rows)<PROTOCOL['warmup']+1:
        raise ValueError('At least 161 historical draws required')
    start=max(PROTOCOL['warmup'],len(rows)-test_count)
    test=rows[start:]
    names=['uniform','frequency','logistic',*STRATEGIES]
    from .experiment_registry import fingerprint
    from .performance import performance_report
    experiment_versions={name:UNIFORM if name=='uniform' else fingerprint(name) for name in names}
    series={name:[] for name in names}
    hit_series={name:[] for name in names}
    audits=[]
    calibration={name:[] for name in names}
    records=[]
    from .evaluation import evaluation_record, compare_records
    for index in range(start,len(rows)):
        actual=rows[index]
        past=history_provider(actual) if history_provider else rows[:index]
        if len(past)<PROTOCOL['warmup'] or any(r['issue']>=actual['issue'] for r in past):
            raise ValueError('Insufficient or invalid visible history; cannot reconstruct this target')
        audit={'target_issue':actual['issue'],'cutoff_issue':past[-1]['issue'],'forecasts':{}}
        if history_provider: audit['training_snapshot']=past[-PROTOCOL['training_window']:]
        for name in names:
            seed=PROTOCOL['seed']+index
            forecast={'seed':seed,'selection':selection_metadata(UNIFORM if name=='uniform' else WEIGHTED)}
            tickets=[];results=None;error=None
            try:
                prob=probability_vectors(game,past,name)
                tickets=select_tickets(game,seed) if name=='uniform' else select_tickets(game,seed,protocol=WEIGHTED,probabilities=prob)
                results=[settle_ticket(game,t,actual) for t in tickets]
                pred=np.array(prob['front']+prob['back'])
                target=np.concatenate([encoded([actual],k,GAMES[game][k][0])[0] for k in ['front','back']])
                forecast.update(probabilities=prob,tickets=tickets,brier=float(np.mean((pred-target)**2)),
                                mean_hits=float(np.mean([hits(t,actual) for t in tickets])))
            except Exception as exc:
                error=type(exc).__name__+': model generation or evaluation failed'
                results=None
            record=evaluation_record(mode='historical',game=game,strategy=name,issue=actual['issue'],
                cutoff_issue=past[-1]['issue'],tickets=tickets,results=results,error=error,
                rule_version=actual['rule_version'],seed=seed,selection=forecast['selection'],
                experiment_version=experiment_versions[name],
                draw_fingerprint=hashlib.sha256(json.dumps(actual,sort_keys=True).encode()).hexdigest())
            forecast['evaluation']=record
            records.append(record);audit['forecasts'][name]=forecast
        audits.append(audit)
    comparison=compare_records(records,names)
    common=set(comparison['issues'])
    for actual,audit in zip(test,audits):
        if actual['issue'] not in common: continue
        target=np.concatenate([encoded([actual],k,GAMES[game][k][0])[0] for k in ['front','back']])
        for name in names:
            forecast=audit['forecasts'][name]
            series[name].append(forecast['brier']);hit_series[name].append(forecast['mean_hits'])
            calibration[name].extend(zip(forecast['probabilities']['front']+forecast['probabilities']['back'],target.tolist()))
    random_hits=[]
    for simulation in range(simulations if common else 0):
        random_hits.append(float(np.mean([hits(t,actual) for j,actual in enumerate(test) if actual['issue'] in common for t in select_tickets(game,PROTOCOL['seed']+simulation*10000+j)])))
    comparisons=[]
    for name in names[1:]:
        p=float(ttest_rel(series['uniform'],series[name]).pvalue) if len(common)>1 else 1.0
        comparisons.append((name,p if np.isfinite(p) else 1.0))
    adjusted={}
    previous=0.0
    for rank,(name,p) in enumerate(sorted(comparisons,key=lambda x:x[1])):
        previous=max(previous,min(1.0,p*(len(comparisons)-rank)))
        adjusted[name]=previous
    metrics=[]
    for name in names:
        bins=[]
        values=np.array(calibration[name]).reshape(-1,2)
        for low,high in zip(np.arange(0,1,.1),np.arange(.1,1.1,.1)):
            mask=(values[:,0]>=low)&(values[:,0]<high)
            if mask.any(): bins.append({'predicted':float(values[mask,0].mean()),'observed':float(values[mask,1].mean()),'count':int(mask.sum())})
        group=comparison['strategies'][name]
        metrics.append({'strategy':name,'brier':float(np.mean(series[name])) if common else None,
            'mean_hits':float(np.mean(hit_series[name])) if common else None,'cost':group['cost'],
            'known_return':float(group['known_return']),'pending_tickets':group['pending_tickets'],
            'net':float(group['net']) if group['net'] is not None else None,
            'evaluated_periods':len(common),'failed_periods':sum(r['strategy']==name and r['status']=='failed' for r in records),
            'holm_p':adjusted.get(name),'calibration':bins})
    return {'performance':performance_report(records),'record_version':'evaluation-record-v1','comparison':comparison,'data_mode':'retained-as-of' if history_provider else 'current-revised','protocol':PROTOCOL,'game':game,'evaluation_periods':len(test),'from_issue':test[0]['issue'],'to_issue':test[-1]['issue'],'training_cutoff':rows[start-1]['issue'],'strategies':metrics,'random_simulations':simulations,'random_hit_interval':np.quantile(random_hits,[.025,.975]).tolist() if random_hits else None,'forecast_audit':audits,'selection_protocols':{'uniform':UNIFORM,'candidate':WEIGHTED,'random_controls':UNIFORM},'probability_semantics':'model-marginals-used-as-weights; sampled-inclusion-not-guaranteed','production_strategy':'uniform-v1','conclusion':'回测为探索性证据，不作为自动晋升依据；正式策略切换须通过独立前瞻验证。','dataset_hash':hashlib.sha256(json.dumps(rows,sort_keys=True,ensure_ascii=False).encode()).hexdigest()}

def backtest(session,game,test_count=60,data_mode="current-revised"):
    from sqlalchemy import select
    from .models import Draw
    from .config import RUNTIME
    rows=list(session.scalars(select(Draw).where(Draw.game==game,Draw.conflict.is_(False)).order_by(Draw.issue)))
    data=[r.data for r in rows]
    if data_mode not in ('current-revised','retained-as-of'):
        raise ValueError('Unknown backtest data mode')
    provider=None
    if data_mode=='retained-as-of':
        from .data_history import history_as_of
        from datetime import datetime, time, date
        from .domain import TZ
        def provider(actual):
            cutoff=datetime.combine(date.fromisoformat(actual['draw_date']),time(20),TZ)
            visible=history_as_of(session,game,cutoff,before_issue=actual['issue'])
            if visible['unavailable_count'] or visible['conflicts']:
                raise ValueError('Incomplete retained observations; point-in-time backtest unavailable')
            return visible['items']
    report=evaluate_history(game,data,test_count=test_count,history_provider=provider)
    directory=RUNTIME/'artifacts'
    directory.mkdir(exist_ok=True)
    import platform
    import sklearn
    from pathlib import Path
    report['environment']={'python':platform.python_version(),'numpy':np.__version__,'sklearn':sklearn.__version__,'code_sha256':hashlib.sha256(b''.join(p.read_bytes() for p in sorted(Path(__file__).parent.glob('*.py')))).hexdigest()}
    artifact_hash=hashlib.sha256(json.dumps(report,sort_keys=True).encode()).hexdigest()
    artifact=directory/f'experiment-{game}-{artifact_hash}.json'
    artifact.write_text(json.dumps({'data':data,'report':report},ensure_ascii=False),encoding='utf-8')
    stored={k:v for k,v in report.items() if k!='forecast_audit'}
    stored['artifact']=artifact.name
    experiment=Experiment(game=game,result=stored)
    session.add(experiment)
    session.commit()
    return stored
