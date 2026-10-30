from lottery.ranking import rank_records


def record(strategy,issue,win=False,amount='0',brier=.1,rule='r'):
    return {'strategy':strategy,'issue':issue,'rule_version':rule,'brier':brier,
            'results':[{'level':6 if win else None,'amount':amount}]+[{'level':None,'amount':'0'}]*4}


def test_common_periods_budget_and_money_intersection():
    rows=[record(s,str(i),s=='a', '5' if s=='a' else '0') for s in ('a','b') for i in range(30)]
    rows.append(record('a','extra',True,'100'))
    rows[0]['results'][0]['amount']=None
    result=rank_records(rows,['a','b'],'any_prize')[0]
    assert len(result['issues'])==30 and len(result['money_issues'])==29
    assert result['rows'][0]['strategy']=='a' and result['rows'][0]['rank']==1
    assert result['rows'][0]['metrics']['cost']==300
    assert result['rows'][0]['money_metrics']['cost']==290
    assert result['rows'][0]['metrics']['net'] is None
    roi=rank_records(rows,['a','b'],'roi')[0]
    assert all(r['rank'] is None and r['reason']=='insufficient_periods' for r in roi['rows'])
    assert result['excluded']==[{'issue':'extra','missing_strategies':['b']}]


def test_ties_empty_intersection_rules_and_rare_prizes():
    rows=[record(s,f'{i:03}',rule=rule) for rule in ('old','new') for s in ('a','b') for i in range(30)]
    for group in rank_records(rows,['a','b'],'brier'):
        assert [r['rank'] for r in group['rows']]==[1,1]
    assert all(r['reason']=='no_first_prize_observed' for g in rank_records(rows,['a','b'],'first_prize') for r in g['rows'])
    assert all(not g['issues'] for g in rank_records(rows,['a','b','failed'],'brier'))


def test_read_only_api_validation(api):
    client,_=api
    assert client.get('/api/rankings?game=ssq&objective=brier').json()['groups']==[]
    assert client.get('/api/rankings?objective=unknown').status_code==422
    assert client.post('/api/rankings').status_code==405

from test_api import api


def test_current_revision_cutoff_budget_and_failures(session,monkeypatch):
    from datetime import datetime
    from sqlalchemy import select
    import lottery.prospective as prospective
    from lottery.domain import TZ
    from lottery.ingestion import ingest
    from lottery.workflow import persist_prediction
    from lottery.models import CandidateForecast, CandidateScore
    from lottery.ranking import ranking_status
    from test_workflow import draw
    ingest(session,draw(),None,'cwl')
    p=persist_prediction(session,'ssq',datetime(2026,10,23,8,tzinfo=TZ))
    f=session.scalar(select(CandidateForecast))
    monkeypatch.setattr(prospective,'versions',lambda:{f.model:f.strategy})
    f.error=None;f.tickets=p.tickets
    actual=ingest(session,draw('2026122','2026-10-25'),None,'cwl')
    score=CandidateScore(forecast_id=f.id,draw_fingerprint=actual.fingerprint,
        metrics={'results':record('a','i')['results'],'cost':10,'brier':.1})
    session.add(score);session.flush()
    def check(reason):
        session.flush();view=ranking_status(session,'ssq')
        assert view['groups']==[] and view['excluded'][0]['reason']==reason
    assert ranking_status(session,'ssq')['groups'][0]['issues']==['2026122']
    f.error='failed';check('generation_failed');f.error=None
    created=f.created_at;f.created_at=f.cutoff_at;check('invalid_forecast_cutoff');f.created_at=created
    actual.conflict=True;check('draw_conflict');actual.conflict=False
    actual.fingerprint='corrected';check('missing_current_revision_score');actual.fingerprint=score.draw_fingerprint
    score.metrics={**score.metrics,'cost':12};check('budget_mismatch')
    score.metrics={**score.metrics,'cost':10};f.tickets=f.tickets[:4];check('budget_mismatch')

from test_prospective import session
