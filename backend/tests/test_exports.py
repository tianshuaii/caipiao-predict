from test_api import api
from sqlalchemy.orm import Session
from lottery.exports import build_export,encode
from lottery.ingestion import coverage,ingest
from lottery.performance import performance_report
from lottery.evaluation import prospective_records
from test_workflow import draw


def test_export_matches_quality_performance_and_empty_states(api,tmp_path):
    _,engine=api
    with Session(engine) as s:
        ingest(s,draw(),None,'cwl');s.commit()
        report=build_export(s,'ssq',tmp_path)
        assert report['data']['quality']==coverage(s,'ssq')
        assert report['data']['performance']==performance_report(prospective_records(s,'ssq'))
        assert report['data']['cutoff']['issue']=='2026121'
        assert report['data']['statistics']['status']=='unavailable'
        assert report['data']['historical_experiment'] is None
        encoded=encode(report)
        assert report['sha256'] in encoded['markdown']
        assert '完整指标' in encoded['markdown'] and 'null' in encoded['json']


def test_corrupt_statistics_and_hash(api,tmp_path):
    import hashlib,json
    _,engine=api
    (tmp_path/('a'*64+'.json')).write_text('broken')
    with Session(engine) as s:report=build_export(s,'dlt',tmp_path)
    assert report['data']['statistics']['unreadable'][0]['id']=='a'*64
    raw=json.dumps(report['data'],ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
    assert hashlib.sha256(raw).hexdigest()==report['sha256']


def test_export_api_readonly_and_format_identity(api,tmp_path,monkeypatch):
    import json
    import lottery.api as routes
    from lottery.models import Notification,Experiment
    monkeypatch.setattr(routes,'RUNTIME',tmp_path)
    client,engine=api
    response=client.get('/api/research/export?game=ssq')
    assert response.status_code==200
    result=response.json()
    assert json.loads(result['json'])==result['report']
    assert result['json'] in result['markdown']
    with Session(engine) as s:
        assert s.query(Notification).count()==0 and s.query(Experiment).count()==0
    assert client.get('/api/research/export?game=bad').status_code==422


def test_unknown_amounts_preserved_in_both_exports(api,tmp_path,monkeypatch):
    from lottery.evaluation import evaluation_record
    import lottery.exports as exports
    _,engine=api
    record=evaluation_record(mode='prospective',game='ssq',strategy='example',issue='2026121',cutoff_issue='2026120',
        tickets=[{}],results=[{'level':1,'amount':None}],rule_version='ssq-2026014')
    monkeypatch.setattr(exports,'prospective_records',lambda session,game:[record])
    with Session(engine) as s:report=build_export(s,'ssq',tmp_path)
    group=report['data']['performance']['groups'][0]
    assert group['net'] is None and group['pending_tickets']==1 and group['max_drawdown_amount'] is None
    assert '待确认1注' in encode(report)['markdown']


def test_statistics_keeps_its_frozen_cutoff_and_full_family(api,tmp_path):
    import hashlib
    from lottery.statistics import save_report
    from lottery.exports import canonical
    dataset={'games':{'ssq':[{'issue':'2025001'}],'dlt':[{'issue':'2025002'}]}}
    statistical={'dataset_sha256':hashlib.sha256(canonical(dataset)).hexdigest(),'version':'test-statistics',
                 'tests':[{'game':'ssq','holm_p':0.7},{'game':'dlt','holm_p':0.8}],'note':'exploratory'}
    key=save_report(dataset,statistical,tmp_path)
    _,engine=api
    with Session(engine) as s:
        ingest(s,draw(),None,'cwl');s.commit()
        result=build_export(s,'ssq',tmp_path)['data']
    assert result['cutoff']['issue']=='2026121'
    assert result['statistics']['selected_game_cutoff']=='2025001'
    assert result['statistics']['id']==key and result['statistics']['report']==statistical
