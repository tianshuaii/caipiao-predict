import pytest
from lottery.combinations import expand, simulate


def config(game='ssq',**kw):
    return dict(game=game,kind='multiple',front=list(range(1,8)),back=[1,2],**kw)


def test_counts_expand_and_cost():
    result=expand(config())
    assert result['units']==14 and result['cost']==28
    assert len({(tuple(t['front']),tuple(t['back'])) for t in result['tickets']})==14
    c=config(front_bankers=[1,2]);c['kind']='banker';c['front']=[3,4,5,6,7]
    result=expand(c)
    assert result['units']==10 and all({1,2}<=set(t['front']) for t in result['tickets'])
    c=dict(game='dlt',kind='banker',front_bankers=[1,2,3,4],front=[5,6],back_bankers=[1],back=[2,3],additional=True)
    assert expand(c)['units']==4 and expand(c)['cost']==12


@pytest.mark.parametrize('change',[{'front':[1,1,2,3,4,5,6]}, {'front':[True,2,3,4,5,6,7]}, {'additional':True}, {'front':list(range(1,34))}, {'kind':'single'}, {'kind':'banker'}, {'front_bankers':[1]}, {'back_bankers':[1]}])
def test_invalid_or_oversized(change):
    with pytest.raises(ValueError):expand({**config(),**change})


def test_settlement_total_pending_and_additional():
    c=dict(game='dlt',kind='single',front=[1,2,3,4,5],back=[1,2],additional=True)
    draw=dict(issue='2026014',front=c['front'],back=c['back'],prizes={'1':{'amount':'100'}})
    r=simulate(c,draw)
    assert r['settlement']['known_return']=='180' and r['settlement']['net']=='177'
    draw['prizes']={}
    r=simulate(c,draw)
    assert r['settlement']['pending']==1 and r['settlement']['net'] is None
    draw['issue']='2019018'
    with pytest.raises(ValueError):simulate(c,draw)

from test_api import api
from sqlalchemy.orm import Session
from lottery.ingestion import ingest
from lottery.models import Draw
from test_workflow import draw


def test_api_preview_settlement_conflict_and_bad_inputs(api):
    client,engine=api
    import json
    params={'config':json.dumps(config())}
    assert client.get('/api/research/combinations',params=params).json()['units']==14
    assert client.get('/api/research/combinations',params={**params,'issue':'2026121'}).status_code==404
    with Session(engine) as session:
        ingest(session,draw(),None,'cwl');session.commit()
    r=client.get('/api/research/combinations',params={**params,'issue':'2026121'})
    assert r.status_code==200 and len(r.json()['settlement']['results'])==14 and r.json()['draw_fingerprint']
    with Session(engine) as session:
        session.query(Draw).first().conflict=True;session.commit()
    assert client.get('/api/research/combinations',params={**params,'issue':'2026121'}).status_code==409
    for value in ('null','[]','{','{"game":"ssq"}'):
        assert client.get('/api/research/combinations',params={'config':value}).status_code==422


def test_compound_sum_equals_individual_settlement():
    from decimal import Decimal
    from lottery.settlement import settle_ticket
    c=config();d=dict(issue='2026121',front=[1,2,3,4,5,6],back=[1],prizes={str(i):{'amount':str(1000//i)} for i in range(1,7)})
    r=simulate(c,d)
    expected=sum(Decimal(settle_ticket('ssq',t,d)['amount']) for t in r['tickets'])
    assert Decimal(r['settlement']['known_return'])==expected
    assert Decimal(r['settlement']['net'])==expected-r['cost']


def test_additional_only_float_prizes_and_rounding():
    c=dict(game='dlt',kind='single',front=[1,2,3,4,5],back=[1,2],additional=True)
    d=dict(issue='2019019',front=c['front'],back=[1,3],prizes={'2':{'amount':'101'}})
    r=simulate(c,d)['settlement']['results'][0]
    assert r['additional_amount']=='80' and r['amount']=='181'
    d['back']=[3,4];d['prizes']={'3':{'amount':'10000'}}
    r=simulate(c,d)['settlement']['results'][0]
    assert r['additional_amount']=='0' and r['amount']=='10000'

@pytest.mark.parametrize('c,units',[
    (dict(game='dlt',kind='banker',front=[1,2,3,4,5],back_bankers=[1],back=[2,3,4]),3),
    (dict(game='ssq',kind='banker',front_bankers=[1,2,3,4,5],front=[6,7],back=[1]),2),
    (dict(game='dlt',kind='multiple',front=[1,2,3,4,5],back=[1,2,3]),3),
])
def test_zone_variants(c,units):
    from lottery.domain import validate_ticket
    result=expand(c)
    assert result['units']==len(result['tickets'])==units
    for ticket in result['tickets']:validate_ticket(c['game'],ticket['front'],ticket['back'])


def test_rejects_overlap_full_bankers_and_inexact_single():
    base=dict(game='dlt',kind='banker',front_bankers=[1],front=[2,3,4,5,6],back=[1,2])
    for change in ({'front':[1,2,3,4,5]}, {'front_bankers':[1,2,3,4,5]}, {'front':[2,3,4,5]}, {'additional':'true'}, {'back':[0,2]}):
        with pytest.raises(ValueError):expand({**base,**change})
