"""Read-only charts from persisted evaluations; never new prediction evidence."""
from .evaluation import compare_records
from .performance import performance_report


def visual_records(records,strategy):
    selected=[r for r in records if r['strategy'] in (strategy,'uniform')]
    groups=[]
    for rule in sorted({r['rule_version'] for r in selected},key=str):
        rows=[r for r in selected if r['rule_version']==rule]
        comparison=compare_records(rows,[strategy,'uniform'])
        included=[r for r in rows if r['issue'] in comparison['issues']]
        report=performance_report(included)
        series=report['groups']
        boundary=min((r['issue'] for r in comparison['money_excluded']),default=None)
        for item in series:
            if boundary:
                item.update(complete=False,net=None,roi=None,max_drawdown_amount=None,max_drawdown_ratio=None)
                for point in item['curve']:
                    if point['issue']>=boundary:
                        for field in ('equity','cumulative_net','drawdown_amount','drawdown_ratio'):point[field]=None
        indexed={s['strategy']:s for s in series}
        if len(indexed)!=len(series):raise ValueError('Mixed experiment versions in source')
        chart=[]
        for i,issue in enumerate(comparison['issues']):
            point={'issue':issue}
            for name,key in ((strategy,'model'),('uniform','uniform')):
                curve=indexed[name]['curve'][i]
                point.update({f'{key}_equity':curve['equity'],f'{key}_net':curve['cumulative_net'],f'{key}_drawdown':curve['drawdown_amount']})
            chart.append(point)
        levels=sorted({level for s in series for level in s['prize_ticket_counts']},key=int)
        prizes=[{'level':level,'model':indexed[strategy]['prize_ticket_counts'].get(level,0),
                 'uniform':indexed['uniform']['prize_ticket_counts'].get(level,0)} for level in levels]
        groups.append({'rule_version':rule,**comparison,'series':series,'chart':chart,'prizes':prizes,'note':report['note']})
    return {'available':any(g['issues'] for g in groups),'strategy':strategy,'initial_capital':'1000','groups':groups,
            'note':'历史探索性回测，仅比较共同期次、同预算及同规则的单一随机基线；不是前瞻验证。任一方奖金未知后双方资金曲线断开。'}
