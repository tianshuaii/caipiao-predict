"""Conservative extraction of public reports, not a census of winning tickets."""
from datetime import date
import hashlib
import math
import re
import time
from urllib.parse import urljoin, urlsplit, urlunsplit
from bs4 import BeautifulSoup
from sqlalchemy import select
from .models import RawFetch, WinnerCase, Run, utcnow
from .domain import canonical_issue

SOURCES={'www.gdfc.org.cn':'广东福彩','m.lottery.gov.cn':'中国体彩','www.lottery.gov.cn':'中国体彩','www.js-lottery.com':'江苏体彩','www.cwl.gov.cn':'中国福彩网'}
SEEDS=[
 'https://www.gdfc.org.cn/datas/content/content_284772.html',
 'https://m.lottery.gov.cn/zx/zj/20260327/10052905.html',
 'https://www.js-lottery.com/xwzx/zdgz/cms/post-147033.html',
]
INDEXES=['https://www.js-lottery.com/xwzx','https://www.gdfc.org.cn/channel/guangdong_news.html']
PARSER='winner-text-v1'
NOTICE='仅统计已公开报道，非全部一等奖中奖彩票；同票可能被重复报道，案例数不等于中奖票数。缺少各票型全部投注量，不能据此计算票型中奖概率或指导选号。'


def validate_url(url):
    u=urlsplit(url)
    if u.scheme!='https' or u.hostname not in SOURCES or u.username or u.password or u.port not in (None,443):
        raise ValueError('Only allowlisted HTTPS official sources are supported')
    return urlunsplit((u.scheme,u.netloc,u.path,u.query,''))


def match_value(pattern,text,cast=str):
    m=re.search(pattern,text)
    return cast(m.group(1)) if m else None


def parse_cases(body,url):
    validate_url(url)
    soup=BeautifulSoup(body,'html.parser')
    container=soup.select_one('.article-content, .m-listcon-cont, .TRS_Editor, .news-content, .detail-content, .content-text-area, article')
    if container is None: return []  # Never parse menus or lists as articles.
    title_node=soup.find('h1') or soup.find('h2') or soup.find('title')
    title=title_node.get_text(' ',strip=True)[:300] if title_node else '官方中奖报道'
    meta=soup.select_one('.article-meta, .m-listcon-info, .news-info, .info')
    pub=match_value(r'(20\d{2}-\d{2}-\d{2})',meta.get_text(' ',strip=True)) if meta else None
    if not pub: pub=match_value(r'发布时间[:：]\s*(20\d{2}-\d{2}-\d{2})',soup.get_text(' ',strip=True))
    if pub:
        try: date.fromisoformat(pub)
        except ValueError: pub=None
    images=[]
    for img in container.find_all('img',src=True):
        link=urljoin(url,img['src'])
        if urlsplit(link).scheme in ('https','http'): images.append(link)
    paragraphs=[p.get_text(' ',strip=True) for p in container.find_all('p')]
    paragraphs=[p for p in paragraphs if p]
    if not paragraphs and images and '一等奖' in title and '票' in title:
        paragraphs=['文章标题：'+title]
    full=' '.join(paragraphs)
    if not paragraphs: return []
    games=[g for g,label in [('dlt','大乐透'),('ssq','双色球')] if label in full+' '+title]
    if len(games)!=1: return []
    game=games[0]
    issue_pattern=r'(?:第\s*)?((?:20)?\d{5})\s*期'
    all_issues=set(re.findall(issue_pattern,full))
    candidates=[]
    for p in paragraphs:
        if '一等奖' not in p or not re.search(r'票|单式|复式|胆拖',p): continue
        issues=set(re.findall(issue_pattern,p))
        if not issues and len(all_issues)==1: issues=all_issues
        if len(issues)!=1: continue
        issue=canonical_issue(next(iter(issues)))
        p=' '.join(p.split())
        types=[key for key,word in [('single','单式'),('multiple','复式'),('banker','胆拖')] if word in p]
        # 胆拖复式 is one method, but references to multiple separate tickets are ambiguous.
        if types==['multiple','banker'] and '胆拖复式' in p: types=['banker']
        kind=types[0] if len(types)==1 else 'unknown'
        if '套餐票' in p or '混合票' in p: kind='mixed'
        single=match_value(r'(\d+)\s*注(?:\s*\d+\s*倍)?\s*(?:机选|自选)?单式',p,int) if kind=='single' else None
        multiple=match_value(r'(\d+)\s*倍(?:\s*(?:机选|自选)?单式|投注|追加|复式|胆拖)',p,int)
        shape=re.search(r'[“"\s](\d{1,2})\s*[+＋]\s*(\d{1,2})[”"\s]*(?:的)?复式',p) if kind=='multiple' else None
        front,back=(int(shape[1]),int(shape[2])) if shape else (None,None)
        expanded=single
        if front and back:
            maxf,needf,maxb,needb=(35,5,12,2) if game=='dlt' else (33,6,16,1)
            if needf<=front<=maxf and needb<=back<=maxb: expanded=math.comb(front,needf)*math.comb(back,needb)
            else: front=back=None
        details={'single_count':single,'multiplier':multiple,'front_count':front,'back_count':back,
                 'expanded_units':expanded,'expanded_units_basis':'按明示票型计算，不含倍投' if expanded else None,
                 'cost':match_value(r'(?:花(?:费)?|投入|一张|用了|用一张|购买的是)\s*(\d+(?:\.\d+)?)\s*元',p),
                 'first_prize_count':match_value(r'(?:中得|收获|揽获)\s*(\d+)\s*注(?:基本(?:投注)?|追加)?一等奖',p,int),
                 'additional':True if game=='dlt' and '追加' in p else None,
                 'total_prize_text':match_value(r'(?:单票累计奖金达|奖金共计|总奖金(?:为|达)?|共揽奖金)\s*([\d,.]+\s*(?:万|亿)?余?元)',p),
                 'banker_description':p if kind=='banker' else None,'region':None}
        candidates.append({'game':game,'issue':issue,'ticket_type':kind,'title':title,'published_date':pub,
                           'details':details,'evidence':p,'images':list(dict.fromkeys(images)),
                           'status':'needs_review' if kind in ('unknown','mixed') else 'text_extracted'})
    return candidates


def import_article(session,url,body,status):
    url=validate_url(url)
    raw=RawFetch(source='winner_report',url=url,params={},status=status,body=body,
                 sha256=hashlib.sha256(body.encode()).hexdigest(),parser_version=PARSER)
    session.add(raw);session.flush()
    if status!=200: return 0
    rows=parse_cases(body,url)
    if not rows: return 0
    for old in session.scalars(select(WinnerCase).where(WinnerCase.article_url==url)):
        old.active=False
    for item in rows:
        key=hashlib.sha256((url+'\n'+item['evidence']).encode()).hexdigest()
        row=session.scalar(select(WinnerCase).where(WinnerCase.case_key==key))
        if row is None:
            row=WinnerCase(case_key=key,article_url=url,source=SOURCES[urlsplit(url).hostname])
            session.add(row)
        for k,v in item.items(): setattr(row,k,date.fromisoformat(v) if k=='published_date' and v else v)
        row.raw_id=raw.id;row.fetched_at=raw.fetched_at;row.parser_version=PARSER;row.active=True
        session.flush()
    return len(rows)


def fetch_official(http,url):
    # Validate every redirect, rather than allowing a source to redirect to arbitrary hosts.
    url=validate_url(url)
    for _ in range(4):
        response=http.get(url,follow_redirects=False)
        if response.is_redirect:
            url=validate_url(urljoin(url,response.headers['location']));continue
        return url,response
    raise ValueError('Too many redirects')


def sync_cases(session,urls=None,limit=20):
    from .collectors import client
    if not 1<=limit<=100: raise ValueError('limit must be between 1 and 100')
    run=Run(kind='winner-cases');session.add(run);session.commit()
    results=[]; targets=list(urls or SEEDS)
    with client() as http:
        if not urls:
            for index in INDEXES:
                try:
                    final,response=fetch_official(http,index)
                    import_article(session,final,response.text,response.status_code)
                    response.raise_for_status()
                    soup=BeautifulSoup(response.text,'html.parser')
                    for a in soup.find_all('a',href=True):
                        if '一等奖' in a.get_text() and any(g in a.get_text() for g in ('大乐透','双色球')):
                            try: targets.append(validate_url(urljoin(final,a['href'])))
                            except ValueError: pass
                    session.commit()
                except Exception as exc:
                    session.rollback();results.append({'url':index,'error':type(exc).__name__})
        for url in list(dict.fromkeys(targets))[:limit]:
            try:
                final,response=fetch_official(http,url)
                count=import_article(session,final,response.text,response.status_code)
                session.commit()
                results.append({'url':final,'status':response.status_code,'cases':count})
            except Exception as exc:
                session.rollback();results.append({'url':url,'error':type(exc).__name__})
            time.sleep(.4)
    run.status='partial' if any('error' in r or r.get('status',200)!=200 for r in results) else 'success'
    run.details={'sources':results,'notice':NOTICE};run.finished_at=utcnow();session.commit()
    return {'run_id':run.id,'status':run.status,'sources':results}
