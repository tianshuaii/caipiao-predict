import json
from pathlib import Path
import pytest
from sqlalchemy import create_engine, select, func
from sqlalchemy.orm import Session
from lottery.models import Base, Draw, Observation
from lottery.collectors import parse_cwl, parse_sporttery, parse_shanghai, parse_zhcw
from lottery.ingestion import ingest, coverage

@pytest.fixture
def session():
    engine = create_engine('sqlite://')
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session

def fixture(game):
    return json.loads((Path(__file__).parent/'fixtures'/f'{game}.json').read_text())

def test_real_official_formats():
    ssq = parse_cwl(fixture('ssq'))
    assert ssq['issue'] == '2026121'
    assert ssq['front'] == [2,7,20,24,26,30]
    assert ssq['prizes']['1']['amount'] == '8113808'
    dlt = parse_sporttery(fixture('dlt'))
    assert dlt['issue'] == '2026120'
    assert dlt['prizes']['7']['amount'] == '7'
    assert '追加' not in str(dlt['prizes'])

def test_duplicate_draw_is_idempotent_and_secondary_conflict_is_retained(session):
    data = parse_cwl(fixture('ssq'))
    ingest(session, data, None, 'cwl')
    ingest(session, data, None, 'cwl')
    assert session.scalar(select(func.count()).select_from(Draw)) == 1
    wrong = dict(data, front=[1,7,20,24,26,30])
    ingest(session, wrong, None, 'shanghai')
    row = session.scalar(select(Draw))
    assert row.data['front'] == data['front']
    assert row.conflict is True
    assert session.scalar(select(func.count()).select_from(Observation)) == 2

def test_official_correction_retains_previous_observation(session):
    data = parse_cwl(fixture('ssq'))
    ingest(session, data, None, 'cwl')
    changed = dict(data, front=[1,7,20,24,26,30])
    ingest(session, changed, None, 'cwl')
    row = session.scalar(select(Draw))
    assert row.revision == 2 and row.data['front'][0] == 1
    assert session.scalar(select(func.count()).select_from(Observation)) == 2

def test_missing_historical_data_is_not_reported_as_complete(session):
    ingest(session, parse_cwl(fixture('ssq')), None, 'cwl')
    report = coverage(session, 'ssq')
    assert report['complete'] is False
    assert report['first_issue'] == '2026121'
    assert report['missing_count'] > 0

def test_ambiguous_bonus_is_not_silently_interpreted_as_base_cash():
    data = fixture('ssq')
    data['prizegrades'][0]['typemoney'] = '5250000（含加奖250000）'
    parsed = parse_cwl(data)
    assert parsed['prizes']['1']['amount'] is None
    assert '含加奖' in parsed['prizes']['1']['raw_amount']

def test_shanghai_html_parser():
    text = "employee.push({'id':'2003001','c':'10,11,12,13,26,28|11','t':'2003-02-16 21:15:00','prize1':'0','bonus1':'0','prize2':'1','bonus2':'10000'})"
    rows = parse_shanghai(text)
    assert rows[0]['issue'] == '2003001'
    assert rows[0]['prizes']['3']['amount'] is None

def test_designated_media_archive_keeps_all_prizes():
    result = parse_zhcw(fixture('zhcw'), 'ssq')
    assert result['issue'] == '2012154'
    assert result['prizes']['3']['amount'] == '3000'
    assert result['prizes']['6']['count'] == 8986567

def test_archive_fetch_uses_its_own_publisher_referer(session):
    import httpx
    from lottery.collectors import fetch, ZHCW_URL
    def server(request):
        return httpx.Response(200, text='{"data":[]}' if request.headers.get('referer')=='https://www.zhcw.com/' else '')
    with httpx.Client(transport=httpx.MockTransport(server),headers={'Referer':'https://www.cwl.gov.cn/'}) as http:
        assert fetch(session,http,'zhcw',ZHCW_URL).body == '{"data":[]}'

def test_numeric_zero_is_known_not_missing():
    from lottery.collectors import number
    assert number(0) == '0'
    assert number(None) is None

def test_official_correction_can_revert(session):
    data=parse_cwl(fixture('ssq'))
    ingest(session,data,None,'cwl')
    ingest(session,dict(data,front=[1,7,20,24,26,30]),None,'cwl')
    restored=ingest(session,data,None,'cwl')
    assert restored.data['front']==data['front']
    assert restored.revision==3

def test_inventory_detects_deleted_year_end(session):
    from lottery.ingestion import record_inventory
    data=parse_cwl(fixture('ssq'))
    for issue in ['2003001','2004001']:
        ingest(session,dict(data,issue=issue),None,'cwl')
    record_inventory(session,'ssq','cwl',['2003001','2003002','2004001'])
    report=coverage(session,'ssq')
    assert report['complete'] is False
    assert '2003002' in report['missing']
