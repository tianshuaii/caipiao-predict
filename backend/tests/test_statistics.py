import itertools
from datetime import date,timedelta
import numpy as np
import pytest
from lottery.statistics import analyze,sum_pmf,adjacent_pmf,save_report,read_report


def dataset(n=60,seed=3,biased=False):
    rng=np.random.default_rng(seed)
    return {'games':{'ssq':[{'issue':f'2025{i+1:03d}','date':str(date(2025,1,1)+timedelta(days=i)),
             'front':list(range(1,7)) if biased else sorted(rng.choice(np.arange(1,34),6,replace=False).tolist()),
             'back':[1] if biased else [int(rng.integers(1,17))]} for i in range(n)]}}


def test_exact_distributions_match_enumeration():
    combinations=list(itertools.combinations(range(1,9),3))
    sums=np.bincount([sum(c) for c in combinations],minlength=25)/len(combinations)
    adjacent=np.bincount([sum(b-a==1 for a,b in zip(c,c[1:])) for c in combinations],minlength=3)/len(combinations)
    assert np.allclose(sum_pmf(8,3),sums)
    assert np.allclose(adjacent_pmf(8,3),adjacent)


def test_null_and_bias_reproducible_and_corrected():
    report=analyze(dataset(),simulations=199)
    assert report==analyze(dataset(),simulations=199)
    assert report['post_hoc'] is True and report['total_tests']==14
    assert all(0<t['p']<=t['holm_p']<=1 for t in report['tests'])
    assert report['significant']==[]
    biased=analyze(dataset(biased=True),simulations=999)
    assert any(t['family']=='frequency' for t in biased['significant'])


def test_invalid_and_small_snapshots():
    small=analyze(dataset(3),simulations=99)
    assert small['tests']==[] and small['skipped'][0]['reason']=='fewer_than_30_draws'
    invalid=dataset();invalid['games']['ssq'][1]['issue']=invalid['games']['ssq'][0]['issue']
    with pytest.raises(ValueError):analyze(invalid,simulations=99)
    invalid=dataset();invalid['games']['ssq'][0]['front']=[1]*6
    with pytest.raises(ValueError):analyze(invalid,simulations=99)
    with pytest.raises(ValueError):analyze(dataset(),simulations=0)


def test_content_addressed_report_integrity(tmp_path):
    data=dataset(3);report=analyze(data,simulations=99)
    key=save_report(data,report,tmp_path)
    assert save_report(data,report,tmp_path)==key
    assert read_report(key,tmp_path)['report']==report
    (tmp_path/(key+'.json')).write_text('{}')
    with pytest.raises(ValueError):read_report(key,tmp_path)
    with pytest.raises(ValueError):read_report('../bad',tmp_path)

from test_api import api


def test_statistics_read_api_and_offline_entry(api,tmp_path,monkeypatch):
    import json
    import lottery.api as routes
    from lottery.statistics import run_file
    monkeypatch.setattr(routes,'RUNTIME',tmp_path)
    path=tmp_path/'input.json';path.write_text(json.dumps(dataset(3)))
    key=run_file(path,99,7,tmp_path/'statistics')
    client,_=api
    listed=client.get('/api/statistics').json()
    assert listed['items'][0]['id']==key
    detail=client.get('/api/statistics/'+key)
    assert detail.status_code==200 and detail.json()['snapshot']==dataset(3)
    assert detail.json()['report']['seed']==7
    assert client.get('/api/statistics/not-a-hash').status_code==422
    assert client.get('/api/statistics/'+'0'*64).status_code==404
    assert (tmp_path/'analysis.json').exists() and (tmp_path/'tests.csv').exists()


def test_rule_partition_and_missing_serial_edges():
    data=dataset()
    for i,row in enumerate(data['games']['ssq']):
        row['issue']=f'2026{i+1:03d}';row['date']=str(date(2026,1,1)+timedelta(days=i))
    report=analyze(data,simulations=99)
    assert report['skipped'][0]['periods']==13
    assert report['groups'][0]['from_issue']=='2026014'
    data=dataset(30)
    for i,row in enumerate(data['games']['ssq']):row['issue']=f'2025{2*i+1:03d}'
    report=analyze(data,simulations=99)
    serial=[t for t in report['tests'] if t['family'] in ('lag1','runs')]
    assert all(not t['informative'] and t['p']==1 for t in serial)


def test_seeded_null_smoke_has_no_gross_false_positive_inflation():
    # Eight seeds are a regression smoke check, not a precision estimate of type-I error.
    rejected=sum(bool(analyze(dataset(40,seed=seed),simulations=999)['significant']) for seed in range(8))
    assert rejected<=2


@pytest.mark.parametrize('name',['analysis.json','tests.csv'])
def test_compatibility_outputs_never_overwrite_input(tmp_path,name):
    import json
    from lottery.statistics import run_file
    path=tmp_path/name;raw=json.dumps(dataset(3));path.write_text(raw)
    with pytest.raises(ValueError,match='output'):
        run_file(path,99,7,tmp_path/'reports')
    assert path.read_text()==raw
    assert not (tmp_path/'reports').exists()
