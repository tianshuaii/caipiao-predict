from lottery.visualization import visual_records
from lottery.evaluation import evaluation_record


def row(strategy,issue,amount='0',level=None,rule='r',count=5):
    return evaluation_record(mode='historical',game='ssq',strategy=strategy,issue=issue,cutoff_issue='2025000',
        tickets=[{}]*count,results=[{'level':level,'amount':amount}]+[{'level':None,'amount':'0'}]*(count-1),rule_version=rule)


def test_common_money_boundary_breaks_both_curves():
    rows=[row(s,f'202500{i}') for s in ('model','uniform') for i in range(1,4)]
    rows[1]=row('model','2025002',None,1)
    result=visual_records(rows,'model')['groups'][0]
    assert result['issues']==['2025001','2025002','2025003']
    assert result['money_issues']==['2025001','2025003']
    assert result['chart'][0]['model_equity']=='990'
    assert all(r['model_equity'] is None and r['uniform_equity'] is None for r in result['chart'][1:])
    assert all(g['net'] is None and g['max_drawdown_amount'] is None for g in result['series'])
    assert result['prizes'][0]=={'level':'1','model':1,'uniform':0}


def test_common_budget_rules_and_known_drawdown():
    rows=[row(s,'2025001') for s in ('model','uniform')]
    rows.extend([row('model','2025002',count=4),row('uniform','2025002')])
    rows.extend([row(s,'2025003',rule='new') for s in ('model','uniform')])
    groups=visual_records(rows,'model')['groups']
    old=next(g for g in groups if g['rule_version']=='r')
    assert old['issues']==['2025001'] and old['excluded'][0]['reason']=='mode_game_rule_or_budget_mismatch'
    assert all(g['max_drawdown_amount']=='10' for g in old['series'])
    assert len(groups)==2

from test_api import api
from sqlalchemy.orm import Session
from lottery.models import Experiment,ResearchJob


def test_read_only_visual_sources_and_old_records(api):
    client,engine=api
    records=[row(s,'2025001') for s in ('model','uniform')]
    with Session(engine) as session:
        old=Experiment(game='ssq',result={})
        experiment=Experiment(game='ssq',result={'forecast_audit':[{'forecasts':{r['strategy']:{'evaluation':r} for r in records}}]})
        job=ResearchJob(status='succeeded',config={'kind':'backtest'},snapshot=[],snapshot_hash='x',submitted_by='test',result={'records':records})
        session.add_all([old,experiment,job]);session.commit()
        old_id,exp_id,job_id=old.id,experiment.id,job.id
    assert not client.get(f'/api/visualizations?source=experiment&id={old_id}').json()['available']
    for source,id in [('experiment',exp_id),('job',job_id)]:
        response=client.get(f'/api/visualizations?source={source}&id={id}')
        assert response.status_code==200
        assert response.json()['groups'][0]['chart'][0]['model_net']=='-10'
        assert client.get(f'/api/visualizations?source={source}&id={id}&strategy=unknown').status_code==422
    assert client.get('/api/visualizations?source=job&id=999').status_code==404
    assert client.get('/api/visualizations?source=unknown&id=1').status_code==422


def test_missing_failed_and_rule_mismatch_never_enter_chart():
    records=[row('model','2025001'),row('uniform','2025001',rule='other'),row('model','2025002')]
    failed=row('model','2025003');failed['status']='failed'
    result=visual_records(records+[failed,row('uniform','2025003')],'model')
    assert not result['available']
    assert all(not g['chart'] for g in result['groups'])
