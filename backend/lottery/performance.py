"""Descriptive end-of-draw ledger; no ranking, imputation, or promotion evidence."""
from collections import Counter
from decimal import Decimal, InvalidOperation
from .evaluation import VALID

VERSION='performance-ledger-v1'


def performance_report(records,initial_capital='1000'):
    try: capital=Decimal(str(initial_capital))
    except InvalidOperation as exc: raise ValueError('Invalid initial capital') from exc
    if not capital.is_finite() or capital<0: raise ValueError('Initial capital must be finite and nonnegative')
    from .uncertainty import rate_interval
    groups={}
    for record in records:
        key=tuple(record.get(k) for k in ('mode','game','kind','strategy','rule_version','experiment_version'))
        groups.setdefault(key,[]).append(record)
    reports=[]
    for key,rows in sorted(groups.items(),key=lambda item:str(item[0])):
        rows=sorted(rows,key=lambda r:r['issue'])
        if len({r['issue'] for r in rows})!=len(rows): raise ValueError('Duplicate issue in performance group')
        known_cost=Decimal(0);known_return=Decimal(0);net=Decimal(0);peak=capital
        max_drawdown=Decimal(0);max_ratio=Decimal(0)
        complete=True;cost_complete=True;curve=[];prizes=Counter();prize_periods=Counter()
        any_prize=0;first_prize=0;pending=0;evaluated=0
        for row in rows:
            valid=row['status'] in VALID
            if row['cost'] is None: cost_complete=False
            else: known_cost+=Decimal(str(row['cost']))
            if valid:
                evaluated+=1
                metrics=row['metrics'];known_return+=Decimal(metrics['known_return']);pending+=metrics['pending']
                levels=[str(r['level']) for r in row['results'] if r['level'] is not None]
                prizes.update(levels);prize_periods.update(set(levels))
                any_prize+=bool(levels);first_prize+='1' in levels
            if not valid or row['metrics']['pending']: complete=False
            equity=None;drawdown=None;ratio=None
            if complete:
                net+=Decimal(row['metrics']['known_return'])-Decimal(str(row['cost']))
                equity=capital+net;peak=max(peak,equity);drawdown=peak-equity
                max_drawdown=max(max_drawdown,drawdown)
                if capital>0:
                    ratio=drawdown/peak;max_ratio=max(max_ratio,ratio)
            curve.append({'issue':row['issue'],'status':row['status'],
                          'cumulative_net':str(net) if complete else None,
                          'equity':str(equity) if equity is not None else None,
                          'drawdown_amount':str(drawdown) if drawdown is not None else None,
                          'drawdown_ratio':float(ratio) if ratio is not None else None})
        reports.append({**dict(zip(('mode','game','kind','strategy','rule_version','experiment_version'),key)),
            'periods':len(rows),'evaluated_periods':evaluated,'status_counts':dict(Counter(r['status'] for r in rows)),
            'any_prize_periods':any_prize,'first_prize_periods':first_prize,
            'any_prize_interval':rate_interval(any_prize,evaluated),
            'first_prize_interval':rate_interval(first_prize,evaluated),
            'any_prize_rate':any_prize/evaluated if evaluated else None,
            'first_prize_rate':first_prize/evaluated if evaluated else None,
            'prize_ticket_counts':dict(prizes),'prize_period_counts':dict(prize_periods),
            'known_cost':str(known_cost),'cost':str(known_cost) if cost_complete else None,
            'known_return':str(known_return),'pending_tickets':pending,'complete':complete,
            'net':str(net) if complete else None,'roi':float(net/known_cost) if complete and known_cost else None,
            'max_drawdown_amount':str(max_drawdown) if complete else None,
            'max_drawdown_ratio':float(max_ratio) if complete and capital>0 else None,'curve':curve})
    return {'version':VERSION,'initial_capital':str(capital),'groups':reports,
            'note':'按开奖期末账面资金计算回撤，包含初始资金峰值；不计算购票过程现金低点。允许账面资金为负，比例可超过100%，不代表可实际持续购买。未知或失败后曲线断开；不触发策略晋升。'}
