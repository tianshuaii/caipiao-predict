"""Read-only descriptive rankings on a common prospective five-ticket cohort."""
import math
from sqlalchemy import select
from .models import CandidateForecast, CandidateScore, Draw
from .portfolio import aggregate, group_result

MIN_PERIODS=30
OBJECTIVES=('brier','any_prize','first_prize','roi')


def rank_records(records,participants,objective):
    if objective not in OBJECTIVES: raise ValueError('Unknown objective')
    groups=[]
    for rule in sorted({r['rule_version'] for r in records}):
        by={s:{} for s in participants}
        for r in records:
            if r['rule_version']==rule and r['strategy'] in by: by[r['strategy']][r['issue']]=r
        union=set().union(*(set(rows) for rows in by.values()))
        issues=sorted(set.intersection(*(set(rows) for rows in by.values()))) if by else []
        metrics={s:{i:group_result(by[s][i]['results'],rule) for i in issues} for s in participants}
        money=[i for i in issues if all(not metrics[s][i]['pending'] for s in participants)]
        rows=[]
        for strategy in participants:
            all_metrics=aggregate(list(metrics[strategy].values()))
            money_metrics=aggregate([metrics[strategy][i] for i in money])
            brier=sum(by[strategy][i]['brier'] for i in issues)/len(issues) if issues else None
            value={'brier':brier,'any_prize':all_metrics['any_prize_rate'],
                   'first_prize':all_metrics['first_prize_rate'],'roi':money_metrics['roi']}[objective]
            periods=len(money if objective=='roi' else issues)
            reason='insufficient_periods' if periods<MIN_PERIODS else 'common_periods_equal_budget'
            rows.append({'strategy':strategy,'brier':brier,'metrics':all_metrics,'money_metrics':money_metrics,
                         'value':value,'periods':periods,'rank':None,'reason':reason})
        if objective=='first_prize' and issues and all(r['value']==0 for r in rows):
            for r in rows:r['reason']='no_first_prize_observed'
        rows.sort(key=lambda r: (r['value'] is None, (r['value'] or 0)*(1 if objective=='brier' else -1),r['strategy']))
        previous=None;rank=None
        for index,row in enumerate(rows,1):
            if row['reason']!='common_periods_equal_budget':continue
            if row['value']!=previous:rank=index
            row['rank']=rank;previous=row['value']
        groups.append({'rule_version':rule,'issues':issues,'money_issues':money,'rows':rows,
                       'excluded':[{'issue':i,'missing_strategies':[s for s in participants if i not in by[s]]} for i in sorted(union-set(issues))],
                       'money_excluded':[{'issue':i,'reason':'unknown_prize_amount'} for i in issues if i not in money]})
    return groups


def ranking_status(session,game,objective='brier'):
    from .prospective import versions
    forecasts=list(session.scalars(select(CandidateForecast).where(CandidateForecast.game==game,CandidateForecast.strategy.in_(list(versions().values())))))
    participants=sorted({f.strategy for f in forecasts})
    draws={d.issue:d for d in session.scalars(select(Draw).where(Draw.game==game))}
    scores={(s.forecast_id,s.draw_fingerprint):s.metrics for s in session.scalars(select(CandidateScore).join(CandidateForecast).where(CandidateForecast.game==game))}
    records=[];excluded=[]
    for f in forecasts:
        d=draws.get(f.issue);m=scores.get((f.id,d.fingerprint)) if d else None
        reason=None
        if f.error:reason='generation_failed'
        elif f.created_at>=f.cutoff_at or f.cutoff_issue>=f.issue:reason='invalid_forecast_cutoff'
        elif not d:reason='awaiting_draw'
        elif d.conflict:reason='draw_conflict'
        elif not m:reason='missing_current_revision_score'
        elif len(f.tickets)!=5 or m.get('cost')!=10 or len(m.get('results',[]))!=5:reason='budget_mismatch'
        elif not isinstance(m.get('brier'),(int,float)) or not math.isfinite(m['brier']):reason='invalid_brier'
        if reason:
            excluded.append({'strategy':f.strategy,'issue':f.issue,'reason':reason});continue
        records.append({'strategy':f.strategy,'issue':f.issue,'rule_version':d.data['rule_version'],
                        'brier':m['brier'],'results':m['results']})
    return {'protocol':'common-prospective-five-v1','objective':objective,'minimum_periods':MIN_PERIODS,
            'participants':participants,'groups':rank_records(records,participants,objective),'excluded':excluded,
            'note':'当前已有预测的候选版本按规则分组，在所有参与策略共同有效期次、每期5注10元下描述性排序；收益另取所有策略奖金完整交集。并列共享名次；少于30期不排名，一等奖全零不排名。Wilson区间为独立固定概率近似；收益不提供置信区间，完整金额子集不能代表总体巨奖尾部。排行不触发晋升，不代表未来中奖概率。'}
