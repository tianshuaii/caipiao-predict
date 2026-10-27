"""Read-only evaluation projections. Historical records never supply promotion evidence."""
from .portfolio import group_result, aggregate

VERSION='evaluation-record-v1'
VALID=('settled','amount_pending')


def evaluation_record(*,mode,game,strategy,issue,cutoff_issue,tickets,results=None,
                      rule_version=None,error=None,status=None,**provenance):
    if mode not in ('historical','prospective'): raise ValueError('Unknown evaluation mode')
    metrics=group_result(results,rule_version,len(tickets)*2) if results is not None else None
    if results is not None and len(results)!=len(tickets): raise ValueError('Ticket/result count mismatch')
    state=status or ('failed' if error else 'waiting' if metrics is None else 'amount_pending' if metrics['pending'] else 'settled')
    if cutoff_issue>=issue: state='invalid_cutoff'
    return {'version':VERSION,'mode':mode,'game':game,'strategy':strategy,'issue':issue,
            'cutoff_issue':cutoff_issue,'rule_version':rule_version,'tickets':tickets,'results':results,
            'cost':len(tickets)*2 if tickets or results is not None else None,'status':state,'error':error,
            'metrics':metrics,**provenance}


def compare_records(records,strategies):
    """Intersection across explicitly selected strategies; exclusions remain inspectable."""
    if not strategies or len(set(strategies))!=len(strategies): raise ValueError('Select distinct strategies')
    indexed={}
    for r in records:
        if r['strategy'] not in strategies: continue
        key=(r['issue'],r['strategy'])
        if key in indexed: raise ValueError('Duplicate strategy/issue evaluation')
        indexed[key]=r
    issues=sorted({issue for issue,_ in indexed})
    included=[];money=[];excluded=[]
    for issue in issues:
        rows=[indexed.get((issue,s)) for s in strategies]
        reason=None
        if any(r is None for r in rows): reason='missing_strategy'
        elif any(r['status'] not in VALID for r in rows): reason='invalid_or_failed'
        elif len({(r['mode'],r['game'],r['rule_version'],r['cost']) for r in rows})!=1: reason='mode_game_rule_or_budget_mismatch'
        if reason: excluded.append({'issue':issue,'reason':reason});continue
        included.append(issue)
        if all(not r['metrics']['pending'] for r in rows): money.append(issue)
    return {'issues':included,'money_issues':money,'excluded':excluded,
            'money_excluded':[{'issue':i,'reason':'unknown_prize_amount'} for i in included if i not in money],
            'strategies':{s:aggregate([indexed[i,s]['metrics'] for i in included]) for s in strategies},
            'money_strategies':{s:aggregate([indexed[i,s]['metrics'] for i in money]) for s in strategies}}


def prospective_records(session,game):
    """Project existing facts without rewriting old scores or manufacturing evidence."""
    from datetime import datetime
    from sqlalchemy import select
    from .models import Draw,Prediction,Settlement,CandidateForecast,CandidateScore
    from .prospective import utc
    draws={d.issue:d for d in session.scalars(select(Draw).where(Draw.game==game))}
    rows=[]
    for model,score_model,foreign_key,kind in ((Prediction,Settlement,'prediction_id','formal'),
                                              (CandidateForecast,CandidateScore,'forecast_id','candidate')):
        scores={(getattr(s,foreign_key),s.draw_fingerprint):s for s in session.scalars(select(score_model).join(model).where(model.game==game))}
        for forecast in session.scalars(select(model).where(model.game==game).order_by(model.issue,model.id)):
            draw=draws.get(forecast.issue)
            score=scores.get((forecast.id,draw.fingerprint)) if draw and not draw.conflict else None
            cutoff=forecast.cutoff_at if kind=='candidate' else utc(datetime.fromisoformat(forecast.provenance['sales_cutoff']))
            error=forecast.error if kind=='candidate' else None
            state=('invalid_cutoff' if forecast.created_at>=cutoff or forecast.cutoff_issue>=forecast.issue else
                   'failed' if error else 'draw_conflict' if draw and draw.conflict else
                   'waiting' if not draw else 'unscored' if not score else None)
            results=None
            if score and state is None:
                try:
                    results=score.metrics['results'] if kind=='candidate' else score.results
                    if not isinstance(results,list) or not results or len(results)!=len(forecast.tickets):
                        raise ValueError('Ticket/result count mismatch')
                    group_result(results,draw.data['rule_version'],len(forecast.tickets)*2)
                except (KeyError,TypeError,ValueError,ArithmeticError):
                    state='invalid_score';error='Persisted settlement results are incomplete or invalid';results=None
            rows.append(evaluation_record(mode='prospective',game=game,strategy=forecast.strategy,
                issue=forecast.issue,cutoff_issue=forecast.cutoff_issue,tickets=forecast.tickets,
                results=results,rule_version=draw.data['rule_version'] if draw else None,error=error,status=state,
                kind=kind,source_id=forecast.id,created_at=forecast.created_at.isoformat()+'Z',
                cutoff_at=cutoff.isoformat()+'Z',dataset_hash=forecast.dataset_hash,
                draw_fingerprint=draw.fingerprint if draw else None,seed=forecast.seed,
                selection=forecast.provenance.get('selection'),planned_cost=10,
                experiment_version=forecast.provenance.get('experiment_hash') or forecast.strategy))
    return sorted(rows,key=lambda r:(r['issue'],r['kind'],r['strategy']))
