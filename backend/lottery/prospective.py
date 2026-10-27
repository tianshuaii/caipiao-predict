"""Frozen prospective forecasts and anytime-valid bounded-loss comparisons.

For X in [-1,1] with conditional mean <=0, exp(lambda*X-lambda**2/2)
is a test supermartingale factor (Hoeffding). A fixed mixture remains valid.
Allocate alpha over every newly registered version, not every evaluation date.
"""
from datetime import datetime, timezone, timedelta
from functools import lru_cache
import hashlib
import json
import math
import time
from pathlib import Path
import numpy as np
from sqlalchemy import select
from .domain import GAMES, TZ
from .models import CandidateForecast, CandidateScore, StrategyDecision, Draw
from .predict import generate_tickets
from .settlement import settle_ticket
from .indicators import STRATEGIES

MIN_SAMPLES=60
UNIFORM='uniform-v1'
LAMBDAS=(.01,.03,.1,.3)

@lru_cache
def versions():
    from .generation_versions import registered_versions
    return registered_versions()

def utc(value):
    return value.astimezone(timezone.utc).replace(tzinfo=None)

def freeze_candidates(session, prediction, now=None):
    from .workflow import ARTIFACTS
    from .selection import select_tickets, selection_metadata, WEIGHTED
    from .model_training import fit_model, predict_model
    from .model_artifacts import save_model
    from .experiment_registry import describe, fingerprint
    now=now or datetime.now(TZ)
    started=time.monotonic()
    cutoff=datetime.fromisoformat(prediction.provenance['sales_cutoff'])
    if now>=cutoff or session.scalar(select(Draw.id).where(Draw.game==prediction.game,Draw.issue==prediction.issue)):
        return []
    raw=(ARTIFACTS/prediction.snapshot_path).read_bytes()
    if hashlib.sha256(raw).hexdigest()!=prediction.dataset_hash:
        raise ValueError('Prediction history snapshot hash mismatch')
    history=[r['data'] for r in json.loads(raw)]
    if not history or any(r['issue']>=prediction.issue for r in history):
        raise ValueError('Future data in candidate input')
    result=[]
    for model,version in versions().items():
        existing=session.scalar(select(CandidateForecast).where(CandidateForecast.game==prediction.game,CandidateForecast.issue==prediction.issue,CandidateForecast.strategy==version))
        if existing:
            result.append(existing);continue
        f=CandidateForecast(game=prediction.game,issue=prediction.issue,strategy=version,model=model,created_at=utc(now),cutoff_at=utc(cutoff),cutoff_issue=prediction.cutoff_issue,seed=prediction.seed,snapshot_path=prediction.snapshot_path,dataset_hash=prediction.dataset_hash,provenance={'selection':selection_metadata(WEIGHTED),'experiment':describe(model),'experiment_hash':fingerprint(model),'protocol':'prospective-e-v1','training_count':len(history),'numpy':np.__version__, 'feature_groups':list(STRATEGIES.get(model,())), 'tickets_per_draw':5})
        try:
            if len(history)<160: raise ValueError('至少需要160期训练历史')
            trained=fit_model(prediction.game,history,model)
            probabilities=predict_model(trained)
            for key in ('front','back'):
                size,count=GAMES[prediction.game][key]
                p=np.array(probabilities[key])
                if len(p)!=size or not np.isfinite(p).all() or (p<=0).any() or (p>=1).any() or abs(p.sum()-count)>1e-6:
                    raise ValueError('Invalid probability vector')
            f.probabilities=probabilities
            f.tickets=select_tickets(prediction.game,int(f.seed),protocol=WEIGHTED,probabilities=probabilities)
            f.provenance={**f.provenance,'experiment':trained.metadata['experiment'],'experiment_hash':trained.metadata['experiment_hash'],'model_artifact':save_model(trained,ARTIFACTS/'models')}
        except Exception as exc:
            f.error=type(exc).__name__+': 候选模型未生成，正式预测可回退基线'
        completed=now+timedelta(seconds=time.monotonic()-started)
        if completed>=cutoff: continue
        f.created_at=utc(max(now,completed))
        session.add(f);session.flush();result.append(f)
    return result

def score_candidates(session,game):
    from decimal import Decimal
    forecasts=session.scalars(select(CandidateForecast).where(CandidateForecast.game==game,CandidateForecast.error.is_(None)))
    for f in forecasts:
        draw=session.scalar(select(Draw).where(Draw.game==game,Draw.issue==f.issue,Draw.conflict.is_(False)))
        if not draw or f.created_at>=f.cutoff_at or f.cutoff_issue>=f.issue: continue
        if session.scalar(select(CandidateScore.id).where(CandidateScore.forecast_id==f.id,CandidateScore.draw_fingerprint==draw.fingerprint)): continue
        p=np.array(f.probabilities['front']+f.probabilities['back'])
        baseline=np.concatenate([np.full(GAMES[game][k][0],GAMES[game][k][1]/GAMES[game][k][0]) for k in ('front','back')])
        actual=np.concatenate([np.array([int(n in draw.data[k]) for n in range(1,GAMES[game][k][0]+1)]) for k in ('front','back')])
        loss=float(np.mean((p-actual)**2)); base=float(np.mean((baseline-actual)**2))
        bound=float(np.mean(np.abs(baseline-p)*np.maximum(np.abs(baseline+p),np.abs(baseline+p-2))))
        normalized=(base-loss)/bound if bound>1e-15 else 0.0
        results=[]; total=Decimal(0);pending=0
        for t in f.tickets:
            result=settle_ticket(game,t,draw.data)
            amount=result['amount']
            if amount is None: pending+=1
            else: total+=Decimal(amount)
            results.append(result)
        session.add(CandidateScore(forecast_id=f.id,draw_fingerprint=draw.fingerprint,metrics={'brier':loss,'baseline':base,'normalized_gain':float(np.clip(normalized,-1,1)),'mean_hits':float(np.mean([r['front_hits']+r['back_hits'] for r in results])),'results':results,'cost':10,'known_return':str(total),'pending':pending}))
    session.flush()

def evidence(metrics,threshold):
    n=len(metrics)
    if not n: return {'samples':0,'brier':None,'baseline':None,'relative_gain':None,'e_value':1.0,'threshold':threshold,'eligible':False,'recent_degraded':False}
    gain=sum(m['normalized_gain'] for m in metrics)
    logs=[l*gain-n*l*l/2 for l in LAMBDAS]
    top=max(logs)
    log_e=top+math.log(sum(math.exp(v-top) for v in logs)/len(logs))
    loss=float(np.mean([m['brier'] for m in metrics]));base=float(np.mean([m['baseline'] for m in metrics]))
    recent=metrics[-30:]; rb=float(np.mean([m['baseline'] for m in recent]));rl=float(np.mean([m['brier'] for m in recent]))
    improvement=(base-loss)/base if base else 0.0
    return {'samples':n,'brier':loss,'baseline':base,'relative_gain':improvement,'e_value':math.exp(min(log_e,690)),'threshold':threshold,'eligible':n>=MIN_SAMPLES and improvement>=.01 and rl<rb and log_e>=math.log(threshold),'recent_degraded':len(recent)==30 and rl>rb*1.01}

def choose(active,candidates,available):
    eligible=sorted([c for c in candidates if c['eligible'] and c['strategy'] in available],key=lambda c:c['brier'])
    current=next((c for c in candidates if c['strategy']==active),None)
    if active!=UNIFORM and (active not in available or not current or not current['eligible'] or current['recent_degraded']):
        return UNIFORM,'候选不可用、有效证据不再达标或近期退化，回退均匀基线'
    if eligible and (active==UNIFORM or eligible[0]['brier']<current['brier']):
        return eligible[0]['strategy'],'前瞻样本、评分改善与持续检验均达标'
    return active,'证据不足或无需更换，保持当前策略'

def status(session,game):
    forecasts=list(session.scalars(select(CandidateForecast).where(CandidateForecast.game==game).order_by(CandidateForecast.id)))
    groups={}
    for f in forecasts: groups.setdefault(f.strategy,[]).append(f)
    draws={r.issue:r for r in session.scalars(select(Draw).where(Draw.game==game))}
    scores={ (s.forecast_id,s.draw_fingerprint):s for s in session.scalars(select(CandidateScore).join(CandidateForecast).where(CandidateForecast.game==game))}
    candidates=[]
    for index,(version,rows) in enumerate(groups.items(),1):
        metrics=[]; fingerprints=[]
        for f in sorted(rows,key=lambda r:r.issue):
            d=draws.get(f.issue)
            score=scores.get((f.id,d.fingerprint)) if d and not d.conflict and not f.error else None
            if score and f.created_at<f.cutoff_at and f.cutoff_issue<f.issue:
                metrics.append(score.metrics);fingerprints.append(f'{f.id}:{d.fingerprint}')
        threshold=index*(index+1)/.05
        candidates.append({'strategy':version,'model':rows[0].model,'forecast_count':len(rows),'failed':sum(bool(f.error) for f in rows),'latest_issue':rows[-1].issue,'latest_error':rows[-1].error,'current_version':version in versions().values(),'evidence_fingerprint':hashlib.sha256('|'.join(fingerprints).encode()).hexdigest(),**evidence(metrics,threshold)})
    decisions=list(session.scalars(select(StrategyDecision).where(StrategyDecision.game==game).order_by(StrategyDecision.id.desc()).limit(20)))
    active=decisions[0].selected if decisions else UNIFORM
    return {'active':active,'minimum_samples':MIN_SAMPLES,'minimum_relative_gain':.01,'method':'Hoeffding mixture e-process; alpha_j=0.05/[j(j+1)] per game','candidates':candidates,'decisions':[{'id':d.id,'previous':d.previous,'selected':d.selected,'reason':d.reason,'created_at':d.created_at.isoformat()+'Z'} for d in decisions]}

def select_strategy(session,game,available=None):
    view=status(session,game)
    available=set(versions().values()) if available is None else set(available)
    if session.scalar(select(Draw.id).where(Draw.game==game,Draw.conflict.is_(True)).limit(1)):
        available=set()
    selected,reason=choose(view['active'],view['candidates'],available)
    payload={'candidates':view['candidates'],'available':sorted(available),'selected':selected}
    key=hashlib.sha256(json.dumps(payload,sort_keys=True).encode()).hexdigest()
    existing=session.scalar(select(StrategyDecision).where(StrategyDecision.game==game,StrategyDecision.evaluation_key==key))
    if existing and selected!=view['active']:
        key=hashlib.sha256((key+str(view['decisions'][0]['id'])).encode()).hexdigest()
        existing=None
    if not existing:
        session.add(StrategyDecision(game=game,evaluation_key=key,previous=view['active'],selected=selected,reason=reason,evidence=payload))
        session.flush()
    return selected,reason


def evaluate_existing(session,game):
    """Score and initialize shadows only; never create a formal prediction."""
    from .models import Prediction
    score_candidates(session,game)
    forecasts=[]
    for prediction in session.scalars(select(Prediction).where(Prediction.game==game)):
        forecasts.extend(freeze_candidates(session,prediction))
    select_strategy(session,game,[f.strategy for f in forecasts if not f.error] if forecasts else None)
