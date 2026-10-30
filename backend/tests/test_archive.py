from sqlalchemy.orm import Session
from test_api import api
from test_workflow import draw
from lottery.ingestion import ingest


def test_combined_archive_filters_total_and_paging(api):
    client,engine=api
    with Session(engine) as s:
        for issue,day in [('2026121','2026-10-22'),('2026122','2026-10-25'),('2026123','2026-10-27')]:
            row=ingest(s,draw(issue,day),None,'cwl')
            row.conflict=issue=='2026122'
        s.commit()
    query='/api/draws?game=ssq&issue_from=2026121&issue_to=2026122&date_from=2026-10-22&date_to=2026-10-25&limit=1'
    result=client.get(query).json()
    assert result['total']==2 and result['items'][0]['issue']=='2026122'
    assert client.get(query+'&offset=1').json()['items'][0]['issue']=='2026121'
    assert client.get(query+'&conflict=true').json()['total']==1
    assert client.get(query+'&conflict=false').json()['items'][0]['issue']=='2026121'
    assert client.get('/api/draws?game=ssq&date_from=2026-10-28').json()['total']==0
    assert client.get('/api/draws?game=dlt').json()['total']==0


def test_invalid_archive_ranges(api):
    client,_=api
    for query in ('issue_from=123','issue_to=2026abc','issue_from=2026123&issue_to=2026121',
                  'date_from=2026-10-28&date_to=2026-10-22','date_to=2026-02-30'):
        assert client.get('/api/draws?'+query).status_code==422
