import math
import pytest
from lottery.feature_service import analyze_features, combination_features, feature_catalog
from test_api import api


def rows():
    return [dict(issue=issue,front=front,back=[1]) for issue,front in [
        ('2025001',[1,2,3,4,5,6]),('2025002',[2,3,4,5,6,7]),
        ('2026001',[1,2,3,4,5,6]),('2026002',[2,3,4,5,6,7])]]


def test_basic_manual_and_completed_gaps():
    r=analyze_features(rows(),'ssq','front','2026002',10)
    one=r['numbers'][0]; two=r['numbers'][1]; unseen=r['numbers'][32]
    assert r['sample_size']==4 and r['short_window']
    assert one['count']==2 and one['frequency']==.5
    assert one['current_omission']==1 and one['max_omission']==1
    assert one['mean_omission']==1 and one['omission_std']==0
    assert one['repeat_intervals']==[{'interval':2,'count':1}]
    assert two['hot_rank']==1 and two['max_omission']==0
    assert unseen['current_omission']==4 and unseen['left_censored']
    assert unseen['max_omission'] is None and unseen['repeat_intervals']==[]
    p=6/33
    assert one['frequency_z']==pytest.approx((2-4*p)/math.sqrt(4*p*(1-p)))


def test_future_changes_do_not_affect_cutoff_and_duplicates_rejected():
    before=analyze_features(rows(),'ssq','front','2025002','all')
    changed=rows();changed[-1]['front']=[99]
    assert analyze_features(changed,'ssq','front','2025002','all')==before
    with pytest.raises(ValueError): analyze_features(rows()+[rows()[0]],'ssq','front','2026002',10)


def test_empty_short_single_ball_and_catalog():
    empty=analyze_features([],'ssq','back','2026002',10)
    assert empty['numbers'][0]['frequency'] is None
    assert empty['numbers'][0]['current_omission'] is None
    single=combination_features([1],16)
    assert single['ac'] is None and single['span'] is None
    assert single['variance']==0 and single['prime_counts']==[1,0,0]
    assert single['previous_repeat'] is None
    catalog=feature_catalog()
    ids=[x['id'] for x in catalog['features']]
    assert len(ids)==len(set(ids))
    assert all(x['formula'] and x['null_semantics'] and x['version'] for x in catalog['features'])
    assert set(empty['numbers'][0])-{'number'} <= set(ids)
    assert set(single) <= set(ids)


def test_combination_manual():
    r=combination_features([1,2,3,11,21,33],33,[1,4,9,12,22,30])
    assert r['odd_even']==[5,1] and r['odd_run']==4
    assert r['small_big']==[4,2] and r['size_run']==4
    assert r['thirds']==[4,1,1] and r['fourths']==[3,1,1,1]
    assert r['sum']==71 and r['median']==7 and r['span']==32
    assert r['tail_sum']==11 and r['same_tail_pairs']==4
    assert r['consecutive_groups']==1 and r['max_consecutive']==3
    assert r['gaps']==[1,1,8,10,12]
    assert r['previous_repeat']==1 and r['previous_neighbors']==4
    assert r['previous_same_tail']==4
    assert r['previous_differences']==[0,-2,-6,-1,-1,3]
    assert r['prime_counts']==[1,3,2] and r['mod3']==[3,1,2]
    differences={b-a for a in [1,2,3,11,21,33] for b in [1,2,3,11,21,33] if b>a}
    assert r['distinct_differences']==len(differences)
    assert r['ac']==len(differences)-5
    assert r['tail_entropy']==pytest.approx(-sum(p*math.log2(p) for p in [.5,1/6,1/3]))


def test_cooccurrence_denominators_and_window_boundary():
    r=analyze_features(rows(),'ssq','front','2026002','all')
    pair=next(x for x in r['cooccurrence'] if x['numbers']==[1,2])
    assert pair['count']==2 and pair['frequency']==.5
    assert pair['conditional']==[
        {'given':[1],'denominator':2,'frequency':1},
        {'given':[2],'denominator':4,'frequency':.5}]
    triple=next(x for x in r['cooccurrence'] if x['numbers']==[1,2,3])
    assert triple['conditional'][0]=={'given':[2,3],'denominator':4,'frequency':.5}
    assert r['combinations'][0]['features']['previous_repeat'] is None
    with pytest.raises(ValueError): analyze_features(rows(),'ssq','front','2026002',15)


def test_api_validation_and_empty_snapshot(api):
    client,_=api
    assert client.get('/api/features/catalog').status_code==200
    params=dict(game='ssq',zone='front',cutoff_issue='2026002',as_of='2000-01-01T00:00:00Z')
    response=client.get('/api/features',params=params)
    assert response.status_code==200 and response.json()['sample_size']==0
    for key,value in [('as_of','2026-01-01'),('window','12'),('zone','red'),('cutoff_issue','abc')]:
        assert client.get('/api/features',params={**params,key:value}).status_code==422

@pytest.mark.parametrize('window',[10,20,30,50,100,500,'all'])
def test_windows_use_last_records_and_share_model_omission(window):
    import numpy as np
    from lottery.indicators import omission_features
    data=[dict(issue=f'2025{i+1:03}',front=[1,2,3,4,5,6] if i%3 else [2,3,4,5,6,7],back=[1]) for i in range(510)]
    result=analyze_features(data,'ssq','front','2025510',window)
    n=510 if window=='all' else window
    assert result['sample_size']==n and result['first_issue']==data[-n]['issue']
    matrix=np.zeros((n,33))
    for i,r in enumerate(data[-n:]): matrix[i,np.array(r['front'])-1]=1
    legacy=omission_features(matrix)
    assert [r['current_omission'] for r in result['numbers']]==legacy[:,0].tolist()
    assert result['combinations'][0]['features']['previous_repeat'] is None


def test_full_numeric_formula_and_partition_boundaries():
    r=combination_features([1,2,3,11,21,33],33)
    assert r['mean']==pytest.approx(71/6)
    assert r['variance']==pytest.approx(sum((v-71/6)**2 for v in [1,2,3,11,21,33])/6)
    assert r['tail_counts']==[0,3,1,2,0,0,0,0,0,0]
    assert r['thirds_density']==pytest.approx([4/11,1/11,1/11])
    assert r['fourths_density']==pytest.approx([3/9,1/8,1/8,1/8])
    assert combination_features([11,12,22,23],33)['thirds']==[1,2,1]
    assert combination_features([9,10,17,18,25,26],33)['fourths']==[1,2,2,1]
    single=analyze_features([dict(issue='2026001',front=[1,2,3,4,5,6],back=[16])],'ssq','back','2026001',10)
    assert single['cooccurrence']==[] and single['numbers'][15]['max_omission'] is None


def test_api_snapshot_isolation_and_conflict_fail_closed(api):
    from datetime import datetime, timedelta
    from sqlalchemy import select
    from sqlalchemy.orm import Session
    from lottery.ingestion import ingest
    from lottery.models import Observation
    from test_workflow import draw
    client,engine=api
    t=datetime(2026,10,23)
    with Session(engine) as session:
        ingest(session,draw(),None,'cwl')
        session.scalar(select(Observation)).created_at=t
        session.commit()
    params=dict(game='ssq',zone='back',cutoff_issue='2026121',as_of='2026-10-23T00:00:00Z')
    before=client.get('/api/features',params=params).json()
    assert before['sample_size']==1 and before['numbers'][0]['count']==1
    with Session(engine) as session:
        changed=draw();changed['back']=[2]
        ingest(session,changed,None,'secondary')
        last=session.scalar(select(Observation).order_by(Observation.id.desc()))
        last.created_at=t+timedelta(hours=1);session.commit()
    assert client.get('/api/features',params=params).json()==before
    assert client.get('/api/features',params={**params,'as_of':'2026-10-23T02:00:00Z'}).status_code==409
    assert client.get('/api/features',params={**params,'as_of':'2026-10-22T23:00:00Z'}).status_code==409


def test_training_entrypoint_is_shared_without_changing_protocol():
    from lottery import feature_service, experiments, indicators
    assert feature_service.feature_sequence is indicators.feature_sequence
    assert experiments.feature_sequence is feature_service.feature_sequence


def test_conflicting_rows_cannot_enter_pure_calculation():
    with pytest.raises(ValueError,match='conflict'):
        analyze_features([{**rows()[0],'conflict':True}],'ssq','front','2025001',10)


def test_distribution_reference_counts_and_empty_semantics():
    result=analyze_features(rows(),'ssq','front','2026002',10)
    assert result['theory']['number_probability']==pytest.approx(6/33)
    for name,bins in result['distributions'].items():
        assert sum(b['count'] for b in bins)==4
        assert sum(b['theoretical_probability'] for b in bins)==pytest.approx(1)
        assert sum(b['frequency'] for b in bins)==pytest.approx(1)
    odd=next(b for b in result['distributions']['odd'] if b['value']==3)
    assert odd['count']==4
    assert odd['theoretical_probability']==pytest.approx(math.comb(17,3)*math.comb(16,3)/math.comb(33,6))
    empty=analyze_features([],'ssq','back','2026002',10)
    assert all(b['frequency'] is None for bins in empty['distributions'].values() for b in bins)
    assert len(empty['distributions']['sum'])==16
