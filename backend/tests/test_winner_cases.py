import pytest
from sqlalchemy import select,func
from test_prospective import session
from test_api import api
from lottery.winner_cases import parse_cases, validate_url, import_article
from lottery.models import WinnerCase

URL='https://www.gdfc.org.cn/datas/content/content_284772.html'
def html(text): return '<html><h1>双色球一等奖案例</h1><div class="article-meta">2026-07-14</div><div class="article-content"><p>'+text+'</p></div></html>'

def test_single_count_and_multiplier_are_not_first_prize_count():
    rows=parse_cases(html('双色球第2026062期开奖，全国中出一等奖30注，中奖彩票是一张5注5倍单式票，中奖奖金共计1666万余元。'),URL)
    r=rows[0]
    assert r['issue']=='2026062' and r['ticket_type']=='single'
    assert r['details']['single_count']==5 and r['details']['multiplier']==5
    assert r['details']['first_prize_count'] is None
    assert r['details']['cost'] is None
    assert r['published_date']=='2026-07-14'

def test_multi_case_article_excludes_second_prize():
    text='<div class="m-listcon-cont"><p>超级大乐透第26027期开奖，花12元购买了张“5+4”复式票，中得1注一等奖，单票累计奖金达733.45万元。</p><p>超级大乐透第26030期开奖，28元套餐票中得1注二等奖。</p></div>'
    r=parse_cases(text,'https://m.lottery.gov.cn/zx/zj/20260327/10052905.html')
    assert len(r)==1 and r[0]['issue']=='2026027'
    assert r[0]['details']['expanded_units']==6
    assert r[0]['details']['cost']=='12'
    assert r[0]['details']['first_prize_count']==1

def test_ambiguous_multiple_tickets_and_unknowns():
    r=parse_cases(html('双色球第2026062期，一等奖中奖彩票分别为单式票和复式票。'),URL)[0]
    assert r['ticket_type']=='unknown' and r['status']=='needs_review'
    assert r['details']['single_count'] is None
    assert parse_cases(html('本期双色球全国中出一等奖30注，复式投注更精彩。'),URL)==[]

def test_urls_reject_external_or_local_and_credentials():
    for url in ('http://127.0.0.1/','https://evil.test/','https://www.gdfc.org.cn.evil.test/','https://x:y@www.gdfc.org.cn/a','https://www.gdfc.org.cn:9999/a'):
        with pytest.raises(ValueError): validate_url(url)
    assert validate_url(URL)==URL

def test_import_idempotence_and_raw_evidence(session):
    body=html('双色球第2026062期开奖，中奖彩票是一张5注5倍单式票，中得一等奖。')
    assert import_article(session,URL,body,200)==1
    assert import_article(session,URL,body,200)==1
    assert session.scalar(select(func.count()).select_from(WinnerCase))==1
    row=session.scalar(select(WinnerCase))
    assert row.raw_id and '5注5倍' in row.evidence and row.active
    changed=body.replace('5注5倍','5注2倍')
    import_article(session,URL,changed,200)
    assert session.scalar(select(func.count()).select_from(WinnerCase).where(WinnerCase.active.is_(True)))==1


def test_banker_preserves_description_without_inventing_counts():
    body='<div class="content-text-area"><p>大乐透第25141期，凭一张胆拖票中得1注一等奖，前区一胆七拖，后区一胆两拖。</p></div>'
    r=parse_cases(body,'https://www.js-lottery.com/xwzx/zdgz/cms/post-1.html')[0]
    assert r['ticket_type']=='banker'
    assert '一胆七拖' in r['details']['banker_description']
    assert r['details']['expanded_units'] is None


def test_api_filters_and_does_not_leak_raw_html(api):
    from sqlalchemy.orm import Session
    c,engine=api
    with Session(engine) as s:
        import_article(s,URL,html('双色球第2026062期，中奖彩票为5注5倍单式票，中得一等奖。'),200)
        s.commit()
    r=c.get('/api/winner-cases?game=ssq&ticket_type=single')
    assert r.status_code==200 and r.json()['total']==1
    assert 'body' not in r.json()['items'][0]
    assert c.get('/api/winner-cases?game=dlt').json()['total']==0
    assert c.get('/api/winner-cases?game=ssq&ticket_type=banker').json()['total']==0
    assert c.get('/api/winner-cases?limit=500').status_code==422


def test_regional_summary_is_not_a_ticket_case():
    body='<div class="content-text-area"><p>追加投注是大乐透特有投注方式，在第26111期，江苏中出2注追加一等奖，分别花落无锡、淮安。</p><p>无锡购彩者购入一张“6+2”复式追加票，中得1注一等奖。</p></div>'
    rows=parse_cases(body,'https://www.js-lottery.com/xwzx/zdgz/cms/post-2.html')
    assert len(rows)==1 and rows[0]['ticket_type']=='multiple'


def test_image_only_ticket_is_pending_not_invented():
    body='<h1>26110期无锡大乐透一等奖中奖票</h1><div class="content-text-area"><p><img src="/ticket.jpg" /></p></div>'
    rows=parse_cases(body,'https://www.js-lottery.com/wfzq/dlt/xwzx/cms/post-148106.html')
    assert len(rows)==1 and rows[0]['issue']=='2026110'
    assert rows[0]['ticket_type']=='unknown' and rows[0]['status']=='needs_review'
    assert rows[0]['images']==['https://www.js-lottery.com/ticket.jpg']
    assert rows[0]['details']['cost'] is None
