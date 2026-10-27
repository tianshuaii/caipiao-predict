import httpx
from sqlalchemy import select
from .collectors import client
from .config import sendkey
from .models import Notification, utcnow

def queue_report(session, run_id, title, body, key):
    existing = session.scalar(select(Notification).where(Notification.report_key == key))
    if existing: return existing
    row = Notification(run_id=run_id, title=title, body=body, report_key=key)
    session.add(row)
    session.flush()
    return row

def deliver(session, row):
    if row.status in ['sent', 'uncertain', 'sending']:
        return row.status
    key = sendkey()
    if not key or not key.startswith('SCT'):
        row.status, row.detail = 'not_configured', 'Server 酱 Turbo SendKey 未配置'
        session.commit()
        return row.status
    if row.attempts >= 3:
        return row.status
    row.status, row.attempts = 'sending', row.attempts + 1
    session.commit()  # Crash after this point is treated as uncertain, never blindly resent.
    try:
        with client() as http:
            response = http.post('https://sctapi.ftqq.com/'+key+'.send', data={'title': row.title, 'desp': row.body})
        if response.status_code >= 500:
            row.status, row.detail = 'uncertain', f'通道返回 HTTP {response.status_code}，需核对是否送达'
        else:
            response.raise_for_status()
            payload = response.json()
            if payload.get('code') == 0:
                row.status, row.detail, row.sent_at = 'sent', 'Server 酱已受理，请在微信核对送达', utcnow()
            else:
                row.status, row.detail = 'failed', 'Server 酱拒绝：code=' + str(payload.get('code'))[:30]
    except (httpx.ConnectError, httpx.ConnectTimeout):
        row.status, row.detail = 'failed', '连接推送通道失败，可单独重试通知'
    except Exception:
        row.status, row.detail = 'uncertain', '推送响应不确定，核对微信后再处理'
    session.commit()
    return row.status
