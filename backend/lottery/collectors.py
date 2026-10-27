"""Adapters for official public sources. Every HTTP response is persisted first."""
import ast
from datetime import date
from decimal import Decimal, InvalidOperation
import hashlib
import json
import os
import re
import ssl
import time
from pathlib import Path
import httpx
from .domain import canonical_issue, rule_version, validate_ticket
from .models import RawFetch

DLT_URL = 'https://webapi.sporttery.cn/gateway/lottery/getHistoryPageListV1.qry'
CWL_URL = 'https://www.cwl.gov.cn/cwl_admin/front/cwlkj/search/kjxx/findDrawNotice'
SH_URL = 'https://appsh.swlc.net.cn/shfcoc_datachart/datachart/ssq/lskj/ls_award.html'
SH_HISTORY_URL = 'https://appsh.swlc.net.cn/shfcoc_ldatacenter/aword/execQueryAllAnalysis.ctl'
ZHCW_URL = 'https://jc.zhcw.com/port/client_json.php'
CHINESE = dict(zip('一二三四五六七八九', range(1, 10)))

def number(value):
    value = str('' if value is None else value).strip().replace(',', '')
    if not re.fullmatch(r'\d+(?:\.\d+)?', value):
        return None
    return str(Decimal(value))

def award(amount, count):
    return {'amount': number(amount), 'count': int(number(count)) if number(count) is not None else None, 'raw_amount': str(amount or '')}

def normalize(game, issue, day, front, back, prizes, url, sales=None, pool=None):
    issue = canonical_issue(issue)
    validate_ticket(game, front, back)
    date.fromisoformat(day)
    return {'game': game, 'issue': issue, 'draw_date': day, 'front': sorted(front), 'back': sorted(back), 'prizes': prizes, 'source_url': url, 'sales': number(sales), 'pool': number(pool), 'rule_version': rule_version(game, issue)}

def parse_sporttery(row):
    balls = [int(x) for x in row['lotteryDrawResult'].split()]
    prizes = {}
    for p in row.get('prizeLevelList', []):
        label = p['prizeLevel']
        if label in [f'{x}等奖' for x in CHINESE]:
            prizes[str(CHINESE[label[0]])] = award(p.get('stakeAmount'), p.get('stakeCount'))
    return normalize('dlt', row['lotteryDrawNum'], row['lotteryDrawTime'][:10], balls[:5], balls[5:], prizes, row.get('drawPdfUrl') or DLT_URL, row.get('totalSaleAmount'), row.get('poolBalanceAfterdraw'))

def parse_cwl(row):
    prizes = {str(p['type']): award(p.get('typemoney'), p.get('typenum')) for p in row.get('prizegrades', [])}
    if row.get('fyjMoney'):
        prizes['7'] = award(row['fyjMoney'], row.get('fyjCount'))
    result = normalize('ssq', row['code'], row['date'][:10], [int(x) for x in row['red'].split(',')], [int(row['blue'])], prizes, 'https://www.cwl.gov.cn' + row.get('detailsLink', ''), row.get('sales'), row.get('poolmoney'))
    result['special_rule'] = row.get('specialRuleInfo', '')
    result['promotion'] = row.get('prizeSpecialInfo', '')
    return result

def parse_shanghai(text):
    if text.lstrip().startswith('{'):
        payload = json.loads(text)
        rows = payload.get('result', [])
    else:
        rows = [ast.literal_eval(x) for x in re.findall(r'employee\.push\((\{[^\n]+?\})\)', text)]
    result = []
    for row in rows:
        front, back = row['c'].split('|')
        prizes = {str(i): award(row.get('bonus'+str(i)), row.get('prize'+str(i))) for i in range(1, 7)}
        result.append(normalize('ssq', row['id'], row['t'][:10], list(map(int, front.split(','))), [int(back)], prizes, SH_URL, row.get('pond'), row.get('betting')))
    return result

def parse_zhcw(row, game):
    prizes = {}
    for entry in row.get('winnerDetails', []):
        base = entry.get('baseBetWinner')
        if isinstance(base, dict):
            prizes[str(entry['awardEtc'])] = award(base.get('awardMoney'), base.get('awardNum'))
    return normalize(game, row['issue'], row['openTime'][:10], list(map(int,row['frontWinningNum'].split())), list(map(int,row['backWinningNum'].split())), prizes, f'https://www.zhcw.com/kjxx/{game}/kjxq/?kjData={row["issue"]}', row.get('saleMoney'), row.get('prizePoolMoney'))

def collect_archive(session):
    """Fill pre-2013 gap using the Welfare Lottery's designated information medium.

    Source declaration: https://www.zhcw.com/h5/c/2019-07-26/582873.shtml
    Include 2013001 as an overlap check against CWL, not a separate sample.
    """
    from .ingestion import ingest, record_inventory
    seen = set()
    total = 0
    with client() as http:
        for page in range(1, 101):
            params = dict(transactionType='10001001', lotteryId=1, issueCount=0, startIssue='2003001', endIssue='2013001', type=1, pageNum=page, pageSize=100)
            raw = fetch(session,http,'zhcw',ZHCW_URL,params)
            payload = json.loads(raw.body)
            if payload.get('resCode') != '000000': raise RuntimeError('ZHCW rejected archive query')
            total = int(payload['total'])
            rows = [parse_zhcw(r,'ssq') for r in payload['data']]
            ids = {r['issue'] for r in rows}
            if not ids or ids.issubset(seen): raise RuntimeError('Archive pagination incomplete')
            for row in rows: ingest(session,row,raw.id,'zhcw')
            session.commit()
            seen.update(ids)
            print(f'ssq archive: {len(seen)}/{total}',flush=True)
            if len(seen) >= total: break
            time.sleep(float(os.getenv('SOURCE_DELAY_SECONDS','0.4')))
    if len(seen) != total: raise RuntimeError('Archive source total mismatch')
    record_inventory(session,'ssq','zhcw',seen)
    return {'source':'zhcw', 'received':len(seen),'source_total':total}

def client():
    ca = '/etc/ssl/cert.pem'
    context = ssl.create_default_context(cafile=ca) if Path(ca).exists() else True
    return httpx.Client(timeout=35, follow_redirects=True, verify=context, headers={'User-Agent': 'LotteryLab/0.1 (personal historical research)', 'Referer': 'https://www.cwl.gov.cn/'})

def fetch(session, http, source, url, params=None):
    error = None
    for attempt in range(3):
        try:
            referer = {'zhcw': 'https://www.zhcw.com/', 'sporttery': 'https://www.lottery.gov.cn/', 'shanghai': 'https://appsh.swlc.net.cn/'}.get(source, 'https://www.cwl.gov.cn/')
            response = http.get(url, params=params, headers={'Referer': referer})
            row = RawFetch(source=source, url=str(response.url), params=params or {}, status=response.status_code, body=response.text, sha256=hashlib.sha256(response.content).hexdigest())
            session.add(row)
            session.commit()
            response.raise_for_status()
            return row
        except httpx.HTTPError as exc:
            error = type(exc).__name__
            if attempt < 2:
                time.sleep(1 + attempt)
    raise RuntimeError(f'{source}: {error}; official source unavailable')

def collect(session, game, full=False):
    from .ingestion import ingest, record_inventory
    from sqlalchemy import select
    from .models import Draw
    known = set(session.scalars(select(Draw.issue).where(Draw.game == game)))
    source = 'sporttery' if game == 'dlt' else 'cwl'
    total, seen, pages = None, set(), 0
    with client() as http:
        for page in range(1, 301):
            if game == 'dlt':
                params = dict(gameNo=85, provinceId=0, pageSize=100, isVerify=1, pageNo=page)
                raw = fetch(session, http, source, DLT_URL, params)
                payload = json.loads(raw.body)
                if not payload.get('success'): raise RuntimeError('Sporttery rejected query')
                value = payload['value']
                total = int(value['total'])
                rows = [parse_sporttery(r) for r in value['list']]
            else:
                params = dict(name='ssq', pageNo=page, pageSize=100, systemType='PC')
                raw = fetch(session, http, source, CWL_URL, params)
                payload = json.loads(raw.body)
                if payload.get('state') != 0: raise RuntimeError('CWL rejected query')
                total = int(payload['total'])
                rows = [parse_cwl(r) for r in payload['result']]
            if not rows: break
            ids = {r['issue'] for r in rows}
            if ids.issubset(seen): raise RuntimeError('Pagination repeated: refusing truncated history')
            for row in rows: ingest(session, row, raw.id, source)
            session.commit()
            pages += 1
            seen.update(ids)
            print(f'{game}: page {page}, received {len(seen)}/{total}', flush=True)
            if len(seen) >= total: break
            if not full and page >= 2 and ids.issubset(known): break
            time.sleep(float(os.getenv('SOURCE_DELAY_SECONDS', '0.4')))
        if full and len(seen) != total:
            raise RuntimeError(f'Incomplete official pagination: {len(seen)} of {total}')
        if full: record_inventory(session,game,source,seen)
        crosscheck = None
        if game == 'ssq':
            try:
                raw = fetch(session, http, 'shanghai', SH_URL)
                checkrows = parse_shanghai(raw.body)
                if not checkrows: raise ValueError('Shanghai response contains no draws')
                for row in checkrows: ingest(session, row, raw.id, 'shanghai')
                session.commit()
                crosscheck = {'source': 'shanghai', 'count': len(checkrows)}
            except (RuntimeError, ValueError, KeyError) as exc:
                crosscheck = {'source': 'shanghai', 'error': str(exc)[:200]}
    return {'game': game, 'source': source, 'source_total': total, 'received': len(seen), 'pages': pages, 'crosscheck': crosscheck}
