"""Descriptive five-ticket objectives, matched on issue and prize-rule version.

Controls are frozen prospectively, never reconstructed after the draw. Across
100 tracks, quantiles describe random variation, not confidence intervals.
"""
from datetime import datetime, timedelta
from decimal import Decimal
import random
import time
import numpy as np
from sqlalchemy import select
from .domain import TZ
from .models import RandomControl, ControlScore, Prediction, Draw, Settlement, CandidateForecast, CandidateScore
from .selection import select_tickets
from .settlement import settle_ticket

CONTROL_GROUPS = 100
PROTOCOL = 'matched-uniform-100x5-checked-v2'


def group_result(results, rule_version, cost=10):
    known=sum((Decimal(str(r['amount'])) for r in results if r['amount'] is not None),Decimal(0))
    pending=sum(r['amount'] is None for r in results)
    return {'rule_version':rule_version,'any_prize':any(r['level'] is not None for r in results),
            'first_prize':any(r['level']==1 for r in results),'winning_tickets':sum(r['level'] is not None for r in results),
            'cost':cost,'known_return':str(known),'pending':pending,'net':None if pending else str(known-cost)}


def aggregate(groups):
    from .uncertainty import rate_interval
    n=len(groups)
    cost=sum(g['cost'] for g in groups)
    known=sum((Decimal(g['known_return']) for g in groups),Decimal(0))
    pending=sum(g['pending'] for g in groups)
    net=None if pending or not n else known-cost
    return {'any_prize_interval':rate_interval(sum(g['any_prize'] for g in groups),n),
            'first_prize_interval':rate_interval(sum(g['first_prize'] for g in groups),n),
            'periods':n,'any_prize_periods':sum(g['any_prize'] for g in groups),
            'first_prize_periods':sum(g['first_prize'] for g in groups),
            'any_prize_rate':sum(g['any_prize'] for g in groups)/n if n else None,
            'first_prize_rate':sum(g['first_prize'] for g in groups)/n if n else None,
            'cost':cost,'known_return':str(known),'pending_tickets':pending,
            'net':str(net) if net is not None else None,'roi':float(net/cost) if net is not None and cost else None}


def freeze_controls(session,prediction,now=None):
    from .prospective import utc
    now=(now or datetime.now(TZ)).astimezone(TZ)
    deadline=datetime.fromisoformat(prediction.provenance['sales_cutoff'])
    if now>=deadline or session.scalar(select(Draw.id).where(Draw.game==prediction.game,Draw.issue==prediction.issue)):
        return None
    existing=session.scalar(select(RandomControl).where(RandomControl.prediction_id==prediction.id))
    if existing: return existing
    started=time.monotonic()
    seed=random.SystemRandom().randrange(2**63)
    seeds=random.Random(seed)
    groups=[select_tickets(prediction.game,seeds.getrandbits(63)) for _ in range(CONTROL_GROUPS)]
    completed=now+timedelta(seconds=time.monotonic()-started)
    if completed>=deadline: return None
    row=RandomControl(prediction_id=prediction.id,game=prediction.game,issue=prediction.issue,
                      created_at=utc(completed),cutoff_at=utc(deadline),seed=str(seed),protocol=PROTOCOL,groups=groups)
    session.add(row);session.flush()
    return row


def score_controls(session,game):
    for batch in session.scalars(select(RandomControl).where(RandomControl.game==game)):
        draw=session.scalar(select(Draw).where(Draw.game==game,Draw.issue==batch.issue,Draw.conflict.is_(False)))
        if not draw or batch.created_at>=batch.cutoff_at: continue
        if session.scalar(select(ControlScore.id).where(ControlScore.control_id==batch.id,ControlScore.draw_fingerprint==draw.fingerprint)): continue
        groups=[]
        for tickets in batch.groups:
            results=[]
            for ticket in tickets:
                result=settle_ticket(game,ticket,draw.data)
                results.append({k:result[k] for k in ('level','amount')})
            groups.append(group_result(results,draw.data['rule_version']))
        session.add(ControlScore(control_id=batch.id,draw_fingerprint=draw.fingerprint,groups=groups))
    session.flush()


def comparison(entries,controls):
    from .uncertainty import paired_uncertainty
    matched=[];excluded=[]
    for issue,metrics in entries:
        groups=controls.get(issue)
        if groups is None:
            excluded.append({'issue':issue,'reason':'missing_controls'})
        elif len(groups)!=CONTROL_GROUPS or any((g['cost'],g['rule_version'])!=(metrics['cost'],metrics['rule_version']) for g in groups):
            excluded.append({'issue':issue,'reason':'control_rule_or_budget_mismatch'})
        else: matched.append((issue,metrics))
    # Monetary comparisons require complete amounts on BOTH sides, on identical issues.
    money=[(issue,m) for issue,m in matched if not m['pending'] and all(not g['pending'] for g in controls[issue])]
    tracks=[aggregate([controls[issue][i] for issue,_ in matched]) for i in range(CONTROL_GROUPS)]
    money_tracks=[aggregate([controls[issue][i] for issue,_ in money]) for i in range(CONTROL_GROUPS)]
    def band(rows,key):
        values=[float(r[key]) for r in rows if r[key] is not None]
        return [float(v) for v in np.quantile(values,[.025,.5,.975])] if values else None
    return {'uncertainty':paired_uncertainty(matched,controls,money),
            'random_tracks':tracks,'random_money_tracks':money_tracks,
            'periods':len(matched),'money_periods':len(money),'excluded':excluded,
            'money_excluded':[{'issue':issue,'reason':'unknown_prize_amount'} for issue,_ in matched if issue not in {i for i,_ in money}],
            'strategy':aggregate([m for _,m in matched]),'money_strategy':aggregate([m for _,m in money]),
            'random_any_prize_rate':band(tracks,'any_prize_rate'),
            'random_first_prize_rate':band(tracks,'first_prize_rate'),
            'random_net':band(money_tracks,'net') if money else None,
            'random_roi':band(money_tracks,'roi') if money else None}


def portfolio_status(session,game):
    from .prospective import utc
    draws={d.issue:d for d in session.scalars(select(Draw).where(Draw.game==game,Draw.conflict.is_(False)))}
    controls={}
    scores={(s.control_id,s.draw_fingerprint):s for s in session.scalars(select(ControlScore).join(RandomControl).where(RandomControl.game==game))}
    for b in session.scalars(select(RandomControl).where(RandomControl.game==game)):
        d=draws.get(b.issue)
        score=scores.get((b.id,d.fingerprint)) if d else None
        if score and b.created_at<b.cutoff_at and b.protocol==PROTOCOL and len(score.groups)==CONTROL_GROUPS:
            controls[b.issue]=score.groups
    groups={}
    def add(kind,strategy,issue,results,cost):
        d=draws[issue]
        key=(kind,strategy,d.data['rule_version'])
        groups.setdefault(key,[]).append((issue,group_result(results,key[2],cost)))
    settlements={(s.prediction_id,s.draw_fingerprint):s for s in session.scalars(select(Settlement).join(Prediction).where(Prediction.game==game))}
    for p in session.scalars(select(Prediction).where(Prediction.game==game)):
        d=draws.get(p.issue)
        s=settlements.get((p.id,d.fingerprint)) if d else None
        if s and p.cutoff_issue<p.issue and p.created_at<utc(datetime.fromisoformat(p.provenance['sales_cutoff'])):
            add('formal',p.strategy,p.issue,s.results,int(s.summary['cost']))
    candidate_scores={(s.forecast_id,s.draw_fingerprint):s for s in session.scalars(select(CandidateScore).join(CandidateForecast).where(CandidateForecast.game==game))}
    for f in session.scalars(select(CandidateForecast).where(CandidateForecast.game==game,CandidateForecast.error.is_(None))):
        d=draws.get(f.issue)
        s=candidate_scores.get((f.id,d.fingerprint)) if d else None
        if s and f.created_at<f.cutoff_at and f.cutoff_issue<f.issue:
            add('candidate',f.strategy,f.issue,s.metrics['results'],s.metrics['cost'])
    rows=[]
    for (kind,strategy,rule),entries in sorted(groups.items()):
        rows.append({'kind':kind,'strategy':strategy,'rule_version':rule,'metrics':aggregate([m for _,m in entries]),'comparison':comparison(entries,controls)})
    return {'control_groups':CONTROL_GROUPS,'protocol':PROTOCOL,'rows':rows,
            'note':'按同彩种、同规则、同策略版本统计；对照仅匹配同期有效数据。范围为100组随机轨迹的2.5%/50%/97.5%分位数，不是置信区间，也不代表未来中奖概率。收益对比仅含双方奖金完整的相同期次；这些指标不触发自动晋升。'}
