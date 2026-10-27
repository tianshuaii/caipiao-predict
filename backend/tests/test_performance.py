import pytest
from lottery.evaluation import evaluation_record
from lottery.performance import performance_report


def row(issue,amount='0',level=None,**kw):
    args=dict(mode='historical',game='ssq',strategy='s-v1',issue=issue,cutoff_issue='2025001',
              tickets=[{'front':[1,2,3,4,5,6],'back':[1]}],results=[{'level':level,'amount':amount}],rule_version='r1')
    args.update(kw)
    return evaluation_record(**args)


def test_manual_equity_drawdown_prizes_and_order():
    rows=[row('2026001'),row('2026002','10',6),row('2026003'),row('2026004')]
    report=performance_report(list(reversed(rows)),initial_capital='10')['groups'][0]
    assert report['cost']=='8' and report['known_return']=='10' and report['net']=='2'
    assert report['roi']==.25 and report['prize_ticket_counts']=={'6':1}
    assert report['prize_period_counts']=={'6':1} and report['any_prize_periods']==1
    assert [p['equity'] for p in report['curve']]==['8','16','14','12']
    assert report['max_drawdown_amount']=='4' and report['max_drawdown_ratio']==.25
    assert [p['cumulative_net'] for p in report['curve']]==['-2','6','4','2']


def test_unknown_prize_breaks_curve_without_removing_prize_or_cost():
    report=performance_report([row('2026001'),row('2026002',None,1),row('2026003','5',6)])['groups'][0]
    assert report['cost']=='6' and report['known_return']=='5'
    assert report['first_prize_periods']==1 and report['pending_tickets']==1
    assert report['net'] is None and report['roi'] is None and report['max_drawdown_amount'] is None
    assert report['curve'][0]['equity']=='998'
    assert [p['equity'] for p in report['curve'][1:]]==[None,None]


def test_failed_record_visible_and_not_treated_as_zero_loss():
    failed=row('2026002',results=None,tickets=[],error='failed')
    r=performance_report([row('2026001'),failed])['groups'][0]
    assert r['periods']==2 and r['evaluated_periods']==1
    assert r['status_counts']=={'settled':1,'failed':1}
    assert r['net'] is None and r['cost'] is None and r['known_cost']=='2'
    assert r['curve'][1]['status']=='failed'


def test_grouping_empty_zero_initial_and_duplicate_records():
    rows=[row('2026001'),row('2026001',rule_version='r2'),row('2026001',strategy='s-v2'),row('2026001',mode='prospective')]
    assert len(performance_report(rows)['groups'])==4
    assert performance_report([])['groups']==[]
    r=performance_report([row('2026001')],initial_capital='0')['groups'][0]
    assert r['max_drawdown_amount']=='2' and r['max_drawdown_ratio'] is None
    with pytest.raises(ValueError,match='Duplicate'):performance_report([rows[0],rows[0]])


@pytest.mark.parametrize('capital',['-1','NaN','Infinity','oops'])
def test_bad_capital_rejected(capital):
    with pytest.raises(ValueError):performance_report([],initial_capital=capital)

from test_api import api


def test_api_exposes_performance_and_validates_capital(api):
    client,_=api
    result=client.get('/api/evaluations?game=ssq&initial_capital=250.50')
    assert result.status_code==200
    assert result.json()['performance']['initial_capital']=='250.50'
    for value in ['-1','NaN','Infinity']:
        assert client.get('/api/evaluations',params={'initial_capital':value}).status_code==422


def test_history_report_contains_per_strategy_performance(monkeypatch):
    import lottery.experiments as e
    from test_experiments import history
    original=e.probability_vectors
    monkeypatch.setattr(e,'probability_vectors',lambda game,past,name:original(game,past,'uniform'))
    report=e.evaluate_history('ssq',history(161),test_count=1,simulations=1)
    assert len(report['performance']['groups'])==15
    assert all(g['mode']=='historical' and g['periods']==1 for g in report['performance']['groups'])


def test_zero_cost_no_roi_and_distinct_experiment_versions():
    a=row('2026001',tickets=[],results=[])
    r=performance_report([a])['groups'][0]
    assert r['roi'] is None and r['net']=='0' and r['max_drawdown_amount']=='0'
    a=row('2026001',experiment_version='a');b=row('2026001',experiment_version='b')
    assert len(performance_report([a,b])['groups'])==2


def test_distinct_drawdown_maxima_and_negative_equity():
    r=performance_report([row('2026001'),row('2026002','94',1),row('2026003'),row('2026004'),row('2026005')],initial_capital='10')['groups'][0]
    assert r['max_drawdown_amount']=='6' and r['max_drawdown_ratio']==.2
    assert r['curve'][0]['drawdown_ratio']==.2 and r['curve'][-1]['drawdown_ratio']==.06
    negative=performance_report([row('2026001')],initial_capital='1')['groups'][0]
    assert negative['curve'][0]['equity']=='-1' and negative['max_drawdown_ratio']==2
