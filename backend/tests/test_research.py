import json
import pytest
from lottery.research import research_selection
from lottery.feature_service import combination_features
from test_api import api


def test_constraints_reproducible_legal_and_unique():
    request={'game':'ssq','seed':42,'count':5,'front':{'odd':3,'small':3,'sum_min':80,'sum_max':130,'span_min':20,'span_max':32}}
    result=research_selection(request)
    assert result==research_selection(request)
    assert result['status']=='complete' and result['budget']==10
    assert len({str(t) for t in result['tickets']})==5
    for ticket in result['tickets']:
        f=combination_features(ticket['front'],33)
        assert f['odd_even'][0]==3 and f['small_big'][0]==3
        assert 80<=f['sum']<=130 and 20<=f['span']<=32


def test_partition_constraints_use_shared_boundaries():
    result=research_selection({'game':'dlt','seed':17,'count':1,'front':{'thirds':[2,2,1],'fourths':[1,2,1,1]}})
    assert result['status']=='complete'
    f=combination_features(result['tickets'][0]['front'],35)
    assert f['thirds']==[2,2,1] and f['fourths']==[1,2,1,1]


def test_provable_infeasible_and_search_exhausted_are_distinct():
    r=research_selection({'game':'ssq','seed':42,'front':{'sum_min':210}})
    assert r['status']=='infeasible' and r['attempts']==0 and r['tickets']==[]
    r=research_selection({'game':'ssq','seed':42,'count':10,'pool_size':1})
    assert r['status']=='exhausted' and r['attempts']==1 and r['matched_count']==1
    assert r['tickets']==[] and r['budget']==20


@pytest.mark.parametrize('change',[{'count':True},{'pool_size':2001},{'seed':-1},{'front':{'sum_min':100,'sum_max':50}},{'front':{'thirds':[1,2]}},{'back':{'span_min':0}},{'unknown':1}])
def test_invalid_config_is_rejected(change):
    with pytest.raises(ValueError):research_selection({'game':'ssq','seed':42,**change})


def test_read_only_api_handles_invalid_and_valid_requests(api):
    client,engine=api
    from sqlalchemy.orm import Session
    from sqlalchemy import select,func
    from lottery.models import Prediction,CandidateForecast
    response=client.get('/api/research/selection',params={'config':json.dumps({'game':'dlt','seed':42})})
    assert response.status_code==200 and response.json()['status']=='complete'
    assert client.get('/api/research/selection',params={'config':'{}'}).status_code==422
    assert client.get('/api/research/selection',params={'config':'{bad'}).status_code==422
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(Prediction))==0
        assert session.scalar(select(func.count()).select_from(CandidateForecast))==0
